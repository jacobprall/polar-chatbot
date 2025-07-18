"""Policy generation interface components."""

import streamlit as st
from typing import Optional, Dict, Any, Callable
import time
import asyncio
from datetime import datetime

from ...models import Session, GeneratedPolicy
from ...models.policy import PolicyGenerationRequest, PolicyGenerationResult
from ...services.session_manager import SessionManager, SessionManagerError
from ...services.policy_generator import SessionPolicyGenerator
from ...services.openai_service import SessionAwareOpenAIService
from ...core.validator import PolarValidator


def initialize_policy_generator() -> SessionPolicyGenerator:
    """Initialize and cache the policy generator."""
    if "policy_generator" not in st.session_state:
        try:
            # Initialize OpenAI service
            openai_service = SessionAwareOpenAIService()
            
            # Initialize validator (optional)
            try:
                validator = PolarValidator()
            except Exception:
                validator = None
                st.warning("⚠️ Polar validator not available - validation will be skipped")
            
            # Create policy generator
            st.session_state.policy_generator = SessionPolicyGenerator(
                ai_service=openai_service,
                validator=validator
            )
        except Exception as e:
            st.error(f"❌ Failed to initialize policy generator: {str(e)}")
            return None
    
    return st.session_state.policy_generator


def render_generation_trigger(session: Session, session_manager: SessionManager) -> bool:
    """Render the policy generation trigger UI with progress indicators."""
    st.subheader("🔧 Policy Generation")
    
    if not session.requirements_text.strip():
        st.warning("⚠️ No requirements found. Please add requirements in the Requirements tab first.")
        return False
    
    # Get generation settings
    settings = _render_generation_settings()
    
    # Get generation buttons state
    buttons = _render_generation_buttons(session)
    
    # Handle generation triggers
    return _handle_generation_triggers(session, session_manager, settings, buttons)


def _render_generation_settings() -> dict:
    """Render generation settings UI and return configuration."""
    with st.expander("⚙️ Generation Settings", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            model = st.selectbox(
                "Model",
                options=["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-3.5-turbo"],
                index=0,
                help="Select the OpenAI model to use for generation"
            )
            
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.0,
                value=0.1,
                step=0.1,
                help="Controls randomness in generation"
            )
        
        with col2:
            max_tokens = st.number_input(
                "Max Tokens",
                min_value=100,
                max_value=4000,
                value=2000,
                step=100,
                help="Maximum number of tokens to generate"
            )
            
            streaming = st.checkbox(
                "Enable Streaming",
                value=True,
                help="Show generation progress in real-time"
            )
    
    return {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "streaming": streaming
    }


def _render_generation_buttons(session: Session) -> dict:
    """Render generation buttons and return their states."""
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        generate_button = st.button(
            "🚀 Generate Policy",
            type="primary",
            help="Generate a new Polar policy from requirements",
            disabled=not session.requirements_text.strip()
        )
    
    with col2:
        has_validation_errors = _has_validation_errors(session)
        retry_button = st.button(
            "🔄 Retry with Errors",
            help="Retry generation using validation errors as context",
            disabled=not has_validation_errors
        )
    
    with col3:
        regenerate_button = st.button(
            "⚡ Quick Regenerate",
            help="Generate a new policy with the same settings"
        )
    
    return {
        "generate": generate_button,
        "retry": retry_button and has_validation_errors,
        "regenerate": regenerate_button
    }


def _has_validation_errors(session: Session) -> bool:
    """Check if current policy has validation errors."""
    current_policy = session.get_current_policy()
    if not current_policy:
        return False
    
    latest_validation = session.get_latest_validation(current_policy.id)
    return latest_validation and not latest_validation.is_valid


def _handle_generation_triggers(session: Session, session_manager: SessionManager, 
                              settings: dict, buttons: dict) -> bool:
    """Handle generation button triggers."""
    if buttons["generate"] or buttons["regenerate"]:
        return _handle_policy_generation(session, session_manager, **settings)
    
    elif buttons["retry"]:
        return _handle_retry_generation(session, session_manager, **settings)
    
    return False


