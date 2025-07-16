import os
from pathlib import Path
from typing import Optional, List, Dict
from abc import ABC
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
    pass

class LocalStorageBackend(StorageBackend):
    """Local filesystem implementation of storage backend"""
    
    def __init__(self, base_path: str = "./"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_full_path(self, key: str) -> Path:
        """Convert storage key to local file path"""
        return self.base_path / key
    
    def get_object(self, key: str) -> Optional[StorageObject]:
        """Retrieve an object from local filesystem"""
        try:
            file_path = self._get_full_path(key)
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Try to determine content type from file extension
            content_type = self._get_content_type(file_path.suffix)
            
            return StorageObject(
                key=key,
                content=content,
                content_type=content_type
            )
        except Exception as e:
            print(f"Error reading file {key}: {e}")
            return None
    
    def put_object(self, key: str, content: str, content_type: str = "text/plain", 
                   metadata: Optional[Dict[str, str]] = None) -> bool:
        """Store an object in local filesystem"""
        try:
            file_path = self._get_full_path(key)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"Error writing file {key}: {e}")
            return False
    
    def list_objects(self, prefix: str = "") -> List[str]:
        """List objects in local filesystem with optional prefix"""
        try:
            prefix_path = self._get_full_path(prefix)
            if not prefix_path.exists():
                return []
            
            objects = []
            for file_path in prefix_path.rglob("*"):
                if file_path.is_file():
                    # Convert back to storage key format
                    relative_path = file_path.relative_to(self.base_path)
                    objects.append(str(relative_path))
            
            return objects
        except Exception as e:
            print(f"Error listing objects with prefix {prefix}: {e}")
            return []
    
    def delete_object(self, key: str) -> bool:
        """Delete an object from local filesystem"""
        try:
            file_path = self._get_full_path(key)
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            print(f"Error deleting file {key}: {e}")
            return False
    
    def object_exists(self, key: str) -> bool:
        """Check if an object exists in local filesystem"""
        file_path = self._get_full_path(key)
        return file_path.exists() and file_path.is_file()
    
    def _get_content_type(self, extension: str) -> str:
        """Determine content type from file extension"""
        content_types = {
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.mdx': 'text/markdown',
            '.polar': 'text/plain',
            '.json': 'application/json',
            '.yaml': 'text/yaml',
            '.yml': 'text/yaml'
        }
        return content_types.get(extension.lower(), 'text/plain') 

