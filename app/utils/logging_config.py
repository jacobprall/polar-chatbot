"""Logging configuration for the Polar Prompt Tester application."""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class StreamlitLogHandler(logging.Handler):
    """Custom log handler that can integrate with Streamlit."""
    
    def __init__(self, streamlit_container=None):
        super().__init__()
        self.streamlit_container = streamlit_container
        self.log_buffer = []
        self.max_buffer_size = 100
    
    def emit(self, record):
        """Emit a log record."""
        try:
            msg = self.format(record)
            self.log_buffer.append({
                'timestamp': datetime.fromtimestamp(record.created),
                'level': record.levelname,
                'message': msg,
                'module': record.module,
                'funcName': record.funcName
            })
            
            # Maintain buffer size
            if len(self.log_buffer) > self.max_buffer_size:
                self.log_buffer = self.log_buffer[-self.max_buffer_size:]
            
            # If we have a Streamlit container, display the log
            if self.streamlit_container and record.levelno >= logging.WARNING:
                self._display_in_streamlit(record, msg)
        
        except Exception:
            self.handleError(record)
    
    def _display_in_streamlit(self, record, message):
        """Display log message in Streamlit if appropriate."""
        try:
            import streamlit as st
            
            if record.levelno >= logging.ERROR:
                self.streamlit_container.error(f"🚨 {message}")
            elif record.levelno >= logging.WARNING:
                self.streamlit_container.warning(f"⚠️ {message}")
            elif record.levelno >= logging.INFO:
                self.streamlit_container.info(f"ℹ️ {message}")
        except Exception:
            pass  # Fail silently if Streamlit is not available
    
    def get_recent_logs(self, level: Optional[str] = None, limit: int = 50):
        """Get recent log entries."""
        logs = self.log_buffer[-limit:]
        
        if level:
            level_upper = level.upper()
            logs = [log for log in logs if log['level'] == level_upper]
        
        return logs


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_file_rotation: bool = True,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    streamlit_container=None
) -> StreamlitLogHandler:
    """
    Set up logging configuration for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        enable_console: Whether to enable console logging
        enable_file_rotation: Whether to enable log file rotation
        max_file_size: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
        streamlit_container: Streamlit container for displaying logs
        
    Returns:
        StreamlitLogHandler instance for accessing logs
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        if enable_file_rotation:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count
            )
        else:
            file_handler = logging.FileHandler(log_file)
        
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Streamlit handler
    streamlit_handler = StreamlitLogHandler(streamlit_container)
    streamlit_handler.setLevel(logging.WARNING)  # Only show warnings and errors in UI
    streamlit_handler.setFormatter(formatter)
    root_logger.addHandler(streamlit_handler)
    
    # Set specific logger levels
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized - Level: {log_level}, File: {log_file}")
    
    return streamlit_handler


def get_log_file_path() -> str:
    """Get the default log file path."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d")
    return str(log_dir / f"polar_prompt_tester_{timestamp}.log")


def configure_streamlit_logging(debug_mode: bool = False) -> StreamlitLogHandler:
    """Configure logging specifically for Streamlit application."""
    log_level = "DEBUG" if debug_mode else "INFO"
    log_file = get_log_file_path()
    
    return setup_logging(
        log_level=log_level,
        log_file=log_file,
        enable_console=True,
        enable_file_rotation=True,
        streamlit_container=None  # Will be set later if needed
    )


def display_log_viewer():
    """Display a log viewer in Streamlit."""
    import streamlit as st
    
    st.subheader("📋 Application Logs")
    
    # Get the Streamlit log handler
    streamlit_handler = None
    for handler in logging.getLogger().handlers:
        if isinstance(handler, StreamlitLogHandler):
            streamlit_handler = handler
            break
    
    if not streamlit_handler:
        st.warning("⚠️ Log handler not found")
        return
    
    # Log level filter
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        level_filter = st.selectbox(
            "Filter by Level",
            options=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            index=0
        )
    
    with col2:
        limit = st.number_input("Max Entries", min_value=10, max_value=500, value=50)
    
    with col3:
        if st.button("🔄 Refresh"):
            st.rerun()
    
    # Get logs
    level = None if level_filter == "ALL" else level_filter
    logs = streamlit_handler.get_recent_logs(level=level, limit=limit)
    
    if not logs:
        st.info("📝 No logs found")
        return
    
    # Display logs
    st.markdown("### Recent Log Entries")
    
    for log in reversed(logs):  # Show most recent first
        timestamp = log['timestamp'].strftime("%H:%M:%S")
        level_icon = {
            'DEBUG': '🐛',
            'INFO': 'ℹ️',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨'
        }.get(log['level'], '📝')
        
        with st.expander(
            f"{level_icon} {timestamp} - {log['level']} - {log['message'][:100]}...",
            expanded=False
        ):
            st.write(f"**Time:** {log['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            st.write(f"**Level:** {log['level']}")
            st.write(f"**Module:** {log['module']}")
            st.write(f"**Function:** {log['funcName']}")
            st.write(f"**Message:**")
            st.code(log['message'], language="text")


def get_debug_info() -> dict:
    """Get debug information about the application state."""
    import streamlit as st
    import sys
    import platform
    
    debug_info = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "streamlit_version": st.__version__,
        "session_state_keys": list(st.session_state.keys()) if hasattr(st, 'session_state') else [],
        "environment_variables": {
            key: value for key, value in os.environ.items() 
            if key.startswith(('OPENAI_', 'AWS_', 'STREAMLIT_'))
        }
    }
    
    return debug_info


def display_debug_info():
    """Display debug information in Streamlit."""
    import streamlit as st
    
    st.subheader("🐛 Debug Information")
    
    debug_info = get_debug_info()
    
    with st.expander("🐍 Python & Platform Info", expanded=False):
        st.write(f"**Python Version:** {debug_info['python_version']}")
        st.write(f"**Platform:** {debug_info['platform']}")
        st.write(f"**Streamlit Version:** {debug_info['streamlit_version']}")
    
    with st.expander("🔧 Session State", expanded=False):
        if debug_info['session_state_keys']:
            st.write("**Session State Keys:**")
            for key in debug_info['session_state_keys']:
                st.write(f"• {key}")
        else:
            st.write("No session state keys found")
    
    with st.expander("🌍 Environment Variables", expanded=False):
        if debug_info['environment_variables']:
            for key, value in debug_info['environment_variables'].items():
                # Mask sensitive values
                if 'key' in key.lower() or 'secret' in key.lower():
                    masked_value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
                    st.write(f"**{key}:** {masked_value}")
                else:
                    st.write(f"**{key}:** {value}")
        else:
            st.write("No relevant environment variables found")