def render_policy_display(session: Session, session_manager: SessionManager) -> None:
    """
    Render the policy display component with syntax highlighting.
    
    Args:
        session: Current session
        session_manager: SessionManager instance
    """
    if not session.generated_policies:
        st.info("📝 No policies have been generated yet. Use the generation controls above to create your first policy.")
        return
    
    st.markdown("---")
    st.subheader("📄 Generated Policy")
    
    # Policy selector
    current_policy = session.get_current_policy()
    if not current_policy and session.generated_policies:
        # If no current policy, make the latest one current
        current_policy = session.generated_policies[-1]
        current_policy.is_current = True
    
    if len(session.generated_policies) > 1:
        policy_options = []
        for i, policy in enumerate(reversed(session.generated_policies)):
            timestamp = policy.generated_at.strftime("%Y-%m-%d %H:%M:%S")
            label = f"Policy {len(session.generated_policies) - i} - {policy.model_used} ({timestamp})"
            policy_options.append((label, policy.id))
        
        selected_label = st.selectbox(
            "Select Policy Version",
            options=[label for label, _ in policy_options],
            index=0,
            help="Choose which policy version to display"
        )
        
        # Find selected policy
        selected_policy_id = next(pid for label, pid in policy_options if label == selected_label)
        current_policy = next(p for p in session.generated_policies if p.id == selected_policy_id)
    
    if current_policy:
        # Policy metadata
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Model", current_policy.model_used)
        
        with col2:
            if current_policy.tokens_used:
                st.metric("Tokens", f"{current_policy.tokens_used:,}")
            else:
                st.metric("Tokens", "N/A")
        
        with col3:
            st.metric("Generation Time", f"{current_policy.generation_time:.2f}s")
        
        with col4:
            st.metric("Generated", current_policy.generated_at.strftime("%H:%M:%S"))
        
        # Policy content with syntax highlighting
        st.markdown("### 📋 Policy Content")
        
        # Action buttons
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        
        with col1:
            if st.button("📋 Copy Policy", help="Copy policy content to clipboard"):
                st.info("💡 Use Ctrl+A, Ctrl+C to copy the policy content below")
        
        with col2:
            if st.button("💾 Download", help="Download policy as .polar file"):
                st.download_button(
                    label="📥 Download .polar",
                    data=current_policy.content,
                    file_name=f"policy_{current_policy.id[:8]}.polar",
                    mime="text/plain"
                )
        
        with col3:
            if st.button("✅ Validate", help="Validate this policy"):
                _handle_policy_validation(current_policy, session, session_manager)
        
        with col4:
            if st.button("🗑️ Delete", help="Delete this policy version", type="secondary"):
                st.session_state.show_delete_policy_dialog = current_policy.id
        
        # Delete confirmation dialog
        if st.session_state.get("show_delete_policy_dialog") == current_policy.id:
            with st.expander("🗑️ Delete Policy", expanded=True):
                st.warning(f"Are you sure you want to delete this policy version?")
                st.error("This action cannot be undone!")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("❌ Yes, Delete", type="primary"):
                        _handle_policy_deletion(current_policy, session, session_manager)
                        st.session_state.show_delete_policy_dialog = None
                        st.rerun()
                
                with col2:
                    if st.button("Cancel"):
                        st.session_state.show_delete_policy_dialog = None
                        st.rerun()
        
        # Display policy with syntax highlighting
        st.code(current_policy.content, language="python", line_numbers=True)
        
        # Validation status for current policy
        latest_validation = session.get_latest_validation(current_policy.id)
        if latest_validation:
            st.markdown("### ✅ Validation Status")
            
            if latest_validation.is_valid:
                st.success(f"✅ Policy validation passed ({latest_validation.validation_time:.2f}s)")
            else:
                st.error(f"❌ Policy validation failed ({latest_validation.validation_time:.2f}s)")
                if latest_validation.error_message:
                    st.code(latest_validation.error_message, language="text")


