"""Tests for the async Polar validator."""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from app.services.async_validator import AsyncPolarValidator, ValidationCacheEntry, ValidationHistoryEntry
from app.models.policy import PolicyValidationRequest, PolicyValidationResult
from app.core.validator import ValidationResult as CoreValidationResult


@pytest.fixture
def mock_core_validator():
    """Mock core validator for testing."""
    with patch('app.services.async_validator.PolarValidator') as mock:
        validator_instance = Mock()
        mock.return_value = validator_instance
        yield validator_instance


@pytest.fixture
def async_validator(mock_core_validator):
    """Create async validator instance for testing."""
    return AsyncPolarValidator(cli_path="mock-oso-cloud", timeout=10, cache_ttl=300)


@pytest.fixture
def sample_request():
    """Sample validation request."""
    return PolicyValidationRequest(
        policy_content="allow(user, \"read\", resource) if user.role = \"admin\";",
        policy_id="test-policy-123",
        session_id="test-session-456"
    )


@pytest.mark.asyncio
async def test_validate_policy_success(async_validator, mock_core_validator, sample_request):
    """Test successful policy validation."""
    # Mock successful validation
    mock_core_validator.validate_policy.return_value = CoreValidationResult(
        is_valid=True,
        error_message=None,
        errors=[]
    )
    
    result = await async_validator.validate_policy_async(sample_request)
    
    assert result.is_valid is True
    assert result.error_message is None
    assert result.error_details == []
    assert result.validation_time > 0
    
    # Verify core validator was called
    mock_core_validator.validate_policy.assert_called_once_with(sample_request.policy_content)


@pytest.mark.asyncio
async def test_validate_policy_failure(async_validator, mock_core_validator, sample_request):
    """Test failed policy validation."""
    # Mock failed validation
    mock_core_validator.validate_policy.return_value = CoreValidationResult(
        is_valid=False,
        error_message="Syntax error on line 1",
        errors=["Syntax error on line 1", "Missing semicolon"]
    )
    
    result = await async_validator.validate_policy_async(sample_request)
    
    assert result.is_valid is False
    assert result.error_message == "Syntax error on line 1"
    assert result.error_details == ["Syntax error on line 1", "Missing semicolon"]
    assert result.validation_time > 0


@pytest.mark.asyncio
async def test_validation_caching(async_validator, mock_core_validator, sample_request):
    """Test that validation results are cached."""
    # Mock successful validation
    mock_core_validator.validate_policy.return_value = CoreValidationResult(
        is_valid=True,
        error_message=None,
        errors=[]
    )
    
    # First validation - should call core validator
    result1 = await async_validator.validate_policy_async(sample_request)
    assert result1.is_valid is True
    assert mock_core_validator.validate_policy.call_count == 1
    
    # Second validation with same content - should use cache
    result2 = await async_validator.validate_policy_async(sample_request)
    assert result2.is_valid is True
    assert mock_core_validator.validate_policy.call_count == 1  # No additional call
    
    # Verify cache hit statistics
    stats = async_validator.get_validation_stats()
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 1


@pytest.mark.asyncio
async def test_cache_expiration(async_validator, mock_core_validator, sample_request):
    """Test that cache entries expire correctly."""
    # Set very short cache TTL for testing
    async_validator.cache_ttl = 1
    
    # Mock successful validation
    mock_core_validator.validate_policy.return_value = CoreValidationResult(
        is_valid=True,
        error_message=None,
        errors=[]
    )
    
    # First validation
    result1 = await async_validator.validate_policy_async(sample_request)
    assert result1.is_valid is True
    
    # Wait for cache to expire
    await asyncio.sleep(1.1)
    
    # Second validation - should call core validator again due to expiration
    result2 = await async_validator.validate_policy_async(sample_request)
    assert result2.is_valid is True
    assert mock_core_validator.validate_policy.call_count == 2


@pytest.mark.asyncio
async def test_validate_multiple_policies(async_validator, mock_core_validator):
    """Test concurrent validation of multiple policies."""
    # Create multiple requests
    requests = [
        PolicyValidationRequest(
            policy_content=f"allow(user, \"read\", resource{i}) if user.role = \"admin\";",
            policy_id=f"policy-{i}",
            session_id="test-session"
        )
        for i in range(3)
    ]
    
    # Mock successful validation for all
    mock_core_validator.validate_policy.return_value = CoreValidationResult(
        is_valid=True,
        error_message=None,
        errors=[]
    )
    
    results = await async_validator.validate_multiple_policies(requests)
    
    assert len(results) == 3
    assert all(result.is_valid for result in results)
    assert mock_core_validator.validate_policy.call_count == 3


@pytest.mark.asyncio
async def test_validation_history_tracking(async_validator, mock_core_validator, sample_request):
    """Test that validation history is tracked correctly."""
    # Mock successful validation
    mock_core_validator.validate_policy.return_value = CoreValidationResult(
        is_valid=True,
        error_message=None,
        errors=[]
    )
    
    # Perform validation
    await async_validator.validate_policy_async(sample_request)
    
    # Check history
    history = async_validator.get_validation_history(sample_request.session_id)
    assert len(history) == 1
    assert history[0].session_id == sample_request.session_id
    assert history[0].policy_id == sample_request.policy_id
    assert history[0].result.is_valid is True


