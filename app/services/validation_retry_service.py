"""Service that integrates validation with retry workflow for policy generation."""

import asyncio
import logging
import time
from typing import Optional, List, Callable, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field

from ..models.session import Session, GeneratedPolicy, ValidationResult
from ..models.policy import (
    PolicyGenerationRequest, 
    PolicyGenerationResult,
    PolicyRetryContext,
    PolicyValidationRequest,
    PolicyValidationResult
)
from ..models.events import SessionEvent, EventType, create_validation_completed_event
from .policy_generator import SessionPolicyGenerator
from .async_validator import AsyncPolarValidator, create_validation_event
from .event_logger import EventLogger

logger = logging.getLogger(__name__)


@dataclass
class ValidationRetryMetrics:
    """Metrics for validation and retry operations."""
    total_generations: int = 0
    successful_validations: int = 0
    failed_validations: int = 0
    total_retries: int = 0
    successful_retries: int = 0
    average_validation_time: float = 0.0
    average_generation_time: float = 0.0
    success_rate: float = 0.0
    retry_success_rate: float = 0.0
    
    def update_generation(self, generation_time: float):
        """Update generation metrics."""
        self.total_generations += 1
        total_time = self.average_generation_time * (self.total_generations - 1)
        self.average_generation_time = (total_time + generation_time) / self.total_generations
    
    def update_validation(self, is_valid: bool, validation_time: float):
        """Update validation metrics."""
        if is_valid:
            self.successful_validations += 1
        else:
            self.failed_validations += 1
        
        total_validations = self.successful_validations + self.failed_validations
        total_time = self.average_validation_time * (total_validations - 1)
        self.average_validation_time = (total_time + validation_time) / total_validations
        
        self.success_rate = self.successful_validations / total_validations if total_validations > 0 else 0.0
    
    def update_retry(self, is_successful: bool):
        """Update retry metrics."""
        self.total_retries += 1
        if is_successful:
            self.successful_retries += 1
        
        self.retry_success_rate = self.successful_retries / self.total_retries if self.total_retries > 0 else 0.0


@dataclass
class ValidationRetryResult:
    """Result of validation and retry workflow."""
    policy_result: PolicyGenerationResult
    validation_result: Optional[PolicyValidationResult] = None
    retry_count: int = 0
    total_time: float = 0.0
    is_final_success: bool = False
    error_context: List[str] = field(default_factory=list)
    
    @property
    def is_successful(self) -> bool:
        """Check if the overall workflow was successful."""
        if not self.policy_result.is_successful():
            return False
        
        # If validation was performed, check validation result
        if self.validation_result is not None:
            return self.validation_result.is_valid
        
        # If no validation was performed (auto_validate=False), 
        # success depends only on policy generation
        return self.is_final_success


