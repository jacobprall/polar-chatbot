"""
UI tests for Streamlit interface components and user interactions.

These tests verify:
- Streamlit interface components and user interactions
- Session state management and persistence
- File upload, download, and sharing functionality
"""

import pytest
import tempfile
import shutil
import io
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Import Streamlit testing utilities
try:
    from streamlit.testing.v1 import AppTest
    STREAMLIT_TESTING_AVAILABLE = True
except ImportError:
    STREAMLIT_TESTING_AVAILABLE = False

from app.services.session_manager import SessionManager
from app.services.policy_generator import SessionPolicyGenerator
from app.storage.local_storage import LocalStorageBackend
from app.models.session import Session, GeneratedPolicy, ValidationResult
from app.models.policy import PolicyGenerationRequest, PolicyGenerationResult


@pytest.mark.skipif(not STREAMLIT_TESTING_AVAILABLE, reason="Streamlit testing not available")
class TestStreamlitUI:
    """Test Streamlit UI components and interactions."""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_services(self, temp_storage_dir):
        """Create mock services for UI testing."""
        storage = LocalStorageBackend(temp_storage_dir)
        session_manager = SessionManager(storage)
        
        # Mock OpenAI service
        mock_openai = Mock()
        mock_openai.generate_policy.return_value = PolicyGenerationResult(
            success=True,
            policy_content='allow(user, "read", resource);',
            model_used="gpt-4",
            tokens_used=100,
            generation_time=2.0
        )
        
        # Mock validator
        from app.core.validator import PolarValidator, ValidationResult as CoreValidationResult
        mock_validator = Mock(spec=PolarValidator)
        mock_validator.validate_policy.return_value = CoreValidationResult(
            is_valid=True,
            error_message=None,
            errors=[]
        )
        
        policy_generator = SessionPolicyGenerator(mock_openai, mock_validator)
        
        return {
            'session_manager': session_manager,
            'policy_generator': policy_generator,
            'storage': storage
        }
    
    def test_main_app_initialization(self, mock_services):
        """Test main Streamlit app initialization."""
        with patch('app.streamlit_app.get_session_manager', return_value=mock_services['session_manager']):
            with patch('app.streamlit_app.get_policy_generator', return_value=mock_services['policy_generator']):
                # Test app initialization
                at = AppTest.from_file("app/streamlit_app.py")
                at.run()
                
                # Check that the app runs without errors
                assert not at.exception
                
                # Check for main UI elements
                assert len(at.title) > 0  # Should have a title
                assert len(at.sidebar) > 0  # Should have sidebar elements
    
    def test_session_creation_ui(self, mock_services):
        """Test session creation through UI."""
        with patch('app.streamlit_app.get_session_manager', return_value=mock_services['session_manager']):
            at = AppTest.from_file("app/streamlit_app.py")
            at.run()
            
            # Simulate creating a new session
            if len(at.text_input) > 0:
                # Find session name input
                session_name_input = at.text_input[0]  # Assuming first text input is session name
                session_name_input.input("Test Session").run()
                
                # Look for create button and click it
                create_buttons = [btn for btn in at.button if "create" in btn.label.lower()]
                if create_buttons:
                    create_buttons[0].click().run()
                    
                    # Verify session was created (check for success message or session list update)
                    assert not at.exception
    
    def test_session_selection_ui(self, mock_services):
        """Test session selection interface."""
        # Pre-create some sessions
        session_manager = mock_services['session_manager']
        session1 = session_manager.create_session("Test Session 1")
        session2 = session_manager.create_session("Test Session 2")
        
        with patch('app.streamlit_app.get_session_manager', return_value=session_manager):
            at = AppTest.from_file("app/streamlit_app.py")
            at.run()
            
            # Check for session selection elements
            if len(at.selectbox) > 0:
                session_selector = at.selectbox[0]  # Assuming first selectbox is session selector
                
                # Verify sessions appear in selector
                options = session_selector.options
                session_names = [session1.name, session2.name]
                assert any(name in str(options) for name in session_names)
    
    def test_requirements_editor_ui(self, mock_services):
        """Test requirements text editor component."""
        # Create a session first
        session_manager = mock_services['session_manager']
        session = session_manager.create_session("Requirements Test Session")
        
        with patch('app.streamlit_app.get_session_manager', return_value=session_manager):
            with patch('app.streamlit_app.get_current_session', return_value=session):
                at = AppTest.from_file("app/streamlit_app.py")
                at.run()
                
                # Look for text area for requirements
                if len(at.text_area) > 0:
                    requirements_area = at.text_area[0]  # Assuming first text area is requirements
                    test_requirements = "Allow users to read resources based on their role"
                    requirements_area.input(test_requirements).run()
                    
                    # Verify no errors occurred
                    assert not at.exception
    
    def test_policy_generation_ui(self, mock_services):
        """Test policy generation interface."""
        # Create session with requirements
        session_manager = mock_services['session_manager']
        session = session_manager.create_session("Generation Test Session")
        session.requirements_text = "Allow admins to read all resources"
        session_manager.save_session(session)
        
        with patch('app.streamlit_app.get_session_manager', return_value=session_manager):
            with patch('app.streamlit_app.get_policy_generator', return_value=mock_services['policy_generator']):
                with patch('app.streamlit_app.get_current_session', return_value=session):
                    at = AppTest.from_file("app/streamlit_app.py")
                    at.run()
                    
                    # Look for generate button
                    generate_buttons = [btn for btn in at.button if "generate" in btn.label.lower()]
                    if generate_buttons:
                        generate_buttons[0].click().run()
                        
                        # Verify no errors occurred during generation
                        assert not at.exception
    
    def test_validation_results_ui(self, mock_services):
        """Test validation results display."""
        # Create session with policy and validation result
        session_manager = mock_services['session_manager']
        session = session_manager.create_session("Validation Test Session")
        
        # Add policy
        policy = GeneratedPolicy.create(
            content='allow(user, "read", resource);',
            model_used="gpt-4"
        )
        session.add_policy(policy)
        
        # Add validation result
        validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=True,
            validation_time=1.2
        )
        session.add_validation_result(validation)
        session_manager.save_session(session)
        
        with patch('app.streamlit_app.get_session_manager', return_value=session_manager):
            with patch('app.streamlit_app.get_current_session', return_value=session):
                at = AppTest.from_file("app/streamlit_app.py")
                at.run()
                
                # Verify validation results are displayed
                # Look for success indicators or validation status
                assert not at.exception
    
    def test_notes_editor_ui(self, mock_services):
        """Test notes editor functionality."""
        # Create session
        session_manager = mock_services['session_manager']
        session = session_manager.create_session("Notes Test Session")
        
        with patch('app.streamlit_app.get_session_manager', return_value=session_manager):
            with patch('app.streamlit_app.get_current_session', return_value=session):
                at = AppTest.from_file("app/streamlit_app.py")
                at.run()
                
                # Look for notes text area
                notes_areas = [ta for ta in at.text_area if "notes" in ta.label.lower()]
                if notes_areas:
                    notes_area = notes_areas[0]
                    test_notes = "These are test notes for the session"
                    notes_area.input(test_notes).run()
                    
                    # Verify no errors occurred
                    assert not at.exception
    
    def test_session_export_functionality(self, mock_services):
        """Test session export and download functionality."""
        # Create session with comprehensive data
        session_manager = mock_services['session_manager']
        session = session_manager.create_session("Export Test Session")
        session.requirements_text = "Test requirements for export"
        session.notes = "Test notes for export"
        
        # Add policy
        policy = GeneratedPolicy.create(
            content='allow(user, "read", resource);',
            model_used="gpt-4"
        )
        session.add_policy(policy)
        session_manager.save_session(session)
        
        with patch('app.streamlit_app.get_session_manager', return_value=session_manager):
            with patch('app.streamlit_app.get_current_session', return_value=session):
                at = AppTest.from_file("app/streamlit_app.py")
                at.run()
                
                # Look for export/download buttons
                export_buttons = [btn for btn in at.button if any(word in btn.label.lower() 
                                for word in ["export", "download", "save"])]
                if export_buttons:
                    export_buttons[0].click().run()
                    
                    # Verify no errors occurred during export
                    assert not at.exception


