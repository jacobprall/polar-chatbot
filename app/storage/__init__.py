from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, BinaryIO
from pathlib import Path
from dataclasses import dataclass

@dataclass
class StorageObject:
    """Represents a storage object with metadata"""
    key: str
    content: str
    content_type: str = "text/plain"
    metadata: Optional[Dict[str, str]] = None

class StorageBackend(ABC):
    """Abstract storage backend following S3-like patterns"""
    
    @abstractmethod
    def get_object(self, key: str) -> Optional[StorageObject]:
        """Retrieve an object from storage"""
        pass
    
    @abstractmethod
    def put_object(self, key: str, content: str, content_type: str = "text/plain", 
                   metadata: Optional[Dict[str, str]] = None) -> bool:
        """Store an object in storage"""
        pass
    
    @abstractmethod
    def list_objects(self, prefix: str = "") -> List[str]:
        """List objects with optional prefix"""
        pass
    
    @abstractmethod
    def delete_object(self, key: str) -> bool:
        """Delete an object from storage"""
        pass
    
    @abstractmethod
    def object_exists(self, key: str) -> bool:
        """Check if an object exists"""
        pass