class ValidationRetryService:
    """Service that integrates validation with retry workflow."""
    
    def __init__(self, 
                 policy_generator: SessionPolicyGenerator,
                 async_validator: AsyncPolarValidator,
                 event_logger: Optional[EventLogger] = None,
                 max_retries: int = 3,
                 auto_validate: bool = True):
        """Initialize the validation retry service.
        
        Args:
            policy_generator: Policy generation service
            async_validator: Async validation service
            event_logger: Optional event logger for audit trail
            max_retries: Maximum number of retry attempts
            auto_validate: Whether to automatically validate generated policies
        """
        self.policy_generator = policy_generator
        self.async_validator = async_validator
        self.event_logger = event_logger
        self.max_retries = max_retries
        self.auto_validate = auto_validate
        
        # Session-specific metrics
        self._session_metrics: Dict[str, ValidationRetryMetrics] = {}
    
    async def generate_and_validate_policy(self, 
                                         request: PolicyGenerationRequest, 
                                         session: Session,
                                         stream_callback: Optional[Callable[[str], None]] = None) -> ValidationRetryResult:
        """Generate a policy and validate it, with automatic retry on validation failure.
        
        Args:
            request: Policy generation request
            session: Session to generate policy for
            stream_callback: Optional callback for streaming generation
            
        Returns:
            ValidationRetryResult with generation and validation outcomes
        """
        start_time = time.time()
        retry_count = 0
        error_context = []
        
        # Initialize metrics for session if not exists
        if session.id not in self._session_metrics:
            self._session_metrics[session.id] = ValidationRetryMetrics()
        
        metrics = self._session_metrics[session.id]
        
        while retry_count <= self.max_retries:
            try:
                # Generate policy
                if stream_callback:
                    policy_result = self.policy_generator.generate_policy_stream(request, session, stream_callback)
                else:
                    policy_result = self.policy_generator.generate_policy(request, session)
                
                metrics.update_generation(policy_result.generation_time)
                
                if not policy_result.is_successful():
                    logger.error(f"Policy generation failed for session {session.id}: {policy_result.error_message}")
                    return ValidationRetryResult(
                        policy_result=policy_result,
                        retry_count=retry_count,
                        total_time=time.time() - start_time,
                        error_context=error_context
                    )
                
                # Log generation event
                current_policy = session.get_current_policy()
                if self.event_logger and current_policy:
                    await self._log_generation_event(session.id, current_policy, policy_result)
                
                # Validate policy if auto-validation is enabled
                if self.auto_validate:
                    validation_result = await self._validate_current_policy(session)
                    metrics.update_validation(validation_result.is_valid, validation_result.validation_time)
                    
                    # Log validation event
                    if self.event_logger:
                        await self._log_validation_event(session.id, session.get_current_policy().id, validation_result)
                    
                    if validation_result.is_valid:
                        # Success! Policy generated and validated
                        logger.info(f"Policy successfully generated and validated for session {session.id}")
                        return ValidationRetryResult(
                            policy_result=policy_result,
                            validation_result=validation_result,
                            retry_count=retry_count,
                            total_time=time.time() - start_time,
                            is_final_success=True,
                            error_context=error_context  # Include error context from previous attempts
                        )
                    else:
                        # Validation failed, prepare for retry
                        error_context.extend(validation_result.error_details)
                        logger.warning(f"Policy validation failed for session {session.id}, attempt {retry_count + 1}: {validation_result.error_message}")
                        
                        if retry_count < self.max_retries:
                            # Prepare retry request with error context
                            request = self._prepare_retry_request(session, validation_result.error_details, retry_count)
                            retry_count += 1
                            metrics.update_retry(False)  # This retry attempt failed
                        else:
                            # Max retries reached
                            logger.error(f"Maximum retries ({self.max_retries}) reached for session {session.id}")
                            return ValidationRetryResult(
                                policy_result=policy_result,
                                validation_result=validation_result,
                                retry_count=retry_count,
                                total_time=time.time() - start_time,
                                error_context=error_context
                            )
                else:
                    # Auto-validation disabled, return successful generation
                    return ValidationRetryResult(
                        policy_result=policy_result,
                        retry_count=retry_count,
                        total_time=time.time() - start_time,
                        is_final_success=True
                    )
                    
            except Exception as e:
                logger.error(f"Unexpected error in generate_and_validate_policy for session {session.id}: {e}")
                error_context.append(f"Unexpected error: {str(e)}")
                
                return ValidationRetryResult(
                    policy_result=PolicyGenerationResult(
                        success=False,
                        error_message=f"Unexpected error: {str(e)}"
                    ),
                    retry_count=retry_count,
                    total_time=time.time() - start_time,
                    error_context=error_context
                )
        
        # Should not reach here, but handle gracefully
        return ValidationRetryResult(
            policy_result=PolicyGenerationResult(
                success=False,
                error_message="Maximum retry attempts exceeded"
            ),
            retry_count=retry_count,
            total_time=time.time() - start_time,
            error_context=error_context
        )
    
    async def validate_existing_policy(self, session: Session, policy_id: str) -> PolicyValidationResult:
        """Validate an existing policy in the session.
        
        Args:
            session: Session containing the policy
            policy_id: ID of the policy to validate
            
        Returns:
            PolicyValidationResult with validation outcome
        """
        # Find the policy
        policy = None
        for p in session.generated_policies:
            if p.id == policy_id:
                policy = p
                break
        
        if not policy:
            logger.error(f"Policy {policy_id} not found in session {session.id}")
            return PolicyValidationResult(
                is_valid=False,
                error_message=f"Policy {policy_id} not found"
            )
        
        # Create validation request
        validation_request = PolicyValidationRequest(
            policy_content=policy.content,
            policy_id=policy.id,
            session_id=session.id
        )
        
        # Validate using async validator
        validation_result = await self.async_validator.validate_policy_async(validation_request)
        
        # Add validation result to session
        session_validation_result = ValidationResult.create(
            policy_id=policy.id,
            is_valid=validation_result.is_valid,
            error_message=validation_result.error_message,
            validation_time=validation_result.validation_time
        )
        session.add_validation_result(session_validation_result)
        
        # Log validation event
        if self.event_logger:
            await self._log_validation_event(session.id, policy.id, validation_result)
        
        # Update metrics
        if session.id in self._session_metrics:
            self._session_metrics[session.id].update_validation(
                validation_result.is_valid, 
                validation_result.validation_time
            )
        
        return validation_result
    
    async def retry_with_validation(self, 
                                  session: Session,
                                  validation_errors: List[str],
                                  stream_callback: Optional[Callable[[str], None]] = None) -> ValidationRetryResult:
        """Retry policy generation with validation errors as context.
        
        Args:
            session: Session to retry generation for
            validation_errors: List of validation errors to provide as context
            stream_callback: Optional callback for streaming generation
            
        Returns:
            ValidationRetryResult with retry outcome
        """
        # Create retry request
        retry_request = self._prepare_retry_request(session, validation_errors, 0)
        
        # Use the main generation and validation workflow
        result = await self.generate_and_validate_policy(retry_request, session, stream_callback)
        
        # Update retry metrics
        if session.id in self._session_metrics:
            self._session_metrics[session.id].update_retry(result.is_successful)
        
        return result
    
    def get_session_metrics(self, session_id: str) -> ValidationRetryMetrics:
        """Get validation and retry metrics for a session.
        
        Args:
            session_id: Session ID to get metrics for
            
        Returns:
            ValidationRetryMetrics for the session
        """
        return self._session_metrics.get(session_id, ValidationRetryMetrics())
    
    def get_validation_history(self, session_id: str, limit: Optional[int] = None) -> List:
        """Get validation history for a session from the async validator.
        
        Args:
            session_id: Session ID to get history for
            limit: Optional limit on number of entries
            
        Returns:
            List of validation history entries
        """
        return self.async_validator.get_validation_history(session_id, limit)
    
    def get_validation_stats(self, session_id: Optional[str] = None) -> Dict:
        """Get validation statistics from the async validator.
        
        Args:
            session_id: Optional session ID to filter stats
            
        Returns:
            Dictionary with validation statistics
        """
        return self.async_validator.get_validation_stats(session_id)
    
    def clear_session_cache(self, session_id: str) -> int:
        """Clear validation cache for a specific session.
        
        Args:
            session_id: Session ID to clear cache for
            
        Returns:
            Number of cache entries cleared
        """
        return self.async_validator.clear_cache(session_id)
    
    async def close(self):
        """Clean up resources."""
        await self.async_validator.close()
    
    async def _validate_current_policy(self, session: Session) -> PolicyValidationResult:
        """Validate the current policy in the session."""
        current_policy = session.get_current_policy()
        if not current_policy:
            return PolicyValidationResult(
                is_valid=False,
                error_message="No current policy to validate"
            )
        
        validation_request = PolicyValidationRequest(
            policy_content=current_policy.content,
            policy_id=current_policy.id,
            session_id=session.id
        )
        
        validation_result = await self.async_validator.validate_policy_async(validation_request)
        
        # Add validation result to session
        session_validation_result = ValidationResult.create(
            policy_id=current_policy.id,
            is_valid=validation_result.is_valid,
            error_message=validation_result.error_message,
            validation_time=validation_result.validation_time
        )
        session.add_validation_result(session_validation_result)
        
        return validation_result
    
    def _prepare_retry_request(self, session: Session, validation_errors: List[str], retry_count: int) -> PolicyGenerationRequest:
        """Prepare a retry request with error context."""
        current_policy = session.get_current_policy()
        
        retry_context = PolicyRetryContext(
            original_requirements=session.requirements_text,
            previous_policy=current_policy.content if current_policy else "",
            validation_errors=validation_errors,
            retry_count=retry_count
        )
        
        return PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            retry_context=retry_context.get_retry_prompt_context(),
            previous_errors=validation_errors
        )
    
    async def _log_generation_event(self, session_id: str, policy: GeneratedPolicy, result: PolicyGenerationResult):
        """Log a policy generation event."""
        if not self.event_logger:
            return
        
        event = SessionEvent.create(
            session_id=session_id,
            event_type=EventType.POLICY_GENERATED,
            document_id=policy.id,
            data={
                "model_used": result.model_used,
                "tokens_used": result.tokens_used,
                "generation_time": result.generation_time,
                "success": result.success
            }
        )
        
        await self.event_logger.log_event_async(event)
    
    async def _log_validation_event(self, session_id: str, policy_id: str, result: PolicyValidationResult):
        """Log a validation event."""
        if not self.event_logger:
            return
        
        event = create_validation_event(session_id, policy_id, result)
        await self.event_logger.log_event_async(event)


# Convenience functions for creating validation retry workflows
async def create_validation_retry_service(policy_generator: SessionPolicyGenerator,
                                        cli_path: str = "oso-cloud",
                                        event_logger: Optional[EventLogger] = None,
                                        max_retries: int = 3,
                                        auto_validate: bool = True) -> ValidationRetryService:
    """Create a validation retry service with default async validator.
    
    Args:
        policy_generator: Policy generation service
        cli_path: Path to oso-cloud CLI
        event_logger: Optional event logger
        max_retries: Maximum retry attempts
        auto_validate: Whether to auto-validate generated policies
        
    Returns:
        Configured ValidationRetryService
    """
    async_validator = AsyncPolarValidator(cli_path=cli_path)
    
    return ValidationRetryService(
        policy_generator=policy_generator,
        async_validator=async_validator,
        event_logger=event_logger,
        max_retries=max_retries,
        auto_validate=auto_validate
    )