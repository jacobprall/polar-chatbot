"""Validation results interface component for the Polar Prompt Tester."""

import streamlit as st
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
import time

from app.models.session import Session, ValidationResult
from app.models.policy import PolicyValidationResult, PolicyValidationRequest
from app.services.session_manager import SessionManager, SessionManagerError
from app.services.async_validator import AsyncPolarValidator
from app.services.validation_retry_service import ValidationRetryService


def render_validation_results_interface(session: Session, session_manager: SessionManager) -> None:
    """
    Render the complete validation results interface.
    
    Args:
        session: Current session
        session_manager: SessionManager instance
    """
    st.header("✅ Validation Results")
    
    # Check if there are any policies to validate
    if not session.generated_policies:
        st.info("📝 No policies have been generated yet. Generate a policy first to see validation results.")
        return
    
    # Get current policy
    current_policy = session.get_current_policy()
    if not current_policy:
        st.warning("⚠️ No current policy found.")
        return
    
    # Main validation interface
    col1, col2 = st.columns([2, 1])
    
    with col1:
        render_validation_status_display(session, current_policy)
    
    with col2:
        render_validation_actions(session, session_manager, current_policy)
    
    st.markdown("---")
    
    # Validation history and metrics
    col1, col2 = st.columns(2)
    
    with col1:
        render_validation_history(session)
    
    with col2:
        render_validation_metrics(session)


