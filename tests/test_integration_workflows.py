"""
Integration tests for complete user workflows in the Polar Prompt Tester.

These tests verify end-to-end functionality including:
- Complete session creation to policy validation workflows
- Storage backend switching and data migration
- Error handling and recovery scenarios
"""

import pytest
import tempfile
import shutil
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from pathlib import Path

from app.services.session_manager import SessionManager
from app.services.policy_generator import SessionPolicyGenerator
from app.services.event_logger import EventLogger
from app.storage.local_storage import LocalStorageBackend
from app.storage.session_storage import SessionStorage
from app.models.session import Session, GeneratedPolicy, ValidationResult
from app.models.policy import (
    PolicyGenerationRequest, 
    PolicyGenerationResult,
    PolicyValidationResult
)
# EventConfig will be created inline


class TestCompleteUserWorkflows:
    """Test complete user workflows from session creation to policy validation."""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def storage_backend(self, temp_storage_dir):
        """Create local storage backend for testing."""
        return LocalStorageBackend(temp_storage_dir)
    
    @pytest.fixture
    def session_manager(self, storage_backend):
        """Create session manager with storage backend."""
        return SessionManager(storage_backend)
    
    @pytest.fixture
    def event_logger(self, storage_backend):
        """Create event logger for testing."""
        return EventLogger(storage_backend)
    
    @pytest.fixture
    def mock_openai_service(self):
        """Mock OpenAI service for testing."""
        from app.services.openai_service import SessionAwareOpenAIService
        service = Mock(spec=SessionAwareOpenAIService)
        service.generate_policy.return_value = PolicyGenerationResult(
            success=True,
            policy_content='allow(user, "read", resource) if user.role = "admin";',
            model_used="gpt-4",
            tokens_used=150,
            generation_time=2.5
        )
        service.generate_policy_stream.return_value = PolicyGenerationResult(
            success=True,
            policy_content='allow(user, "read", resource) if user.role = "admin";',
            model_used="gpt-4",
            tokens_used=150,
            generation_time=2.5
        )
        return service
    
    @pytest.fixture
    def policy_generator(self, mock_openai_service, mock_validator):
        """Create policy generator with mocked OpenAI service."""
        return SessionPolicyGenerator(mock_openai_service, mock_validator)
    
    @pytest.fixture
    def mock_validator(self):
        """Mock validator for testing."""
        from app.core.validator import PolarValidator, ValidationResult as CoreValidationResult
        validator = Mock(spec=PolarValidator)
        validator.validate_policy.return_value = CoreValidationResult(
            is_valid=True,
            error_message=None,
            errors=[]
        )
        return validator
    
    def test_complete_session_workflow_success(self, session_manager, policy_generator, event_logger):
        """Test complete successful workflow from session creation to validation."""
        # 1. Create new session
        session = session_manager.create_session(
            "Integration Test Session",
            "Testing complete workflow"
        )
        
        assert session.id is not None
        assert session.name == "Integration Test Session"
        assert len(session.generated_policies) == 0
        assert len(session.validation_results) == 0
        
        # 2. Add requirements to session
        session.requirements_text = "Allow administrators to read all resources in the system"
        session.notes = "This is a test policy for admin access"
        session_manager.save_session(session)
        
        # 3. Generate policy
        generation_request = PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            model_config={"model": "gpt-4", "temperature": 0.1}
        )
        
        result = policy_generator.generate_policy(generation_request, session)
        
        # 4. Verify generation success
        assert result.is_successful()
        assert len(session.generated_policies) == 1
        
        # 5. Verify policy details
        policy = session.generated_policies[0]
        assert policy.content == 'allow(user, "read", resource) if user.role = "admin";'
        assert policy.model_used == "gpt-4"
        assert policy.tokens_used == 150
        assert policy.is_current is True
        
        # 6. Validate the policy
        validation_result = policy_generator.validate_policy(
            policy.content, policy.id, session.id
        )
        assert validation_result.is_valid is True
        
        # 7. Add validation result to session
        session_validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=validation_result.is_valid,
            validation_time=validation_result.validation_time
        )
        session.add_validation_result(session_validation)
        
        # 8. Save session with generated policy and validation
        session_manager.save_session(session)
        
        # 9. Load session and verify persistence
        loaded_session = session_manager.load_session(session.id)
        assert loaded_session.requirements_text == session.requirements_text
        assert loaded_session.notes == session.notes
        assert len(loaded_session.generated_policies) == 1
        assert len(loaded_session.validation_results) == 1
        assert loaded_session.generated_policies[0].content == policy.content
        
        # 10. Verify session metadata
        metadata = session_manager.get_session_metadata(session.id)
        assert metadata.has_requirements is True
        assert metadata.has_policies is True
        assert metadata.policy_count == 1
    
    def test_workflow_with_validation_failure(self, session_manager, policy_generator):
        """Test workflow with validation failure."""
        # Create session
        session = session_manager.create_session("Validation Failure Test")
        session.requirements_text = "Allow users to write to resources"
        
        # Mock validation to fail
        from app.core.validator import ValidationResult as CoreValidationResult
        policy_generator.validator.validate_policy.return_value = CoreValidationResult(
            is_valid=False,
            error_message="Syntax error: missing semicolon",
            errors=["Missing semicolon at end of rule"]
        )
        
        # Generate policy
        generation_request = PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            model_config={"model": "gpt-4"}
        )
        
        result = policy_generator.generate_policy(generation_request, session)
        
        # Verify generation succeeded
        assert result.is_successful()
        assert len(session.generated_policies) == 1
        
        # Verify validation failed
        policy = session.generated_policies[0]
        validation_result = policy_generator.validate_policy(
            policy.content, policy.id, session.id
        )
        assert validation_result.is_valid is False
        assert "missing semicolon" in validation_result.error_message
        
        # Add validation result to session
        session_validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=validation_result.is_valid,
            error_message=validation_result.error_message,
            validation_time=validation_result.validation_time
        )
        session.add_validation_result(session_validation)
        
        # Save and verify persistence
        session_manager.save_session(session)
        loaded_session = session_manager.load_session(session.id)
        assert len(loaded_session.generated_policies) == 1
        assert len(loaded_session.validation_results) == 1
        assert loaded_session.validation_results[0].is_valid is False
    
    def test_multiple_sessions_workflow(self, session_manager, policy_generator):
        """Test workflow with multiple concurrent sessions."""
        sessions = []
        
        # Create multiple sessions with different requirements
        session_configs = [
            ("Admin Access Session", "Allow admins to read all resources"),
            ("User Access Session", "Allow users to read their own resources"),
            ("Editor Access Session", "Allow editors to write to documents"),
        ]
        
        for name, requirements in session_configs:
            session = session_manager.create_session(name)
            session.requirements_text = requirements
            session_manager.save_session(session)
            sessions.append(session)
        
        # Generate policies for all sessions
        for session in sessions:
            request = PolicyGenerationRequest(
                session_id=session.id,
                requirements_text=session.requirements_text,
                model_config={"model": "gpt-4"}
            )
            result = policy_generator.generate_policy(request, session)
            assert result.is_successful()
        
        # Save all sessions
        for session in sessions:
            session_manager.save_session(session)
        
        # Verify session listing
        session_list = session_manager.list_sessions()
        assert len(session_list) == 3
        
        # Verify each session has policies
        for metadata in session_list:
            assert metadata.has_requirements is True
            assert metadata.has_policies is True
            assert metadata.policy_count == 1
        
        # Verify session statistics
        stats = session_manager.get_session_statistics()
        assert stats["total_sessions"] == 3
        assert stats["sessions_with_requirements"] == 3
        assert stats["sessions_with_policies"] == 3
        assert stats["total_policies"] == 3
    
    def test_session_search_and_filtering(self, session_manager):
        """Test session search and filtering functionality."""
        # Create sessions with different names and characteristics
        test_sessions = [
            ("Production API Access", "Production environment access rules"),
            ("Development API Access", "Development environment access rules"),
            ("User Management System", "User role and permission management"),
            ("Document Management", "Document access and editing permissions"),
            ("Test Environment Setup", "Testing environment configuration"),
        ]
        
        created_sessions = []
        for name, requirements in test_sessions:
            session = session_manager.create_session(name)
            session.requirements_text = requirements
            
            # Add policies to some sessions
            if "API" in name:
                policy = GeneratedPolicy.create(
                    content=f'allow(user, "access", api) if user.env = "{name.split()[0].lower()}";',
                    model_used="gpt-4"
                )
                session.add_policy(policy)
            
            session_manager.save_session(session)
            created_sessions.append(session)
        
        # Test search functionality
        api_sessions = session_manager.search_sessions("API")
        assert len(api_sessions) == 2
        assert all("API" in session.name for session in api_sessions)
        
        # Test search with limit
        limited_results = session_manager.search_sessions("", limit=3)
        assert len(limited_results) == 3
        
        # Test listing with search term
        management_sessions = session_manager.list_sessions(search_term="Management")
        assert len(management_sessions) == 2
        assert all("Management" in session.name for session in management_sessions)
        
        # Test session statistics
        stats = session_manager.get_session_statistics()
        assert stats["total_sessions"] == 5
        assert stats["sessions_with_requirements"] == 5
        assert stats["sessions_with_policies"] == 2  # Only API sessions have policies
        assert stats["total_policies"] == 2
    
    def test_error_recovery_workflow(self, session_manager, policy_generator):
        """Test error recovery scenarios in the workflow."""
        # Create session
        session = session_manager.create_session("Error Recovery Test")
        session.requirements_text = "Test error recovery"
        
        # Test policy generation failure
        policy_generator.ai_service.generate_policy.return_value = PolicyGenerationResult(
            success=False,
            error_message="OpenAI API error: Rate limit exceeded"
        )
        
        generation_request = PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            model_config={"model": "gpt-4"}
        )
        
        result = policy_generator.generate_policy(generation_request, session)
        
        # Verify failure handling
        assert not result.is_successful()
        assert "Rate limit exceeded" in result.error_message
        assert len(session.generated_policies) == 0  # No policy should be added on failure
        
        # Test recovery - fix the service and try again
        policy_generator.ai_service.generate_policy.return_value = PolicyGenerationResult(
            success=True,
            policy_content='allow(user, "test", resource);',
            model_used="gpt-4",
            tokens_used=100,
            generation_time=2.0
        )
        
        recovery_result = policy_generator.generate_policy(generation_request, session)
        
        # Verify recovery
        assert recovery_result.is_successful()
        assert len(session.generated_policies) == 1
        
        # Save and verify persistence
        session_manager.save_session(session)
        loaded_session = session_manager.load_session(session.id)
        assert len(loaded_session.generated_policies) == 1
    
    def test_session_data_integrity(self, session_manager):
        """Test session data integrity across save/load cycles."""
        # Create comprehensive session
        session = session_manager.create_session("Data Integrity Test")
        session.requirements_text = "Comprehensive requirements for testing data integrity"
        session.notes = "Detailed notes about this test session with special characters: àáâãäå"
        session.metadata = {
            "test_type": "integration",
            "priority": "high",
            "tags": ["testing", "integrity", "validation"]
        }
        
        # Add multiple policies with different characteristics
        policies = [
            GeneratedPolicy.create(
                content='allow(user, "read", resource) if user.role = "admin";',
                model_used="gpt-4",
                tokens_used=120,
                generation_time=2.5
            ),
            GeneratedPolicy.create(
                content='allow(user, "write", resource) if user.role = "editor";',
                model_used="gpt-3.5-turbo",
                tokens_used=95,
                generation_time=1.8
            ),
            GeneratedPolicy.create(
                content='deny(user, "delete", resource) if user.role != "admin";',
                model_used="gpt-4",
                tokens_used=110,
                generation_time=2.2
            )
        ]
        
        for policy in policies:
            session.add_policy(policy)
        
        # Mark the last policy as current
        policies[-1].is_current = True
        
        # Add validation results
        validations = [
            ValidationResult.create(
                policy_id=policies[0].id,
                is_valid=True,
                validation_time=1.2
            ),
            ValidationResult.create(
                policy_id=policies[1].id,
                is_valid=False,
                error_message="Syntax error in rule",
                validation_time=0.8
            ),
            ValidationResult.create(
                policy_id=policies[2].id,
                is_valid=True,
                validation_time=1.5
            )
        ]
        
        for validation in validations:
            session.add_validation_result(validation)
        
        # Save session
        session_manager.save_session(session)
        
        # Load session and verify all data
        loaded_session = session_manager.load_session(session.id)
        
        # Verify basic session data
        assert loaded_session.id == session.id
        assert loaded_session.name == session.name
        assert loaded_session.requirements_text == session.requirements_text
        assert loaded_session.notes == session.notes
        assert loaded_session.metadata == session.metadata
        
        # Verify policies
        assert len(loaded_session.generated_policies) == 3
        loaded_policies = {p.id: p for p in loaded_session.generated_policies}
        
        for original_policy in policies:
            loaded_policy = loaded_policies[original_policy.id]
            assert loaded_policy.content == original_policy.content
            assert loaded_policy.model_used == original_policy.model_used
            assert loaded_policy.tokens_used == original_policy.tokens_used
            assert loaded_policy.generation_time == original_policy.generation_time
            assert loaded_policy.is_current == original_policy.is_current
        
        # Verify validation results
        assert len(loaded_session.validation_results) == 3
        loaded_validations = {v.policy_id: v for v in loaded_session.validation_results}
        
        for original_validation in validations:
            loaded_validation = loaded_validations[original_validation.policy_id]
            assert loaded_validation.is_valid == original_validation.is_valid
            assert loaded_validation.error_message == original_validation.error_message
            assert loaded_validation.validation_time == original_validation.validation_time
        
        # Verify session metadata
        metadata = session_manager.get_session_metadata(session.id)
        assert metadata.has_requirements is True
        assert metadata.has_policies is True
        assert metadata.policy_count == 3


