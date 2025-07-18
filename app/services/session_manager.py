"""
SessionManager service for handling session operations in the Polar Prompt Tester.

This service provides high-level session management functionality including:
- Session creation, loading, and persistence
- Session metadata management and validation
- Session listing and search functionality
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import asdict

from ..models.session import Session, SessionMetadata, GeneratedPolicy, ValidationResult
from ..storage.base import StorageBackend, StorageError, StorageNotFoundError
from ..storage.session_storage import SessionStorage


class SessionManagerError(Exception):
    """Base exception for SessionManager operations"""
    pass


class SessionNotFoundError(SessionManagerError):
    """Raised when a session is not found"""
    pass


class SessionValidationError(SessionManagerError):
    """Raised when session data validation fails"""
    pass


class SessionManager:
    """
    High-level session management service.
    
    Provides comprehensive session operations including creation, loading,
    persistence, and search functionality with proper validation and error handling.
    """
    
    def __init__(self, storage_backend: StorageBackend):
        """
        Initialize SessionManager with storage backend.
        
        Args:
            storage_backend: Storage backend implementation
        """
        self.storage = storage_backend
        self.session_storage = SessionStorage(storage_backend)
    
    def create_session(self, name: str, description: str = "") -> Session:
        """
        Create a new session with validation.
        
        Args:
            name: Session name (required, non-empty)
            description: Optional session description
            
        Returns:
            Created Session object
            
        Raises:
            SessionValidationError: If name is invalid
            SessionManagerError: If creation fails
        """
        # Validate session name
        if not name or not name.strip():
            raise SessionValidationError("Session name cannot be empty")
        
        if len(name.strip()) > 100:
            raise SessionValidationError("Session name cannot exceed 100 characters")
        
        try:
            # Create new session
            session = Session.create(name.strip())
            
            # Store session metadata in storage
            self.session_storage.create_session(
                session.id, 
                session.name, 
                description
            )
            
            # Store initial session data
            self._persist_session(session)
            
            return session
            
        except StorageError as e:
            raise SessionManagerError(f"Failed to create session: {str(e)}")
    
    def load_session(self, session_id: str) -> Session:
        """
        Load a session by ID with full data reconstruction.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Complete Session object with all data
            
        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionManagerError: If loading fails
        """
        if not session_id or not session_id.strip():
            raise SessionValidationError("Session ID cannot be empty")
        
        try:
            # Check if session exists
            if not self.session_storage.session_exists(session_id):
                raise SessionNotFoundError(f"Session not found: {session_id}")
            
            # Load session metadata
            storage_metadata = self.session_storage.get_session_metadata(session_id)
            
            # Initialize session with metadata
            session = Session(
                id=storage_metadata.id,
                name=storage_metadata.name,
                created_at=storage_metadata.created_at,
                updated_at=storage_metadata.updated_at
            )
            
            # Load session data files
            self._load_session_data(session)
            
            return session
            
        except StorageNotFoundError:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        except StorageError as e:
            raise SessionManagerError(f"Failed to load session: {str(e)}")
    
    def save_session(self, session: Session) -> bool:
        """
        Save session data with validation and timestamp update.
        
        Args:
            session: Session object to save
            
        Returns:
            True if successful
            
        Raises:
            SessionValidationError: If session data is invalid
            SessionManagerError: If save operation fails
        """
        # Validate session
        self._validate_session(session)
        
        try:
            # Update timestamp
            session.update_timestamp()
            
            # Persist session data
            self._persist_session(session)
            
            # Update metadata in storage
            storage_metadata = self.session_storage.get_session_metadata(session.id)
            storage_metadata.name = session.name
            storage_metadata.updated_at = session.updated_at
            self.session_storage.update_session_metadata(storage_metadata)
            
            return True
            
        except StorageError as e:
            raise SessionManagerError(f"Failed to save session: {str(e)}")
    
    def list_sessions(self, limit: Optional[int] = None, 
                     search_term: Optional[str] = None) -> List[SessionMetadata]:
        """
        List sessions with optional filtering and search.
        
        Args:
            limit: Maximum number of sessions to return
            search_term: Optional search term to filter by name
            
        Returns:
            List of SessionMetadata objects sorted by update time (newest first)
            
        Raises:
            SessionManagerError: If listing fails
        """
        try:
            # Get all sessions from storage
            storage_sessions = self.session_storage.list_sessions()
            
            # Convert storage metadata to our SessionMetadata format
            sessions = []
            for storage_session in storage_sessions:
                try:
                    # Create SessionMetadata from storage metadata
                    # We need to load the session to get policy counts and requirements status
                    full_session = self.load_session(storage_session.id)
                    session_metadata = full_session.to_metadata()
                    sessions.append(session_metadata)
                except (SessionNotFoundError, SessionManagerError):
                    # If we can't load the full session, create basic metadata
                    session_metadata = SessionMetadata(
                        id=storage_session.id,
                        name=storage_session.name,
                        created_at=storage_session.created_at,
                        updated_at=storage_session.updated_at,
                        has_requirements=False,
                        has_policies=False,
                        policy_count=0
                    )
                    sessions.append(session_metadata)
            
            # Apply search filter if provided
            if search_term and search_term.strip():
                search_lower = search_term.strip().lower()
                sessions = [
                    s for s in sessions 
                    if search_lower in s.name.lower()
                ]
            
            # Sort by updated_at descending (newest first)
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            
            # Apply limit if specified
            if limit and limit > 0:
                sessions = sessions[:limit]
            
            return sessions
            
        except StorageError as e:
            raise SessionManagerError(f"Failed to list sessions: {str(e)}")
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all its data.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if successful or session didn't exist
            
        Raises:
            SessionManagerError: If deletion fails
        """
        if not session_id or not session_id.strip():
            raise SessionValidationError("Session ID cannot be empty")
        
        try:
            return self.session_storage.delete_session(session_id)
        except StorageError as e:
            raise SessionManagerError(f"Failed to delete session: {str(e)}")
    
    def session_exists(self, session_id: str) -> bool:
        """
        Check if a session exists.
        
        Args:
            session_id: Session ID to check
            
        Returns:
            True if session exists
        """
        if not session_id or not session_id.strip():
            return False
        
        try:
            return self.session_storage.session_exists(session_id)
        except StorageError:
            return False
    
    def get_session_metadata(self, session_id: str) -> SessionMetadata:
        """
        Get lightweight session metadata without loading full session.
        
        Args:
            session_id: Session ID
            
        Returns:
            SessionMetadata object
            
        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionManagerError: If metadata retrieval fails
        """
        try:
            # Load minimal session data to create metadata
            session = self.load_session(session_id)
            return session.to_metadata()
        except SessionNotFoundError:
            raise
        except SessionManagerError as e:
            raise SessionManagerError(f"Failed to get session metadata: {str(e)}")
    
    def search_sessions(self, query: str, limit: int = 50) -> List[SessionMetadata]:
        """
        Search sessions by name with fuzzy matching.
        
        Args:
            query: Search query
            limit: Maximum results to return
            
        Returns:
            List of matching SessionMetadata objects
        """
        if not query or not query.strip():
            return self.list_sessions(limit=limit)
        
        return self.list_sessions(limit=limit, search_term=query)
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about all sessions.
        
        Returns:
            Dictionary with session statistics
        """
        try:
            sessions = self.list_sessions()
            
            total_sessions = len(sessions)
            sessions_with_requirements = sum(1 for s in sessions if s.has_requirements)
            sessions_with_policies = sum(1 for s in sessions if s.has_policies)
            total_policies = sum(s.policy_count for s in sessions)
            
            # Calculate storage stats
            storage_stats = self.session_storage.get_storage_stats()
            
            return {
                "total_sessions": total_sessions,
                "sessions_with_requirements": sessions_with_requirements,
                "sessions_with_policies": sessions_with_policies,
                "total_policies": total_policies,
                "average_policies_per_session": total_policies / max(total_sessions, 1),
                "storage_size_bytes": storage_stats.get("total_size_bytes", 0),
                "average_session_size_bytes": storage_stats.get("average_session_size", 0)
            }
        except StorageError as e:
            raise SessionManagerError(f"Failed to get session statistics: {str(e)}")
    
    def _validate_session(self, session: Session) -> None:
        """
        Validate session data integrity.
        
        Args:
            session: Session to validate
            
        Raises:
            SessionValidationError: If validation fails
        """
        if not session.id:
            raise SessionValidationError("Session ID cannot be empty")
        
        if not session.name or not session.name.strip():
            raise SessionValidationError("Session name cannot be empty")
        
        if len(session.name) > 100:
            raise SessionValidationError("Session name cannot exceed 100 characters")
        
        # Validate generated policies
        for policy in session.generated_policies:
            if not policy.id:
                raise SessionValidationError("Policy ID cannot be empty")
            if not policy.content:
                raise SessionValidationError("Policy content cannot be empty")
        
        # Validate validation results
        for result in session.validation_results:
            if not result.id:
                raise SessionValidationError("Validation result ID cannot be empty")
            if not result.policy_id:
                raise SessionValidationError("Validation result must reference a policy")
    
    def _persist_session(self, session: Session) -> None:
        """
        Persist session data to storage.
        
        Args:
            session: Session to persist
            
        Raises:
            StorageError: If persistence fails
        """
        # Store requirements
        if session.requirements_text:
            self.session_storage.store_session_file(
                session.id, 
                "requirements.txt", 
                session.requirements_text,
                "text/plain"
            )
        
        # Store notes
        if session.notes:
            self.session_storage.store_session_file(
                session.id,
                "notes.md",
                session.notes,
                "text/markdown"
            )
        
        # Store generated policies
        for policy in session.generated_policies:
            policy_filename = f"policies/{policy.id}.polar"
            self.session_storage.store_session_file(
                session.id,
                policy_filename,
                policy.content,
                "text/plain"
            )
            
            # Store policy metadata
            policy_metadata = {
                "id": policy.id,
                "generated_at": policy.generated_at.isoformat(),
                "model_used": policy.model_used,
                "tokens_used": policy.tokens_used,
                "generation_time": policy.generation_time,
                "is_current": policy.is_current
            }
            metadata_filename = f"policies/{policy.id}_metadata.json"
            self.session_storage.store_session_file(
                session.id,
                metadata_filename,
                json.dumps(policy_metadata, indent=2),
                "application/json"
            )
        
        # Store validation results
        for result in session.validation_results:
            result_data = {
                "id": result.id,
                "policy_id": result.policy_id,
                "is_valid": result.is_valid,
                "error_message": result.error_message,
                "validated_at": result.validated_at.isoformat(),
                "validation_time": result.validation_time
            }
            result_filename = f"validation_results/{result.id}.json"
            self.session_storage.store_session_file(
                session.id,
                result_filename,
                json.dumps(result_data, indent=2),
                "application/json"
            )
        
        # Store session metadata
        session_data = {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "metadata": session.metadata
        }
        self.session_storage.store_session_file(
            session.id,
            "session.json",
            json.dumps(session_data, indent=2),
            "application/json"
        )
    
    def _load_session_data(self, session: Session) -> None:
        """
        Load session data from storage files.
        
        Args:
            session: Session object to populate with data
            
        Raises:
            StorageError: If loading fails
        """
        # Load requirements
        if self.session_storage.session_file_exists(session.id, "requirements.txt"):
            session.requirements_text = self.session_storage.get_session_file(
                session.id, "requirements.txt"
            )
        
        # Load notes
        if self.session_storage.session_file_exists(session.id, "notes.md"):
            session.notes = self.session_storage.get_session_file(
                session.id, "notes.md"
            )
        
        # Load session metadata if exists
        if self.session_storage.session_file_exists(session.id, "session.json"):
            session_data = json.loads(
                self.session_storage.get_session_file(session.id, "session.json")
            )
            session.metadata = session_data.get("metadata", {})
        
        # Load generated policies
        session_files = self.session_storage.list_session_files(session.id)
        policy_files = [f for f in session_files if f.startswith("policies/") and f.endswith(".polar")]
        
        for policy_file in policy_files:
            policy_id = policy_file.split("/")[1].replace(".polar", "")
            
            # Load policy content
            policy_content = self.session_storage.get_session_file(session.id, policy_file)
            
            # Load policy metadata
            metadata_file = f"policies/{policy_id}_metadata.json"
            if self.session_storage.session_file_exists(session.id, metadata_file):
                metadata_content = self.session_storage.get_session_file(session.id, metadata_file)
                metadata = json.loads(metadata_content)
                
                policy = GeneratedPolicy(
                    id=metadata["id"],
                    content=policy_content,
                    generated_at=datetime.fromisoformat(metadata["generated_at"]),
                    model_used=metadata["model_used"],
                    tokens_used=metadata.get("tokens_used"),
                    generation_time=metadata.get("generation_time", 0.0),
                    is_current=metadata.get("is_current", False)
                )
                session.generated_policies.append(policy)
        
        # Load validation results
        validation_files = [f for f in session_files if f.startswith("validation_results/") and f.endswith(".json")]
        
        for validation_file in validation_files:
            validation_content = self.session_storage.get_session_file(session.id, validation_file)
            validation_data = json.loads(validation_content)
            
            result = ValidationResult(
                id=validation_data["id"],
                policy_id=validation_data["policy_id"],
                is_valid=validation_data["is_valid"],
                error_message=validation_data.get("error_message"),
                validated_at=datetime.fromisoformat(validation_data["validated_at"]),
                validation_time=validation_data.get("validation_time", 0.0)
            )
            session.validation_results.append(result)