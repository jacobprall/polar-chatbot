"""
Abstract storage backend interface with S3-compatible methods
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from dataclasses import dataclass, field


# Storage Exceptions
class StorageError(Exception):
    """Base exception for storage operations"""
    pass


class StorageNotFoundError(StorageError):
    """Raised when a storage object is not found"""
    pass


class StoragePermissionError(StorageError):
    """Raised when storage operation lacks permissions"""
    pass


class StorageConnectionError(StorageError):
    """Raised when storage backend connection fails"""
    pass


class StorageConfigurationError(StorageError):
    """Raised when storage backend is misconfigured"""
    pass


class StorageQuotaExceededError(StorageError):
    """Raised when storage quota is exceeded"""
    pass


class StorageIntegrityError(StorageError):
    """Raised when storage data integrity check fails"""
    pass


@dataclass
class StorageObject:
    """Represents a storage object with comprehensive metadata"""
    key: str
    content: str
    content_type: str = "text/plain"
    size: int = 0
    last_modified: Optional[datetime] = None
    etag: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    version_id: Optional[str] = None
    
    def __post_init__(self):
        """Calculate size if not provided"""
        if self.size == 0:
            self.size = len(self.content.encode('utf-8'))
        if self.last_modified is None:
            self.last_modified = datetime.utcnow()


@dataclass
class StorageObjectInfo:
    """Lightweight object info for listing operations"""
    key: str
    size: int
    last_modified: datetime
    etag: Optional[str] = None
    content_type: str = "text/plain"
    version_id: Optional[str] = None
    is_delete_marker: bool = False


@dataclass
class StorageMultipartUpload:
    """Represents a multipart upload session"""
    upload_id: str
    key: str
    initiated: datetime
    parts: List[Dict[str, Any]] = field(default_factory=list)


class StorageBackend(ABC):
    """
    Abstract storage backend following S3-compatible patterns
    
    This interface provides a unified API for different storage backends
    (local filesystem, S3, etc.) with comprehensive error handling and
    metadata support.
    """
    
    @abstractmethod
    def get_object(self, key: str, version_id: Optional[str] = None) -> StorageObject:
        """
        Retrieve an object from storage
        
        Args:
            key: Object key/path
            version_id: Specific version to retrieve (if versioning supported)
            
        Returns:
            StorageObject with content and metadata
            
        Raises:
            StorageNotFoundError: If object doesn't exist
            StoragePermissionError: If access is denied
            StorageError: For other storage errors
        """
        pass
    
    @abstractmethod
    def put_object(self, key: str, content: str, content_type: str = "text/plain", 
                   metadata: Optional[Dict[str, str]] = None,
                   tags: Optional[Dict[str, str]] = None) -> bool:
        """
        Store an object in storage
        
        Args:
            key: Object key/path
            content: Object content
            content_type: MIME type of content
            metadata: Additional metadata key-value pairs
            tags: Object tags for categorization
            
        Returns:
            True if successful
            
        Raises:
            StoragePermissionError: If write access is denied
            StorageQuotaExceededError: If storage quota exceeded
            StorageError: If storage operation fails
        """
        pass
    
    @abstractmethod
    def list_objects(self, prefix: str = "", max_keys: int = 1000, 
                    continuation_token: Optional[str] = None) -> Dict[str, Any]:
        """
        List objects with optional prefix
        
        Args:
            prefix: Key prefix to filter by
            max_keys: Maximum number of objects to return
            continuation_token: Token for paginated results
            
        Returns:
            Dictionary containing:
            - 'objects': List of StorageObjectInfo objects
            - 'is_truncated': Boolean indicating if more results exist
            - 'next_continuation_token': Token for next page (if applicable)
            - 'common_prefixes': List of common prefixes (directories)
            
        Raises:
            StorageError: If listing operation fails
        """
        pass
    
    @abstractmethod
    def delete_object(self, key: str, version_id: Optional[str] = None) -> bool:
        """
        Delete an object from storage
        
        Args:
            key: Object key/path
            version_id: Specific version to delete (if versioning supported)
            
        Returns:
            True if successful or object didn't exist
            
        Raises:
            StoragePermissionError: If delete access is denied
            StorageError: If deletion fails
        """
        pass
    
    @abstractmethod
    def object_exists(self, key: str, version_id: Optional[str] = None) -> bool:
        """
        Check if an object exists
        
        Args:
            key: Object key/path
            version_id: Specific version to check (if versioning supported)
            
        Returns:
            True if object exists
            
        Raises:
            StorageError: If check operation fails
        """
        pass
    
    @abstractmethod
    def copy_object(self, source_key: str, dest_key: str, 
                   source_version_id: Optional[str] = None,
                   metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Copy an object within storage
        
        Args:
            source_key: Source object key
            dest_key: Destination object key
            source_version_id: Specific source version (if versioning supported)
            metadata: New metadata for destination object
            
        Returns:
            True if successful
            
        Raises:
            StorageNotFoundError: If source doesn't exist
            StoragePermissionError: If copy access is denied
            StorageError: If copy operation fails
        """
        pass
    
    @abstractmethod
    def get_object_metadata(self, key: str, version_id: Optional[str] = None) -> Dict[str, str]:
        """
        Get object metadata without downloading content
        
        Args:
            key: Object key/path
            version_id: Specific version (if versioning supported)
            
        Returns:
            Dictionary of metadata
            
        Raises:
            StorageNotFoundError: If object doesn't exist
            StorageError: If metadata retrieval fails
        """
        pass
    
    def get_presigned_url(self, key: str, expires_in: int = 3600, 
                         method: str = "GET") -> Optional[str]:
        """
        Generate a presigned URL for object access (optional for backends that support it)
        
        Args:
            key: Object key/path
            expires_in: URL expiration time in seconds
            method: HTTP method (GET, PUT, DELETE)
            
        Returns:
            Presigned URL or None if not supported
        """
        return None
    
    def batch_delete(self, keys: List[str]) -> Dict[str, bool]:
        """
        Delete multiple objects in batch
        
        Args:
            keys: List of object keys to delete
            
        Returns:
            Dictionary mapping keys to success status
        """
        results = {}
        for key in keys:
            try:
                results[key] = self.delete_object(key)
            except StorageError:
                results[key] = False
        return results
    
    def list_object_versions(self, key: str) -> List[StorageObjectInfo]:
        """
        List all versions of an object (if versioning supported)
        
        Args:
            key: Object key/path
            
        Returns:
            List of StorageObjectInfo for all versions
        """
        # Default implementation for backends without versioning
        if self.object_exists(key):
            obj = self.get_object(key)
            return [StorageObjectInfo(
                key=obj.key,
                size=obj.size,
                last_modified=obj.last_modified,
                etag=obj.etag,
                content_type=obj.content_type,
                version_id=obj.version_id
            )]
        return []
    
    def get_object_tags(self, key: str, version_id: Optional[str] = None) -> Dict[str, str]:
        """
        Get object tags
        
        Args:
            key: Object key/path
            version_id: Specific version (if versioning supported)
            
        Returns:
            Dictionary of tags
        """
        # Default implementation returns empty tags
        return {}
    
    def put_object_tags(self, key: str, tags: Dict[str, str], 
                       version_id: Optional[str] = None) -> bool:
        """
        Set object tags
        
        Args:
            key: Object key/path
            tags: Dictionary of tags to set
            version_id: Specific version (if versioning supported)
            
        Returns:
            True if successful
        """
        # Default implementation does nothing
        return True
    
    def create_multipart_upload(self, key: str, content_type: str = "text/plain",
                               metadata: Optional[Dict[str, str]] = None) -> str:
        """
        Initiate a multipart upload (for large objects)
        
        Args:
            key: Object key/path
            content_type: MIME type of content
            metadata: Additional metadata
            
        Returns:
            Upload ID for the multipart upload
            
        Raises:
            StorageError: If multipart upload not supported or fails
        """
        raise StorageError("Multipart upload not supported by this backend")
    
    def upload_part(self, key: str, upload_id: str, part_number: int, 
                   content: str) -> Dict[str, str]:
        """
        Upload a part in a multipart upload
        
        Args:
            key: Object key/path
            upload_id: Multipart upload ID
            part_number: Part number (1-based)
            content: Part content
            
        Returns:
            Dictionary with part info (ETag, etc.)
            
        Raises:
            StorageError: If multipart upload not supported or fails
        """
        raise StorageError("Multipart upload not supported by this backend")
    
    def complete_multipart_upload(self, key: str, upload_id: str, 
                                 parts: List[Dict[str, Any]]) -> bool:
        """
        Complete a multipart upload
        
        Args:
            key: Object key/path
            upload_id: Multipart upload ID
            parts: List of part info dictionaries
            
        Returns:
            True if successful
            
        Raises:
            StorageError: If multipart upload not supported or fails
        """
        raise StorageError("Multipart upload not supported by this backend")
    
    def abort_multipart_upload(self, key: str, upload_id: str) -> bool:
        """
        Abort a multipart upload
        
        Args:
            key: Object key/path
            upload_id: Multipart upload ID
            
        Returns:
            True if successful
        """
        # Default implementation does nothing
        return True
    
    def get_storage_info(self) -> Dict[str, Any]:
        """
        Get storage backend information and statistics
        
        Returns:
            Dictionary with backend info, capacity, usage, etc.
        """
        return {
            "backend_type": self.__class__.__name__,
            "supports_versioning": False,
            "supports_multipart": False,
            "supports_presigned_urls": False,
            "supports_tags": False
        }
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the storage backend
        
        Returns:
            Dictionary with health status and details
        """
        try:
            # Try a simple operation to verify connectivity
            test_key = "_health_check_test"
            self.put_object(test_key, "test", "text/plain")
            exists = self.object_exists(test_key)
            self.delete_object(test_key)
            
            return {
                "status": "healthy" if exists else "degraded",
                "timestamp": datetime.utcnow().isoformat(),
                "details": "Basic operations working" if exists else "Write/read test failed"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }