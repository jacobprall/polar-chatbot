"""Event data models for session audit logging."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List
from enum import Enum
import uuid


class EventType(Enum):
    """Types of events that can occur in a session."""
    SESSION_CREATED = "SessionCreated"
    SESSION_UPDATED = "SessionUpdated"
    DOCUMENT_CREATED = "DocumentCreated"
    DOCUMENT_EDITED = "DocumentEdited"
    TEST_RUN = "TestRun"
    VALIDATION_COMPLETED = "ValidationCompleted"
    DOCUMENT_REWORKED = "DocumentReworked"
    NOTES_ADDED = "NotesAdded"
    POLICY_GENERATED = "PolicyGenerated"
    POLICY_VALIDATED = "PolicyValidated"


@dataclass
class SessionEvent:
    """Represents a single event in the session audit log."""
    id: str
    session_id: str
    timestamp: datetime
    event_type: EventType
    user_id: str
    document_id: str
    version: int
    data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(cls, session_id: str, event_type: EventType, user_id: str = "default_user",
               document_id: str = "", version: int = 1, data: Dict[str, Any] = None) -> 'SessionEvent':
        """Create a new session event with auto-generated ID and timestamp."""
        return cls(
            id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=datetime.utcnow(),
            event_type=event_type,
            user_id=user_id,
            document_id=document_id,
            version=version,
            data=data or {}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "document_id": self.document_id,
            "version": self.version,
            "data": self.data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionEvent':
        """Create event from dictionary (for deserialization)."""
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            user_id=data["user_id"],
            document_id=data["document_id"],
            version=data["version"],
            data=data.get("data", {})
        )


@dataclass
class EventBatch:
    """Represents a batch of events for efficient storage operations."""
    events: List[SessionEvent] = field(default_factory=list)
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_event(self, event: SessionEvent) -> None:
        """Add an event to the batch."""
        self.events.append(event)
    
    def to_jsonl(self) -> str:
        """Convert batch to JSON Lines format for storage."""
        import json
        lines = []
        for event in self.events:
            lines.append(json.dumps(event.to_dict()))
        return '\n'.join(lines)
    
    @classmethod
    def from_jsonl(cls, jsonl_content: str) -> 'EventBatch':
        """Create event batch from JSON Lines content."""
        import json
        batch = cls()
        for line in jsonl_content.strip().split('\n'):
            if line.strip():
                event_data = json.loads(line)
                batch.add_event(SessionEvent.from_dict(event_data))
        return batch


# Event factory functions for common event types
def create_session_created_event(session_id: str, session_name: str, user_id: str = "default_user") -> SessionEvent:
    """Create a session created event."""
    return SessionEvent.create(
        session_id=session_id,
        event_type=EventType.SESSION_CREATED,
        user_id=user_id,
        document_id=session_id,
        data={"session_name": session_name}
    )


def create_requirements_edited_event(session_id: str, requirements_length: int, 
                                   user_id: str = "default_user") -> SessionEvent:
    """Create a requirements document edited event."""
    return SessionEvent.create(
        session_id=session_id,
        event_type=EventType.DOCUMENT_EDITED,
        user_id=user_id,
        document_id="requirements",
        data={"document_type": "requirements", "content_length": requirements_length}
    )


def create_policy_generated_event(session_id: str, policy_id: str, model_used: str,
                                tokens_used: int = None, generation_time: float = 0.0,
                                user_id: str = "default_user") -> SessionEvent:
    """Create a policy generated event."""
    return SessionEvent.create(
        session_id=session_id,
        event_type=EventType.POLICY_GENERATED,
        user_id=user_id,
        document_id=policy_id,
        data={
            "model_used": model_used,
            "tokens_used": tokens_used,
            "generation_time": generation_time
        }
    )


def create_validation_completed_event(session_id: str, policy_id: str, is_valid: bool,
                                    error_message: str = None, validation_time: float = 0.0,
                                    user_id: str = "default_user") -> SessionEvent:
    """Create a validation completed event."""
    return SessionEvent.create(
        session_id=session_id,
        event_type=EventType.VALIDATION_COMPLETED,
        user_id=user_id,
        document_id=policy_id,
        data={
            "is_valid": is_valid,
            "error_message": error_message,
            "validation_time": validation_time
        }
    )


def create_notes_added_event(session_id: str, notes_length: int, 
                           user_id: str = "default_user") -> SessionEvent:
    """Create a notes added/updated event."""
    return SessionEvent.create(
        session_id=session_id,
        event_type=EventType.NOTES_ADDED,
        user_id=user_id,
        document_id="notes",
        data={"notes_length": notes_length}
    )