def render_generation_history(session: Session) -> None:
    """
    Render the generation history and version management UI.
    
    Args:
        session: Current session
    """
    if not session.generated_policies:
        st.info("📊 No generation history available yet.")
        return
    
    st.markdown("---")
    st.subheader("📊 Generation History")
    
    # Generation statistics
    col1, col2, col3, col4 = st.columns(4)
    
    total_policies = len(session.generated_policies)
    total_tokens = sum(p.tokens_used or 0 for p in session.generated_policies)
    total_time = sum(p.generation_time for p in session.generated_policies)
    avg_time = total_time / total_policies if total_policies > 0 else 0
    
    with col1:
        st.metric("Total Generations", total_policies)
    
    with col2:
        st.metric("Total Tokens", f"{total_tokens:,}")
    
    with col3:
        st.metric("Total Time", f"{total_time:.1f}s")
    
    with col4:
        st.metric("Avg Time", f"{avg_time:.1f}s")
    
    # Models used
    models_used = list(set(p.model_used for p in session.generated_policies))
    if models_used:
        st.markdown(f"**Models Used:** {', '.join(models_used)}")
    
    # Generation timeline
    st.markdown("### 📈 Generation Timeline")
    
    # Create a simple timeline view
    for i, policy in enumerate(reversed(session.generated_policies)):
        policy_num = len(session.generated_policies) - i
        
        with st.expander(
            f"Policy {policy_num} - {policy.model_used} ({policy.generated_at.strftime('%Y-%m-%d %H:%M:%S')})",
            expanded=False
        ):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Policy preview (first 200 characters)
                preview = policy.content[:200] + "..." if len(policy.content) > 200 else policy.content
                st.code(preview, language="python")
            
            with col2:
                st.write(f"**Model:** {policy.model_used}")
                if policy.tokens_used:
                    st.write(f"**Tokens:** {policy.tokens_used:,}")
                st.write(f"**Time:** {policy.generation_time:.2f}s")
                st.write(f"**Current:** {'Yes' if policy.is_current else 'No'}")
                
                # Validation status
                validation = session.get_latest_validation(policy.id)
                if validation:
                    status = "✅ Valid" if validation.is_valid else "❌ Invalid"
                    st.write(f"**Validation:** {status}")


def _handle_policy_generation(session: Session, session_manager: SessionManager, 
                            model: str, temperature: float, max_tokens: int, 
                            streaming: bool) -> bool:
    """Handle policy generation request."""
    policy_generator = initialize_policy_generator()
    if not policy_generator:
        return False
    
    request = PolicyGenerationRequest(
        session_id=session.id,
        requirements_text=session.requirements_text,
        model_config={"model": model, "temperature": temperature, "max_tokens": max_tokens}
    )
    
    return _execute_generation(policy_generator, request, session, session_manager, streaming)


def _execute_generation(policy_generator: SessionPolicyGenerator, request: PolicyGenerationRequest,
                       session: Session, session_manager: SessionManager, streaming: bool) -> bool:
    """Execute policy generation with progress tracking."""
    progress_placeholder = st.empty()
    content_placeholder = st.empty()
    
    try:
        progress_placeholder.info("🔄 Generating policy...")
        
        if streaming:
            generated_content = []
            def stream_callback(chunk: str):
                generated_content.append(chunk)
                content_placeholder.code(''.join(generated_content), language="text")
            
            result = policy_generator.generate_policy_stream(request, session, stream_callback)
        else:
            result = policy_generator.generate_policy(request, session)
        
        return _handle_generation_result(result, session, session_manager, progress_placeholder, content_placeholder)
    
    except Exception as e:
        progress_placeholder.error(f"❌ Generation error: {str(e)}")
        content_placeholder.empty()
        return False


def _handle_generation_result(result: PolicyGenerationResult, session: Session, 
                            session_manager: SessionManager, progress_placeholder, content_placeholder) -> bool:
    """Handle the result of policy generation."""
    if result.is_successful():
        progress_placeholder.success(f"✅ Policy generated successfully! ({result.generation_time:.2f}s)")
        session_manager.save_session(session)
        
        time.sleep(2)
        content_placeholder.empty()
        return True
    else:
        progress_placeholder.error(f"❌ Generation failed: {result.error_message}")
        content_placeholder.empty()
        return False


def _handle_retry_generation(session: Session, session_manager: SessionManager,
                           model: str, temperature: float, max_tokens: int,
                           streaming: bool) -> bool:
    """Handle retry generation with validation errors."""
    policy_generator = initialize_policy_generator()
    if not policy_generator:
        return False
    
    # Validate retry conditions
    validation_errors = _get_validation_errors_for_retry(session)
    if not validation_errors:
        return False
    
    # Create retry request
    request = PolicyGenerationRequest(
        session_id=session.id,
        requirements_text=session.requirements_text,
        model_config={"model": model, "temperature": temperature, "max_tokens": max_tokens},
        previous_errors=validation_errors
    )
    
    return _execute_retry_generation(policy_generator, request, session, session_manager, streaming, validation_errors)


