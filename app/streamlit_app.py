"""Main Streamlit application entry point for Polar Prompt Tester."""

import streamlit as st
from typing import Optional
import traceback

from app.models import get_config, Session
from app.services.session_manager import SessionManager, SessionManagerError
from app.storage.local_storage import LocalStorageBackend
from app.ui.components.session_selector import (
    render_session_selector, render_session_header, handle_session_deletion
)


def initialize_session_manager() -> SessionManager:
    """Initialize and cache the session manager."""
    if "session_manager" not in st.session_state:
        config = get_config()
        
        # Initialize storage backend based on configuration
        if config.storage.type == "local":
            storage_backend = LocalStorageBackend(config.storage.path)
        else:
            # S3 backend would be initialized here
            st.error("S3 storage backend not yet implemented")
            storage_backend = LocalStorageBackend(config.storage.path)
        
        st.session_state.session_manager = SessionManager(storage_backend)
    
    return st.session_state.session_manager


def load_current_session(session_manager: SessionManager, session_id: str) -> Optional[Session]:
    """Load and cache the current session."""
    cache_key = f"session_{session_id}"
    
    # Check if session is already cached and up to date
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    
    try:
        session = session_manager.load_session(session_id)
        st.session_state[cache_key] = session
        return session
    except SessionManagerError as e:
        st.error(f"❌ Failed to load session: {str(e)}")
        return None


def clear_session_cache(session_id: str) -> None:
    """Clear cached session data to force reload."""
    cache_key = f"session_{session_id}"
    if cache_key in st.session_state:
        del st.session_state[cache_key]


def render_session_workspace(session: Session, session_manager: SessionManager) -> None:
    """
    Render the main session workspace with tabs.
    
    Args:
        session: Current session
        session_manager: SessionManager instance
    """
    # Session header
    render_session_header(session)
    
    # Handle session deletion
    if st.session_state.get("show_delete_dialog", False):
        if handle_session_deletion(session_manager, session.id):
            return  # Session was deleted, return to session selection
    
    # Main workspace tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📝 Requirements", 
        "🔧 Policy Generation", 
        "✅ Validation Results", 
        "📋 Notes", 
        "📊 Session History"
    ])
    
    with tab1:
        from app.ui.components.requirements_editor import render_requirements_editor, render_requirements_templates
        
        # Check if user wants to use a template
        if not session.requirements_text or st.button("📋 Use Template", help="Load a requirements template"):
            template_content = render_requirements_templates()
            if template_content:
                session.requirements_text = template_content
                session.update_timestamp()
                try:
                    session_manager.save_session(session)
                    st.success("✅ Template loaded successfully")
                    clear_session_cache(session.id)  # Force reload
                    st.rerun()
                except SessionManagerError as e:
                    st.error(f"❌ Failed to save template: {str(e)}")
        
        # Render the requirements editor
        if render_requirements_editor(session, session_manager):
            # Requirements were updated, clear cache to force reload
            clear_session_cache(session.id)
    
    with tab2:
        st.info("🔧 Policy generation interface will be implemented in subtask 6.3.")
        
        # Show current policies if any
        if session.generated_policies:
            st.subheader(f"Generated Policies ({len(session.generated_policies)})")
            for i, policy in enumerate(session.generated_policies):
                with st.expander(f"Policy {i+1} - {policy.model_used} ({policy.generated_at.strftime('%Y-%m-%d %H:%M')})"):
                    st.code(policy.content, language="text")
        else:
            st.info("No policies have been generated for this session yet.")
    
    with tab3:
        st.info("✅ Validation results interface will be implemented in subtask 6.4.")
        
        # Show validation results if any
        if session.validation_results:
            st.subheader(f"Validation Results ({len(session.validation_results)})")
            for result in session.validation_results:
                status_icon = "✅" if result.is_valid else "❌"
                st.write(f"{status_icon} **Policy {result.policy_id}** - {result.validated_at.strftime('%Y-%m-%d %H:%M')}")
                if result.error_message:
                    st.error(result.error_message)
        else:
            st.info("No validation results available for this session yet.")
    
    with tab4:
        st.info("📋 Notes interface will be implemented in subtask 6.5.")
        
        # Show current notes if any
        if session.notes:
            st.text_area(
                "Current Notes",
                value=session.notes,
                height=200,
                disabled=True
            )
        else:
            st.info("No notes have been added to this session yet.")
    
    with tab5:
        st.info("📊 Session history interface will be implemented in subtask 6.5.")
        
        # Basic session statistics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Requirements", "Yes" if session.requirements_text else "No")
        
        with col2:
            st.metric("Generated Policies", len(session.generated_policies))
        
        with col3:
            st.metric("Validation Results", len(session.validation_results))


def main():
    """Main Streamlit application."""
    # Load configuration
    config = get_config()
    
    # Set page configuration
    st.set_page_config(
        page_title=config.streamlit.title,
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session manager
    try:
        session_manager = initialize_session_manager()
    except Exception as e:
        st.error(f"❌ Failed to initialize application: {str(e)}")
        st.code(traceback.format_exc())
        return
    
    # Main application header
    st.title(config.streamlit.title)
    st.markdown("*Interactive Polar policy generation and testing*")
    
    # Check for selected session
    selected_session_id = st.session_state.get("selected_session_id")
    
    if not selected_session_id:
        # Show session selection interface
        st.markdown("---")
        selected_session_id = render_session_selector(session_manager)
    
    if selected_session_id:
        # Load and display the selected session
        current_session = load_current_session(session_manager, selected_session_id)
        
        if current_session:
            # Add session navigation in sidebar
            with st.sidebar:
                st.markdown("### 🎯 Current Session")
                st.write(f"**{current_session.name}**")
                st.caption(f"ID: {current_session.id[:8]}...")
                
                if st.button("🔙 Back to Session List", type="secondary"):
                    # Clear selected session and reload
                    if "selected_session_id" in st.session_state:
                        del st.session_state.selected_session_id
                    clear_session_cache(selected_session_id)
                    st.rerun()
                
                st.markdown("---")
                
                # Quick session stats
                st.markdown("### 📊 Quick Stats")
                st.metric("Requirements", "✅" if current_session.requirements_text else "❌")
                st.metric("Policies", len(current_session.generated_policies))
                st.metric("Validations", len(current_session.validation_results))
            
            # Render main session workspace
            render_session_workspace(current_session, session_manager)
        else:
            # Failed to load session, go back to selection
            if "selected_session_id" in st.session_state:
                del st.session_state.selected_session_id
            st.rerun()
    else:
        # Show welcome message when no session is selected
        st.markdown("---")
        st.info("👆 Select an existing session or create a new one to get started!")
        
        # Show application status in sidebar
        with st.sidebar:
            st.markdown("### ⚙️ Application Status")
            
            try:
                stats = session_manager.get_session_statistics()
                st.metric("Total Sessions", stats["total_sessions"])
                st.metric("Sessions with Policies", stats["sessions_with_policies"])
                st.metric("Total Policies", stats["total_policies"])
            except SessionManagerError:
                st.warning("Unable to load statistics")
            
            st.markdown("---")
            
            # Configuration info
            with st.expander("🔧 Configuration"):
                st.json({
                    "storage_type": config.storage.type,
                    "storage_path": config.storage.path,
                    "max_sessions": config.sessions.max_sessions,
                    "openai_model": config.openai.model
                })


if __name__ == "__main__":
    main()