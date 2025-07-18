"""
Session-specific storage operations built on top of the storage backend
"""

import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from .base import StorageBackend, StorageError, StorageNotFoundError


@dataclass
class SessionMetadata:
    """Session metadata structure"""
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    description: str = ""
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionMetadata':
        """Create from dictionary"""
        data = data.copy()
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)


class SessionStorage:
    """Session-specific storage operations"""
    
    def __init__(self, storage_backend: StorageBackend, sessions_prefix: str = "sessions"):
        self.storage = storage_backend
        self.sessions_prefix = sessions_prefix
    
    def _get_session_key(self, session_id: str, filename: str) -> str:
        """Generate storage key for session file"""
        return f"{self.sessions_prefix}/{session_id}/{filename}"
    
    def _get_session_prefix(self, session_id: str) -> str:
        """Get prefix for all session files"""
        return f"{self.sessions_prefix}/{session_id}/"
    
    def create_session(self, session_id: str, name: str, description: str = "") -> SessionMetadata:
        """Create a new session"""
        now = datetime.utcnow()
        metadata = SessionMetadata(
            id=session_id,
            name=name,
            created_at=now,
            updated_at=now,
            description=description
        )
        
        # Store session metadata
        metadata_key = self._get_session_key(session_id, "metadata.json")
        self.storage.put_object(
            metadata_key,
            json.dumps(metadata.to_dict(), indent=2),
            "application/json"
        )
        
        return metadata
    
    def get_session_metadata(self, session_id: str) -> SessionMetadata:
        """Get session metadata"""
        metadata_key = self._get_session_key(session_id, "metadata.json")
        try:
            obj = self.storage.get_object(metadata_key)
            data = json.loads(obj.content)
            return SessionMetadata.from_dict(data)
        except StorageNotFoundError:
            raise StorageNotFoundError(f"Session not found: {session_id}")
    
    def update_session_metadata(self, session_metadata: SessionMetadata) -> None:
        """Update session metadata"""
        session_metadata.updated_at = datetime.utcnow()
        metadata_key = self._get_session_key(session_metadata.id, "metadata.json")
        self.storage.put_object(
            metadata_key,
            json.dumps(session_metadata.to_dict(), indent=2),
            "application/json"
        )
    
    def list_sessions(self) -> List[SessionMetadata]:
        """List all sessions"""
        sessions = []
        
        # List all objects in sessions prefix
        result = self.storage.list_objects(f"{self.sessions_prefix}/")
        objects = result.get('objects', [])
        
        # Find all metadata.json files
        session_ids = set()
        for obj in objects:
            if obj.key.endswith("/metadata.json"):
                # Extract session ID from path
                parts = obj.key.split("/")
                if len(parts) >= 3:  # sessions/{session_id}/metadata.json
                    session_ids.add(parts[1])
        
        # Load metadata for each session
        for session_id in session_ids:
            try:
                metadata = self.get_session_metadata(session_id)
                sessions.append(metadata)
            except StorageNotFoundError:
                continue  # Skip sessions with missing metadata
        
        # Sort by updated_at descending (most recent first)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions
    
    def session_exists(self, session_id: str) -> bool:
        """Check if session exists"""
        metadata_key = self._get_session_key(session_id, "metadata.json")
        return self.storage.object_exists(metadata_key)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete entire session and all its files"""
        if not self.session_exists(session_id):
            return True  # Already deleted
        
        # List all files in session
        session_prefix = self._get_session_prefix(session_id)
        result = self.storage.list_objects(session_prefix)
        objects = result.get('objects', [])
        
        # Delete all session files
        success = True
        for obj in objects:
            try:
                self.storage.delete_object(obj.key)
            except StorageError:
                success = False
        
        return success
    
    def store_session_file(self, session_id: str, filename: str, content: str, 
                          content_type: str = "text/plain", 
                          metadata: Optional[Dict[str, str]] = None) -> bool:
        """Store a file within a session"""
        key = self._get_session_key(session_id, filename)
        return self.storage.put_object(key, content, content_type, metadata)
    
    def get_session_file(self, session_id: str, filename: str) -> str:
        """Get content of a session file"""
        key = self._get_session_key(session_id, filename)
        obj = self.storage.get_object(key)
        return obj.content
    
    def session_file_exists(self, session_id: str, filename: str) -> bool:
        """Check if a session file exists"""
        key = self._get_session_key(session_id, filename)
        return self.storage.object_exists(key)
    
    def list_session_files(self, session_id: str) -> List[str]:
        """List all files in a session"""
        session_prefix = self._get_session_prefix(session_id)
        result = self.storage.list_objects(session_prefix)
        objects = result.get('objects', [])
        
        # Extract filenames relative to session directory
        filenames = []
        for obj in objects:
            # Remove session prefix to get relative filename
            if obj.key.startswith(session_prefix):
                filename = obj.key[len(session_prefix):]
                filenames.append(filename)
        
        return filenames
    
    def copy_session(self, source_session_id: str, dest_session_id: str, 
                    new_name: str) -> SessionMetadata:
        """Copy a session to a new session"""
        # Get source session metadata
        source_metadata = self.get_session_metadata(source_session_id)
        
        # Create new session metadata
        now = datetime.utcnow()
        dest_metadata = SessionMetadata(
            id=dest_session_id,
            name=new_name,
            created_at=now,
            updated_at=now,
            description=f"Copy of {source_metadata.name}",
            tags=source_metadata.tags.copy()
        )
        
        # List all files in source session
        source_files = self.list_session_files(source_session_id)
        
        # Copy each file
        for filename in source_files:
            if filename != "metadata.json":  # Skip metadata, we'll create new one
                source_key = self._get_session_key(source_session_id, filename)
                dest_key = self._get_session_key(dest_session_id, filename)
                self.storage.copy_object(source_key, dest_key)
        
        # Store new metadata
        metadata_key = self._get_session_key(dest_session_id, "metadata.json")
        self.storage.put_object(
            metadata_key,
            json.dumps(dest_metadata.to_dict(), indent=2),
            "application/json"
        )
        
        return dest_metadata
    
    def cleanup_empty_sessions(self) -> int:
        """Remove sessions that only have metadata (no content files)"""
        sessions = self.list_sessions()
        cleaned_count = 0
        
        for session in sessions:
            files = self.list_session_files(session.id)
            # If session only has metadata.json, consider it empty
            if len(files) <= 1 and (not files or files[0] == "metadata.json"):
                self.delete_session(session.id)
                cleaned_count += 1
        
        return cleaned_count
    
    def get_session_size(self, session_id: str) -> int:
        """Get total size of all files in a session"""
        session_prefix = self._get_session_prefix(session_id)
        result = self.storage.list_objects(session_prefix)
        objects = result.get('objects', [])
        return sum(obj.size for obj in objects)
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        sessions = self.list_sessions()
        total_sessions = len(sessions)
        
        total_size = 0
        for session in sessions:
            total_size += self.get_session_size(session.id)
        
        return {
            "total_sessions": total_sessions,
            "total_size_bytes": total_size,
            "average_session_size": total_size / max(total_sessions, 1)
        }