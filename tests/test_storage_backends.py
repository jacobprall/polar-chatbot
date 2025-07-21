"""
Unit tests for storage backend implementations.
"""

import pytest
import tempfile
import shutil
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.storage.base import (
    StorageBackend, StorageObject, StorageObjectInfo,
    StorageError, StorageNotFoundError, StoragePermissionError,
    StorageConnectionError, StorageConfigurationError
)
from app.storage.local_storage import LocalStorageBackend
from app.storage.s3_storage import S3StorageBackend


class TestLocalStorageBackend:
    """Test cases for LocalStorageBackend."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def storage(self, temp_dir):
        """Create a LocalStorageBackend instance for testing."""
        return LocalStorageBackend(temp_dir)
    
    def test_init_creates_directory(self, temp_dir):
        """Test that initialization creates the base directory."""
        # Remove the directory first
        shutil.rmtree(temp_dir)
        assert not Path(temp_dir).exists()
        
        # Initialize storage
        storage = LocalStorageBackend(temp_dir)
        assert Path(temp_dir).exists()
        assert storage.base_path == Path(temp_dir)
    
    def test_init_permission_error(self):
        """Test initialization with permission error."""
        with patch('pathlib.Path.mkdir', side_effect=PermissionError("Access denied")):
            with pytest.raises(StoragePermissionError):
                LocalStorageBackend("/invalid/path")
    
    def test_put_and_get_object(self, storage):
        """Test basic put and get operations."""
        key = "test/file.txt"
        content = "Hello, World!"
        content_type = "text/plain"
        metadata = {"author": "test", "version": "1.0"}
        
        # Put object
        result = storage.put_object(key, content, content_type, metadata)
        assert result is True
        
        # Get object
        obj = storage.get_object(key)
        assert obj.key == key
        assert obj.content == content
        assert obj.content_type == content_type
        assert obj.size == len(content.encode('utf-8'))
        assert obj.metadata == metadata
        assert obj.last_modified is not None
        assert obj.etag is not None
    
    def test_get_nonexistent_object(self, storage):
        """Test getting non-existent object."""
        with pytest.raises(StorageNotFoundError):
            storage.get_object("nonexistent/file.txt")
    
    def test_object_exists(self, storage):
        """Test object existence checking."""
        key = "test/exists.txt"
        
        # Object doesn't exist initially
        assert not storage.object_exists(key)
        
        # Create object
        storage.put_object(key, "content")
        assert storage.object_exists(key)
        
        # Delete object
        storage.delete_object(key)
        assert not storage.object_exists(key)
    
    def test_delete_object(self, storage):
        """Test object deletion."""
        key = "test/delete.txt"
        
        # Create object
        storage.put_object(key, "content", metadata={"test": "value"})
        assert storage.object_exists(key)
        
        # Delete object
        result = storage.delete_object(key)
        assert result is True
        assert not storage.object_exists(key)
        
        # Delete non-existent object (should be idempotent)
        result = storage.delete_object("nonexistent.txt")
        assert result is True
    
    def test_list_objects_empty(self, storage):
        """Test listing objects when none exist."""
        result = storage.list_objects()
        assert result['objects'] == []
        assert result['is_truncated'] is False
        assert result['next_continuation_token'] is None
    
    def test_list_objects_with_content(self, storage):
        """Test listing objects with existing content."""
        # Create multiple objects
        objects = [
            ("file1.txt", "content1"),
            ("dir/file2.txt", "content2"),
            ("dir/subdir/file3.txt", "content3"),
            ("other.json", "{}"),
        ]
        
        for key, content in objects:
            storage.put_object(key, content)
        
        # List all objects
        result = storage.list_objects()
        assert len(result['objects']) == 4
        
        # Verify object info
        keys = [obj.key for obj in result['objects']]
        assert "file1.txt" in keys
        assert "dir/file2.txt" in keys
        assert "dir/subdir/file3.txt" in keys
        assert "other.json" in keys
    
    def test_list_objects_with_prefix(self, storage):
        """Test listing objects with prefix filter."""
        # Create objects with different prefixes
        storage.put_object("prefix1/file1.txt", "content1")
        storage.put_object("prefix1/file2.txt", "content2")
        storage.put_object("prefix2/file3.txt", "content3")
        storage.put_object("other.txt", "content4")
        
        # List with prefix
        result = storage.list_objects(prefix="prefix1/")
        assert len(result['objects']) == 2
        keys = [obj.key for obj in result['objects']]
        assert "prefix1/file1.txt" in keys
        assert "prefix1/file2.txt" in keys
    
    def test_list_objects_with_max_keys(self, storage):
        """Test listing objects with max_keys limit."""
        # Create multiple objects
        for i in range(5):
            storage.put_object(f"file{i}.txt", f"content{i}")
        
        # List with limit
        result = storage.list_objects(max_keys=3)
        assert len(result['objects']) == 3
        assert result['is_truncated'] is True
    
    def test_copy_object(self, storage):
        """Test object copying."""
        source_key = "source.txt"
        dest_key = "destination.txt"
        content = "Original content"
        metadata = {"original": "true"}
        
        # Create source object
        storage.put_object(source_key, content, metadata=metadata)
        
        # Copy object
        result = storage.copy_object(source_key, dest_key)
        assert result is True
        
        # Verify destination exists and has same content
        dest_obj = storage.get_object(dest_key)
        assert dest_obj.content == content
        assert dest_obj.metadata == metadata
        
        # Verify source still exists
        assert storage.object_exists(source_key)
    
    def test_copy_nonexistent_object(self, storage):
        """Test copying non-existent object."""
        with pytest.raises(StorageNotFoundError):
            storage.copy_object("nonexistent.txt", "destination.txt")
    
    def test_get_object_metadata(self, storage):
        """Test getting object metadata."""
        key = "test.txt"
        metadata = {"author": "test", "version": "2.0"}
        
        storage.put_object(key, "content", metadata=metadata)
        
        retrieved_metadata = storage.get_object_metadata(key)
        assert retrieved_metadata == metadata
    
    def test_get_metadata_nonexistent_object(self, storage):
        """Test getting metadata for non-existent object."""
        with pytest.raises(StorageNotFoundError):
            storage.get_object_metadata("nonexistent.txt")
    
    def test_content_type_detection(self, storage):
        """Test content type detection from file extensions."""
        test_cases = [
            ("file.txt", "text/plain"),
            ("file.md", "text/markdown"),
            ("file.json", "application/json"),
            ("file.yaml", "text/yaml"),
            ("file.polar", "text/plain"),
            ("file.unknown", "text/plain"),  # Default
        ]
        
        for key, expected_type in test_cases:
            storage.put_object(key, "content")
            obj = storage.get_object(key)
            assert obj.content_type == expected_type
    
    def test_get_storage_info(self, storage):
        """Test getting storage information."""
        # Create some test files
        storage.put_object("file1.txt", "content1")
        storage.put_object("file2.txt", "longer content here")
        
        info = storage.get_storage_info()
        
        assert info["backend_type"] == "LocalStorageBackend"
        assert "base_path" in info
        assert info["supports_versioning"] is False
        assert info["supports_multipart"] is False
        assert info["total_size_bytes"] > 0
        assert info["file_count"] == 2
    
    def test_health_check(self, storage):
        """Test storage health check."""
        health = storage.health_check()
        
        assert health["status"] == "healthy"
        assert "timestamp" in health
        assert "details" in health
    
    def test_health_check_failure(self, storage):
        """Test health check with storage failure."""
        with patch.object(storage, 'put_object', side_effect=StorageError("Disk full")):
            health = storage.health_check()
            
            assert health["status"] == "unhealthy"
            assert "error" in health
    
    def test_batch_delete(self, storage):
        """Test batch deletion of objects."""
        # Create multiple objects
        keys = ["file1.txt", "file2.txt", "file3.txt", "nonexistent.txt"]
        for key in keys[:3]:  # Create first 3, leave last one non-existent
            storage.put_object(key, "content")
        
        # Batch delete
        results = storage.batch_delete(keys)
        
        assert len(results) == 4
        assert results["file1.txt"] is True
        assert results["file2.txt"] is True
        assert results["file3.txt"] is True
        assert results["nonexistent.txt"] is True  # Idempotent
        
        # Verify objects are deleted
        for key in keys[:3]:
            assert not storage.object_exists(key)
    
    def test_session_specific_operations(self, storage):
        """Test session-specific storage operations."""
        session_id = "test-session-123"
        
        # Create session directory
        result = storage.create_session_directory(session_id)
        assert result is True
        
        # Verify directory structure
        session_path = storage.base_path / "sessions" / session_id
        assert session_path.exists()
        assert (session_path / "policies").exists()
        assert (session_path / "validation_results").exists()
        
        # Get session statistics
        stats = storage.get_session_statistics(session_id)
        assert stats["session_id"] == session_id
        assert stats["file_count"] == 0
        assert stats["total_size_bytes"] == 0
    
    def test_session_statistics_not_found(self, storage):
        """Test getting statistics for non-existent session."""
        with pytest.raises(StorageNotFoundError):
            storage.get_session_statistics("nonexistent-session")
    
    def test_cleanup_empty_sessions(self, storage):
        """Test cleanup of empty sessions."""
        # Create sessions with different content levels
        session1 = "session-empty"
        session2 = "session-with-metadata"
        session3 = "session-with-content"
        
        # Empty session
        storage.create_session_directory(session1)
        
        # Session with only metadata
        storage.create_session_directory(session2)
        storage.put_object(f"sessions/{session2}/metadata.json", "{}")
        
        # Session with actual content
        storage.create_session_directory(session3)
        storage.put_object(f"sessions/{session3}/metadata.json", "{}")
        storage.put_object(f"sessions/{session3}/requirements.txt", "content")
        
        # Cleanup empty sessions
        cleaned_count = storage.cleanup_empty_sessions()
        
        # Should clean up session1 and session2, but not session3
        assert cleaned_count == 2
        assert not (storage.base_path / "sessions" / session1).exists()
        assert not (storage.base_path / "sessions" / session2).exists()
        assert (storage.base_path / "sessions" / session3).exists()
    
    def test_backup_and_restore_session(self, storage, temp_dir):
        """Test session backup and restore functionality."""
        session_id = "backup-test-session"
        backup_path = Path(temp_dir) / "backups"
        backup_path.mkdir()
        
        # Create session with content
        storage.create_session_directory(session_id)
        storage.put_object(f"sessions/{session_id}/requirements.txt", "Test requirements")
        storage.put_object(f"sessions/{session_id}/policies/policy1.polar", "allow(user, \"read\", resource);")
        
        # Backup session
        result = storage.backup_session(session_id, str(backup_path))
        assert result is True
        
        # Verify backup exists
        backup_dir = backup_path / f"session_{session_id}_backup"
        assert backup_dir.exists()
        assert (backup_dir / "requirements.txt").exists()
        assert (backup_dir / "policies" / "policy1.polar").exists()
        
        # Delete original session
        storage.delete_object(f"sessions/{session_id}/requirements.txt")
        storage.delete_object(f"sessions/{session_id}/policies/policy1.polar")
        
        # Restore session
        result = storage.restore_session(session_id, str(backup_path))
        assert result is True
        
        # Verify restoration
        assert storage.object_exists(f"sessions/{session_id}/requirements.txt")
        assert storage.object_exists(f"sessions/{session_id}/policies/policy1.polar")
    
    def test_validate_session_integrity(self, storage):
        """Test session integrity validation."""
        session_id = "integrity-test-session"
        
        # Create valid session
        storage.create_session_directory(session_id)
        storage.put_object(f"sessions/{session_id}/metadata.json", "{}")
        storage.put_object(f"sessions/{session_id}/requirements.txt", "Valid content")
        
        # Validate integrity
        integrity = storage.validate_session_integrity(session_id)
        
        assert integrity["session_id"] == session_id
        assert integrity["is_valid"] is True
        assert integrity["file_count"] == 2
        assert len(integrity["issues"]) == 0
    
    def test_validate_session_integrity_missing_metadata(self, storage):
        """Test session integrity validation with missing metadata."""
        session_id = "invalid-session"
        
        # Create session without metadata
        storage.create_session_directory(session_id)
        storage.put_object(f"sessions/{session_id}/requirements.txt", "Content")
        
        # Validate integrity
        integrity = storage.validate_session_integrity(session_id)
        
        assert integrity["is_valid"] is False
        assert any("Missing metadata.json" in issue for issue in integrity["issues"])
    
    def test_error_handling_permission_denied(self, storage):
        """Test error handling for permission denied scenarios."""
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with pytest.raises(StoragePermissionError):
                storage.put_object("test.txt", "content")
            
            with pytest.raises(StoragePermissionError):
                storage.get_object("test.txt")


class TestS3StorageBackend:
    """Test cases for S3StorageBackend."""
    
    @pytest.fixture
    def mock_s3_client(self):
        """Create a mock S3 client."""
        with patch('boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            yield mock_client
    
    @pytest.fixture
    def s3_storage(self, mock_s3_client):
        """Create an S3StorageBackend instance for testing."""
        return S3StorageBackend(
            bucket_name="test-bucket",
            region="us-east-1",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret"
        )
    
    def test_init_with_credentials(self, mock_s3_client):
        """Test S3 storage initialization with explicit credentials."""
        storage = S3StorageBackend(
            bucket_name="test-bucket",
            region="us-west-2",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret"
        )
        
        assert storage.bucket_name == "test-bucket"
        assert storage.region == "us-west-2"
    
    def test_init_with_profile(self, mock_s3_client):
        """Test S3 storage initialization with AWS profile."""
        storage = S3StorageBackend(
            bucket_name="test-bucket",
            aws_profile="test-profile"
        )
        
        assert storage.bucket_name == "test-bucket"
    
    def test_put_object_success(self, s3_storage, mock_s3_client):
        """Test successful object upload to S3."""
        mock_s3_client.put_object.return_value = {"ETag": "test-etag"}
        
        result = s3_storage.put_object(
            "test/file.txt", 
            "content", 
            "text/plain",
            {"author": "test"}
        )
        
        assert result is True
        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args
        assert call_args[1]["Bucket"] == "test-bucket"
        assert call_args[1]["Key"] == "test/file.txt"
        assert call_args[1]["Body"] == "content"
        assert call_args[1]["ContentType"] == "text/plain"
        assert call_args[1]["Metadata"] == {"author": "test"}
    
    def test_put_object_client_error(self, s3_storage, mock_s3_client):
        """Test S3 put_object with client error."""
        from botocore.exceptions import ClientError
        
        mock_s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "PutObject"
        )
        
        with pytest.raises(StoragePermissionError):
            s3_storage.put_object("test.txt", "content")
    
    def test_get_object_success(self, s3_storage, mock_s3_client):
        """Test successful object retrieval from S3."""
        mock_response = {
            "Body": Mock(),
            "ContentType": "text/plain",
            "ContentLength": 7,
            "LastModified": datetime.utcnow(),
            "ETag": "test-etag",
            "Metadata": {"author": "test"}
        }
        mock_response["Body"].read.return_value = b"content"
        mock_s3_client.get_object.return_value = mock_response
        
        obj = s3_storage.get_object("test/file.txt")
        
        assert obj.key == "test/file.txt"
        assert obj.content == "content"
        assert obj.content_type == "text/plain"
        assert obj.size == 7
        assert obj.metadata == {"author": "test"}
        assert obj.etag == "test-etag"
    
    def test_get_object_not_found(self, s3_storage, mock_s3_client):
        """Test getting non-existent object from S3."""
        from botocore.exceptions import ClientError
        
        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "GetObject"
        )
        
        with pytest.raises(StorageNotFoundError):
            s3_storage.get_object("nonexistent.txt")
    
    def test_object_exists_true(self, s3_storage, mock_s3_client):
        """Test object existence check when object exists."""
        mock_s3_client.head_object.return_value = {"ContentLength": 100}
        
        result = s3_storage.object_exists("existing.txt")
        assert result is True
    
    def test_object_exists_false(self, s3_storage, mock_s3_client):
        """Test object existence check when object doesn't exist."""
        from botocore.exceptions import ClientError
        
        mock_s3_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "HeadObject"
        )
        
        result = s3_storage.object_exists("nonexistent.txt")
        assert result is False
    
    def test_delete_object_success(self, s3_storage, mock_s3_client):
        """Test successful object deletion from S3."""
        mock_s3_client.delete_object.return_value = {}
        
        result = s3_storage.delete_object("test.txt")
        assert result is True
        
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="test.txt"
        )
    
    def test_list_objects_success(self, s3_storage, mock_s3_client):
        """Test successful object listing from S3."""
        mock_response = {
            "Contents": [
                {
                    "Key": "file1.txt",
                    "Size": 100,
                    "LastModified": datetime.utcnow(),
                    "ETag": "etag1"
                },
                {
                    "Key": "file2.txt", 
                    "Size": 200,
                    "LastModified": datetime.utcnow(),
                    "ETag": "etag2"
                }
            ],
            "IsTruncated": False
        }
        mock_s3_client.list_objects_v2.return_value = mock_response
        
        result = s3_storage.list_objects()
        
        assert len(result["objects"]) == 2
        assert result["is_truncated"] is False
        assert result["objects"][0].key == "file1.txt"
        assert result["objects"][0].size == 100
        assert result["objects"][1].key == "file2.txt"
        assert result["objects"][1].size == 200
    
    def test_list_objects_with_prefix(self, s3_storage, mock_s3_client):
        """Test object listing with prefix."""
        mock_s3_client.list_objects_v2.return_value = {"Contents": []}
        
        s3_storage.list_objects(prefix="test/")
        
        mock_s3_client.list_objects_v2.assert_called_once()
        call_args = mock_s3_client.list_objects_v2.call_args[1]
        assert call_args["Prefix"] == "test/"
    
    def test_copy_object_success(self, s3_storage, mock_s3_client):
        """Test successful object copying in S3."""
        mock_s3_client.copy_object.return_value = {}
        
        result = s3_storage.copy_object("source.txt", "dest.txt")
        assert result is True
        
        mock_s3_client.copy_object.assert_called_once()
        call_args = mock_s3_client.copy_object.call_args[1]
        assert call_args["Bucket"] == "test-bucket"
        assert call_args["Key"] == "dest.txt"
        assert call_args["CopySource"]["Bucket"] == "test-bucket"
        assert call_args["CopySource"]["Key"] == "source.txt"
    
    def test_get_object_metadata_success(self, s3_storage, mock_s3_client):
        """Test getting object metadata from S3."""
        mock_response = {
            "Metadata": {"author": "test", "version": "1.0"}
        }
        mock_s3_client.head_object.return_value = mock_response
        
        metadata = s3_storage.get_object_metadata("test.txt")
        assert metadata == {"author": "test", "version": "1.0"}
    
    def test_get_presigned_url(self, s3_storage, mock_s3_client):
        """Test generating presigned URL."""
        mock_s3_client.generate_presigned_url.return_value = "https://presigned-url"
        
        url = s3_storage.get_presigned_url("test.txt", expires_in=3600)
        assert url == "https://presigned-url"
        
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "test.txt"},
            ExpiresIn=3600
        )
    
    def test_batch_delete_success(self, s3_storage, mock_s3_client):
        """Test batch deletion in S3."""
        mock_s3_client.delete_objects.return_value = {
            "Deleted": [
                {"Key": "file1.txt"},
                {"Key": "file2.txt"}
            ],
            "Errors": []
        }
        
        keys = ["file1.txt", "file2.txt", "file3.txt"]
        results = s3_storage.batch_delete(keys)
        
        # Should use S3 batch delete for efficiency
        mock_s3_client.delete_objects.assert_called_once()
        
        # All should be marked as successful
        assert all(results[key] for key in keys)
    
    def test_get_storage_info(self, s3_storage):
        """Test getting S3 storage information."""
        info = s3_storage.get_storage_info()
        
        assert info["backend_type"] == "S3StorageBackend"
        assert info["bucket_name"] == "test-bucket"
        assert info["region"] == "us-east-1"
        assert info["supports_versioning"] is True
        assert info["supports_multipart"] is True
        assert info["supports_presigned_urls"] is True
    
    def test_health_check_success(self, s3_storage, mock_s3_client):
        """Test S3 health check success."""
        mock_s3_client.head_bucket.return_value = {}
        
        health = s3_storage.health_check()
        
        assert health["status"] == "healthy"
        assert "timestamp" in health
    
    def test_health_check_failure(self, s3_storage, mock_s3_client):
        """Test S3 health check failure."""
        from botocore.exceptions import ClientError
        
        mock_s3_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
            "HeadBucket"
        )
        
        health = s3_storage.health_check()
        
        assert health["status"] == "unhealthy"
        assert "error" in health
    
    def test_connection_error_handling(self, s3_storage, mock_s3_client):
        """Test handling of connection errors."""
        from botocore.exceptions import EndpointConnectionError
        
        mock_s3_client.put_object.side_effect = EndpointConnectionError(
            endpoint_url="https://s3.amazonaws.com"
        )
        
        with pytest.raises(StorageConnectionError):
            s3_storage.put_object("test.txt", "content")
    
    def test_configuration_error_handling(self, mock_s3_client):
        """Test handling of configuration errors."""
        from botocore.exceptions import NoCredentialsError
        
        mock_s3_client.side_effect = NoCredentialsError()
        
        with pytest.raises(StorageConfigurationError):
            S3StorageBackend(bucket_name="test-bucket")


