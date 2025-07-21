"""
Unit tests for SessionManager service.
"""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.services.session_manager import (
    SessionManager, 
    SessionManagerError, 
    SessionNotFoundError, 
    SessionValidationError
)
from app.models.session import Session, SessionMetadata, GeneratedPolicy, ValidationResult
from app.storage.local_storage import LocalStorageBackend
from app.storage.base import StorageError, StorageNotFoundError


class TestSessionManager:
    """Test cases for SessionManager functionality."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage backend for testing."""
        temp_dir = tempfile.mkdtemp()
        storage = LocalStorageBackend(temp_dir)
        yield storage
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def session_manager(self, temp_storage):
        """Create a SessionManager instance for testing."""
        return SessionManager(temp_storage)
    
    @pytest.fixture
    def sample_session(self):
        """Create a sample session for testing."""
        session = Session.create("Test Session")
        session.requirements_text = "Allow users to read resources"
        session.notes = "Test notes"
        return session
    
    def test_create_session_success(self, session_manager):
        """Test successful session creation."""
        session = session_manager.create_session("Test Session", "Test description")
        
        assert session.name == "Test Session"
        assert session.id is not None
        assert session.created_at is not None
        assert session.updated_at is not None
        assert len(session.generated_policies) == 0
        assert len(session.validation_results) == 0
    
    def test_create_session_empty_name(self, session_manager):
        """Test session creation with empty name."""
        with pytest.raises(SessionValidationError):
            session_manager.create_session("")
        
        with pytest.raises(SessionValidationError):
            session_manager.create_session("   ")
    
    def test_create_session_long_name(self, session_manager):
        """Test session creation with overly long name."""
        long_name = "x" * 101  # Exceeds 100 character limit
        with pytest.raises(SessionValidationError):
            session_manager.create_session(long_name)
    
    def test_create_session_storage_error(self, session_manager):
        """Test session creation with storage error."""
        with patch.object(session_manager.session_storage, 'create_session', 
                         side_effect=StorageError("Storage failed")):
            with pytest.raises(SessionManagerError):
                session_manager.create_session("Test Session")
    
    def test_load_session_success(self, session_manager, sample_session):
        """Test successful session loading."""
        # First create and save the session
        created_session = session_manager.create_session(sample_session.name)
        created_session.requirements_text = sample_session.requirements_text
        created_session.notes = sample_session.notes
        session_manager.save_session(created_session)
        
        # Load the session
        loaded_session = session_manager.load_session(created_session.id)
        
        assert loaded_session.id == created_session.id
        assert loaded_session.name == created_session.name
        assert loaded_session.requirements_text == sample_session.requirements_text
        assert loaded_session.notes == sample_session.notes
    
    def test_load_session_not_found(self, session_manager):
        """Test loading non-existent session."""
        with pytest.raises(SessionNotFoundError):
            session_manager.load_session("nonexistent-session-id")
    
    def test_load_session_empty_id(self, session_manager):
        """Test loading session with empty ID."""
        with pytest.raises(SessionValidationError):
            session_manager.load_session("")
        
        with pytest.raises(SessionValidationError):
            session_manager.load_session("   ")
    
    def test_save_session_success(self, session_manager, sample_session):
        """Test successful session saving."""
        # Create session first
        created_session = session_manager.create_session(sample_session.name)
        created_session.requirements_text = sample_session.requirements_text
        created_session.notes = sample_session.notes
        
        # Add a policy
        policy = GeneratedPolicy.create(
            content="allow(user, \"read\", resource);",
            model_used="gpt-4"
        )
        created_session.add_policy(policy)
        
        # Add a validation result
        validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=True
        )
        created_session.add_validation_result(validation)
        
        result = session_manager.save_session(created_session)
        assert result is True
        
        # Verify by loading
        loaded_session = session_manager.load_session(created_session.id)
        assert len(loaded_session.generated_policies) == 1
        assert len(loaded_session.validation_results) == 1
    
    def test_save_session_validation_error(self, session_manager):
        """Test saving session with validation errors."""
        session = Session.create("Test")
        session.name = ""  # Invalid empty name
        
        with pytest.raises(SessionValidationError):
            session_manager.save_session(session)
    
    def test_list_sessions_empty(self, session_manager):
        """Test listing sessions when none exist."""
        sessions = session_manager.list_sessions()
        assert sessions == []
    
    def test_list_sessions_with_data(self, session_manager):
        """Test listing sessions with existing data."""
        # Create multiple sessions
        session1 = session_manager.create_session("Session 1")
        session2 = session_manager.create_session("Session 2")
        session3 = session_manager.create_session("Session 3")
        
        sessions = session_manager.list_sessions()
        
        assert len(sessions) == 3
        # Should be sorted by updated_at descending (newest first)
        session_names = [s.name for s in sessions]
        assert "Session 3" in session_names
        assert "Session 2" in session_names
        assert "Session 1" in session_names
    
    def test_list_sessions_with_limit(self, session_manager):
        """Test listing sessions with limit."""
        # Create multiple sessions
        for i in range(5):
            session_manager.create_session(f"Session {i}")
        
        sessions = session_manager.list_sessions(limit=3)
        assert len(sessions) == 3
    
    def test_list_sessions_with_search(self, session_manager):
        """Test listing sessions with search term."""
        session_manager.create_session("Test Session")
        session_manager.create_session("Production Session")
        session_manager.create_session("Development Session")
        
        # Search for "Test"
        sessions = session_manager.list_sessions(search_term="Test")
        assert len(sessions) == 1
        assert sessions[0].name == "Test Session"
        
        # Search for "Session" (should match all)
        sessions = session_manager.list_sessions(search_term="Session")
        assert len(sessions) == 3
    
    def test_delete_session_success(self, session_manager):
        """Test successful session deletion."""
        session = session_manager.create_session("Test Session")
        
        result = session_manager.delete_session(session.id)
        assert result is True
        
        # Verify session is gone
        assert not session_manager.session_exists(session.id)
    
    def test_delete_session_nonexistent(self, session_manager):
        """Test deleting non-existent session."""
        result = session_manager.delete_session("nonexistent-id")
        assert result is True  # Should be idempotent
    
    def test_delete_session_empty_id(self, session_manager):
        """Test deleting session with empty ID."""
        with pytest.raises(SessionValidationError):
            session_manager.delete_session("")
    
    def test_session_exists(self, session_manager):
        """Test session existence checking."""
        # Non-existent session
        assert not session_manager.session_exists("nonexistent-id")
        
        # Create session
        session = session_manager.create_session("Test Session")
        assert session_manager.session_exists(session.id)
        
        # Delete session
        session_manager.delete_session(session.id)
        assert not session_manager.session_exists(session.id)
    
    def test_session_exists_empty_id(self, session_manager):
        """Test session existence with empty ID."""
        assert not session_manager.session_exists("")
        assert not session_manager.session_exists("   ")
    
    def test_get_session_metadata(self, session_manager):
        """Test getting session metadata."""
        session = session_manager.create_session("Test Session")
        session.requirements_text = "Test requirements"
        session_manager.save_session(session)
        
        metadata = session_manager.get_session_metadata(session.id)
        
        assert metadata.id == session.id
        assert metadata.name == session.name
        assert metadata.has_requirements is True
        assert metadata.has_policies is False
        assert metadata.policy_count == 0
    
    def test_get_session_metadata_not_found(self, session_manager):
        """Test getting metadata for non-existent session."""
        with pytest.raises(SessionNotFoundError):
            session_manager.get_session_metadata("nonexistent-id")
    
    def test_search_sessions(self, session_manager):
        """Test session search functionality."""
        session_manager.create_session("Test Session Alpha")
        session_manager.create_session("Test Session Beta")
        session_manager.create_session("Production Session")
        
        # Search with query
        results = session_manager.search_sessions("Test")
        assert len(results) == 2
        
        # Search with empty query (should return all)
        results = session_manager.search_sessions("")
        assert len(results) == 3
        
        # Search with limit
        results = session_manager.search_sessions("Session", limit=2)
        assert len(results) == 2
    
    def test_get_session_statistics(self, session_manager):
        """Test getting session statistics."""
        # Create sessions with different characteristics
        session1 = session_manager.create_session("Session 1")
        session1.requirements_text = "Requirements 1"
        policy1 = GeneratedPolicy.create(content="policy1", model_used="gpt-4")
        session1.add_policy(policy1)
        session_manager.save_session(session1)
        
        session2 = session_manager.create_session("Session 2")
        session2.requirements_text = "Requirements 2"
        session_manager.save_session(session2)
        
        session3 = session_manager.create_session("Session 3")
        # No requirements or policies
        session_manager.save_session(session3)
        
        stats = session_manager.get_session_statistics()
        
        assert stats["total_sessions"] == 3
        assert stats["sessions_with_requirements"] == 2
        assert stats["sessions_with_policies"] == 1
        assert stats["total_policies"] == 1
        assert stats["average_policies_per_session"] == 1/3
        assert "storage_size_bytes" in stats
        assert "average_session_size_bytes" in stats
    
    def test_validate_session_valid(self, session_manager):
        """Test session validation with valid session."""
        session = Session.create("Valid Session")
        session.requirements_text = "Valid requirements"
        
        policy = GeneratedPolicy.create(
            content="allow(user, \"read\", resource);",
            model_used="gpt-4"
        )
        session.add_policy(policy)
        
        validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=True
        )
        session.add_validation_result(validation)
        
        # Should not raise any exception
        session_manager._validate_session(session)
    
    def test_validate_session_invalid_id(self, session_manager):
        """Test session validation with invalid ID."""
        session = Session.create("Test Session")
        session.id = ""  # Invalid empty ID
        
        with pytest.raises(SessionValidationError):
            session_manager._validate_session(session)
    
    def test_validate_session_invalid_name(self, session_manager):
        """Test session validation with invalid name."""
        session = Session.create("Test Session")
        session.name = ""  # Invalid empty name
        
        with pytest.raises(SessionValidationError):
            session_manager._validate_session(session)
        
        session.name = "x" * 101  # Too long
        with pytest.raises(SessionValidationError):
            session_manager._validate_session(session)
    
    def test_validate_session_invalid_policy(self, session_manager):
        """Test session validation with invalid policy."""
        session = Session.create("Test Session")
        
        # Policy with empty ID
        policy = GeneratedPolicy.create(content="test", model_used="gpt-4")
        policy.id = ""
        session.add_policy(policy)
        
        with pytest.raises(SessionValidationError):
            session_manager._validate_session(session)
        
        # Policy with empty content
        policy.id = "valid-id"
        policy.content = ""
        
        with pytest.raises(SessionValidationError):
            session_manager._validate_session(session)
    
    def test_validate_session_invalid_validation_result(self, session_manager):
        """Test session validation with invalid validation result."""
        session = Session.create("Test Session")
        
        # Validation result with empty ID
        validation = ValidationResult.create(policy_id="policy-1", is_valid=True)
        validation.id = ""
        session.add_validation_result(validation)
        
        with pytest.raises(SessionValidationError):
            session_manager._validate_session(session)
        
        # Validation result with empty policy_id
        validation.id = "valid-id"
        validation.policy_id = ""
        
        with pytest.raises(SessionValidationError):
            session_manager._validate_session(session)
    
    def test_persist_and_load_session_data(self, session_manager):
        """Test complete session persistence and loading cycle."""
        # Create session with comprehensive data
        session = session_manager.create_session("Comprehensive Session")
        session.requirements_text = "Detailed requirements text"
        session.notes = "Important notes about this session"
        session.metadata = {"custom_field": "custom_value"}
        
        # Add multiple policies
        policy1 = GeneratedPolicy.create(
            content="allow(user, \"read\", resource);",
            model_used="gpt-4",
            tokens_used=100,
            generation_time=2.5
        )
        policy2 = GeneratedPolicy.create(
            content="allow(admin, \"write\", resource);",
            model_used="gpt-3.5-turbo",
            tokens_used=80,
            generation_time=1.8
        )
        session.add_policy(policy1)
        session.add_policy(policy2)
        
        # Add validation results
        validation1 = ValidationResult.create(
            policy_id=policy1.id,
            is_valid=True,
            validation_time=1.2
        )
        validation2 = ValidationResult.create(
            policy_id=policy2.id,
            is_valid=False,
            error_message="Syntax error",
            validation_time=0.8
        )
        session.add_validation_result(validation1)
        session.add_validation_result(validation2)
        
        # Save session
        session_manager.save_session(session)
        
        # Load session and verify all data
        loaded_session = session_manager.load_session(session.id)
        
        assert loaded_session.id == session.id
        assert loaded_session.name == session.name
        assert loaded_session.requirements_text == session.requirements_text
        assert loaded_session.notes == session.notes
        assert loaded_session.metadata == session.metadata
        
        # Verify policies
        assert len(loaded_session.generated_policies) == 2
        loaded_policies = {p.id: p for p in loaded_session.generated_policies}
        
        assert policy1.id in loaded_policies
        assert policy2.id in loaded_policies
        assert loaded_policies[policy1.id].content == policy1.content
        assert loaded_policies[policy1.id].model_used == policy1.model_used
        assert loaded_policies[policy1.id].tokens_used == policy1.tokens_used
        assert loaded_policies[policy1.id].generation_time == policy1.generation_time
        
        # Verify validation results
        assert len(loaded_session.validation_results) == 2
        loaded_validations = {v.policy_id: v for v in loaded_session.validation_results}
        
        assert policy1.id in loaded_validations
        assert policy2.id in loaded_validations
        assert loaded_validations[policy1.id].is_valid is True
        assert loaded_validations[policy2.id].is_valid is False
        assert loaded_validations[policy2.id].error_message == "Syntax error"
    
    def test_concurrent_session_operations(self, session_manager):
        """Test concurrent session operations don't interfere."""
        # Create multiple sessions
        sessions = []
        for i in range(5):
            session = session_manager.create_session(f"Session {i}")
            session.requirements_text = f"Requirements for session {i}"
            sessions.append(session)
        
        # Save all sessions
        for session in sessions:
            session_manager.save_session(session)
        
        # Load all sessions and verify they're independent
        for original_session in sessions:
            loaded_session = session_manager.load_session(original_session.id)
            assert loaded_session.name == original_session.name
            assert loaded_session.requirements_text == original_session.requirements_text
    
    def test_session_manager_error_handling(self, session_manager):
        """Test error handling in various edge cases."""
        # Test with storage backend that fails
        with patch.object(session_manager.session_storage, 'get_session_metadata',
                         side_effect=StorageError("Storage unavailable")):
            with pytest.raises(SessionManagerError):
                session_manager.load_session("any-id")
        
        # Test statistics with storage error
        with patch.object(session_manager.session_storage, 'get_storage_stats',
                         side_effect=StorageError("Stats unavailable")):
            with pytest.raises(SessionManagerError):
                session_manager.get_session_statistics()


if __name__ == "__main__":
    pytest.main([__file__])