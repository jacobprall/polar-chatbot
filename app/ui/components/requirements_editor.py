"""Requirements input interface components."""

import streamlit as st
from typing import Optional, Tuple
import time
from datetime import datetime

from ...models import Session
from ...services.session_manager import SessionManager, SessionManagerError


def render_requirements_editor(session: Session, session_manager: SessionManager) -> bool:
    """
    Render the requirements input interface with auto-save functionality.
    
    Args:
        session: Current session
        session_manager: SessionManager instance
        
    Returns:
        True if requirements were updated
    """
    st.subheader("📝 Requirements Input")
    
    # File upload section
    st.markdown("### 📁 Import Requirements")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Upload requirements document",
            type=['txt', 'md', 'mdx'],
            help="Upload a text file containing your requirements",
            key="requirements_file_upload"
        )
    
    with col2:
        if uploaded_file is not None:
            if st.button("📥 Load File", type="primary"):
                try:
                    # Read file content
                    file_content = uploaded_file.read().decode('utf-8')
                    
                    # Update session requirements
                    session.requirements_text = file_content
                    session.update_timestamp()
                    
                    # Save to storage
                    session_manager.save_session(session)
                    
                    st.success(f"✅ Loaded {len(file_content)} characters from {uploaded_file.name}")
                    
                    # Clear the file uploader
                    st.session_state.requirements_file_upload = None
                    
                    # Force refresh
                    time.sleep(0.5)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Failed to load file: {str(e)}")
    
    st.markdown("---")
    
    # Text editor section
    st.markdown("### ✏️ Requirements Editor")
    
    # Auto-save status indicator
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown("*Auto-save is enabled - changes are saved automatically*")
    
    with col2:
        # Character count
        char_count = len(session.requirements_text)
        st.metric("Characters", f"{char_count:,}")
    
    with col3:
        # Word count (approximate)
        word_count = len(session.requirements_text.split()) if session.requirements_text else 0
        st.metric("Words", f"{word_count:,}")
    
    # Main text editor
    requirements_key = f"requirements_editor_{session.id}"
    
    # Initialize session state for this editor if not exists
    if requirements_key not in st.session_state:
        st.session_state[requirements_key] = session.requirements_text
    
    # Text area with auto-save
    new_requirements = st.text_area(
        "Requirements Text",
        value=st.session_state[requirements_key],
        height=400,
        placeholder="""Enter your requirements here. For example:

As a user, I want to be able to authenticate with the system, so that I can access protected resources.

Acceptance Criteria:
- Users must be able to log in with email and password
- Invalid credentials should show appropriate error messages
- Successful login should redirect to the dashboard
- Session should expire after 24 hours of inactivity

Additional Requirements:
- Support for password reset functionality
- Two-factor authentication for enhanced security
- Remember me option for convenience""",
        help="Enter detailed requirements that will be used to generate Polar policies",
        key=f"requirements_text_{session.id}"
    )
    
    # Auto-save logic
    requirements_updated = False
    if new_requirements != st.session_state[requirements_key]:
        st.session_state[requirements_key] = new_requirements
        
        # Update session
        session.requirements_text = new_requirements
        session.update_timestamp()
        
        # Auto-save with debouncing
        if f"last_save_{session.id}" not in st.session_state:
            st.session_state[f"last_save_{session.id}"] = 0
        
        current_time = time.time()
        if current_time - st.session_state[f"last_save_{session.id}"] > 2:  # 2 second debounce
            try:
                session_manager.save_session(session)
                st.session_state[f"last_save_{session.id}"] = current_time
                requirements_updated = True
                
                # Show brief save confirmation
                with st.empty():
                    st.success("💾 Auto-saved")
                    time.sleep(1)
                    
            except SessionManagerError as e:
                st.error(f"❌ Auto-save failed: {str(e)}")
    
    # Manual save and clear buttons
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        if st.button("💾 Save Now", help="Manually save requirements"):
            try:
                session.requirements_text = new_requirements
                session.update_timestamp()
                session_manager.save_session(session)
                st.success("✅ Requirements saved successfully")
                requirements_updated = True
            except SessionManagerError as e:
                st.error(f"❌ Save failed: {str(e)}")
    
    with col2:
        if st.button("🔄 Reload", help="Reload requirements from storage"):
            try:
                # Reload session from storage
                reloaded_session = session_manager.load_session(session.id)
                st.session_state[requirements_key] = reloaded_session.requirements_text
                st.success("✅ Requirements reloaded")
                st.rerun()
            except SessionManagerError as e:
                st.error(f"❌ Reload failed: {str(e)}")
    
    with col3:
        if st.button("📋 Copy Text", help="Copy requirements to clipboard"):
            # Note: Streamlit doesn't have direct clipboard access
            # This would need a JavaScript component for full functionality
            st.info("💡 Use Ctrl+A, Ctrl+C to copy all text")
    
    with col4:
        if st.button("🗑️ Clear All", help="Clear all requirements text", type="secondary"):
            st.session_state.show_clear_dialog = True
    
    # Clear confirmation dialog
    if st.session_state.get("show_clear_dialog", False):
        with st.expander("🗑️ Clear Requirements", expanded=True):
            st.warning("Are you sure you want to clear all requirements text?")
            st.error("This action cannot be undone!")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("❌ Yes, Clear All", type="primary"):
                    session.requirements_text = ""
                    st.session_state[requirements_key] = ""
                    session.update_timestamp()
                    
                    try:
                        session_manager.save_session(session)
                        st.success("✅ Requirements cleared")
                        st.session_state.show_clear_dialog = False
                        requirements_updated = True
                        st.rerun()
                    except SessionManagerError as e:
                        st.error(f"❌ Failed to clear requirements: {str(e)}")
            
            with col2:
                if st.button("Cancel"):
                    st.session_state.show_clear_dialog = False
                    st.rerun()
    
    # Requirements preview section
    if session.requirements_text:
        st.markdown("---")
        st.markdown("### 👀 Requirements Preview")
        
        with st.expander("View formatted requirements", expanded=False):
            # Display requirements with basic markdown formatting
            st.markdown(session.requirements_text)
    
    # Requirements analysis section
    if session.requirements_text:
        st.markdown("---")
        st.markdown("### 📊 Requirements Analysis")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Line count
            line_count = len(session.requirements_text.split('\n'))
            st.metric("Lines", line_count)
        
        with col2:
            # Paragraph count (empty lines as separators)
            paragraphs = [p.strip() for p in session.requirements_text.split('\n\n') if p.strip()]
            st.metric("Paragraphs", len(paragraphs))
        
        with col3:
            # Bullet points count
            bullet_count = session.requirements_text.count('- ') + session.requirements_text.count('* ')
            st.metric("Bullet Points", bullet_count)
        
        with col4:
            # Estimated reading time (average 200 words per minute)
            reading_time = max(1, word_count // 200)
            st.metric("Read Time", f"{reading_time} min")
        
        # Content quality indicators
        with st.expander("📋 Content Quality Indicators", expanded=False):
            quality_checks = []
            
            # Check for user stories
            if "as a" in session.requirements_text.lower() or "as an" in session.requirements_text.lower():
                quality_checks.append("✅ Contains user stories")
            else:
                quality_checks.append("⚠️ No user stories detected")
            
            # Check for acceptance criteria
            if "acceptance criteria" in session.requirements_text.lower() or "criteria:" in session.requirements_text.lower():
                quality_checks.append("✅ Contains acceptance criteria")
            else:
                quality_checks.append("⚠️ No acceptance criteria detected")
            
            # Check for requirements structure
            if any(keyword in session.requirements_text.lower() for keyword in ["shall", "must", "should", "when", "then"]):
                quality_checks.append("✅ Contains structured requirements")
            else:
                quality_checks.append("⚠️ Consider adding structured requirements (WHEN/THEN format)")
            
            # Check for length
            if word_count > 50:
                quality_checks.append("✅ Sufficient detail provided")
            else:
                quality_checks.append("⚠️ Requirements might need more detail")
            
            for check in quality_checks:
                st.write(check)
    
    return requirements_updated


def render_requirements_templates() -> Optional[str]:
    """
    Render requirements templates section.
    
    Returns:
        Selected template content or None
    """
    st.markdown("### 📋 Requirements Templates")
    
    templates = {
        "Authentication System": """As a user, I want to authenticate with the system, so that I can access protected resources.

Acceptance Criteria:
- WHEN a user provides valid credentials THEN the system SHALL authenticate the user
- WHEN a user provides invalid credentials THEN the system SHALL display an error message
- WHEN a user is authenticated THEN the system SHALL create a session
- WHEN a session expires THEN the system SHALL require re-authentication

Additional Requirements:
- Support for password reset functionality
- Two-factor authentication for enhanced security
- Session timeout after 24 hours of inactivity""",
        
        "Document Management": """As a user, I want to manage documents in the system, so that I can organize and control access to my files.

Acceptance Criteria:
- WHEN a user uploads a document THEN the system SHALL store it securely
- WHEN a user sets document permissions THEN the system SHALL enforce those permissions
- WHEN a user shares a document THEN the system SHALL notify the recipient
- WHEN a user deletes a document THEN the system SHALL remove it permanently

Additional Requirements:
- Version control for document updates
- Audit trail for all document operations
- Support for multiple file formats""",
        
        "API Access Control": """As a developer, I want to control API access, so that I can secure my application endpoints.

Acceptance Criteria:
- WHEN an API request is made THEN the system SHALL validate the API key
- WHEN a user exceeds rate limits THEN the system SHALL return a 429 error
- WHEN accessing protected endpoints THEN the system SHALL verify permissions
- WHEN an unauthorized request is made THEN the system SHALL log the attempt

Additional Requirements:
- Role-based access control for different API endpoints
- Request logging and monitoring
- Support for OAuth 2.0 authentication""",
        
        "Custom Template": "Enter your own requirements here..."
    }
    
    selected_template = st.selectbox(
        "Choose a template to get started:",
        options=list(templates.keys()),
        help="Select a template to populate the requirements editor"
    )
    
    if selected_template and selected_template != "Custom Template":
        with st.expander(f"Preview: {selected_template}", expanded=False):
            st.markdown(templates[selected_template])
        
        if st.button(f"📋 Use {selected_template} Template", type="primary"):
            return templates[selected_template]
    
    return None