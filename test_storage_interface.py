#!/usr/bin/env python3
"""
Test script to verify storage interface implementations
"""

import tempfile
import os
import sys

# Add app directory to path
sys.path.insert(0, 'app')

from storage import LocalStorageBackend, StorageError

def test_local_storage():
    """Test LocalStorageBackend functionality"""
    print("Testing LocalStorageBackend...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalStorageBackend(temp_dir)
        
        # Test basic operations
        print("  Testing put_object...")
        success = storage.put_object('test.txt', 'Hello World', 'text/plain')
        assert success, "put_object failed"
        
        print("  Testing get_object...")
        obj = storage.get_object('test.txt')
        assert obj.content == 'Hello World', f"Expected 'Hello World', got '{obj.content}'"
        assert obj.size > 0, "Object size should be greater than 0"
        
        print("  Testing object_exists...")
        exists = storage.object_exists('test.txt')
        assert exists, "Object should exist"
        
        print("  Testing list_objects...")
        result = storage.list_objects()
        assert 'objects' in result, "Result should contain 'objects' key"
        assert len(result['objects']) == 1, f"Expected 1 object, got {len(result['objects'])}"
        
        print("  Testing session operations...")
        success = storage.create_session_directory('test_session')
        assert success, "create_session_directory failed"
        
        print("  Testing storage info...")
        info = storage.get_storage_info()
        assert 'backend_type' in info, "Storage info should contain backend_type"
        assert info['backend_type'] == 'LocalStorageBackend', "Backend type should be LocalStorageBackend"
        
        print("  Testing delete_object...")
        success = storage.delete_object('test.txt')
        assert success, "delete_object failed"
        
        exists = storage.object_exists('test.txt')
        assert not exists, "Object should not exist after deletion"
        
    print("LocalStorageBackend test passed!")

def test_storage_interface():
    """Test that storage interface is properly defined"""
    print("Testing storage interface...")
    
    from storage import StorageBackend, StorageObject, StorageObjectInfo
    from storage import StorageError, StorageNotFoundError, StoragePermissionError
    
    # Test that classes are properly imported
    assert StorageBackend is not None, "StorageBackend should be importable"
    assert StorageObject is not None, "StorageObject should be importable"
    assert StorageObjectInfo is not None, "StorageObjectInfo should be importable"
    
    # Test exception hierarchy
    assert issubclass(StorageNotFoundError, StorageError), "StorageNotFoundError should inherit from StorageError"
    assert issubclass(StoragePermissionError, StorageError), "StoragePermissionError should inherit from StorageError"
    
    print("Storage interface test passed!")

if __name__ == "__main__":
    try:
        test_storage_interface()
        test_local_storage()
        print("\nAll tests passed successfully! ✅")
    except Exception as e:
        print(f"\nTest failed: {e} ❌")
        sys.exit(1)