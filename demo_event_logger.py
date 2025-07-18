#!/usr/bin/env python3
"""
Demonstration script for the EventLogger functionality.

This script shows how to use the EventLogger to:
1. Log session events
2. Retrieve and filter events
3. Replay session state from events
4. Get session timeline and statistics
"""

import tempfile
import shutil
from datetime import datetime

from app.services.event_logger import EventLogger
from app.models.events import (
    create_session_created_event,
    create_requirements_edited_event,
    create_policy_generated_event,
    create_validation_completed_event,
    create_notes_added_event
)
# EventConfig removed - using simple defaults
from app.storage.local_storage import LocalStorageBackend


def main():
    """Demonstrate EventLogger functionality."""
    print("🎯 EventLogger Demonstration")
    print("=" * 50)
    
    # Create temporary storage
    temp_dir = tempfile.mkdtemp()
    print(f"📁 Using temporary storage: {temp_dir}")
    
    try:
        # Initialize EventLogger
        storage = LocalStorageBackend(temp_dir)
        event_logger = EventLogger(storage)
        
        session_id = "demo-session-123"
        
        print(f"\n📝 Creating events for session: {session_id}")
        
        # Create a sequence of events
        events = [
            create_session_created_event(session_id, "Demo Session"),
            create_requirements_edited_event(session_id, 450),
            create_policy_generated_event(session_id, "policy-1", "gpt-4", 1200, 2.5),
            create_validation_completed_event(session_id, "policy-1", False, "Syntax error on line 5", 0.8),
            create_policy_generated_event(session_id, "policy-2", "gpt-4", 1350, 3.1),
            create_validation_completed_event(session_id, "policy-2", True, None, 0.9),
            create_notes_added_event(session_id, 150)
        ]
        
        # Log events
        print(f"📊 Logging {len(events)} events...")
        event_logger.log_events(events)
        
        # Retrieve all events
        print(f"\n🔍 Retrieving all events for session {session_id}:")
        all_events = event_logger.get_all_events(session_id)
        for i, event in enumerate(all_events, 1):
            print(f"  {i}. {event.event_type.value} at {event.timestamp.strftime('%H:%M:%S')}")
        
        # Filter events by type
        print(f"\n🎯 Filtering events by type (POLICY_GENERATED):")
        policy_events = event_logger.get_events(session_id, event_types=[event.event_type for event in events if "POLICY" in event.event_type.value])
        for event in policy_events:
            print(f"  - {event.event_type.value}: {event.data}")
        
        # Get session timeline
        print(f"\n📅 Session timeline:")
        timeline = event_logger.get_session_timeline(session_id)
        for entry in timeline:
            print(f"  {entry['timestamp'][:19]} | {entry['summary']}")
        
        # Replay session state
        print(f"\n🔄 Replaying session state from events:")
        replayed_session = event_logger.replay_session(session_id)
        print(f"  Session ID: {replayed_session.id}")
        print(f"  Session Name: {replayed_session.name}")
        print(f"  Created: {replayed_session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Updated: {replayed_session.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Generated Policies: {len(replayed_session.generated_policies)}")
        print(f"  Validation Results: {len(replayed_session.validation_results)}")
        
        # Show policy details
        if replayed_session.generated_policies:
            current_policy = replayed_session.get_current_policy()
            if current_policy:
                print(f"  Current Policy: {current_policy.id} (generated with {current_policy.model_used})")
        
        # Show validation results
        if replayed_session.validation_results:
            latest_validation = replayed_session.validation_results[-1]
            status = "✅ Valid" if latest_validation.is_valid else "❌ Invalid"
            print(f"  Latest Validation: {status}")
            if latest_validation.error_message:
                print(f"    Error: {latest_validation.error_message}")
        
        # Validate event integrity
        print(f"\n🔒 Validating event integrity:")
        integrity = event_logger.validate_event_integrity(session_id)
        status = "✅ Valid" if integrity["is_valid"] else "❌ Invalid"
        print(f"  Status: {status}")
        print(f"  Event Count: {integrity['event_count']}")
        if integrity["issues"]:
            print(f"  Issues: {', '.join(integrity['issues'])}")
        
        # Get statistics
        print(f"\n📈 Event storage statistics:")
        stats = event_logger.get_event_statistics()
        print(f"  Sessions with events: {stats['total_sessions_with_events']}")
        print(f"  Estimated total events: {stats['estimated_total_events']}")
        print(f"  Storage backend: {stats['storage_backend']}")
        
        print(f"\n✅ EventLogger demonstration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        raise
    
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print(f"🧹 Cleaned up temporary storage")


if __name__ == "__main__":
    main()