def render_validation_status_display(session: Session, current_policy) -> None:
    """
    Render the validation status display with error details.
    
    Args:
        session: Current session
        current_policy: Current policy to display validation for
    """
    st.subheader(f"🔍 Policy Validation Status")
    
    # Get latest validation result for current policy
    latest_validation = session.get_latest_validation(current_policy.id)
    
    if not latest_validation:
        st.info("⏳ This policy has not been validated yet.")
        return
    
    # Display validation status
    if latest_validation.is_valid:
        st.success("✅ **Policy is valid!**")
        st.write(f"✨ Validated at: {latest_validation.validated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"⚡ Validation time: {latest_validation.validation_time:.2f} seconds")
    else:
        st.error("❌ **Policy validation failed**")
        st.write(f"🕒 Validated at: {latest_validation.validated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"⚡ Validation time: {latest_validation.validation_time:.2f} seconds")
        
        # Display error details
        if latest_validation.error_message:
            st.subheader("🚨 Error Details")
            st.error(latest_validation.error_message)
            
            # Show error in expandable code block for better readability
            with st.expander("📋 Full Error Message"):
                st.code(latest_validation.error_message, language="text")
    
    # Show policy content being validated
    with st.expander("📄 Policy Content", expanded=False):
        st.code(current_policy.content, language="polar")


def render_validation_actions(session: Session, session_manager: SessionManager, current_policy) -> None:
    """
    Render validation action buttons with error context integration.
    
    Args:
        session: Current session
        session_manager: SessionManager instance
        current_policy: Current policy
    """
    st.subheader("🎯 Actions")
    
    # Validate button
    if st.button("🔍 Validate Policy", type="primary", use_container_width=True):
        with st.spinner("Validating policy..."):
            try:
                # Initialize async validator
                validator = AsyncPolarValidator()
                
                # Create validation request
                validation_request = PolicyValidationRequest(
                    policy_content=current_policy.content,
                    policy_id=current_policy.id,
                    session_id=session.id
                )
                
                # Run validation
                validation_result = asyncio.run(validator.validate_policy_async(validation_request))
                
                # Create session validation result
                session_validation_result = ValidationResult.create(
                    policy_id=current_policy.id,
                    is_valid=validation_result.is_valid,
                    error_message=validation_result.error_message,
                    validation_time=validation_result.validation_time
                )
                
                # Add to session and save
                session.add_validation_result(session_validation_result)
                session_manager.save_session(session)
                
                # Show result
                if validation_result.is_valid:
                    st.success("✅ Policy is valid!")
                else:
                    st.error("❌ Policy validation failed")
                
                # Clean up
                asyncio.run(validator.close())
                
                # Refresh the page to show new results
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Validation failed: {str(e)}")
    
    # Retry button (only show if last validation failed)
    latest_validation = session.get_latest_validation(current_policy.id)
    if latest_validation and not latest_validation.is_valid:
        st.markdown("---")
        st.write("**🔄 Retry Generation**")
        st.caption("Generate a new policy using validation errors as context")
        
        if st.button("🔄 Retry with Error Context", type="secondary", use_container_width=True):
            # Store retry context in session state for policy generation tab
            st.session_state["retry_requested"] = True
            st.session_state["retry_errors"] = [latest_validation.error_message] if latest_validation.error_message else []
            st.session_state["retry_policy_id"] = current_policy.id
            
            st.success("🔄 Retry request prepared! Switch to the Policy Generation tab to generate a new policy with error context.")
    
    # Clear validation history button
    if session.validation_results:
        st.markdown("---")
        if st.button("🗑️ Clear Validation History", type="secondary", use_container_width=True):
            if st.session_state.get("confirm_clear_validation", False):
                # Clear validation results
                session.validation_results = []
                session.update_timestamp()
                session_manager.save_session(session)
                
                # Reset confirmation state
                st.session_state["confirm_clear_validation"] = False
                st.success("✅ Validation history cleared!")
                st.rerun()
            else:
                st.session_state["confirm_clear_validation"] = True
                st.warning("⚠️ Click again to confirm clearing all validation history.")


def render_validation_history(session: Session) -> None:
    """
    Render validation history display.
    
    Args:
        session: Current session
    """
    st.subheader("📚 Validation History")
    
    if not session.validation_results:
        st.info("📝 No validation history available.")
        return
    
    # Sort validation results by timestamp (most recent first)
    sorted_results = sorted(session.validation_results, key=lambda r: r.validated_at, reverse=True)
    
    # Show recent validations
    for i, result in enumerate(sorted_results[:10]):  # Show last 10 validations
        # Find the policy this validation belongs to
        policy = None
        for p in session.generated_policies:
            if p.id == result.policy_id:
                policy = p
                break
        
        policy_name = f"Policy {result.policy_id[:8]}..." if policy else "Unknown Policy"
        
        # Create expandable entry for each validation
        status_icon = "✅" if result.is_valid else "❌"
        status_text = "Valid" if result.is_valid else "Invalid"
        
        with st.expander(f"{status_icon} {policy_name} - {status_text} ({result.validated_at.strftime('%m/%d %H:%M')})"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Policy ID:** {result.policy_id}")
                st.write(f"**Status:** {status_text}")
                st.write(f"**Validated:** {result.validated_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            with col2:
                st.write(f"**Validation Time:** {result.validation_time:.2f}s")
                if result.error_message:
                    st.write("**Has Errors:** Yes")
                else:
                    st.write("**Has Errors:** No")
            
            if result.error_message:
                st.write("**Error Message:**")
                st.code(result.error_message, language="text")
    
    # Show total count if there are more results
    if len(sorted_results) > 10:
        st.caption(f"Showing 10 most recent validations out of {len(sorted_results)} total.")


def render_validation_metrics(session: Session) -> None:
    """
    Render validation success metrics and statistics.
    
    Args:
        session: Current session
    """
    st.subheader("📊 Validation Metrics")
    
    if not session.validation_results:
        st.info("📝 No validation data available.")
        return
    
    # Calculate metrics
    total_validations = len(session.validation_results)
    successful_validations = sum(1 for r in session.validation_results if r.is_valid)
    failed_validations = total_validations - successful_validations
    success_rate = (successful_validations / total_validations) * 100 if total_validations > 0 else 0
    
    # Average validation time
    avg_validation_time = sum(r.validation_time for r in session.validation_results) / total_validations if total_validations > 0 else 0
    
    # Display metrics
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Total Validations", total_validations)
        st.metric("Successful", successful_validations, delta=f"{success_rate:.1f}%")
    
    with col2:
        st.metric("Failed", failed_validations)
        st.metric("Avg Time", f"{avg_validation_time:.2f}s")
    
    # Success rate progress bar
    st.write("**Success Rate**")
    st.progress(success_rate / 100)
    st.caption(f"{success_rate:.1f}% of validations passed")
    
    # Recent validation trend (last 5 validations)
    if total_validations >= 5:
        recent_results = sorted(session.validation_results, key=lambda r: r.validated_at, reverse=True)[:5]
        recent_success_rate = (sum(1 for r in recent_results if r.is_valid) / 5) * 100
        
        st.write("**Recent Trend (Last 5)**")
        trend_delta = recent_success_rate - success_rate
        trend_color = "normal" if abs(trend_delta) < 10 else ("inverse" if trend_delta < 0 else "normal")
        st.metric("Recent Success Rate", f"{recent_success_rate:.1f}%", 
                 delta=f"{trend_delta:+.1f}%", delta_color=trend_color)
    
    # Policy-specific metrics
    if len(session.generated_policies) > 1:
        st.write("**Per-Policy Metrics**")
        
        policy_metrics = {}
        for result in session.validation_results:
            if result.policy_id not in policy_metrics:
                policy_metrics[result.policy_id] = {"total": 0, "successful": 0}
            
            policy_metrics[result.policy_id]["total"] += 1
            if result.is_valid:
                policy_metrics[result.policy_id]["successful"] += 1
        
        for policy_id, metrics in policy_metrics.items():
            policy_success_rate = (metrics["successful"] / metrics["total"]) * 100
            st.write(f"Policy {policy_id[:8]}...: {metrics['successful']}/{metrics['total']} ({policy_success_rate:.1f}%)")


def render_validation_error_analysis(session: Session) -> None:
    """
    Render detailed error analysis for failed validations.
    
    Args:
        session: Current session
    """
    st.subheader("🔍 Error Analysis")
    
    failed_validations = [r for r in session.validation_results if not r.is_valid and r.error_message]
    
    if not failed_validations:
        st.info("✅ No validation errors to analyze.")
        return
    
    # Group errors by similarity (simple keyword matching)
    error_groups = {}
    for result in failed_validations:
        error_msg = result.error_message.lower()
        
        # Simple error categorization
        if "syntax" in error_msg:
            category = "Syntax Errors"
        elif "undefined" in error_msg or "not found" in error_msg:
            category = "Undefined References"
        elif "type" in error_msg:
            category = "Type Errors"
        elif "permission" in error_msg or "allow" in error_msg:
            category = "Permission Logic"
        else:
            category = "Other Errors"
        
        if category not in error_groups:
            error_groups[category] = []
        error_groups[category].append(result)
    
    # Display error groups
    for category, errors in error_groups.items():
        with st.expander(f"{category} ({len(errors)} occurrences)"):
            for error in errors[:3]:  # Show first 3 examples
                st.write(f"**{error.validated_at.strftime('%m/%d %H:%M')}:** {error.error_message}")
            
            if len(errors) > 3:
                st.caption(f"... and {len(errors) - 3} more similar errors")


# Helper functions for async operations in Streamlit
def run_async_validation(policy_content: str, policy_id: str, session_id: str) -> PolicyValidationResult:
    """
    Helper function to run async validation in Streamlit context.
    
    Args:
        policy_content: Policy content to validate
        policy_id: Policy ID
        session_id: Session ID
        
    Returns:
        PolicyValidationResult
    """
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Initialize validator
        validator = AsyncPolarValidator()
        
        # Create validation request
        request = PolicyValidationRequest(
            policy_content=policy_content,
            policy_id=policy_id,
            session_id=session_id
        )
        
        # Run validation
        result = loop.run_until_complete(validator.validate_policy_async(request))
        
        # Clean up
        loop.run_until_complete(validator.close())
        loop.close()
        
        return result
        
    except Exception as e:
        return PolicyValidationResult(
            is_valid=False,
            error_message=f"Validation error: {str(e)}",
            error_details=[str(e)]
        )


def get_validation_status_color(is_valid: bool) -> str:
    """Get color for validation status display."""
    return "green" if is_valid else "red"


def format_validation_time(validation_time: float) -> str:
    """Format validation time for display."""
    if validation_time < 1:
        return f"{validation_time * 1000:.0f}ms"
    else:
        return f"{validation_time:.2f}s"


def get_error_severity(error_message: str) -> str:
    """Determine error severity based on error message."""
    if not error_message:
        return "info"
    
    error_lower = error_message.lower()
    
    if any(keyword in error_lower for keyword in ["fatal", "critical", "severe"]):
        return "error"
    elif any(keyword in error_lower for keyword in ["warning", "deprecated"]):
        return "warning"
    else:
        return "error"  # Default to error for validation failures