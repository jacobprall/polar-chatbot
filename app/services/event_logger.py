"""
Event logging service for session audit trail and state replay.

This module provides append-only event logging functionality that maintains
a complete audit trail of all session activities and enables session state
reconstruction from events.
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from ..models.events import SessionEvent, EventBatch, EventType
from ..models.session import Session, GeneratedPolicy, ValidationResult
from ..storage.base import StorageBackend, StorageError, StorageNotFoundError
# EventConfig removed - using simple defaults


class EventLoggerError(Exception):
    """Base exception for event logging operations"""
    pass


class EventReplayError(EventLoggerError):
    """Raised when event replay fails"""
    pass


class EventStorageError(EventLoggerError):
    """Raised when event storage operations fail"""
    pass


class EventLogger:
    """
    Append-only event logger for session audit trail and state replay.
    
    This class provides functionality to:
    - Log session events to append-only storage
    - Retrieve events for analysis and replay
    - Rebuild session state from event history
    - Handle event batching for performance
    """
    
    def __init__(self, storage_backend: StorageBackend):
        """
        Initialize the event logger.
        
        Args:
            storage_backend: Storage backend for event persistence
        """
        self.storage = storage_backend
        # Simple defaults instead of config
        self.batch_size = 10
        self.retention_days = 90
        self._current_batch: Optional[EventBatch] = None
        self._batch_timer: Optional[datetime] = None
    
    def log_event(self, event: SessionEvent) -> bool:
        """
        Log a single event to the append-only event log.
        
        Args:
            event: The session event to log
            
        Returns:
            True if event was successfully logged
            
        Raises:
            EventStorageError: If event storage fails
        """
        try:
            # Add event to current batch
            if self._current_batch is None:
                self._current_batch = EventBatch()
                self._batch_timer = datetime.utcnow()
            
            self._current_batch.add_event(event)
            
            # Check if batch should be flushed
            if (len(self._current_batch.events) >= self.batch_size or
                self._should_flush_batch()):
                return self._flush_batch()
            
            return True
            
        except Exception as e:
            raise EventStorageError(f"Failed to log event {event.id}: {e}")
    
    async def log_event_async(self, event: SessionEvent) -> bool:
        """
        Async version of log_event for use in async contexts.
        
        Args:
            event: The session event to log
            
        Returns:
            True if event was successfully logged
            
        Raises:
            EventStorageError: If event storage fails
        """
        # For now, just call the sync version
        # In a real implementation, this could use async storage operations
        return self.log_event(event)
    
    def log_events(self, events: List[SessionEvent]) -> bool:
        """
        Log multiple events in batch.
        
        Args:
            events: List of session events to log
            
        Returns:
            True if all events were successfully logged
            
        Raises:
            EventStorageError: If batch event storage fails
        """
        try:
            batch = EventBatch()
            for event in events:
                batch.add_event(event)
            
            return self._store_batch(batch)
            
        except Exception as e:
            raise EventStorageError(f"Failed to log event batch: {e}")
    
    def get_events(self, session_id: str, 
                   event_types: Optional[List[EventType]] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None) -> List[SessionEvent]:
        """
        Retrieve events for a session with optional filtering.
        
        Args:
            session_id: Session ID to retrieve events for
            event_types: Optional list of event types to filter by
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            List of session events matching the criteria
            
        Raises:
            EventStorageError: If event retrieval fails
        """
        try:
            events = []
            event_key = self._get_event_key(session_id)
            
            try:
                event_obj = self.storage.get_object(event_key)
                batch = EventBatch.from_jsonl(event_obj.content)
                events.extend(batch.events)
            except StorageNotFoundError:
                # No events exist for this session yet
                return []
            
            # Apply filters
            filtered_events = events
            
            if event_types:
                filtered_events = [e for e in filtered_events if e.event_type in event_types]
            
            if start_time:
                filtered_events = [e for e in filtered_events if e.timestamp >= start_time]
            
            if end_time:
                filtered_events = [e for e in filtered_events if e.timestamp <= end_time]
            
            # Sort by timestamp
            filtered_events.sort(key=lambda e: e.timestamp)
            
            return filtered_events
            
        except Exception as e:
            raise EventStorageError(f"Failed to retrieve events for session {session_id}: {e}")
    
    def get_all_events(self, session_id: str) -> List[SessionEvent]:
        """
        Get all events for a session in chronological order.
        
        Args:
            session_id: Session ID to retrieve events for
            
        Returns:
            List of all session events in chronological order
        """
        return self.get_events(session_id)
    
    def replay_session(self, session_id: str) -> Session:
        """
        Rebuild session state from event history.
        
        This method replays all events for a session in chronological order
        to reconstruct the current session state.
        
        Args:
            session_id: Session ID to replay
            
        Returns:
            Reconstructed session object
            
        Raises:
            EventReplayError: If session replay fails
            EventStorageError: If event retrieval fails
        """
        try:
            events = self.get_all_events(session_id)
            
            if not events:
                raise EventReplayError(f"No events found for session {session_id}")
            
            # Initialize session from first event (should be SESSION_CREATED)
            session = None
            
            for event in events:
                session = self._apply_event_to_session(session, event)
            
            if session is None:
                raise EventReplayError(f"Failed to reconstruct session {session_id}")
            
            return session
            
        except EventStorageError:
            raise
        except Exception as e:
            raise EventReplayError(f"Failed to replay session {session_id}: {e}")
    
    def get_session_timeline(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get a timeline view of session events for analysis.
        
        Args:
            session_id: Session ID to get timeline for
            
        Returns:
            List of timeline entries with event summaries
        """
        try:
            events = self.get_all_events(session_id)
            timeline = []
            
            for event in events:
                timeline_entry = {
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type.value,
                    "user_id": event.user_id,
                    "document_id": event.document_id,
                    "version": event.version,
                    "summary": self._get_event_summary(event)
                }
                timeline.append(timeline_entry)
            
            return timeline
            
        except Exception as e:
            raise EventStorageError(f"Failed to get timeline for session {session_id}: {e}")
    
    def cleanup_old_events(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up events older than retention period.
        
        Args:
            retention_days: Number of days to retain events (uses config default if None)
            
        Returns:
            Number of event files cleaned up
        """
        try:
            retention_days = retention_days or self.retention_days
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            # List all event files
            result = self.storage.list_objects(prefix="events/")
            cleaned_count = 0
            
            for obj_info in result['objects']:
                if obj_info.last_modified < cutoff_date:
                    self.storage.delete_object(obj_info.key)
                    cleaned_count += 1
            
            return cleaned_count
            
        except Exception as e:
            raise EventStorageError(f"Failed to cleanup old events: {e}")
    
    def validate_event_integrity(self, session_id: str) -> Dict[str, Any]:
        """
        Validate the integrity of events for a session.
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            Dictionary with validation results
        """
        try:
            events = self.get_all_events(session_id)
            
            issues = []
            event_count = len(events)
            
            if not events:
                return {
                    "session_id": session_id,
                    "is_valid": True,
                    "event_count": 0,
                    "issues": ["No events found - session may not exist"]
                }
            
            # Check for required first event
            if events[0].event_type != EventType.SESSION_CREATED:
                issues.append("First event is not SESSION_CREATED")
            
            # Check chronological order
            for i in range(1, len(events)):
                if events[i].timestamp < events[i-1].timestamp:
                    issues.append(f"Events out of chronological order at index {i}")
            
            # Check for duplicate event IDs
            event_ids = [e.id for e in events]
            if len(event_ids) != len(set(event_ids)):
                issues.append("Duplicate event IDs found")
            
            # Try to replay session to check consistency
            try:
                self.replay_session(session_id)
            except EventReplayError as e:
                issues.append(f"Session replay failed: {e}")
            
            return {
                "session_id": session_id,
                "is_valid": len(issues) == 0,
                "event_count": event_count,
                "issues": issues,
                "first_event": events[0].timestamp.isoformat() if events else None,
                "last_event": events[-1].timestamp.isoformat() if events else None
            }
            
        except Exception as e:
            return {
                "session_id": session_id,
                "is_valid": False,
                "event_count": 0,
                "issues": [f"Validation failed: {e}"]
            }
    
    def flush_pending_events(self) -> bool:
        """
        Flush any pending events in the current batch.
        
        Returns:
            True if flush was successful
        """
        if self._current_batch and self._current_batch.events:
            return self._flush_batch()
        return True
    
    def get_event_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about event storage.
        
        Returns:
            Dictionary with event storage statistics
        """
        try:
            result = self.storage.list_objects(prefix="events/")
            
            total_events = 0
            total_size = 0
            session_count = len(result['objects'])
            
            for obj_info in result['objects']:
                total_size += obj_info.size
                # Estimate event count (rough approximation)
                total_events += max(1, obj_info.size // 200)  # Assume ~200 bytes per event
            
            return {
                "total_sessions_with_events": session_count,
                "estimated_total_events": total_events,
                "total_storage_bytes": total_size,
                "storage_backend": self.storage.__class__.__name__
            }
            
        except Exception as e:
            return {
                "error": f"Failed to get event statistics: {e}"
            }
    
    # Private methods
    
    def _should_flush_batch(self) -> bool:
        """Check if current batch should be flushed based on time."""
        if self._batch_timer is None:
            return False
        
        # Flush if batch is older than 30 seconds
        return (datetime.utcnow() - self._batch_timer).total_seconds() > 30
    
    def _flush_batch(self) -> bool:
        """Flush the current batch to storage."""
        if self._current_batch is None or not self._current_batch.events:
            return True
        
        try:
            success = self._store_batch(self._current_batch)
            self._current_batch = None
            self._batch_timer = None
            return success
        except Exception as e:
            raise EventStorageError(f"Failed to flush event batch: {e}")
    
    def _store_batch(self, batch: EventBatch) -> bool:
        """Store an event batch to storage."""
        try:
            # Group events by session for storage
            session_events = {}
            for event in batch.events:
                if event.session_id not in session_events:
                    session_events[event.session_id] = []
                session_events[event.session_id].append(event)
            
            # Store events for each session
            for session_id, events in session_events.items():
                event_key = self._get_event_key(session_id)
                
                # Load existing events
                existing_events = []
                try:
                    existing_obj = self.storage.get_object(event_key)
                    existing_batch = EventBatch.from_jsonl(existing_obj.content)
                    existing_events = existing_batch.events
                except StorageNotFoundError:
                    # No existing events, start fresh
                    pass
                
                # Append new events
                all_events = existing_events + events
                
                # Create new batch with all events
                combined_batch = EventBatch()
                for event in all_events:
                    combined_batch.add_event(event)
                
                # Store updated batch
                content = combined_batch.to_jsonl()
                self.storage.put_object(
                    key=event_key,
                    content=content,
                    content_type="application/x-jsonlines",
                    metadata={
                        "session_id": session_id,
                        "event_count": str(len(all_events)),
                        "last_updated": datetime.utcnow().isoformat()
                    }
                )
            
            return True
            
        except Exception as e:
            raise EventStorageError(f"Failed to store event batch: {e}")
    
    def _get_event_key(self, session_id: str) -> str:
        """Get storage key for session events."""
        return f"events/{session_id}_events.jsonl"
    
    def _apply_event_to_session(self, session: Optional[Session], event: SessionEvent) -> Session:
        """Apply a single event to session state."""
        try:
            if event.event_type == EventType.SESSION_CREATED:
                if session is not None:
                    raise EventReplayError("SESSION_CREATED event found but session already exists")
                
                session_name = event.data.get("session_name", "Unnamed Session")
                session = Session(
                    id=event.session_id,
                    name=session_name,
                    created_at=event.timestamp,
                    updated_at=event.timestamp
                )
            
            elif event.event_type == EventType.DOCUMENT_EDITED:
                if session is None:
                    raise EventReplayError("DOCUMENT_EDITED event found but no session exists")
                
                if event.document_id == "requirements":
                    # We don't store the actual content in events for privacy/size reasons
                    # Just update the timestamp
                    session.updated_at = event.timestamp
            
            elif event.event_type == EventType.POLICY_GENERATED:
                if session is None:
                    raise EventReplayError("POLICY_GENERATED event found but no session exists")
                
                policy = GeneratedPolicy(
                    id=event.document_id,
                    content="",  # Content stored separately
                    generated_at=event.timestamp,
                    model_used=event.data.get("model_used", "unknown"),
                    tokens_used=event.data.get("tokens_used"),
                    generation_time=event.data.get("generation_time", 0.0),
                    is_current=True  # Will be updated by subsequent events
                )
                session.add_policy(policy)
            
            elif event.event_type == EventType.VALIDATION_COMPLETED:
                if session is None:
                    raise EventReplayError("VALIDATION_COMPLETED event found but no session exists")
                
                result = ValidationResult(
                    id=f"val_{event.id}",
                    policy_id=event.document_id,
                    is_valid=event.data.get("is_valid", False),
                    error_message=event.data.get("error_message"),
                    validated_at=event.timestamp,
                    validation_time=event.data.get("validation_time", 0.0)
                )
                session.add_validation_result(result)
            
            elif event.event_type == EventType.NOTES_ADDED:
                if session is None:
                    raise EventReplayError("NOTES_ADDED event found but no session exists")
                
                # Notes content stored separately, just update timestamp
                session.updated_at = event.timestamp
            
            elif event.event_type == EventType.SESSION_UPDATED:
                if session is None:
                    raise EventReplayError("SESSION_UPDATED event found but no session exists")
                
                session.updated_at = event.timestamp
            
            # Update session timestamp for all events
            if session:
                session.updated_at = max(session.updated_at, event.timestamp)
            
            return session
            
        except Exception as e:
            raise EventReplayError(f"Failed to apply event {event.id} to session: {e}")
    
    def _get_event_summary(self, event: SessionEvent) -> str:
        """Get a human-readable summary of an event."""
        summaries = {
            EventType.SESSION_CREATED: lambda e: f"Session '{e.data.get('session_name', 'Unnamed')}' created",
            EventType.DOCUMENT_EDITED: lambda e: f"Requirements document edited ({e.data.get('content_length', 0)} chars)",
            EventType.POLICY_GENERATED: lambda e: f"Policy generated using {e.data.get('model_used', 'unknown')} model",
            EventType.VALIDATION_COMPLETED: lambda e: f"Validation {'passed' if e.data.get('is_valid') else 'failed'}",
            EventType.NOTES_ADDED: lambda e: f"Notes updated ({e.data.get('notes_length', 0)} chars)",
            EventType.SESSION_UPDATED: lambda e: "Session metadata updated",
            EventType.DOCUMENT_REWORKED: lambda e: "Document reworked based on feedback"
        }
        
        summary_func = summaries.get(event.event_type)
        if summary_func:
            try:
                return summary_func(event)
            except Exception:
                pass
        
        return f"{event.event_type.value} event"