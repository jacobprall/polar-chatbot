"""
Integration tests for EventLogger with other components.
"""

import pytest
import tempfile
import shutil
from datetime import datetime

from app.services.event_logger import EventLogger
from app.services.session_manager import SessionManager
from app.models.events import EventType, create_session_created_event
from app.models.config import EventConfig
from app.storage.local_storage import LocalStorageBackend


class TestEventLoggerIntegration:
    """Integration tests for EventLogger with other components."""
    
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
        config = EventConfig(batch_size=5, retention_days=30)
        return EventLogger(temp_storage, config)
    
    @pytest.fixture
    def session_manager(self, temp_storage):
        """Create a SessionManager instance for testing."""
        return SessionManager(temp_storage)
    
    def test_event_logger_with_session_manager(self, event_logger, session_manager):
        """Test EventLogger integration with SessionManager."""
        # Create a session using SessionManager
        session = session_manager.create_session("Integration Test Session")
        
        # Log session creation event
        session_created_event = create_session_created_event(
            session_id=session.id,
            session_name=session.name
        )
        
        result = event_logger.log_event(session_created_event)
        assert result is True
        
        # Flush events to storage
        event_logger.flush_pending_events()
        
        # Retrieve events and verify
        events = event_logger.get_events(session.id)
        assert len(events) == 1
        assert events[0].event_type == EventType.SESSION_CREATED
        assert events[0].session_id == session.id
        
        # Test session replay
        replayed_session = event_logger.replay_session(session.id)
        assert replayed_session.id == session.id
        assert replayed_session.name == session.name
    
    def test_event_logger_storage_consistency(self, event_logger):
        """Test that EventLogger maintains storage consistency."""
        session_id = "consistency-test-session"
        
        # Create multiple events
        events = [
            create_session_created_event(session_id, "Consistency Test"),
        ]
        
        # Log events
        event_logger.log_events(events)
        
        # Verify events can be retrieved
        retrieved_events = event_logger.get_events(session_id)
        assert len(retrieved_events) == len(events)
        
        # Verify event integrity
        integrity = event_logger.validate_event_integrity(session_id)
        assert integrity["is_valid"] is True
        assert integrity["event_count"] == len(events)
    
    def test_event_logger_statistics(self, event_logger):
        """Test EventLogger statistics functionality."""
        # Create some test events
        session_ids = ["stats-test-1", "stats-test-2"]
        
        for session_id in session_ids:
            event = create_session_created_event(session_id, f"Stats Test {session_id}")
            event_logger.log_event(event)
        
        event_logger.flush_pending_events()
        
        # Get statistics
        stats = event_logger.get_event_statistics()
        
        assert "total_sessions_with_events" in stats
        assert "estimated_total_events" in stats
        assert stats["total_sessions_with_events"] >= len(session_ids)
    
    def test_event_logger_timeline(self, event_logger):
        """Test EventLogger timeline functionality."""
        session_id = "timeline-test-session"
        
        # Create session event
        event = create_session_created_event(session_id, "Timeline Test")
        event_logger.log_event(event)
        event_logger.flush_pending_events()
        
        # Get timeline
        timeline = event_logger.get_session_timeline(session_id)
        
        assert len(timeline) == 1
        assert timeline[0]["event_type"] == "SessionCreated"
        assert "timestamp" in timeline[0]
        assert "summary" in timeline[0]
        assert "Session 'Timeline Test' created" in timeline[0]["summary"]


if __name__ == "__main__":
    pytest.main([__file__])