class TestUIComponentsWithoutStreamlit:
    """Test UI components without requiring Streamlit testing framework."""
    
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
    
    def test_session_state_management(self, session_manager):
        """Test session state management logic."""
        # Test session creation
        session = session_manager.create_session("State Test Session")
        assert session.id is not None
        
        # Test session modification
        session.requirements_text = "Test requirements"
        session.notes = "Test notes"
        session_manager.save_session(session)
        
        # Test session loading
        loaded_session = session_manager.load_session(session.id)
        assert loaded_session.requirements_text == "Test requirements"
        assert loaded_session.notes == "Test notes"
    
    def test_file_upload_simulation(self, session_manager):
        """Test file upload functionality simulation."""
        session = session_manager.create_session("File Upload Test")
        
        # Simulate file upload content
        uploaded_content = "Allow users to access resources based on their department"
        
        # Process uploaded content (simulating what the UI would do)
        session.requirements_text = uploaded_content
        session_manager.save_session(session)
        
        # Verify content was saved
        loaded_session = session_manager.load_session(session.id)
        assert loaded_session.requirements_text == uploaded_content
    
    def test_session_sharing_data_preparation(self, session_manager):
        """Test preparation of session data for sharing."""
        # Create comprehensive session
        session = session_manager.create_session("Sharing Test Session")
        session.requirements_text = "Comprehensive requirements for sharing test"
        session.notes = "Detailed notes about this session"
        
        # Add policy
        policy = GeneratedPolicy.create(
            content='allow(user, "read", resource) if user.role = "admin";',
            model_used="gpt-4",
            tokens_used=150,
            generation_time=2.5
        )
        session.add_policy(policy)
        
        # Add validation result
        validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=True,
            validation_time=1.2
        )
        session.add_validation_result(validation)
        
        session_manager.save_session(session)
        
        # Prepare sharing data (what the UI would export)
        sharing_data = {
            "session_name": session.name,
            "requirements": session.requirements_text,
            "notes": session.notes,
            "policies": [
                {
                    "content": p.content,
                    "model_used": p.model_used,
                    "tokens_used": p.tokens_used,
                    "generation_time": p.generation_time,
                    "is_current": p.is_current
                }
                for p in session.generated_policies
            ],
            "validations": [
                {
                    "policy_id": v.policy_id,
                    "is_valid": v.is_valid,
                    "error_message": v.error_message,
                    "validation_time": v.validation_time
                }
                for v in session.validation_results
            ]
        }
        
        # Verify sharing data structure
        assert sharing_data["session_name"] == session.name
        assert sharing_data["requirements"] == session.requirements_text
        assert sharing_data["notes"] == session.notes
        assert len(sharing_data["policies"]) == 1
        assert len(sharing_data["validations"]) == 1
        assert sharing_data["policies"][0]["content"] == policy.content
        assert sharing_data["validations"][0]["is_valid"] is True
    
    def test_ui_error_handling_simulation(self, session_manager):
        """Test UI error handling scenarios."""
        # Test loading non-existent session
        try:
            session_manager.load_session("nonexistent-session-id")
            assert False, "Should have raised an exception"
        except Exception as e:
            # UI should handle this gracefully
            assert "not found" in str(e).lower()
        
        # Test creating session with invalid name
        try:
            session_manager.create_session("")
            assert False, "Should have raised an exception"
        except Exception as e:
            # UI should handle this gracefully
            assert "empty" in str(e).lower() or "invalid" in str(e).lower()
    
    def test_session_persistence_across_ui_interactions(self, session_manager):
        """Test that session data persists across UI interactions."""
        # Simulate multiple UI interactions
        session = session_manager.create_session("Persistence Test")
        
        # First interaction: add requirements
        session.requirements_text = "Initial requirements"
        session_manager.save_session(session)
        
        # Second interaction: add notes
        loaded_session = session_manager.load_session(session.id)
        loaded_session.notes = "Added notes"
        session_manager.save_session(loaded_session)
        
        # Third interaction: add policy
        loaded_session = session_manager.load_session(session.id)
        policy = GeneratedPolicy.create(
            content='allow(user, "read", resource);',
            model_used="gpt-4"
        )
        loaded_session.add_policy(policy)
        session_manager.save_session(loaded_session)
        
        # Final verification
        final_session = session_manager.load_session(session.id)
        assert final_session.requirements_text == "Initial requirements"
        assert final_session.notes == "Added notes"
        assert len(final_session.generated_policies) == 1
    
    def test_concurrent_ui_sessions(self, session_manager):
        """Test handling of multiple concurrent UI sessions."""
        # Simulate multiple users/tabs working with different sessions
        session1 = session_manager.create_session("User 1 Session")
        session2 = session_manager.create_session("User 2 Session")
        
        # User 1 adds requirements
        session1.requirements_text = "User 1 requirements"
        session_manager.save_session(session1)
        
        # User 2 adds different requirements
        session2.requirements_text = "User 2 requirements"
        session_manager.save_session(session2)
        
        # Verify sessions remain independent
        loaded_session1 = session_manager.load_session(session1.id)
        loaded_session2 = session_manager.load_session(session2.id)
        
        assert loaded_session1.requirements_text == "User 1 requirements"
        assert loaded_session2.requirements_text == "User 2 requirements"
        assert loaded_session1.id != loaded_session2.id
    
    def test_ui_data_validation(self, session_manager):
        """Test data validation in UI components."""
        session = session_manager.create_session("Validation Test")
        
        # Test various input scenarios that UI should handle
        test_cases = [
            ("", "Empty requirements"),
            ("   ", "Whitespace-only requirements"),
            ("A" * 10000, "Very long requirements"),
            ("Requirements with special chars: àáâãäå", "Unicode requirements"),
            ("Requirements\nwith\nmultiple\nlines", "Multi-line requirements"),
        ]
        
        for requirements, description in test_cases:
            session.requirements_text = requirements
            try:
                session_manager.save_session(session)
                # Verify it can be loaded back
                loaded_session = session_manager.load_session(session.id)
                assert loaded_session.requirements_text == requirements, f"Failed for: {description}"
            except Exception as e:
                # Some cases might fail validation, which is acceptable
                assert "validation" in str(e).lower() or "invalid" in str(e).lower()
    
    def test_ui_performance_with_large_sessions(self, session_manager):
        """Test UI performance considerations with large sessions."""
        session = session_manager.create_session("Large Session Test")
        
        # Add many policies to simulate large session
        for i in range(10):  # Reasonable number for testing
            policy = GeneratedPolicy.create(
                content=f'allow(user, "action_{i}", resource_{i});',
                model_used="gpt-4",
                tokens_used=100 + i,
                generation_time=2.0 + i * 0.1
            )
            session.add_policy(policy)
            
            # Add corresponding validation
            validation = ValidationResult.create(
                policy_id=policy.id,
                is_valid=i % 2 == 0,  # Alternate between valid/invalid
                validation_time=1.0 + i * 0.1
            )
            session.add_validation_result(validation)
        
        # Add large requirements and notes
        session.requirements_text = "Large requirements text. " * 100
        session.notes = "Large notes text. " * 100
        
        # Test save and load performance
        import time
        start_time = time.time()
        session_manager.save_session(session)
        save_time = time.time() - start_time
        
        start_time = time.time()
        loaded_session = session_manager.load_session(session.id)
        load_time = time.time() - start_time
        
        # Verify data integrity
        assert len(loaded_session.generated_policies) == 10
        assert len(loaded_session.validation_results) == 10
        assert len(loaded_session.requirements_text) > 1000
        assert len(loaded_session.notes) > 1000
        
        # Performance should be reasonable (adjust thresholds as needed)
        assert save_time < 5.0, f"Save took too long: {save_time}s"
        assert load_time < 5.0, f"Load took too long: {load_time}s"


if __name__ == "__main__":
    pytest.main([__file__])