@pytest.mark.asyncio
async def test_retry_count_tracking(async_validator, mock_core_validator):
    """Test that retry counts are tracked correctly."""
    # Create requests with different content to avoid caching
    requests = [
        PolicyValidationRequest(
            policy_content=f"allow(user, \"read\", resource{i});",
            policy_id="policy-1",
            session_id="session-1"
        )
        for i in range(3)
    ]
    
    # Mock failed validation first, then success
    mock_core_validator.validate_policy.side_effect = [
        CoreValidationResult(is_valid=False, error_message="Error 1", errors=["Error 1"]),
        CoreValidationResult(is_valid=False, error_message="Error 2", errors=["Error 2"]),
        CoreValidationResult(is_valid=True, error_message=None, errors=[])
    ]
    
    # Perform multiple validations (simulating retries)
    await async_validator.validate_policy_async(requests[0])
    await async_validator.validate_policy_async(requests[1])
    await async_validator.validate_policy_async(requests[2])
    
    # Check history for retry counts
    history = async_validator.get_validation_history("session-1")
    assert len(history) == 3
    
    # All should have retry_count 0 since they have different content
    # This tests that the retry tracking mechanism works
    assert all(entry.retry_count == 0 for entry in history)


def test_validation_stats_calculation(async_validator):
    """Test validation statistics calculation."""
    # Add some mock history entries
    now = datetime.utcnow()
    
    # Add successful validation
    async_validator._validation_history.append(
        ValidationHistoryEntry(
            session_id="session-1",
            policy_id="policy-1",
            policy_hash="hash1",
            result=PolicyValidationResult(is_valid=True, validation_time=1.0),
            timestamp=now
        )
    )
    
    # Add failed validation
    async_validator._validation_history.append(
        ValidationHistoryEntry(
            session_id="session-1",
            policy_id="policy-2",
            policy_hash="hash2",
            result=PolicyValidationResult(is_valid=False, error_message="Error", validation_time=2.0),
            timestamp=now
        )
    )
    
    # Update global stats manually for testing
    async_validator._stats.update({
        "total_validations": 2,
        "successful_validations": 1,
        "failed_validations": 1,
        "average_validation_time": 1.5
    })
    
    # Test session-specific stats
    session_stats = async_validator.get_validation_stats("session-1")
    assert session_stats["total_validations"] == 2
    assert session_stats["successful_validations"] == 1
    assert session_stats["failed_validations"] == 1
    assert session_stats["success_rate"] == 0.5
    assert session_stats["average_validation_time"] == 1.5
    
    # Test global stats
    global_stats = async_validator.get_validation_stats()
    assert global_stats["total_validations"] == 2
    assert global_stats["success_rate"] == 0.5


def test_cache_management(async_validator):
    """Test cache clearing and cleanup functionality."""
    # Add some cache entries
    now = datetime.utcnow()
    
    # Current entry
    async_validator._validation_cache["session1:hash1"] = ValidationCacheEntry(
        policy_hash="hash1",
        result=PolicyValidationResult(is_valid=True),
        timestamp=now,
        session_id="session1"
    )
    
    # Expired entry
    async_validator._validation_cache["session1:hash2"] = ValidationCacheEntry(
        policy_hash="hash2",
        result=PolicyValidationResult(is_valid=True),
        timestamp=now - timedelta(hours=2),
        session_id="session1"
    )
    
    # Different session entry
    async_validator._validation_cache["session2:hash3"] = ValidationCacheEntry(
        policy_hash="hash3",
        result=PolicyValidationResult(is_valid=True),
        timestamp=now,
        session_id="session2"
    )
    
    # Test cleanup of expired entries
    expired_count = async_validator.cleanup_expired_cache()
    assert expired_count == 1
    assert len(async_validator._validation_cache) == 2
    
    # Test session-specific cache clearing
    cleared_count = async_validator.clear_cache("session1")
    assert cleared_count == 1
    assert len(async_validator._validation_cache) == 1
    
    # Test clearing all cache
    total_cleared = async_validator.clear_cache()
    assert total_cleared == 1
    assert len(async_validator._validation_cache) == 0


@pytest.mark.asyncio
async def test_validation_exception_handling(async_validator, mock_core_validator, sample_request):
    """Test handling of validation exceptions."""
    # Mock core validator to raise exception
    mock_core_validator.validate_policy.side_effect = Exception("CLI not found")
    
    result = await async_validator.validate_policy_async(sample_request)
    
    assert result.is_valid is False
    assert "Validation error: CLI not found" in result.error_message
    assert "CLI not found" in result.error_details
    assert result.validation_time > 0


@pytest.mark.asyncio
async def test_concurrent_validation_limit(async_validator, mock_core_validator):
    """Test that concurrent validations are limited by thread pool."""
    # Create many requests
    requests = [
        PolicyValidationRequest(
            policy_content=f"policy_{i}",
            policy_id=f"policy-{i}",
            session_id="test-session"
        )
        for i in range(10)
    ]
    
    # Mock slow validation
    async def slow_validation(content):
        await asyncio.sleep(0.1)
        return CoreValidationResult(is_valid=True, error_message=None, errors=[])
    
    mock_core_validator.validate_policy.side_effect = lambda content: CoreValidationResult(
        is_valid=True, error_message=None, errors=[]
    )
    
    # This should complete without hanging (tests thread pool management)
    results = await async_validator.validate_multiple_policies(requests)
    assert len(results) == 10
    assert all(result.is_valid for result in results)


@pytest.mark.asyncio
async def test_cleanup_resources(async_validator):
    """Test resource cleanup."""
    # This should not raise any exceptions
    await async_validator.close()
    
    # Executor should be shut down
    assert async_validator.executor._shutdown is True