#!/usr/bin/env python3
"""
Debug script to test session loading
"""

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from app.services.session_manager import SessionManager
from app.storage.local_storage import LocalStorageBackend

def debug_session_loading():
    """Debug session loading"""
    storage = LocalStorageBackend("./test_sessions")
    session_manager = SessionManager(storage)
    
    # Debug storage layer directly with different patterns
    print("Debugging storage layer...")
    
    # Try different prefix patterns
    patterns_to_try = ["", "sessions", "sessions/"]
    for pattern in patterns_to_try:
        print(f"\nTrying pattern: '{pattern}'")
        result = storage.list_objects(pattern)
        objects = result.get('objects', [])
        print(f"  Found {len(objects)} objects")
        for obj in objects[:5]:  # Show first 5
            print(f"    - {obj.key}")
    
    # Check if we can directly access a known file
    print(f"\nTesting direct file access...")
    try:
        obj = storage.get_object("sessions/c02af5e8-c023-43c4-a060-054d26cf01d2/metadata.json")
        print(f"  Successfully accessed metadata file: {len(obj.content)} chars")
    except Exception as e:
        print(f"  Failed to access metadata file: {e}")
    
    # Debug session storage layer
    print("\nDebugging session storage layer...")
    storage_sessions = session_manager.session_storage.list_sessions()
    print(f"Storage sessions found: {len(storage_sessions)}")
    for session in storage_sessions:
        print(f"  - {session.id}: {session.name}")
    
    # List sessions through session manager
    sessions = session_manager.list_sessions()
    print(f"\nSession manager found {len(sessions)} sessions")
    
    if sessions:
        session_id = sessions[0].id
        print(f"Loading session: {session_id}")
        
        # Debug the session storage file listing
        session_files = session_manager.session_storage.list_session_files(session_id)
        print(f"Session files: {session_files}")
        
        # Check for policy files specifically
        policy_files = [f for f in session_files if f.startswith("policies/") and f.endswith(".polar")]
        print(f"Policy files found: {policy_files}")
        
        # Check for validation files
        validation_files = [f for f in session_files if f.startswith("validation_results/") and f.endswith(".json")]
        print(f"Validation files found: {validation_files}")
        
        # Load the session
        session = session_manager.load_session(session_id)
        print(f"Loaded session with {len(session.generated_policies)} policies and {len(session.validation_results)} validation results")

if __name__ == "__main__":
    debug_session_loading()