class TestStorageBackendSwitching:
    """Test storage backend switching and data migration."""
    
    @pytest.fixture
    def temp_dirs(self):
        """Create multiple temporary directories for testing."""
        dirs = [tempfile.mkdtemp() for _ in range(3)]
        yield dirs
        for temp_dir in dirs:
            shutil.rmtree(temp_dir)
    
    def test_local_to_local_migration(self, temp_dirs):
        """Test migration between different local storage locations."""
        source_dir, dest_dir, _ = temp_dirs
        
        # Create source storage and session manager
        source_storage = LocalStorageBackend(source_dir)
        source_manager = SessionManager(source_storage)
        
        # Create test session with data
        session = source_manager.create_session("Migration Test Session")
        session.requirements_text = "Test requirements for migration"
        session.notes = "Test notes for migration"
        
        # Add policy and validation
        policy = GeneratedPolicy.create(
            content='allow(user, "read", resource);',
            model_used="gpt-4"
        )
        session.add_policy(policy)
        
        validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=True
        )
        session.add_validation_result(validation)
        
        source_manager.save_session(session)
        
        # Create destination storage and manager
        dest_storage = LocalStorageBackend(dest_dir)
        dest_manager = SessionManager(dest_storage)
        
        # Migrate data by copying files
        self._migrate_local_storage(source_storage, dest_storage)
        
        # Verify migration
        migrated_session = dest_manager.load_session(session.id)
        assert migrated_session.name == session.name
        assert migrated_session.requirements_text == session.requirements_text
        assert migrated_session.notes == session.notes
        assert len(migrated_session.generated_policies) == 1
        assert len(migrated_session.validation_results) == 1
        
        # Verify session listing works in destination
        sessions = dest_manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].id == session.id
    
    def test_storage_backend_compatibility(self, temp_dirs):
        """Test that different storage backends can read the same data format."""
        storage_dir = temp_dirs[0]
        
        # Create session with local storage
        local_storage = LocalStorageBackend(storage_dir)
        session_manager = SessionManager(local_storage)
        
        session = session_manager.create_session("Compatibility Test")
        session.requirements_text = "Test cross-backend compatibility"
        
        policy = GeneratedPolicy.create(
            content='allow(user, "access", resource);',
            model_used="gpt-4"
        )
        session.add_policy(policy)
        session_manager.save_session(session)
        
        # Create new storage backend pointing to same directory
        new_local_storage = LocalStorageBackend(storage_dir)
        new_session_manager = SessionManager(new_local_storage)
        
        # Verify data can be read by new backend instance
        loaded_session = new_session_manager.load_session(session.id)
        assert loaded_session.name == session.name
        assert loaded_session.requirements_text == session.requirements_text
        assert len(loaded_session.generated_policies) == 1
        
        # Verify session listing
        sessions = new_session_manager.list_sessions()
        assert len(sessions) == 1
    
    def test_storage_error_handling_during_migration(self, temp_dirs):
        """Test error handling during storage migration scenarios."""
        source_dir, dest_dir, _ = temp_dirs
        
        # Create source with data
        source_storage = LocalStorageBackend(source_dir)
        source_manager = SessionManager(source_storage)
        
        session = source_manager.create_session("Error Handling Test")
        session.requirements_text = "Test error handling during migration"
        source_manager.save_session(session)
        
        # Create destination storage
        dest_storage = LocalStorageBackend(dest_dir)
        dest_manager = SessionManager(dest_storage)
        
        # Test partial migration (simulate failure)
        # Copy only some files to simulate incomplete migration
        source_session_dir = Path(source_dir) / "sessions" / session.id
        dest_session_dir = Path(dest_dir) / "sessions" / session.id
        dest_session_dir.mkdir(parents=True)
        
        # Copy only metadata, not requirements
        import shutil
        shutil.copy2(
            source_session_dir / "metadata.json",
            dest_session_dir / "metadata.json"
        )
        
        # Try to load session - should handle missing files gracefully
        try:
            loaded_session = dest_manager.load_session(session.id)
            # Session should load but with missing data
            assert loaded_session.name == session.name
            assert loaded_session.requirements_text == ""  # Missing file
        except Exception as e:
            # Or it might raise an exception, which is also acceptable
            assert "requirements.txt" in str(e) or "not found" in str(e).lower()
    
    def _migrate_local_storage(self, source_storage, dest_storage):
        """Helper method to migrate data between local storage backends."""
        import shutil
        
        source_path = source_storage.base_path
        dest_path = dest_storage.base_path
        
        # Copy all session data
        sessions_source = source_path / "sessions"
        sessions_dest = dest_path / "sessions"
        
        if sessions_source.exists():
            if sessions_dest.exists():
                shutil.rmtree(sessions_dest)
            shutil.copytree(sessions_source, sessions_dest)
        
        # Copy events if they exist
        events_source = source_path / "events"
        events_dest = dest_path / "events"
        
        if events_source.exists():
            if events_dest.exists():
                shutil.rmtree(events_dest)
            shutil.copytree(events_source, events_dest)


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios."""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def session_manager(self, temp_storage_dir):
        """Create session manager for testing."""
        storage = LocalStorageBackend(temp_storage_dir)
        return SessionManager(storage)
    
    def test_corrupted_session_recovery(self, session_manager, temp_storage_dir):
        """Test recovery from corrupted session data."""
        # Create valid session
        session = session_manager.create_session("Corruption Test")
        session.requirements_text = "Test corruption recovery"
        session_manager.save_session(session)
        
        # Corrupt session metadata file
        metadata_path = Path(temp_storage_dir) / "sessions" / session.id / "metadata.json"
        with open(metadata_path, 'w') as f:
            f.write("invalid json content {")
        
        # Try to load corrupted session
        try:
            loaded_session = session_manager.load_session(session.id)
            # If it loads, verify it handles corruption gracefully
            assert loaded_session.id == session.id
        except Exception as e:
            # Or it might raise an exception, which is acceptable
            assert "json" in str(e).lower() or "corrupt" in str(e).lower()
    
    def test_missing_session_files_recovery(self, session_manager, temp_storage_dir):
        """Test recovery when session files are missing."""
        # Create session
        session = session_manager.create_session("Missing Files Test")
        session.requirements_text = "Test missing files recovery"
        
        # Add policy
        policy = GeneratedPolicy.create(
            content='allow(user, "read", resource);',
            model_used="gpt-4"
        )
        session.add_policy(policy)
        session_manager.save_session(session)
        
        # Remove requirements file
        requirements_path = Path(temp_storage_dir) / "sessions" / session.id / "requirements.txt"
        requirements_path.unlink()
        
        # Load session - should handle missing file gracefully
        loaded_session = session_manager.load_session(session.id)
        assert loaded_session.id == session.id
        assert loaded_session.requirements_text == ""  # Missing file should result in empty string
        assert len(loaded_session.generated_policies) == 1  # Other data should still be there
    
    def test_storage_permission_errors(self, temp_storage_dir):
        """Test handling of storage permission errors."""
        storage = LocalStorageBackend(temp_storage_dir)
        session_manager = SessionManager(storage)
        
        # Create session
        session = session_manager.create_session("Permission Test")
        
        # Mock permission error during save
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with pytest.raises(Exception):  # Should raise some form of error
                session_manager.save_session(session)
    
    def test_storage_disk_full_simulation(self, session_manager):
        """Test handling of disk full scenarios."""
        session = session_manager.create_session("Disk Full Test")
        session.requirements_text = "Test disk full handling"
        
        # Mock disk full error
        with patch.object(session_manager.session_storage, 'store_session_file', 
                         side_effect=OSError("No space left on device")):
            with pytest.raises(Exception):  # Should raise some form of error
                session_manager.save_session(session)
    
    def test_validation_timeout_handling(self, session_manager, policy_generator):
        """Test handling of validation timeouts."""
        # Create session
        session = session_manager.create_session("Timeout Test")
        session.requirements_text = "Test timeout handling"
        
        # Mock validator to raise timeout
        import subprocess
        policy_generator.validator.validate_policy.side_effect = subprocess.TimeoutExpired("oso-cloud", 30)
        
        # Generate policy
        generation_request = PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            model_config={"model": "gpt-4"}
        )
        
        result = policy_generator.generate_policy(generation_request, session)
        
        # Policy generation should succeed
        assert result.is_successful()
        assert len(session.generated_policies) == 1
        
        # Validation should handle timeout gracefully
        policy = session.generated_policies[0]
        validation_result = policy_generator.validate_policy(
            policy.content, policy.id, session.id
        )
        
        # Should indicate validation failure due to timeout
        assert validation_result.is_valid is False
        assert "timed out" in validation_result.error_message.lower()
    
    def test_concurrent_access_handling(self, session_manager):
        """Test handling of concurrent access to the same session."""
        # Create session
        session = session_manager.create_session("Concurrent Test")
        session.requirements_text = "Test concurrent access"
        session_manager.save_session(session)
        
        # Simulate concurrent modifications
        session1 = session_manager.load_session(session.id)
        session2 = session_manager.load_session(session.id)
        
        # Modify both sessions
        session1.notes = "Modified by process 1"
        session2.notes = "Modified by process 2"
        
        # Save both (last one wins)
        session_manager.save_session(session1)
        session_manager.save_session(session2)
        
        # Load and verify final state
        final_session = session_manager.load_session(session.id)
        assert final_session.notes == "Modified by process 2"  # Last write wins
    
    def test_session_cleanup_after_errors(self, session_manager, temp_storage_dir):
        """Test cleanup of partial session data after errors."""
        # Create session that will fail during save
        session = session_manager.create_session("Cleanup Test")
        session.requirements_text = "Test cleanup after errors"
        
        # Add policy
        policy = GeneratedPolicy.create(
            content='allow(user, "read", resource);',
            model_used="gpt-4"
        )
        session.add_policy(policy)
        
        # Mock failure during policy file save
        original_store = session_manager.session_storage.store_session_file
        call_count = 0
        
        def failing_store(session_id, filename, content, content_type=None):
            nonlocal call_count
            call_count += 1
            if "policies/" in filename and call_count > 2:  # Fail on policy file
                raise OSError("Simulated storage failure")
            return original_store(session_id, filename, content, content_type)
        
        with patch.object(session_manager.session_storage, 'store_session_file', 
                         side_effect=failing_store):
            with pytest.raises(Exception):
                session_manager.save_session(session)
        
        # Verify partial data exists but session is in inconsistent state
        session_dir = Path(temp_storage_dir) / "sessions" / session.id
        assert session_dir.exists()
        
        # Try to load session - should handle inconsistent state
        try:
            loaded_session = session_manager.load_session(session.id)
            # Might load with partial data
            assert loaded_session.id == session.id
        except Exception:
            # Or might fail to load, which is also acceptable
            pass


if __name__ == "__main__":
    pytest.main([__file__])