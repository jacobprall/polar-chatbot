"""Tests for the validation retry service."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.services.validation_retry_service import (
    ValidationRetryService, 
    ValidationRetryMetrics, 
    ValidationRetryResult,
    create_validation_retry_service
)
from app.models.session import Session, GeneratedPolicy
from app.models.policy import (
    PolicyGenerationRequest, 
    PolicyGenerationResult,
    PolicyValidationResult
)


@pytest.fixture
def mock_policy_generator():
    """Mock policy generator."""
    generator = Mock()
    
    def mock_generate_policy(request, session):
        result = PolicyGenerationResult(
            success=True,
            policy_content="allow(user, \"read\", resource);",
            model_used="gpt-4",
            tokens_used=100,
            generation_time=2.0
        )
        # Actually add policy to session like the real generator would
        if result.is_successful():
            policy = GeneratedPolicy.create(
                content=result.policy_content,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                generation_time=result.generation_time
            )
            session.add_policy(policy)
        return result
    
    def mock_generate_policy_stream(request, session, callback):
        result = PolicyGenerationResult(
            success=True,
            policy_content="allow(user, \"read\", resource);",
            model_used="gpt-4",
            tokens_used=100,
            generation_time=2.0
        )
        # Actually add policy to session like the real generator would
        if result.is_successful():
            policy = GeneratedPolicy.create(
                content=result.policy_content,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                generation_time=result.generation_time
            )
            session.add_policy(policy)
        return result
    
    generator.generate_policy.side_effect = mock_generate_policy
    generator.generate_policy_stream.side_effect = mock_generate_policy_stream
    return generator


@pytest.fixture
def mock_async_validator():
    """Mock async validator."""
    validator = AsyncMock()
    validator.validate_policy_async.return_value = PolicyValidationResult(
        is_valid=True,
        validation_time=1.0
    )
    validator.get_validation_history.return_value = []
    validator.get_validation_stats.return_value = {}
    validator.clear_cache.return_value = 0
    return validator


@pytest.fixture
def mock_event_logger():
    """Mock event logger."""
    logger = AsyncMock()
    logger.log_event_async.return_value = True
    return logger


@pytest.fixture
def validation_retry_service(mock_policy_generator, mock_async_validator, mock_event_logger):
    """Create validation retry service for testing."""
    return ValidationRetryService(
        policy_generator=mock_policy_generator,
        async_validator=mock_async_validator,
        event_logger=mock_event_logger,
        max_retries=2,
        auto_validate=True
    )


@pytest.fixture
def sample_session():
    """Sample session for testing."""
    session = Session.create("Test Session")
    session.requirements_text = "Allow users to read resources"
    return session


@pytest.fixture
def sample_request():
    """Sample policy generation request."""
    return PolicyGenerationRequest(
        session_id="test-session",
        requirements_text="Allow users to read resources"
    )


def test_validation_retry_metrics():
    """Test validation retry metrics tracking."""
    metrics = ValidationRetryMetrics()
    
    # Test generation metrics
    metrics.update_generation(2.0)
    metrics.update_generation(3.0)
    
    assert metrics.total_generations == 2
    assert metrics.average_generation_time == 2.5
    
    # Test validation metrics
    metrics.update_validation(True, 1.0)
    metrics.update_validation(False, 2.0)
    
    assert metrics.successful_validations == 1
    assert metrics.failed_validations == 1
    assert metrics.average_validation_time == 1.5
    assert metrics.success_rate == 0.5
    
    # Test retry metrics
    metrics.update_retry(True)
    metrics.update_retry(False)
    
    assert metrics.total_retries == 2
    assert metrics.successful_retries == 1
    assert metrics.retry_success_rate == 0.5


@pytest.mark.asyncio
async def test_successful_generation_and_validation(validation_retry_service, sample_session, sample_request):
    """Test successful policy generation and validation."""
    # The mock_policy_generator fixture already handles adding policies to session
    validation_retry_service.async_validator.validate_policy_async.return_value = PolicyValidationResult(
        is_valid=True,
        validation_time=1.0
    )
    
    result = await validation_retry_service.generate_and_validate_policy(sample_request, sample_session)
    
    assert result.is_successful
    assert result.policy_result.is_successful()
    assert result.validation_result.is_valid
    assert result.retry_count == 0
    assert result.is_final_success
    
    # Verify policy was added to session
    assert len(sample_session.generated_policies) == 1


@pytest.mark.asyncio
async def test_validation_failure_with_retry(validation_retry_service, sample_session, sample_request):
    """Test validation failure followed by successful retry."""
    # Mock validation: first fails, second succeeds
    validation_retry_service.async_validator.validate_policy_async.side_effect = [
        PolicyValidationResult(
            is_valid=False,
            error_message="Syntax error",
            error_details=["Missing semicolon"],
            validation_time=1.0
        ),
        PolicyValidationResult(
            is_valid=True,
            validation_time=1.0
        )
    ]
    
    result = await validation_retry_service.generate_and_validate_policy(sample_request, sample_session)
    
    assert result.is_successful
    assert result.retry_count == 1
    assert result.is_final_success
    assert len(result.error_context) > 0  # Should have error context from first validation
    
    # Verify both generation calls were made (initial + retry)
    assert validation_retry_service.policy_generator.generate_policy.call_count == 2
    
    # Verify both validation calls were made
    assert validation_retry_service.async_validator.validate_policy_async.call_count == 2


@pytest.mark.asyncio
async def test_max_retries_exceeded(validation_retry_service, sample_session, sample_request):
    """Test behavior when maximum retries are exceeded."""
    # Mock validation (always fails)
    validation_retry_service.async_validator.validate_policy_async.return_value = PolicyValidationResult(
        is_valid=False,
        error_message="Persistent error",
        error_details=["Unfixable issue"],
        validation_time=1.0
    )
    
    result = await validation_retry_service.generate_and_validate_policy(sample_request, sample_session)
    
    assert not result.is_successful
    assert result.retry_count == 2  # max_retries
    assert not result.is_final_success
    assert len(result.error_context) > 0  # Should have error context
    
    # Verify maximum attempts were made (initial + 2 retries = 3 total)
    assert validation_retry_service.policy_generator.generate_policy.call_count == 3


@pytest.mark.asyncio
async def test_generation_failure(validation_retry_service, sample_session, sample_request):
    """Test handling of policy generation failure."""
    # Mock failed generation by overriding the side_effect
    def mock_failed_generate_policy(request, session):
        return PolicyGenerationResult(
            success=False,
            error_message="API error"
        )
    
    validation_retry_service.policy_generator.generate_policy.side_effect = mock_failed_generate_policy
    
    result = await validation_retry_service.generate_and_validate_policy(sample_request, sample_session)
    
    assert not result.is_successful
    assert not result.policy_result.is_successful()
    assert result.validation_result is None
    assert result.retry_count == 0
    
    # Validation should not be called if generation fails
    validation_retry_service.async_validator.validate_policy_async.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_generation(validation_retry_service, sample_session, sample_request):
    """Test streaming policy generation with validation."""
    validation_retry_service.async_validator.validate_policy_async.return_value = PolicyValidationResult(
        is_valid=True,
        validation_time=1.0
    )
    
    # Mock stream callback
    stream_callback = Mock()
    
    result = await validation_retry_service.generate_and_validate_policy(
        sample_request, 
        sample_session, 
        stream_callback
    )
    
    assert result.is_successful
    assert result.is_final_success
    
    # Verify streaming generation was called
    validation_retry_service.policy_generator.generate_policy_stream.assert_called_once()
    
    # Verify regular generation was not called
    validation_retry_service.policy_generator.generate_policy.assert_not_called()


@pytest.mark.asyncio
async def test_validate_existing_policy(validation_retry_service, sample_session):
    """Test validation of existing policy in session."""
    # Add a policy to the session
    policy = GeneratedPolicy.create(
        content="allow(user, \"read\", resource);",
        model_used="gpt-4"
    )
    sample_session.generated_policies.append(policy)
    
    # Mock validation
    validation_retry_service.async_validator.validate_policy_async.return_value = PolicyValidationResult(
        is_valid=True,
        validation_time=1.0
    )
    
    # Mock session methods
    sample_session.add_validation_result = Mock()
    
    result = await validation_retry_service.validate_existing_policy(sample_session, policy.id)
    
    assert result.is_valid
    assert result.validation_time == 1.0
    
    # Verify validation result was added to session
    sample_session.add_validation_result.assert_called_once()


@pytest.mark.asyncio
async def test_validate_nonexistent_policy(validation_retry_service, sample_session):
    """Test validation of non-existent policy."""
    result = await validation_retry_service.validate_existing_policy(sample_session, "nonexistent-id")
    
    assert not result.is_valid
    assert "not found" in result.error_message


@pytest.mark.asyncio
async def test_retry_with_validation(validation_retry_service, sample_session):
    """Test retry with validation errors as context."""
    # Mock session methods
    sample_session.get_current_policy = Mock(return_value=GeneratedPolicy.create(
        content="old policy",
        model_used="gpt-4"
    ))
    sample_session.add_policy = Mock()
    sample_session.add_validation_result = Mock()
    
    # Mock successful retry
    validation_retry_service.policy_generator.generate_policy.return_value = PolicyGenerationResult(
        success=True,
        policy_content="fixed policy",
        model_used="gpt-4",
        generation_time=2.0
    )
    
    validation_retry_service.async_validator.validate_policy_async.return_value = PolicyValidationResult(
        is_valid=True,
        validation_time=1.0
    )
    
    validation_errors = ["Syntax error", "Missing rule"]
    
    result = await validation_retry_service.retry_with_validation(
        sample_session, 
        validation_errors
    )
    
    assert result.is_successful
    assert result.is_final_success


def test_session_metrics_tracking(validation_retry_service, sample_session):
    """Test session-specific metrics tracking."""
    # Initially no metrics
    metrics = validation_retry_service.get_session_metrics(sample_session.id)
    assert metrics.total_generations == 0
    
    # Add some metrics manually to test
    validation_retry_service._session_metrics[sample_session.id] = ValidationRetryMetrics()
    validation_retry_service._session_metrics[sample_session.id].update_generation(2.0)
    validation_retry_service._session_metrics[sample_session.id].update_validation(True, 1.0)
    
    metrics = validation_retry_service.get_session_metrics(sample_session.id)
    assert metrics.total_generations == 1
    assert metrics.successful_validations == 1


def test_validation_history_delegation(validation_retry_service):
    """Test that validation history calls are delegated to async validator."""
    # Reset the mock to avoid async issues
    validation_retry_service.async_validator.get_validation_history = Mock(return_value=[])
    validation_retry_service.get_validation_history("session-1", 10)
    validation_retry_service.async_validator.get_validation_history.assert_called_once_with("session-1", 10)


def test_validation_stats_delegation(validation_retry_service):
    """Test that validation stats calls are delegated to async validator."""
    # Reset the mock to avoid async issues
    validation_retry_service.async_validator.get_validation_stats = Mock(return_value={})
    validation_retry_service.get_validation_stats("session-1")
    validation_retry_service.async_validator.get_validation_stats.assert_called_once_with("session-1")


def test_cache_clearing_delegation(validation_retry_service):
    """Test that cache clearing calls are delegated to async validator."""
    # Reset the mock to avoid async issues
    validation_retry_service.async_validator.clear_cache = Mock(return_value=0)
    validation_retry_service.clear_session_cache("session-1")
    validation_retry_service.async_validator.clear_cache.assert_called_once_with("session-1")


@pytest.mark.asyncio
async def test_auto_validate_disabled(mock_policy_generator, mock_async_validator):
    """Test behavior when auto-validation is disabled."""
    service = ValidationRetryService(
        policy_generator=mock_policy_generator,
        async_validator=mock_async_validator,
        auto_validate=False
    )
    
    session = Session.create("Test Session")
    session.requirements_text = "Test requirements"
    session.add_policy = Mock()
    
    request = PolicyGenerationRequest(
        session_id=session.id,
        requirements_text="Test requirements"
    )
    
    result = await service.generate_and_validate_policy(request, session)
    
    assert result.is_successful  # Should be successful without validation
    assert result.validation_result is None  # No validation performed
    assert result.is_final_success
    
    # Validation should not be called
    mock_async_validator.validate_policy_async.assert_not_called()


@pytest.mark.asyncio
async def test_create_validation_retry_service():
    """Test the convenience function for creating validation retry service."""
    with patch('app.services.validation_retry_service.AsyncPolarValidator') as mock_validator_class:
        mock_validator_instance = AsyncMock()
        mock_validator_class.return_value = mock_validator_instance
        
        mock_policy_generator = Mock()
        
        service = await create_validation_retry_service(
            policy_generator=mock_policy_generator,
            cli_path="test-cli",
            max_retries=5,
            auto_validate=False
        )
        
        assert isinstance(service, ValidationRetryService)
        assert service.policy_generator == mock_policy_generator
        assert service.async_validator == mock_validator_instance
        assert service.max_retries == 5
        assert service.auto_validate is False
        
        # Verify async validator was created with correct CLI path
        mock_validator_class.assert_called_once_with(cli_path="test-cli")


@pytest.mark.asyncio
async def test_resource_cleanup(validation_retry_service):
    """Test resource cleanup."""
    await validation_retry_service.close()
    validation_retry_service.async_validator.close.assert_called_once()


@pytest.mark.asyncio
async def test_exception_handling(validation_retry_service, sample_session, sample_request):
    """Test handling of unexpected exceptions."""
    # Mock policy generator to raise exception
    validation_retry_service.policy_generator.generate_policy.side_effect = Exception("Unexpected error")
    
    result = await validation_retry_service.generate_and_validate_policy(sample_request, sample_session)
    
    assert not result.is_successful
    assert not result.policy_result.is_successful()
    assert "Unexpected error" in result.policy_result.error_message
    assert len(result.error_context) > 0
    assert any("Unexpected error" in error for error in result.error_context)