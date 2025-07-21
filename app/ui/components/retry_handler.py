"""Retry mechanisms and recovery utilities for Streamlit components."""

import streamlit as st
import time
import asyncio
from typing import Callable, Any, Optional, Dict, List
from dataclasses import dataclass
from enum import Enum
import logging

from .error_handler import StreamlitErrorHandler, ErrorContext, ErrorCategory, ErrorSeverity

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Different retry strategies."""
    IMMEDIATE = "immediate"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    FIXED_DELAY = "fixed_delay"
    USER_TRIGGERED = "user_triggered"


@dataclass
class RetryConfig:
    """Configuration for retry operations."""
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    show_progress: bool = True
    allow_user_cancel: bool = True


@dataclass
class RetryAttempt:
    """Information about a retry attempt."""
    attempt_number: int
    timestamp: float
    error: Optional[Exception] = None
    success: bool = False
    duration: float = 0.0


class RetryHandler:
    """Handles retry logic with Streamlit UI integration."""
    
    def __init__(self, error_handler: StreamlitErrorHandler):
        self.error_handler = error_handler
        self.active_retries: Dict[str, List[RetryAttempt]] = {}
    
    def retry_with_ui(self, 
                     operation: Callable[[], Any],
                     operation_name: str,
                     config: RetryConfig = None,
                     context: ErrorContext = None,
                     container=None) -> tuple[bool, Any]:
        """
        Execute an operation with retry logic and UI feedback.
        
        Args:
            operation: Function to execute
            operation_name: Human-readable name for the operation
            config: Retry configuration
            context: Error context for logging
            container: Streamlit container for UI elements
            
        Returns:
            Tuple of (success, result)
        """
        if config is None:
            config = RetryConfig()
        
        if context is None:
            context = ErrorContext()
        
        display_container = container or st
        retry_id = f"{operation_name}_{time.time()}"
        self.active_retries[retry_id] = []
        
        # Create UI elements
        progress_placeholder = display_container.empty()
        status_placeholder = display_container.empty()
        cancel_placeholder = display_container.empty() if config.allow_user_cancel else None
        
        try:
            for attempt in range(1, config.max_attempts + 1):
                attempt_start = time.time()
                
                # Update progress
                if config.show_progress:
                    progress_placeholder.info(f"🔄 {operation_name} (Attempt {attempt}/{config.max_attempts})")
                
                # Show cancel button
                if cancel_placeholder and attempt > 1:
                    if cancel_placeholder.button(f"❌ Cancel {operation_name}", key=f"cancel_{retry_id}_{attempt}"):
                        status_placeholder.warning(f"⚠️ {operation_name} cancelled by user")
                        return False, None
                
                try:
                    # Execute the operation
                    result = operation()
                    
                    # Success!
                    attempt_duration = time.time() - attempt_start
                    self.active_retries[retry_id].append(RetryAttempt(
                        attempt_number=attempt,
                        timestamp=attempt_start,
                        success=True,
                        duration=attempt_duration
                    ))
                    
                    # Clear UI elements
                    progress_placeholder.empty()
                    if cancel_placeholder:
                        cancel_placeholder.empty()
                    
                    status_placeholder.success(f"✅ {operation_name} completed successfully!")
                    
                    # Brief success display
                    time.sleep(1)
                    status_placeholder.empty()
                    
                    return True, result
                
                except Exception as e:
                    attempt_duration = time.time() - attempt_start
                    self.active_retries[retry_id].append(RetryAttempt(
                        attempt_number=attempt,
                        timestamp=attempt_start,
                        error=e,
                        success=False,
                        duration=attempt_duration
                    ))
                    
                    # Log the error
                    context.user_action = f"{operation_name} (Attempt {attempt})"
                    self.error_handler.handle_error(e, context, show_immediately=False)
                    
                    # Check if we should retry
                    if attempt < config.max_attempts:
                        delay = self._calculate_delay(config, attempt)
                        
                        status_placeholder.warning(
                            f"⚠️ {operation_name} failed (Attempt {attempt}/{config.max_attempts}). "
                            f"Retrying in {delay:.1f} seconds..."
                        )
                        
                        # Wait with countdown if delay is significant
                        if delay > 2:
                            self._show_countdown(delay, status_placeholder)
                        else:
                            time.sleep(delay)
                    else:
                        # Final failure
                        progress_placeholder.empty()
                        if cancel_placeholder:
                            cancel_placeholder.empty()
                        
                        status_placeholder.error(f"❌ {operation_name} failed after {config.max_attempts} attempts")
                        
                        # Show retry summary
                        self._show_retry_summary(retry_id, display_container)
                        
                        return False, None
        
        finally:
            # Cleanup
            if retry_id in self.active_retries:
                del self.active_retries[retry_id]
    
    def _calculate_delay(self, config: RetryConfig, attempt: int) -> float:
        """Calculate delay for next retry attempt."""
        if config.strategy == RetryStrategy.IMMEDIATE:
            return 0.0
        elif config.strategy == RetryStrategy.FIXED_DELAY:
            return config.base_delay
        elif config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = config.base_delay * (config.backoff_multiplier ** (attempt - 1))
            return min(delay, config.max_delay)
        else:
            return config.base_delay
    
    def _show_countdown(self, delay: float, container) -> None:
        """Show countdown timer for retry delay."""
        countdown_placeholder = container.empty()
        
        for remaining in range(int(delay), 0, -1):
            countdown_placeholder.info(f"⏳ Retrying in {remaining} seconds...")
            time.sleep(1)
        
        countdown_placeholder.empty()
    
    def _show_retry_summary(self, retry_id: str, container) -> None:
        """Show summary of retry attempts."""
        if retry_id not in self.active_retries:
            return
        
        attempts = self.active_retries[retry_id]
        
        with container.expander("🔍 Retry Details", expanded=False):
            st.write(f"**Total Attempts:** {len(attempts)}")
            
            for attempt in attempts:
                status_icon = "✅" if attempt.success else "❌"
                st.write(f"{status_icon} Attempt {attempt.attempt_number}: "
                        f"{attempt.duration:.2f}s")
                
                if attempt.error:
                    st.code(str(attempt.error), language="text")


class OperationRetryUI:
    """UI components for retry operations."""
    
    def __init__(self, retry_handler: RetryHandler):
        self.retry_handler = retry_handler
    
    def render_retry_button(self, 
                          operation: Callable[[], Any],
                          operation_name: str,
                          button_text: str = None,
                          config: RetryConfig = None,
                          context: ErrorContext = None,
                          disabled: bool = False,
                          help_text: str = None) -> bool:
        """
        Render a retry button that executes an operation with retry logic.
        
        Args:
            operation: Function to execute
            operation_name: Human-readable name for the operation
            button_text: Custom button text
            config: Retry configuration
            context: Error context
            disabled: Whether button is disabled
            help_text: Help text for button
            
        Returns:
            True if operation succeeded, False otherwise
        """
        if button_text is None:
            button_text = f"🔄 Retry {operation_name}"
        
        if config is None:
            config = RetryConfig()
        
        button_key = f"retry_{operation_name.lower().replace(' ', '_')}_{time.time()}"
        
        if st.button(button_text, disabled=disabled, help=help_text, key=button_key):
            success, _ = self.retry_handler.retry_with_ui(
                operation=operation,
                operation_name=operation_name,
                config=config,
                context=context
            )
            return success
        
        return False
    
    def render_retry_section(self,
                           operations: Dict[str, Callable[[], Any]],
                           title: str = "🔄 Retry Operations",
                           config: RetryConfig = None) -> Dict[str, bool]:
        """
        Render a section with multiple retry operations.
        
        Args:
            operations: Dictionary of operation_name -> operation_function
            title: Section title
            config: Retry configuration
            
        Returns:
            Dictionary of operation_name -> success_status
        """
        results = {}
        
        st.subheader(title)
        
        for operation_name, operation in operations.items():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**{operation_name}**")
            
            with col2:
                success = self.render_retry_button(
                    operation=operation,
                    operation_name=operation_name,
                    button_text="🔄 Retry",
                    config=config
                )
                results[operation_name] = success
        
        return results


# Convenience functions for common retry scenarios
def create_retry_handler() -> RetryHandler:
    """Create and cache a retry handler instance."""
    if "retry_handler" not in st.session_state:
        from .error_handler import create_error_handler
        error_handler = create_error_handler()
        st.session_state.retry_handler = RetryHandler(error_handler)
    
    return st.session_state.retry_handler


def retry_policy_generation(generator_func: Callable[[], Any],
                          session_id: str,
                          config: RetryConfig = None) -> tuple[bool, Any]:
    """Retry policy generation with appropriate configuration."""
    retry_handler = create_retry_handler()
    
    if config is None:
        config = RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=2.0,
            show_progress=True
        )
    
    context = ErrorContext(
        session_id=session_id,
        user_action="Policy Generation",
        component="PolicyGenerator"
    )
    
    return retry_handler.retry_with_ui(
        operation=generator_func,
        operation_name="Policy Generation",
        config=config,
        context=context
    )


def retry_policy_validation(validator_func: Callable[[], Any],
                          policy_id: str,
                          session_id: str,
                          config: RetryConfig = None) -> tuple[bool, Any]:
    """Retry policy validation with appropriate configuration."""
    retry_handler = create_retry_handler()
    
    if config is None:
        config = RetryConfig(
            max_attempts=2,
            strategy=RetryStrategy.FIXED_DELAY,
            base_delay=1.0,
            show_progress=True
        )
    
    context = ErrorContext(
        session_id=session_id,
        user_action="Policy Validation",
        component="PolarValidator",
        additional_data={"policy_id": policy_id}
    )
    
    return retry_handler.retry_with_ui(
        operation=validator_func,
        operation_name="Policy Validation",
        config=config,
        context=context
    )


def retry_session_operation(operation_func: Callable[[], Any],
                          operation_name: str,
                          session_id: str,
                          config: RetryConfig = None) -> tuple[bool, Any]:
    """Retry session operations with appropriate configuration."""
    retry_handler = create_retry_handler()
    
    if config is None:
        config = RetryConfig(
            max_attempts=2,
            strategy=RetryStrategy.IMMEDIATE,
            show_progress=True
        )
    
    context = ErrorContext(
        session_id=session_id,
        user_action=operation_name,
        component="SessionManager"
    )
    
    return retry_handler.retry_with_ui(
        operation=operation_func,
        operation_name=operation_name,
        config=config,
        context=context
    )


def retry_storage_operation(operation_func: Callable[[], Any],
                          operation_name: str,
                          config: RetryConfig = None) -> tuple[bool, Any]:
    """Retry storage operations with appropriate configuration."""
    retry_handler = create_retry_handler()
    
    if config is None:
        config = RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=1.0,
            max_delay=10.0,
            show_progress=True
        )
    
    context = ErrorContext(
        user_action=operation_name,
        component="StorageBackend"
    )
    
    return retry_handler.retry_with_ui(
        operation=operation_func,
        operation_name=operation_name,
        config=config,
        context=context
    )