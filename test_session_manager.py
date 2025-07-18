#!/usr/bin/env python3
"""
Test script for SessionManager functionality
"""

import sys
import os
from datetime import datetime

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from app.services.session_manager import SessionManager, SessionManagerError, SessionNotFoundError, SessionValidationError
from app.storage.local_storage import LocalStorageBackend
from app.models.session import GeneratedPolicy, ValidationResult


def test_session_manager():
    """Test basic SessionManager functionality"""
    print("Testing SessionManager...")
    
    # Initialize storage and session manager
    storage = LocalStorageBackend("./test_sessions")
    session_manager = SessionManager(storage)
    
    try:
        # Test 1: Create a new session
        print("\n1. Testing session creation...")
        session = session_manager.create_session("Test Session", "A test session for validation")
        print(f"✓ Created session: {session.name} (ID: {session.id})")
        
        # Test 2: Load the session
        print("\n2. Testing session loading...")
        loaded_session = session_manager.load_session(session.id)
        print(f"✓ Loaded session: {loaded_session.name}")
        assert loaded_session.id == session.id
        assert loaded_session.name == session.name
        
        # Test 3: Add some data to the session
        print("\n3. Testing session data updates...")
        loaded_session.requirements_text = "Test requirements for Polar policy generation"
        loaded_session.notes = "These are test notes"
        
        # Add a generated policy
        policy = GeneratedPolicy.create(
            content="allow(user, \"read\", resource) if user.role = \"admin\";",
            model_used="gpt-4",
            tokens_used=150,
            generation_time=2.5
        )
        loaded_session.add_policy(policy)
        
        # Add a validation result
        validation = ValidationResult.create(
            policy_id=policy.id,
            is_valid=True,
            validation_time=0.8
        )
        loaded_session.add_validation_result(validation)
        
        # Save the updated session
        success = session_manager.save_session(loaded_session)
        print(f"✓ Saved session with data: {success}")
        
        # Test 4: Reload and verify data persistence
        print("\n4. Testing data persistence...")
        reloaded_session = session_manager.load_session(session.id)
        print(f"✓ Requirements text: {len(reloaded_session.requirements_text)} chars")
        print(f"✓ Notes: {len(reloaded_session.notes)} chars")
        print(f"✓ Generated policies: {len(reloaded_session.generated_policies)}")
        print(f"✓ Validation results: {len(reloaded_session.validation_results)}")
        
        assert reloaded_session.requirements_text == loaded_session.requirements_text
        assert reloaded_session.notes == loaded_session.notes
        assert len(reloaded_session.generated_policies) == 1
        assert len(reloaded_session.validation_results) == 1
        
        # Test 5: List sessions
        print("\n5. Testing session listing...")
        sessions = session_manager.list_sessions()
        print(f"✓ Found {len(sessions)} sessions")
        assert len(sessions) >= 1
        
        # Test 6: Search sessions
        print("\n6. Testing session search...")
        search_results = session_manager.search_sessions("Test")
        print(f"✓ Search found {len(search_results)} sessions")
        assert len(search_results) >= 1
        
        # Test 7: Get session metadata
        print("\n7. Testing session metadata...")
        metadata = session_manager.get_session_metadata(session.id)
        print(f"✓ Metadata - Name: {metadata.name}, Policies: {metadata.policy_count}")
        assert metadata.has_requirements == True
        assert metadata.has_policies == True
        assert metadata.policy_count == 1
        
        # Test 8: Get statistics
        print("\n8. Testing session statistics...")
        stats = session_manager.get_session_statistics()
        print(f"✓ Statistics - Total sessions: {stats['total_sessions']}")
        print(f"✓ Sessions with requirements: {stats['sessions_with_requirements']}")
        print(f"✓ Sessions with policies: {stats['sessions_with_policies']}")
        print(f"✓ Total policies: {stats['total_policies']}")
        
        # Test 9: Session existence check
        print("\n9. Testing session existence...")
        exists = session_manager.session_exists(session.id)
        print(f"✓ Session exists: {exists}")
        assert exists == True
        
        # Test 10: Delete session
        print("\n10. Testing session deletion...")
        deleted = session_manager.delete_session(session.id)
        print(f"✓ Session deleted: {deleted}")
        
        # Verify deletion
        exists_after_delete = session_manager.session_exists(session.id)
        print(f"✓ Session exists after deletion: {exists_after_delete}")
        assert exists_after_delete == False
        
        print("\n✅ All SessionManager tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_error_handling():
    """Test SessionManager error handling"""
    print("\nTesting SessionManager error handling...")
    
    storage = LocalStorageBackend("./test_sessions")
    session_manager = SessionManager(storage)
    
    try:
        # Test invalid session name
        try:
            session_manager.create_session("")
            assert False, "Should have raised SessionValidationError"
        except SessionValidationError:
            print("✓ Empty session name validation works")
        
        # Test loading non-existent session
        try:
            session_manager.load_session("non-existent-id")
            assert False, "Should have raised SessionNotFoundError"
        except SessionNotFoundError:
            print("✓ Non-existent session handling works")
        
        # Test invalid session ID
        try:
            session_manager.load_session("")
            assert False, "Should have raised SessionValidationError"
        except SessionValidationError:
            print("✓ Empty session ID validation works")
        
        print("✅ Error handling tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {str(e)}")
        return False


if __name__ == "__main__":
    print("SessionManager Test Suite")
    print("=" * 50)
    
    # Run tests
    basic_tests_passed = test_session_manager()
    error_tests_passed = test_error_handling()
    
    if basic_tests_passed and error_tests_passed:
        print("\n🎉 All tests passed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)