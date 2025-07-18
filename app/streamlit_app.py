"""Main Streamlit application entry point for Polar Prompt Tester."""

import streamlit as st
from app.models import get_config

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
    
    # Main title
    st.title(config.streamlit.title)
    st.markdown("---")
    
    # Placeholder for main application content
    st.info("🚧 Application under development. Core data models and configuration are ready!")
    
    # Display configuration status
    with st.expander("Configuration Status"):
        st.json({
            "streamlit": {
                "title": config.streamlit.title,
                "port": config.streamlit.port,
                "theme": config.streamlit.theme
            },
            "storage": {
                "type": config.storage.type,
                "path": config.storage.path
            },
            "sessions": {
                "max_sessions": config.sessions.max_sessions,
                "auto_save_interval": config.sessions.auto_save_interval
            }
        })

if __name__ == "__main__":
    main()