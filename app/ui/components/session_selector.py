"""Session selection and creation UI components."""

import streamlit as st
from typing import Optional, List
from datetime import datetime

from ...models import Session, SessionMetadata
from ...services.session_manager import SessionManager, SessionManagerError


def render_session_selector(session_manager: SessionManager) -> Optional[str]:
    """
    Render session selection interface.
    
    Args:
        session_manager: SessionManager instance
        
    Returns:
        Selected session ID or None
    """
    st.subheader("📁 Session Management")
    
    # Create two columns for session actions
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Session creation
        with st.expander("➕ Create New Session", expanded=False):
            with st.form("create_session_form"):
                session_name = st.text_input(
                    "Session Name",
                    placeholder="Enter a descriptive name for your session",
                    help="Choose a name that describes your testing scenario"
                )
                session_description = st.text_area(
                    "Description (Optional)",
                    placeholder="Brief description of what you're testing",
                    height=80
                )
                
                create_button = st.form_submit_button("Create Session", type="primary")
                
                if create_button:
                    if session_name and session_name.strip():
                        try:
                            new_session = session_manager.create_session(
                                session_name.strip(), 
                                session_description.strip()
                            )
                            st.success(f"✅ Created session: {new_session.name}")
                            st.session_state.selected_session_id = new_session.id
                            st.rerun()
                        except SessionManagerError as e:
                            st.error(f"❌ Failed to create session: {str(e)}")
                    else:
                        st.error("❌ Session name is required")
    
    with col2:
        # Session statistics
        try:
            stats = session_manager.get_session_statistics()
            st.metric("Total Sessions", stats["total_sessions"])
            st.metric("With Policies", stats["sessions_with_policies"])
        except SessionManagerError:
            st.warning("Unable to load session statistics")
    
    # Session listing and selection
    st.markdown("### 📋 Existing Sessions")
    
    try:
        sessions = session_manager.list_sessions(limit=50)
        
        if not sessions:
            st.info("No sessions found. Create your first session above!")
            return None
        
        # Search functionality
        search_term = st.text_input(
            "🔍 Search Sessions",
            placeholder="Search by session name...",
            key="session_search"
        )
        
        # Filter sessions based on search
        if search_term:
            filtered_sessions = [
                s for s in sessions 
                if search_term.lower() in s.name.lower()
            ]
        else:
            filtered_sessions = sessions
        
        if not filtered_sessions:
            st.warning("No sessions match your search criteria.")
            return None
        
        # Display sessions in a more compact format
        selected_session_id = None
        
        for session in filtered_sessions[:20]:  # Limit to 20 for performance
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    # Session name and metadata
                    st.markdown(f"**{session.name}**")
                    st.caption(f"Created: {session.created_at.strftime('%Y-%m-%d %H:%M')}")
                
                with col2:
                    # Status indicators
                    if session.has_requirements:
                        st.success("📝 Req")
                    else:
                        st.warning("📝 No Req")
                
                with col3:
                    # Policy count
                    if session.has_policies:
                        st.info(f"🔧 {session.policy_count}")
                    else:
                        st.warning("🔧 0")
                
                with col4:
                    # Select button
                    if st.button(
                        "Select", 
                        key=f"select_{session.id}",
                        type="primary" if st.session_state.get("selected_session_id") == session.id else "secondary"
                    ):
                        selected_session_id = session.id
                        st.session_state.selected_session_id = session.id
                        st.rerun()
                
                st.divider()
        
        return selected_session_id or st.session_state.get("selected_session_id")
        
    except SessionManagerError as e:
        st.error(f"❌ Failed to load sessions: {str(e)}")
        return None


def render_session_header(session: Session) -> None:
    """
    Render the header for the selected session.
    
    Args:
        session: Current session
    """
    st.markdown("---")
    
    # Session header with metadata
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown(f"## 🎯 {session.name}")
        st.caption(f"Session ID: `{session.id}`")
    
    with col2:
        st.metric(
            "Policies Generated", 
            len(session.generated_policies),
            help="Total number of policies generated in this session"
        )
    
    with col3:
        # Last updated
        time_diff = datetime.utcnow() - session.updated_at
        if time_diff.days > 0:
            updated_str = f"{time_diff.days} days ago"
        elif time_diff.seconds > 3600:
            updated_str = f"{time_diff.seconds // 3600} hours ago"
        elif time_diff.seconds > 60:
            updated_str = f"{time_diff.seconds // 60} minutes ago"
        else:
            updated_str = "Just now"
        
        st.metric("Last Updated", updated_str)
    
    # Session actions
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        if st.button("🔄 Refresh Session", help="Reload session data"):
            st.rerun()
    
    with col2:
        if st.button("📋 Session Info", help="View detailed session information"):
            st.session_state.show_session_info = True
    
    with col3:
        if st.button("📤 Export Session", help="Export session data"):
            st.session_state.show_export_dialog = True
    
    with col4:
        if st.button("🗑️ Delete Session", help="Delete this session", type="secondary"):
            st.session_state.show_delete_dialog = True
    
    # Handle session info dialog
    if st.session_state.get("show_session_info", False):
        with st.expander("📋 Session Information", expanded=True):
            st.json({
                "id": session.id,
                "name": session.name,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "has_requirements": bool(session.requirements_text.strip()),
                "policy_count": len(session.generated_policies),
                "validation_count": len(session.validation_results),
                "notes_length": len(session.notes)
            })
            
            if st.button("Close Info"):
                st.session_state.show_session_info = False
                st.rerun()
    
    # Handle export dialog
    if st.session_state.get("show_export_dialog", False):
        with st.expander("📤 Export Session", expanded=True):
            st.info("Export functionality will be implemented in a future update.")
            if st.button("Close Export"):
                st.session_state.show_export_dialog = False
                st.rerun()
    
    # Handle delete dialog
    if st.session_state.get("show_delete_dialog", False):
        with st.expander("🗑️ Delete Session", expanded=True):
            st.warning(f"Are you sure you want to delete session '{session.name}'?")
            st.error("This action cannot be undone!")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("❌ Yes, Delete", type="primary"):
                    st.session_state.delete_confirmed = True
            with col2:
                if st.button("Cancel"):
                    st.session_state.show_delete_dialog = False
                    st.rerun()
    
    st.markdown("---")


def handle_session_deletion(session_manager: SessionManager, session_id: str) -> bool:
    """
    Handle session deletion with confirmation.
    
    Args:
        session_manager: SessionManager instance
        session_id: ID of session to delete
        
    Returns:
        True if session was deleted
    """
    if st.session_state.get("delete_confirmed", False):
        try:
            session_manager.delete_session(session_id)
            st.success("✅ Session deleted successfully")
            
            # Clear session state
            if "selected_session_id" in st.session_state:
                del st.session_state.selected_session_id
            if "delete_confirmed" in st.session_state:
                del st.session_state.delete_confirmed
            if "show_delete_dialog" in st.session_state:
                del st.session_state.show_delete_dialog
            
            st.rerun()
            return True
            
        except SessionManagerError as e:
            st.error(f"❌ Failed to delete session: {str(e)}")
            st.session_state.delete_confirmed = False
    
    return False