"""
Tests for the EventLogger service.
"""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from app.services.event_logger import EventLogger, EventLoggerError, EventReplayError, EventStorageError
from app.models.events import SessionEvent, EventType, EventBatch
from app.models.events import (
    create_session_created_event,
    create_requirements_edited_event,
    create_policy_generated_event,
    create_validation_completed_event,
    create_notes_added_event
)
from app.models.config import EventConfig
from app.storage.local_storage import LocalStorageBackend


class TestEventLogger:
    """Test cases for EventLogger functionality."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage backend for testing."""
        temp_dir = tempfile.mkdtemp()
        storage = LocalStorageBackend(temp_dir)
        yield storage
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def event_logger(self, temp_storage):
        """Create an EventLogger instance for testing."""
        config = EventConfig(batch_size=3, retention_days=30)
        return EventLogger(temp_storage, config)
    
    @pytest.fixture
    def sample_session_id(self):
        """Sample session ID for testing."""
        return "test-session-123"
    
    @pytest.fixture
    def sample_events(self, sample_session_id):
        """Create sample events for testing."""
        events = []
        
        # Session created
        events.append(create_session_created_event(
            session_id=sample_session_id,
            session_name="Test Session"
        ))
        
        # Requirements edited
        events.append(create_requirements_edited_event(
            session_id=sample_session_id,
            requirements_length=500
        ))
        
        # Policy generated
        events.append(create_policy_generated_event(
            session_id=sample_session_id,
            policy_id="policy-123",
            model_used="gpt-4",
            tokens_used=1500,
            generation_time=3.2
        ))
        
        # Validation completed
        events.append(create_validation_completed_event(
            session_id=sample_session_id,
            policy_id="policy-123",
            is_valid=True,
            validation_time=1.1
        ))
        
        # Notes added
        events.append(create_notes_added_event(
            session_id=sample_session_id,
            notes_length=200
        ))
        
        return events
    
    def test_log_single_event(self, event_logger, sample_events):
        """Test logging a single event."""
        event = sample_events[0]
        
        result = event_logger.log_event(event)
        assert result is True
        
        # Flush any pending events
        event_logger.flush_pending_events()
        
        # Retrieve and verify
        retrieved_events = event_logger.get_events(event.session_id)
        assert len(retrieved_events) == 1
        assert retrieved_events[0].id == event.id
        assert retrieved_events[0].event_type == event.event_type
    
    def test_log_multiple_events(self, event_logger, sample_events):
        """Test logging multiple events."""
        result = event_logger.log_events(sample_events)
        assert result is True
        
        # Retrieve and verify
        retrieved_events = event_logger.get_events(sample_events[0].session_id)
        assert len(retrieved_events) == len(sample_events)
        
        # Verify chronological order
        for i in range(1, len(retrieved_events)):
            assert retrieved_events[i].timestamp >= retrieved_events[i-1].timestamp
    
    def test_event_batching(self, temp_storage, sample_events):
        """Test event batching functionality."""
        config = EventConfig(batch_size=2)  # Small batch size for testing
        event_logger = EventLogger(temp_storage, config)
        
        # Log events one by one
        for event in sample_events[:3]:  # Log 3 events with batch size 2
            event_logger.log_event(event)
        
        # Should have flushed automatically after 2 events
        retrieved_events = event_logger.get_events(sample_events[0].session_id)
        assert len(retrieved_events) >= 2
        
        # Flush remaining events
        event_logger.flush_pending_events()
        
        # Now should have all events
        retrieved_events = event_logger.get_events(sample_events[0].session_id)
        assert len(retrieved_events) == 3
    
    def test_get_events_with_filters(self, event_logger, sample_events):
        """Test retrieving events with various filters."""
        # Store all events
        event_logger.log_events(sample_events)
        
        session_id = sample_events[0].session_id
        
        # Filter by event type
        policy_events = event_logger.get_events(
            session_id, 
            event_types=[EventType.POLICY_GENERATED]
        )
        assert len(policy_events) == 1
        assert policy_events[0].event_type == EventType.POLICY_GENERATED
        
        # Filter by time range
        now = datetime.utcnow()
        recent_events = event_logger.get_events(
            session_id,
            start_time=now - timedelta(minutes=1)
        )
        assert len(recent_events) == len(sample_events)
        
        # Filter by multiple event types
        doc_events = event_logger.get_events(
            session_id,
            event_types=[EventType.DOCUMENT_EDITED, EventType.NOTES_ADDED]
        )
        assert len(doc_events) == 2
    
    def test_session_replay(self, event_logger, sample_events):
        """Test session state replay from events."""
        # Store events
        event_logger.log_events(sample_events)
        
        # Replay session
        session = event_logger.replay_session(sample_events[0].session_id)
        
        # Verify session reconstruction
        assert session.id == sample_events[0].session_id
        assert session.name == "Test Session"
        assert len(session.generated_policies) == 1
        assert len(session.validation_results) == 1
        
        # Verify policy details
        policy = session.generated_policies[0]
        assert policy.id == "policy-123"
        assert policy.model_used == "gpt-4"
        assert policy.tokens_used == 1500
        assert policy.generation_time == 3.2
        
        # Verify validation details
        validation = session.validation_results[0]
        assert validation.policy_id == "policy-123"
        assert validation.is_valid is True
        assert validation.validation_time == 1.1
    
    def test_replay_nonexistent_session(self, event_logger):
        """Test replaying a session that doesn't exist."""
        with pytest.raises(EventReplayError):
            event_logger.replay_session("nonexistent-session")
    
    def test_replay_invalid_event_sequence(self, event_logger, sample_session_id):
        """Test replaying with invalid event sequence."""
        # Create events without SESSION_CREATED first
        invalid_events = [
            create_requirements_edited_event(sample_session_id, 100),
            create_policy_generated_event(sample_session_id, "policy-1", "gpt-4")
        ]
        
        event_logger.log_events(invalid_events)
        
        with pytest.raises(EventReplayError):
            event_logger.replay_session(sample_session_id)
    
    def test_get_session_timeline(self, event_logger, sample_events):
        """Test getting session timeline."""
        event_logger.log_events(sample_events)
        
        timeline = event_logger.get_session_timeline(sample_events[0].session_id)
        
        assert len(timeline) == len(sample_events)
        
        # Verify timeline structure
        for entry in timeline:
            assert "timestamp" in entry
            assert "event_type" in entry
            assert "summary" in entry
            assert "user_id" in entry
        
        # Verify specific summaries
        summaries = [entry["summary"] for entry in timeline]
        assert any("Session 'Test Session' created" in s for s in summaries)
        assert any("Policy generated using gpt-4" in s for s in summaries)
        assert any("Validation passed" in s for s in summaries)
    
    def test_event_integrity_validation(self, event_logger, sample_events):
        """Test event integrity validation."""
        # Store valid events
        event_logger.log_events(sample_events)
        
        session_id = sample_events[0].session_id
        integrity = event_logger.validate_event_integrity(session_id)
        
        assert integrity["is_valid"] is True
        assert integrity["event_count"] == len(sample_events)
        assert len(integrity["issues"]) == 0
        assert "first_event" in integrity
        assert "last_event" in integrity
    
    def test_event_integrity_validation_invalid(self, event_logger, sample_session_id):
        """Test event integrity validation with invalid events."""
        # Create events with wrong order (no SESSION_CREATED first)
        invalid_events = [
            create_policy_generated_event(sample_session_id, "policy-1", "gpt-4"),
            create_session_created_event(sample_session_id, "Test Session")
        ]
        
        event_logger.log_events(invalid_events)
        
        integrity = event_logger.validate_event_integrity(sample_session_id)
        
        assert integrity["is_valid"] is False
        assert len(integrity["issues"]) > 0
        assert any("First event is not SESSION_CREATED" in issue for issue in integrity["issues"])
    
    def test_event_statistics(self, event_logger, sample_events):
        """Test getting event statistics."""
        event_logger.log_events(sample_events)
        
        stats = event_logger.get_event_statistics()
        
        assert "total_sessions_with_events" in stats
        assert "estimated_total_events" in stats
        assert "total_storage_bytes" in stats
        assert "storage_backend" in stats
        
        assert stats["total_sessions_with_events"] >= 1
        assert stats["estimated_total_events"] >= len(sample_events)
    
    def test_cleanup_old_events(self, event_logger, sample_events):
        """Test cleaning up old events."""
        # Store events
        event_logger.log_events(sample_events)
        
        # Clean up with very short retention (should not delete recent events)
        cleaned = event_logger.cleanup_old_events(retention_days=1)
        assert cleaned == 0  # No events should be deleted
        
        # Verify events still exist
        retrieved_events = event_logger.get_events(sample_events[0].session_id)
        assert len(retrieved_events) == len(sample_events)
    
    def test_event_batch_serialization(self):
        """Test EventBatch serialization and deserialization."""
        batch = EventBatch()
        
        # Add some events
        event1 = create_session_created_event("session-1", "Test Session")
        event2 = create_requirements_edited_event("session-1", 100)
        
        batch.add_event(event1)
        batch.add_event(event2)
        
        # Serialize to JSONL
        jsonl_content = batch.to_jsonl()
        assert len(jsonl_content.split('\n')) == 2
        
        # Deserialize back
        restored_batch = EventBatch.from_jsonl(jsonl_content)
        assert len(restored_batch.events) == 2
        assert restored_batch.events[0].id == event1.id
        assert restored_batch.events[1].id == event2.id
    
    def test_concurrent_event_logging(self, event_logger, sample_session_id):
        """Test logging events for multiple sessions concurrently."""
        session_ids = [f"{sample_session_id}-{i}" for i in range(3)]
        
        # Create events for multiple sessions
        all_events = []
        for session_id in session_ids:
            events = [
                create_session_created_event(session_id, f"Session {session_id}"),
                create_requirements_edited_event(session_id, 100),
                create_policy_generated_event(session_id, f"policy-{session_id}", "gpt-4")
            ]
            all_events.extend(events)
        
        # Log all events
        event_logger.log_events(all_events)
        
        # Verify each session has its events
        for session_id in session_ids:
            session_events = event_logger.get_events(session_id)
            assert len(session_events) == 3
            assert all(e.session_id == session_id for e in session_events)
    
    def test_error_handling(self, event_logger):
        """Test error handling in various scenarios."""
        # Test with invalid event data
        invalid_event = SessionEvent(
            id="invalid",
            session_id="",  # Empty session ID
            timestamp=datetime.utcnow(),
            event_type=EventType.SESSION_CREATED,
            user_id="test",
            document_id="",
            version=1,
            data={}
        )
        
        # Should still log the event (validation is lenient)
        result = event_logger.log_event(invalid_event)
        assert result is True
    
    def test_flush_pending_events(self, event_logger, sample_events):
        """Test flushing pending events."""
        # Log an event (should be batched)
        event_logger.log_event(sample_events[0])
        
        # Manually flush
        result = event_logger.flush_pending_events()
        assert result is True
        
        # Verify event was stored
        retrieved_events = event_logger.get_events(sample_events[0].session_id)
        assert len(retrieved_events) == 1
    
    def test_empty_session_timeline(self, event_logger):
        """Test getting timeline for session with no events."""
        timeline = event_logger.get_session_timeline("nonexistent-session")
        assert timeline == []
    
    def test_get_all_events(self, event_logger, sample_events):
        """Test getting all events for a session."""
        event_logger.log_events(sample_events)
        
        all_events = event_logger.get_all_events(sample_events[0].session_id)
        assert len(all_events) == len(sample_events)
        
        # Verify chronological order
        for i in range(1, len(all_events)):
            assert all_events[i].timestamp >= all_events[i-1].timestamp


if __name__ == "__main__":
    pytest.main([__file__])