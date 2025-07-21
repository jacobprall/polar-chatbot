"""Streamlit-specific error handling components and utilities."""

import streamlit as st
import logging
import traceback
from typing import Optional, Dict, Any, Callable, Union
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for UI display."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better organization."""
    VALIDATION = "validation"
    GENERATION = "generation"
    STORAGE = "storage"
    SESSION = "session"
    NETWORK = "network"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for errors."""
    session_id: Optional[str] = None
    user_action: Optional[str] = None
    component: Optional[str] = None
    timestamp: datetime = None
    additional_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.additional_data is None:
            self.additional_data = {}


@dataclass
class StreamlitError:
    """Structured error information for Streamlit display."""
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    exception: Optional[Exception] = None
    recovery_actions: Optional[list[str]] = None
    show_details: bool = False
    
    def get_icon(self) -> str:
        """Get appropriate icon for error severity."""
        icons = {
            ErrorSeverity.INFO: "ℹ️",
            ErrorSeverity.WARNING: "⚠️",
            ErrorSeverity.ERROR: "❌",
            ErrorSeverity.CRITICAL: "🚨"
        }
        return icons.get(self.severity, "❓")
    
    def get_color(self) -> str:
        """Get appropriate color for error severity."""
        colors = {
            ErrorSeverity.INFO: "blue",
            ErrorSeverity.WARNING: "orange", 
            ErrorSeverity.ERROR: "red",
            ErrorSeverity.CRITICAL: "red"
        }
        return colors.get(self.severity, "gray")


class StreamlitErrorHandler:
    """Main error handler for Streamlit applications."""
    
    def __init__(self, enable_debug: bool = False):
        self.enable_debug = enable_debug
        self.error_history = []
        self.max_history = 100
    
    def handle_error(self, error: Union[Exception, StreamlitError], 
                    context: Optional[ErrorContext] = None,
                    show_immediately: bool = True) -> StreamlitError:
        """
        Handle an error and optionally display it immediately.
        
        Args:
            error: Exception or StreamlitError to handle
            context: Additional context information
            show_immediately: Whether to display the error immediately
            
        Returns:
            StreamlitError object for further handling
        """
        if isinstance(error, StreamlitError):
            streamlit_error = error
        else:
            streamlit_error = self._convert_exception_to_error(error, context)
        
        # Log the error
        self._log_error(streamlit_error)
        
        # Add to history
        self._add_to_history(streamlit_error)
        
        # Display immediately if requested
        if show_immediately:
            self.display_error(streamlit_error)
        
        return streamlit_error
    
    def display_error(self, error: StreamlitError, container=None) -> None:
        """
        Display an error in the Streamlit UI.
        
        Args:
            error: StreamlitError to display
            container: Optional Streamlit container to display in
        """
        display_container = container or st
        
        # Choose display method based on severity
        if error.severity == ErrorSeverity.INFO:
            display_container.info(f"{error.get_icon()} {error.message}")
        elif error.severity == ErrorSeverity.WARNING:
            display_container.warning(f"{error.get_icon()} {error.message}")
        elif error.severity in [ErrorSeverity.ERROR, ErrorSeverity.CRITICAL]:
            display_container.error(f"{error.get_icon()} {error.message}")
        
        # Show recovery actions if available
        if error.recovery_actions:
            with display_container.expander("🔧 Suggested Actions", expanded=False):
                for i, action in enumerate(error.recovery_actions, 1):
                    st.write(f"{i}. {action}")
        
        # Show error details if enabled and available
        if error.show_details and (error.exception or error.context.additional_data):
            with display_container.expander("🔍 Error Details", expanded=False):
                if error.exception:
                    st.code(str(error.exception), language="text")
                    if self.enable_debug:
                        st.code(traceback.format_exc(), language="text")
                
                if error.context.additional_data:
                    st.json(error.context.additional_data)
    
    def display_error_summary(self, container=None) -> None:
        """Display a summary of recent errors."""
        display_container = container or st
        
        if not self.error_history:
            display_container.success("✅ No recent errors")
            return
        
        recent_errors = self.error_history[-10:]  # Last 10 errors
        
        display_container.subheader("📊 Recent Errors")
        
        for i, error in enumerate(reversed(recent_errors), 1):
            with display_container.expander(
                f"{error.get_icon()} {error.category.value.title()}: {error.message[:50]}...",
                expanded=False
            ):
                st.write(f"**Time:** {error.context.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                st.write(f"**Severity:** {error.severity.value.title()}")
                st.write(f"**Category:** {error.category.value.title()}")
                if error.context.component:
                    st.write(f"**Component:** {error.context.component}")
                if error.context.user_action:
                    st.write(f"**User Action:** {error.context.user_action}")
                
                if error.recovery_actions:
                    st.write("**Suggested Actions:**")
                    for action in error.recovery_actions:
                        st.write(f"• {action}")
    
    def clear_error_history(self) -> None:
        """Clear the error history."""
        self.error_history.clear()
        st.success("✅ Error history cleared")
    
    def _convert_exception_to_error(self, exception: Exception, 
                                  context: Optional[ErrorContext] = None) -> StreamlitError:
        """Convert a generic exception to a StreamlitError."""
        if context is None:
            context = ErrorContext()
        
        # Determine error category and severity based on exception type
        category, severity = self._categorize_exception(exception)
        
        # Generate user-friendly message
        message = self._generate_user_friendly_message(exception, category)
        
        # Generate recovery actions
        recovery_actions = self._generate_recovery_actions(exception, category)
        
        return StreamlitError(
            message=message,
            severity=severity,
            category=category,
            context=context,
            exception=exception,
            recovery_actions=recovery_actions,
            show_details=self.enable_debug
        )
    
    def _categorize_exception(self, exception: Exception) -> tuple[ErrorCategory, ErrorSeverity]:
        """Categorize an exception and determine its severity."""
        exception_name = type(exception).__name__
        exception_message = str(exception).lower()
        
        # Network-related errors
        if any(term in exception_name.lower() for term in ['connection', 'timeout', 'network']):
            return ErrorCategory.NETWORK, ErrorSeverity.ERROR
        
        # OpenAI/API errors
        if 'openai' in exception_message or 'api' in exception_message:
            return ErrorCategory.GENERATION, ErrorSeverity.ERROR
        
        # Validation errors
        if any(term in exception_message for term in ['validation', 'invalid', 'syntax']):
            return ErrorCategory.VALIDATION, ErrorSeverity.WARNING
        
        # Storage errors
        if any(term in exception_message for term in ['storage', 'file', 'permission', 's3']):
            return ErrorCategory.STORAGE, ErrorSeverity.ERROR
        
        # Session errors
        if 'session' in exception_message:
            return ErrorCategory.SESSION, ErrorSeverity.ERROR
        
        # Configuration errors
        if any(term in exception_message for term in ['config', 'setting', 'key']):
            return ErrorCategory.CONFIGURATION, ErrorSeverity.CRITICAL
        
        return ErrorCategory.UNKNOWN, ErrorSeverity.ERROR
    
    def _generate_user_friendly_message(self, exception: Exception, 
                                      category: ErrorCategory) -> str:
        """Generate a user-friendly error message."""
        exception_message = str(exception)
        
        messages = {
            ErrorCategory.NETWORK: "Network connection issue occurred",
            ErrorCategory.GENERATION: "Policy generation failed",
            ErrorCategory.VALIDATION: "Policy validation failed",
            ErrorCategory.STORAGE: "Data storage operation failed",
            ErrorCategory.SESSION: "Session management error occurred",
            ErrorCategory.CONFIGURATION: "Configuration error detected",
            ErrorCategory.UNKNOWN: "An unexpected error occurred"
        }
        
        base_message = messages.get(category, "An error occurred")
        
        # Add specific details for common error patterns
        if "api key" in exception_message.lower():
            return "OpenAI API key is missing or invalid"
        elif "rate limit" in exception_message.lower():
            return "API rate limit exceeded - please wait and try again"
        elif "timeout" in exception_message.lower():
            return "Operation timed out - please check your connection and try again"
        elif "permission" in exception_message.lower():
            return "Permission denied - check file/folder access rights"
        elif "not found" in exception_message.lower():
            return "Required resource not found"
        
        return f"{base_message}: {exception_message[:100]}"
    
    def _generate_recovery_actions(self, exception: Exception, 
                                 category: ErrorCategory) -> list[str]:
        """Generate recovery action suggestions."""
        exception_message = str(exception).lower()
        
        actions = {
            ErrorCategory.NETWORK: [
                "Check your internet connection",
                "Verify API endpoints are accessible",
                "Try again in a few moments"
            ],
            ErrorCategory.GENERATION: [
                "Check your OpenAI API key configuration",
                "Verify your requirements are clear and well-formatted",
                "Try using a different model or reducing complexity"
            ],
            ErrorCategory.VALIDATION: [
                "Review the generated policy for syntax errors",
                "Check if the Polar CLI is properly installed",
                "Try regenerating the policy with clearer requirements"
            ],
            ErrorCategory.STORAGE: [
                "Check file/folder permissions",
                "Verify storage configuration settings",
                "Ensure sufficient disk space is available"
            ],
            ErrorCategory.SESSION: [
                "Try refreshing the page",
                "Create a new session if the current one is corrupted",
                "Check session storage configuration"
            ],
            ErrorCategory.CONFIGURATION: [
                "Review your configuration settings",
                "Check environment variables",
                "Verify all required dependencies are installed"
            ]
        }
        
        base_actions = actions.get(category, ["Try refreshing the page", "Contact support if the issue persists"])
        
        # Add specific actions for common error patterns
        if "api key" in exception_message:
            return ["Set your OpenAI API key in the configuration", "Verify the API key is valid and active"]
        elif "rate limit" in exception_message:
            return ["Wait a few minutes before trying again", "Consider upgrading your API plan"]
        elif "timeout" in exception_message:
            return ["Check your internet connection", "Try again with a shorter request"]
        
        return base_actions
    
    def _log_error(self, error: StreamlitError) -> None:
        """Log the error using Python logging."""
        log_message = f"[{error.category.value}] {error.message}"
        
        if error.context.session_id:
            log_message += f" (Session: {error.context.session_id})"
        
        if error.context.component:
            log_message += f" (Component: {error.context.component})"
        
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, exc_info=error.exception)
        elif error.severity == ErrorSeverity.ERROR:
            logger.error(log_message, exc_info=error.exception)
        elif error.severity == ErrorSeverity.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def _add_to_history(self, error: StreamlitError) -> None:
        """Add error to history, maintaining size limit."""
        self.error_history.append(error)
        
        # Maintain history size limit
        if len(self.error_history) > self.max_history:
            self.error_history = self.error_history[-self.max_history:]


@contextmanager
def error_boundary(handler: StreamlitErrorHandler, 
                  context: Optional[ErrorContext] = None,
                  show_errors: bool = True):
    """
    Context manager for handling errors within a code block.
    
    Args:
        handler: StreamlitErrorHandler instance
        context: Optional error context
        show_errors: Whether to display errors immediately
    """
    try:
        yield
    except Exception as e:
        handler.handle_error(e, context, show_errors)


def create_error_handler() -> StreamlitErrorHandler:
    """Create and cache an error handler instance."""
    if "error_handler" not in st.session_state:
        # Check if debug mode is enabled
        debug_mode = st.secrets.get("debug", {}).get("enabled", False)
        st.session_state.error_handler = StreamlitErrorHandler(enable_debug=debug_mode)
    
    return st.session_state.error_handler


def display_error_dashboard():
    """Display an error dashboard for debugging."""
    st.subheader("🐛 Error Dashboard")
    
    error_handler = create_error_handler()
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        error_handler.display_error_summary()
    
    with col2:
        if st.button("🗑️ Clear History"):
            error_handler.clear_error_history()
        
        st.metric("Total Errors", len(error_handler.error_history))
        
        if error_handler.error_history:
            recent_error = error_handler.error_history[-1]
            st.metric("Last Error", recent_error.context.timestamp.strftime("%H:%M:%S"))


# Convenience functions for common error scenarios
def handle_generation_error(exception: Exception, session_id: str, 
                          handler: Optional[StreamlitErrorHandler] = None) -> StreamlitError:
    """Handle policy generation errors."""
    if handler is None:
        handler = create_error_handler()
    
    context = ErrorContext(
        session_id=session_id,
        user_action="Policy Generation",
        component="PolicyGenerator"
    )
    
    return handler.handle_error(exception, context)


def handle_validation_error(exception: Exception, policy_id: str, session_id: str,
                          handler: Optional[StreamlitErrorHandler] = None) -> StreamlitError:
    """Handle policy validation errors."""
    if handler is None:
        handler = create_error_handler()
    
    context = ErrorContext(
        session_id=session_id,
        user_action="Policy Validation",
        component="PolarValidator",
        additional_data={"policy_id": policy_id}
    )
    
    return handler.handle_error(exception, context)


def handle_session_error(exception: Exception, session_id: str,
                        handler: Optional[StreamlitErrorHandler] = None) -> StreamlitError:
    """Handle session management errors."""
    if handler is None:
        handler = create_error_handler()
    
    context = ErrorContext(
        session_id=session_id,
        user_action="Session Management",
        component="SessionManager"
    )
    
    return handler.handle_error(exception, context)


def handle_storage_error(exception: Exception, operation: str,
                        handler: Optional[StreamlitErrorHandler] = None) -> StreamlitError:
    """Handle storage operation errors."""
    if handler is None:
        handler = create_error_handler()
    
    context = ErrorContext(
        user_action=f"Storage {operation}",
        component="StorageBackend"
    )
    
    return handler.handle_error(exception, context)