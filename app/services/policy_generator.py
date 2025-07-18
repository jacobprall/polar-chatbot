"""Simplified policy generator for session-based Polar policy generation."""

import time
import logging
from typing import Optional, List, Callable
from datetime import datetime

from ..models.session import Session, GeneratedPolicy
from ..models.policy import (
    PolicyGenerationRequest, 
    PolicyGenerationResult,
    PolicyRetryContext,
    PolicyValidationRequest,
    PolicyValidationResult
)
from .openai_service import SessionAwareOpenAIService
from ..core.validator import PolarValidator

logger = logging.getLogger(__name__)


class SessionPolicyGenerator:
    """Simplified policy generator that integrates with session management"""
    
    def __init__(self, 
                 ai_service: SessionAwareOpenAIService,
                 validator: Optional[PolarValidator] = None,
                 max_retries: int = 3):
        self.ai_service = ai_service
        self.validator = validator
        self.max_retries = max_retries
    
    def generate_policy(self, request: PolicyGenerationRequest, session: Session) -> PolicyGenerationResult:
        """Generate a Polar policy for the given session"""
        logger.info(f"Generating policy for session {session.id}")
        result = self.ai_service.generate_policy(request, session)
        return self._process_generation_result(result, session, "policy")
    
    def generate_policy_stream(self, 
                             request: PolicyGenerationRequest, 
                             session: Session,
                             callback: Callable[[str], None]) -> PolicyGenerationResult:
        """Generate a Polar policy with streaming support"""
        logger.info(f"Generating policy with streaming for session {session.id}")
        result = self.ai_service.generate_policy_stream(request, session, callback)
        return self._process_generation_result(result, session, "streaming policy")
    
    def _process_generation_result(self, result: PolicyGenerationResult, 
                                 session: Session, generation_type: str) -> PolicyGenerationResult:
        """Process generation result and add policy to session if successful"""
        if result.is_successful():
            policy = GeneratedPolicy.create(
                content=result.policy_content,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                generation_time=result.generation_time
            )
            session.add_policy(policy)
            logger.info(f"Successfully generated {generation_type} {policy.id} for session {session.id}")
        else:
            logger.error(f"{generation_type.title()} generation failed for session {session.id}: {result.error_message}")
        
        return result
    
    def validate_policy(self, policy_content: str, policy_id: str, session_id: str) -> PolicyValidationResult:
        """Validate a generated policy"""
        if not self.validator:
            logger.warning("No validator configured, skipping validation")
            return PolicyValidationResult(
                is_valid=True,
                error_message="Validation skipped - no validator configured"
            )
        
        logger.info(f"Validating policy {policy_id} for session {session_id}")
        start_time = time.time()
        
        try:
            # Use the existing validator
            validation_result = self.validator.validate_policy(policy_content)
            validation_time = time.time() - start_time
            
            if validation_result.is_valid:
                logger.info(f"Policy {policy_id} validation successful")
                return PolicyValidationResult(
                    is_valid=True,
                    validation_time=validation_time
                )
            else:
                logger.warning(f"Policy {policy_id} validation failed: {validation_result.error_message}")
                return PolicyValidationResult(
                    is_valid=False,
                    error_message=validation_result.error_message,
                    error_details=validation_result.errors or [],
                    validation_time=validation_time
                )
        
        except Exception as e:
            validation_time = time.time() - start_time
            logger.error(f"Policy validation error for {policy_id}: {e}")
            return PolicyValidationResult(
                is_valid=False,
                error_message=f"Validation error: {str(e)}",
                validation_time=validation_time
            )
    
    def retry_policy_generation(self, 
                              session: Session,
                              validation_errors: List[str],
                              retry_count: int = 0) -> PolicyGenerationResult:
        """Retry policy generation with error context"""
        return self._retry_policy_generation_internal(session, validation_errors, retry_count, streaming=False)
    
    def retry_policy_generation_stream(self,
                                     session: Session,
                                     validation_errors: List[str],
                                     callback: Callable[[str], None],
                                     retry_count: int = 0) -> PolicyGenerationResult:
        """Retry policy generation with streaming and error context"""
        return self._retry_policy_generation_internal(session, validation_errors, retry_count, 
                                                    streaming=True, callback=callback)
    
    def _retry_policy_generation_internal(self, session: Session, validation_errors: List[str],
                                        retry_count: int, streaming: bool = False,
                                        callback: Optional[Callable[[str], None]] = None) -> PolicyGenerationResult:
        """Internal method for retry policy generation"""
        if retry_count >= self.max_retries:
            logger.error(f"Maximum retry attempts ({self.max_retries}) reached for session {session.id}")
            return PolicyGenerationResult(
                success=False,
                error_message=f"Maximum retry attempts ({self.max_retries}) exceeded"
            )
        
        stream_text = "with streaming " if streaming else ""
        logger.info(f"Retrying policy generation {stream_text}for session {session.id} (attempt {retry_count + 1})")
        
        # Validate retry conditions
        current_policy = session.get_current_policy()
        if not current_policy:
            logger.error(f"No current policy found for retry in session {session.id}")
            return PolicyGenerationResult(
                success=False,
                error_message="No current policy found for retry"
            )
        
        # Create retry request
        retry_request = self._build_retry_request(session, current_policy, validation_errors, retry_count)
        
        # Generate new policy
        if streaming and callback:
            result = self.ai_service.generate_policy_stream(retry_request, session, callback)
        else:
            result = self.ai_service.generate_policy(retry_request, session)
        
        return self._process_generation_result(result, session, f"retry policy{' (streaming)' if streaming else ''}")
    
    def _build_retry_request(self, session: Session, current_policy: GeneratedPolicy,
                           validation_errors: List[str], retry_count: int) -> PolicyGenerationRequest:
        """Build retry request with context"""
        retry_context = PolicyRetryContext(
            original_requirements=session.requirements_text,
            previous_policy=current_policy.content,
            validation_errors=validation_errors,
            retry_count=retry_count
        )
        
        return PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            retry_context=retry_context.get_retry_prompt_context(),
            previous_errors=validation_errors
        )
    
    def get_generation_history(self, session: Session) -> List[GeneratedPolicy]:
        """Get the generation history for a session"""
        return sorted(session.generated_policies, key=lambda p: p.generated_at)
    
    def get_generation_stats(self, session: Session) -> dict:
        """Get generation statistics for a session"""
        policies = session.generated_policies
        
        if not policies:
            return {
                "total_generations": 0,
                "total_tokens": 0,
                "total_time": 0.0,
                "average_time": 0.0,
                "models_used": []
            }
        
        total_tokens = sum(p.tokens_used or 0 for p in policies)
        total_time = sum(p.generation_time for p in policies)
        models_used = list(set(p.model_used for p in policies))
        
        return {
            "total_generations": len(policies),
            "total_tokens": total_tokens,
            "total_time": total_time,
            "average_time": total_time / len(policies),
            "models_used": models_used
        }