def _get_validation_errors_for_retry(session: Session) -> list[str]:
    """Get validation errors for retry generation."""
    current_policy = session.get_current_policy()
    if not current_policy:
        st.error("❌ No current policy found for retry")
        return []
    
    latest_validation = session.get_latest_validation(current_policy.id)
    if not latest_validation or latest_validation.is_valid:
        st.error("❌ No validation errors found for retry")
        return []
    
    return [latest_validation.error_message] if latest_validation.error_message else []


def _execute_retry_generation(policy_generator: SessionPolicyGenerator, request: PolicyGenerationRequest,
                            session: Session, session_manager: SessionManager, streaming: bool,
                            validation_errors: list[str]) -> bool:
    """Execute retry generation with progress tracking."""
    progress_placeholder = st.empty()
    content_placeholder = st.empty()
    
    try:
        progress_placeholder.info("🔄 Retrying policy generation with error context...")
        
        if streaming:
            generated_content = []
            def stream_callback(chunk: str):
                generated_content.append(chunk)
                content_placeholder.code(''.join(generated_content), language="text")
            
            result = policy_generator.retry_policy_generation_stream(session, validation_errors, stream_callback)
        else:
            result = policy_generator.retry_policy_generation(session, validation_errors)
        
        return _handle_generation_result(result, session, session_manager, progress_placeholder, content_placeholder)
    
    except Exception as e:
        progress_placeholder.error(f"❌ Retry generation error: {str(e)}")
        content_placeholder.empty()
        return False


def _handle_policy_validation(policy: GeneratedPolicy, session: Session, 
                            session_manager: SessionManager) -> None:
    """Handle policy validation request."""
    policy_generator = initialize_policy_generator()
    if not policy_generator:
        return
    
    progress_placeholder = st.empty()
    
    try:
        progress_placeholder.info("🔄 Validating policy...")
        
        # Validate the policy
        validation_result = policy_generator.validate_policy(
            policy.content, policy.id, session.id
        )
        
        # Create validation result and add to session
        from ...models.session import ValidationResult
        result = ValidationResult.create(
            policy_id=policy.id,
            is_valid=validation_result.is_valid,
            error_message=validation_result.error_message,
            validation_time=validation_result.validation_time
        )
        
        session.add_validation_result(result)
        session_manager.save_session(session)
        
        if validation_result.is_valid:
            progress_placeholder.success(f"✅ Policy validation passed! ({validation_result.validation_time:.2f}s)")
        else:
            progress_placeholder.error(f"❌ Policy validation failed ({validation_result.validation_time:.2f}s)")
    
    except Exception as e:
        progress_placeholder.error(f"❌ Validation error: {str(e)}")


def _handle_policy_deletion(policy: GeneratedPolicy, session: Session, 
                          session_manager: SessionManager) -> None:
    """Handle policy deletion."""
    try:
        # Remove policy from session
        session.generated_policies = [p for p in session.generated_policies if p.id != policy.id]
        
        # Remove associated validation results
        session.validation_results = [r for r in session.validation_results if r.policy_id != policy.id]
        
        # If this was the current policy, make the latest remaining policy current
        if policy.is_current and session.generated_policies:
            session.generated_policies[-1].is_current = True
        
        session.update_timestamp()
        session_manager.save_session(session)
        
        st.success("✅ Policy deleted successfully")
    
    except Exception as e:
        st.error(f"❌ Failed to delete policy: {str(e)}")


def render_policy_generation_interface(session: Session, session_manager: SessionManager) -> None:
    """
    Render the complete policy generation interface.
    
    Args:
        session: Current session
        session_manager: SessionManager instance
    """
    # Generation trigger section
    generation_triggered = render_generation_trigger(session, session_manager)
    
    # Policy display section
    render_policy_display(session, session_manager)
    
    # Generation history section
    render_generation_history(session)
    
    # If generation was triggered, refresh the page to show new content
    if generation_triggered:
        time.sleep(1)  # Brief delay to show success message
        st.rerun()