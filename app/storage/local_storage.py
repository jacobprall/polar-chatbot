import os
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from .base import (
    StorageBackend, StorageObject, StorageObjectInfo,
    StorageError, StorageNotFoundError, StoragePermissionError
)

class LocalStorageBackend(StorageBackend):
    """Local filesystem implementation of storage backend"""
    
    def __init__(self, base_path: str = "./"):
        self.base_path = Path(base_path)
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise StoragePermissionError(f"Cannot create storage directory {base_path}: {e}")
        except Exception as e:
            raise StorageError(f"Failed to initialize storage at {base_path}: {e}")
    
    def _get_full_path(self, key: str) -> Path:
        """Convert storage key to local file path"""
        # Normalize the key to prevent path traversal
        normalized_key = str(Path(key)).replace('..', '')
        return self.base_path / normalized_key
    
    def _get_file_stats(self, file_path: Path) -> tuple:
        """Get file statistics"""
        stat = file_path.stat()
        size = stat.st_size
        last_modified = datetime.fromtimestamp(stat.st_mtime)
        # Generate simple etag from file size and mtime
        etag = hashlib.md5(f"{size}:{stat.st_mtime}".encode()).hexdigest()
        return size, last_modified, etag
    
    def get_object(self, key: str, version_id: Optional[str] = None) -> StorageObject:
        """Retrieve an object from local filesystem"""
        try:
            file_path = self._get_full_path(key)
            if not file_path.exists():
                raise StorageNotFoundError(f"Object not found: {key}")
            
            if not file_path.is_file():
                raise StorageError(f"Path is not a file: {key}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            size, last_modified, etag = self._get_file_stats(file_path)
            content_type = self._get_content_type(file_path.suffix)
            
            # Load metadata from companion file if it exists
            metadata = self._load_metadata(key)
            
            return StorageObject(
                key=key,
                content=content,
                content_type=content_type,
                size=size,
                last_modified=last_modified,
                etag=etag,
                metadata=metadata
            )
        except StorageNotFoundError:
            raise
        except PermissionError as e:
            raise StoragePermissionError(f"Permission denied reading {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error reading file {key}: {e}")
    
    def put_object(self, key: str, content: str, content_type: str = "text/plain", 
                   metadata: Optional[Dict[str, str]] = None,
                   tags: Optional[Dict[str, str]] = None) -> bool:
        """Store an object in local filesystem"""
        try:
            file_path = self._get_full_path(key)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Store metadata if provided
            if metadata:
                self._save_metadata(key, metadata)
            
            return True
        except PermissionError as e:
            raise StoragePermissionError(f"Permission denied writing {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error writing file {key}: {e}")
    
    def list_objects(self, prefix: str = "", max_keys: int = 1000, 
                    continuation_token: Optional[str] = None) -> Dict[str, Any]:
        """List objects in local filesystem with optional prefix"""
        try:
            if prefix:
                prefix_path = self._get_full_path(prefix)
                if prefix_path.is_file():
                    # If prefix points to a file, return just that file
                    search_path = prefix_path.parent
                    pattern = prefix_path.name + "*"
                else:
                    search_path = prefix_path
                    pattern = "**/*"  # Use recursive pattern for directories
            else:
                search_path = self.base_path
                pattern = "**/*"
            
            if not search_path.exists():
                return {
                    'objects': [],
                    'is_truncated': False,
                    'next_continuation_token': None,
                    'common_prefixes': []
                }
            
            objects = []
            count = 0
            
            for file_path in search_path.glob(pattern):
                if count >= max_keys:
                    break
                    
                if file_path.is_file() and not file_path.name.endswith('.metadata'):
                    try:
                        # Convert back to storage key format
                        relative_path = file_path.relative_to(self.base_path)
                        key = str(relative_path).replace('\\', '/')  # Normalize path separators
                        
                        # Skip if doesn't match prefix
                        if prefix and not key.startswith(prefix):
                            continue
                        
                        size, last_modified, etag = self._get_file_stats(file_path)
                        content_type = self._get_content_type(file_path.suffix)
                        
                        objects.append(StorageObjectInfo(
                            key=key,
                            size=size,
                            last_modified=last_modified,
                            etag=etag,
                            content_type=content_type
                        ))
                        count += 1
                    except Exception:
                        # Skip files that can't be processed
                        continue
            
            return {
                'objects': objects,
                'is_truncated': count >= max_keys,
                'next_continuation_token': None,  # Local storage doesn't support pagination
                'common_prefixes': []  # Could be enhanced to return directory prefixes
            }
        except Exception as e:
            raise StorageError(f"Error listing objects with prefix {prefix}: {e}")
    
    def delete_object(self, key: str, version_id: Optional[str] = None) -> bool:
        """Delete an object from local filesystem"""
        try:
            file_path = self._get_full_path(key)
            if file_path.exists():
                file_path.unlink()
                # Also delete metadata file if it exists
                self._delete_metadata(key)
                return True
            return True  # Return True even if file doesn't exist (idempotent)
        except PermissionError as e:
            raise StoragePermissionError(f"Permission denied deleting {key}: {e}")
        except Exception as e:
            raise StorageError(f"Error deleting file {key}: {e}")
    
    def object_exists(self, key: str, version_id: Optional[str] = None) -> bool:
        """Check if an object exists in local filesystem"""
        try:
            file_path = self._get_full_path(key)
            return file_path.exists() and file_path.is_file()
        except Exception as e:
            raise StorageError(f"Error checking existence of {key}: {e}")
    
    def copy_object(self, source_key: str, dest_key: str, 
                   source_version_id: Optional[str] = None,
                   metadata: Optional[Dict[str, str]] = None) -> bool:
        """Copy an object within local storage"""
        try:
            source_path = self._get_full_path(source_key)
            if not source_path.exists():
                raise StorageNotFoundError(f"Source object not found: {source_key}")
            
            dest_path = self._get_full_path(dest_key)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file content
            with open(source_path, 'r', encoding='utf-8') as src:
                content = src.read()
            
            with open(dest_path, 'w', encoding='utf-8') as dst:
                dst.write(content)
            
            # Copy metadata if it exists
            source_metadata = self._load_metadata(source_key)
            if source_metadata:
                self._save_metadata(dest_key, source_metadata)
            
            return True
        except StorageNotFoundError:
            raise
        except PermissionError as e:
            raise StoragePermissionError(f"Permission denied copying {source_key} to {dest_key}: {e}")
        except Exception as e:
            raise StorageError(f"Error copying {source_key} to {dest_key}: {e}")
    
    def get_object_metadata(self, key: str, version_id: Optional[str] = None) -> Dict[str, str]:
        """Get object metadata without downloading content"""
        try:
            file_path = self._get_full_path(key)
            if not file_path.exists():
                raise StorageNotFoundError(f"Object not found: {key}")
            
            return self._load_metadata(key)
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Error getting metadata for {key}: {e}")
    
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
    
    def _get_metadata_path(self, key: str) -> Path:
        """Get path for metadata file"""
        file_path = self._get_full_path(key)
        return file_path.with_suffix(file_path.suffix + '.metadata')
    
    def _load_metadata(self, key: str) -> Dict[str, str]:
        """Load metadata from companion file"""
        metadata_path = self._get_metadata_path(key)
        if not metadata_path.exists():
            return {}
        
        try:
            import json
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_metadata(self, key: str, metadata: Dict[str, str]) -> None:
        """Save metadata to companion file"""
        if not metadata:
            return
        
        metadata_path = self._get_metadata_path(key)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            import json
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
        except Exception:
            pass  # Metadata is optional, don't fail the main operation
    
    def _delete_metadata(self, key: str) -> None:
        """Delete metadata file if it exists"""
        metadata_path = self._get_metadata_path(key)
        if metadata_path.exists():
            try:
                metadata_path.unlink()
            except Exception:
                pass  # Metadata cleanup is optional 

    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage backend information and statistics"""
        try:
            total_size = 0
            file_count = 0
            
            for file_path in self.base_path.rglob('*'):
                if file_path.is_file() and not file_path.name.endswith('.metadata'):
                    total_size += file_path.stat().st_size
                    file_count += 1
            
            return {
                "backend_type": "LocalStorageBackend",
                "base_path": str(self.base_path),
                "supports_versioning": False,
                "supports_multipart": False,
                "supports_presigned_urls": False,
                "supports_tags": False,
                "total_size_bytes": total_size,
                "file_count": file_count,
                "available_space": self._get_available_space()
            }
        except Exception as e:
            return {
                "backend_type": "LocalStorageBackend",
                "base_path": str(self.base_path),
                "error": str(e)
            }
    
    def _get_available_space(self) -> Optional[int]:
        """Get available disk space"""
        try:
            import shutil
            return shutil.disk_usage(self.base_path).free
        except Exception:
            return None
    
    # Session-specific operations
    def create_session_directory(self, session_id: str) -> bool:
        """Create a directory structure for a session"""
        try:
            session_path = self.base_path / "sessions" / session_id
            session_path.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories for organized storage
            (session_path / "policies").mkdir(exist_ok=True)
            (session_path / "validation_results").mkdir(exist_ok=True)
            
            return True
        except Exception as e:
            raise StorageError(f"Failed to create session directory for {session_id}: {e}")
    
    def cleanup_empty_sessions(self) -> int:
        """Remove sessions that only have metadata (no content files)"""
        try:
            sessions_path = self.base_path / "sessions"
            if not sessions_path.exists():
                return 0
            
            cleaned_count = 0
            for session_dir in sessions_path.iterdir():
                if session_dir.is_dir():
                    files = list(session_dir.rglob('*'))
                    # Filter out directories and metadata files
                    content_files = [f for f in files if f.is_file() and not f.name.endswith('.metadata')]
                    
                    # If only metadata.json exists or no files at all, consider it empty
                    if len(content_files) <= 1 and (not content_files or content_files[0].name == "metadata.json"):
                        import shutil
                        shutil.rmtree(session_dir)
                        cleaned_count += 1
            
            return cleaned_count
        except Exception as e:
            raise StorageError(f"Failed to cleanup empty sessions: {e}")
    
    def get_session_statistics(self, session_id: str) -> Dict[str, Any]:
        """Get statistics for a specific session"""
        try:
            session_path = self.base_path / "sessions" / session_id
            if not session_path.exists():
                raise StorageNotFoundError(f"Session directory not found: {session_id}")
            
            total_size = 0
            file_count = 0
            file_types = {}
            
            for file_path in session_path.rglob('*'):
                if file_path.is_file() and not file_path.name.endswith('.metadata'):
                    size = file_path.stat().st_size
                    total_size += size
                    file_count += 1
                    
                    # Track file types
                    ext = file_path.suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1
            
            return {
                "session_id": session_id,
                "total_size_bytes": total_size,
                "file_count": file_count,
                "file_types": file_types,
                "last_modified": self._get_session_last_modified(session_id)
            }
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get session statistics for {session_id}: {e}")
    
    def _get_session_last_modified(self, session_id: str) -> Optional[datetime]:
        """Get the last modified time for any file in the session"""
        try:
            session_path = self.base_path / "sessions" / session_id
            if not session_path.exists():
                return None
            
            latest_time = None
            for file_path in session_path.rglob('*'):
                if file_path.is_file():
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if latest_time is None or mtime > latest_time:
                        latest_time = mtime
            
            return latest_time
        except Exception:
            return None
    
    def backup_session(self, session_id: str, backup_path: str) -> bool:
        """Create a backup of a session to a specified path"""
        try:
            import shutil
            session_path = self.base_path / "sessions" / session_id
            if not session_path.exists():
                raise StorageNotFoundError(f"Session not found: {session_id}")
            
            backup_dest = Path(backup_path) / f"session_{session_id}_backup"
            shutil.copytree(session_path, backup_dest, dirs_exist_ok=True)
            return True
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to backup session {session_id}: {e}")
    
    def restore_session(self, session_id: str, backup_path: str) -> bool:
        """Restore a session from a backup"""
        try:
            import shutil
            backup_source = Path(backup_path) / f"session_{session_id}_backup"
            if not backup_source.exists():
                raise StorageNotFoundError(f"Backup not found: {backup_source}")
            
            session_path = self.base_path / "sessions" / session_id
            if session_path.exists():
                shutil.rmtree(session_path)
            
            shutil.copytree(backup_source, session_path)
            return True
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to restore session {session_id}: {e}")
    
    def validate_session_integrity(self, session_id: str) -> Dict[str, Any]:
        """Validate the integrity of a session's files"""
        try:
            session_path = self.base_path / "sessions" / session_id
            if not session_path.exists():
                raise StorageNotFoundError(f"Session not found: {session_id}")
            
            issues = []
            file_count = 0
            
            # Check for required files
            metadata_file = session_path / "metadata.json"
            if not metadata_file.exists():
                issues.append("Missing metadata.json file")
            
            # Check file accessibility
            for file_path in session_path.rglob('*'):
                if file_path.is_file():
                    file_count += 1
                    try:
                        # Try to read a small portion to check accessibility
                        with open(file_path, 'r', encoding='utf-8') as f:
                            f.read(100)  # Read first 100 characters
                    except Exception as e:
                        issues.append(f"Cannot read file {file_path.name}: {e}")
            
            return {
                "session_id": session_id,
                "is_valid": len(issues) == 0,
                "file_count": file_count,
                "issues": issues
            }
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to validate session {session_id}: {e}")