class TestStorageBackendInterface:
    """Test the abstract StorageBackend interface."""
    
    def test_abstract_methods_not_implemented(self):
        """Test that abstract methods raise NotImplementedError."""
        # Can't instantiate abstract class directly
        with pytest.raises(TypeError):
            StorageBackend()
    
    def test_default_implementations(self):
        """Test default implementations of optional methods."""
        # Create a minimal concrete implementation
        class TestBackend(StorageBackend):
            def get_object(self, key, version_id=None):
                return StorageObject(key=key, content="test")
            
            def put_object(self, key, content, content_type="text/plain", metadata=None, tags=None):
                return True
            
            def list_objects(self, prefix="", max_keys=1000, continuation_token=None):
                return {"objects": [], "is_truncated": False, "next_continuation_token": None, "common_prefixes": []}
            
            def delete_object(self, key, version_id=None):
                return True
            
            def object_exists(self, key, version_id=None):
                return True
            
            def copy_object(self, source_key, dest_key, source_version_id=None, metadata=None):
                return True
            
            def get_object_metadata(self, key, version_id=None):
                return {}
        
        backend = TestBackend()
        
        # Test default implementations
        assert backend.get_presigned_url("test.txt") is None
        assert backend.list_object_versions("test.txt") == []
        assert backend.get_object_tags("test.txt") == {}
        assert backend.put_object_tags("test.txt", {}) is True
        
        # Test multipart upload defaults (should raise errors)
        with pytest.raises(StorageError):
            backend.create_multipart_upload("test.txt")
        
        with pytest.raises(StorageError):
            backend.upload_part("test.txt", "upload-id", 1, "content")
        
        with pytest.raises(StorageError):
            backend.complete_multipart_upload("test.txt", "upload-id", [])
        
        # Test abort multipart (should not raise)
        assert backend.abort_multipart_upload("test.txt", "upload-id") is True
        
        # Test storage info
        info = backend.get_storage_info()
        assert info["backend_type"] == "TestBackend"
        assert info["supports_versioning"] is False


if __name__ == "__main__":
    pytest.main([__file__])