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
                 validator: Optional[PolarValidator] = None):
        self.ai_service = ai_service
        self.validator = validator
        self.max_retries = 3
    
    def generate_policy(self, request: PolicyGenerationRequest, session: Session) -> PolicyGenerationResult:
        """Generate a Polar policy for the given session"""
        logger.info(f"Generating policy for session {session.id}")
        
        # Generate the policy using AI service
        result = self.ai_service.generate_policy(request, session)
        
        if result.is_successful():
            # Create and add the policy to the session
            policy = GeneratedPolicy.create(
                content=result.policy_content,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                generation_time=result.generation_time
            )
            session.add_policy(policy)
            
            logger.info(f"Successfully generated policy {policy.id} for session {session.id}")
        else:
            logger.error(f"Policy generation failed for session {session.id}: {result.error_message}")
        
        return result
    
    def generate_policy_stream(self, 
                             request: PolicyGenerationRequest, 
                             session: Session,
                             callback: Callable[[str], None]) -> PolicyGenerationResult:
        """Generate a Polar policy with streaming support"""
        logger.info(f"Generating policy with streaming for session {session.id}")
        
        # Generate the policy using streaming AI service
        result = self.ai_service.generate_policy_stream(request, session, callback)
        
        if result.is_successful():
            # Create and add the policy to the session
            policy = GeneratedPolicy.create(
                content=result.policy_content,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                generation_time=result.generation_time
            )
            session.add_policy(policy)
            
            logger.info(f"Successfully generated streaming policy {policy.id} for session {session.id}")
        else:
            logger.error(f"Streaming policy generation failed for session {session.id}: {result.error_message}")
        
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
        if retry_count >= self.max_retries:
            logger.error(f"Maximum retry attempts ({self.max_retries}) reached for session {session.id}")
            return PolicyGenerationResult(
                success=False,
                error_message=f"Maximum retry attempts ({self.max_retries}) exceeded"
            )
        
        logger.info(f"Retrying policy generation for session {session.id} (attempt {retry_count + 1})")
        
        # Get the current policy for context
        current_policy = session.get_current_policy()
        if not current_policy:
            logger.error(f"No current policy found for retry in session {session.id}")
            return PolicyGenerationResult(
                success=False,
                error_message="No current policy found for retry"
            )
        
        # Build retry context
        retry_context = PolicyRetryContext(
            original_requirements=session.requirements_text,
            previous_policy=current_policy.content,
            validation_errors=validation_errors,
            retry_count=retry_count
        )
        
        # Create retry request
        retry_request = PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            retry_context=retry_context.get_retry_prompt_context(),
            previous_errors=validation_errors
        )
        
        # Generate new policy
        result = self.ai_service.generate_policy(retry_request, session)
        
        if result.is_successful():
            # Create and add the new policy to the session
            policy = GeneratedPolicy.create(
                content=result.policy_content,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                generation_time=result.generation_time
            )
            session.add_policy(policy)
            
            logger.info(f"Successfully generated retry policy {policy.id} for session {session.id}")
        else:
            logger.error(f"Retry policy generation failed for session {session.id}: {result.error_message}")
        
        return result
    
    def retry_policy_generation_stream(self,
                                     session: Session,
                                     validation_errors: List[str],
                                     callback: Callable[[str], None],
                                     retry_count: int = 0) -> PolicyGenerationResult:
        """Retry policy generation with streaming and error context"""
        if retry_count >= self.max_retries:
            logger.error(f"Maximum retry attempts ({self.max_retries}) reached for session {session.id}")
            return PolicyGenerationResult(
                success=False,
                error_message=f"Maximum retry attempts ({self.max_retries}) exceeded"
            )
        
        logger.info(f"Retrying policy generation with streaming for session {session.id} (attempt {retry_count + 1})")
        
        # Get the current policy for context
        current_policy = session.get_current_policy()
        if not current_policy:
            logger.error(f"No current policy found for retry in session {session.id}")
            return PolicyGenerationResult(
                success=False,
                error_message="No current policy found for retry"
            )
        
        # Build retry context
        retry_context = PolicyRetryContext(
            original_requirements=session.requirements_text,
            previous_policy=current_policy.content,
            validation_errors=validation_errors,
            retry_count=retry_count
        )
        
        # Create retry request
        retry_request = PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            retry_context=retry_context.get_retry_prompt_context(),
            previous_errors=validation_errors
        )
        
        # Generate new policy with streaming
        result = self.ai_service.generate_policy_stream(retry_request, session, callback)
        
        if result.is_successful():
            # Create and add the new policy to the session
            policy = GeneratedPolicy.create(
                content=result.policy_content,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                generation_time=result.generation_time
            )
            session.add_policy(policy)
            
            logger.info(f"Successfully generated streaming retry policy {policy.id} for session {session.id}")
        else:
            logger.error(f"Streaming retry policy generation failed for session {session.id}: {result.error_message}")
        
        return result
    
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