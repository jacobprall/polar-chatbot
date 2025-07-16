import time
import logging
from typing import Optional, List
from pathlib import Path

from ..models.policy_request import PolicyRequest, PolicyResponse, ValidationStatus
from ..models.config import AppConfig
from ..services import AIService, GenerationRequest, OpenAIService
from ..storage import StorageBackend, LocalStorageBackend
from .validator import PolarValidator
from .error_handler import ErrorHandler

logger = logging.getLogger(__name__)

class PolicyGenerator:
    """Main policy generator orchestrating the entire process"""
    
    def __init__(self, 
                 ai_service: AIService,
                 storage_backend: StorageBackend,
                 validator: PolarValidator,
                 error_handler: ErrorHandler,
                 config: AppConfig):
        self.ai_service = ai_service
        self.storage_backend = storage_backend
        self.validator = validator
        self.error_handler = error_handler
        self.config = config

    @classmethod
    def from_config(cls, config: AppConfig) -> 'PolicyGenerator':
        """Create a PolicyGenerator instance from configuration"""
        # Setup AI service
        ai_service = OpenAIService(
            api_key=config.ai.api_key,
            default_model=config.ai.model
        )
        
        # Setup storage backend
        storage_backend = LocalStorageBackend(config.storage.base_path)
        
        # Setup validator
        validator = PolarValidator(
            cli_path=config.polar.cli_path,
            timeout=config.polar.validation_timeout
        )
        
        # Setup error handler
        error_handler = ErrorHandler(ai_service, storage_backend)
        
        return cls(
            ai_service=ai_service,
            storage_backend=storage_backend,
            validator=validator,
            error_handler=error_handler,
            config=config
        )
    
    def generate_policy(self, request: PolicyRequest) -> PolicyResponse:
        """Generate a policy from the given request"""
        start_time = time.time()
        
        try:
            # Step 1: Read and concatenate system prompts
            logger.info("Reading system prompts...")
            system_prompt = self._build_system_prompt(request.system_prompts)
            if not system_prompt:
                return PolicyResponse(
                    success=False,
                    error_message="Failed to read system prompts"
                )
            
            # Step 2: Generate policy using AI service
            logger.info("Generating policy using AI service...")
            generation_request = GenerationRequest(
                system_prompt=system_prompt,
                user_prompt=request.prompt,
                model_config=request.model_config
            )
            
            generation_response = self.ai_service.generate(generation_request)
            
            if generation_response.error:
                return PolicyResponse(
                    success=False,
                    error_message=f"AI generation failed: {generation_response.error}"
                )
            
            # Step 3: Write generated policy to storage
            logger.info("Writing policy to storage...")
            output_key = f"{request.output_directory}/{request.output_filename}"
            success = self.storage_backend.put_object(
                key=output_key,
                content=generation_response.content,
                content_type="text/plain"
            )
            
            if not success:
                return PolicyResponse(
                    success=False,
                    error_message="Failed to write policy to storage"
                )
            
            # Step 4: Validate the generated policy
            logger.info("Validating generated policy...")
            validation_result = self.validator.validate_policy(generation_response.content)
            
            if validation_result.is_valid:
                # Success case
                generation_time = time.time() - start_time
                return PolicyResponse(
                    success=True,
                    file_path=output_key,
                    content=generation_response.content,
                    validation_status=ValidationStatus.SUCCESS,
                    model_used=generation_response.model_used,
                    tokens_used=generation_response.tokens_used,
                    generation_time=generation_time
                )
            else:
                # Try to fix validation errors
                logger.info("Validation failed, attempting to fix...")
                return self._handle_validation_failure(
                    request, generation_response, validation_result, start_time
                )
                
        except Exception as e:
            logger.error(f"Unexpected error in policy generation: {e}")
            return PolicyResponse(
                success=False,
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def _build_system_prompt(self, system_prompt_paths: List[str]) -> Optional[str]:
        """Build system prompt by reading and concatenating files"""
        try:
            concatenated_content = ""
            
            for prompt_path in system_prompt_paths:
                # Try to read from storage backend
                storage_object = self.storage_backend.get_object(prompt_path)
                if storage_object:
                    concatenated_content += storage_object.content + "\n\n"
                else:
                    logger.warning(f"Could not read system prompt: {prompt_path}")
            
            return concatenated_content.strip() if concatenated_content else None
            
        except Exception as e:
            logger.error(f"Error building system prompt: {e}")
            return None
    
    def _handle_validation_failure(self, 
                                 request: PolicyRequest,
                                 generation_response: 'GenerationResponse',
                                 validation_result: 'ValidationResult',
                                 start_time: float) -> PolicyResponse:
        """Handle validation failure by attempting to fix the policy"""
        
        # Retry the policy using error handler
        retry_attempt = self.error_handler.retry_policy(
            original_content=generation_response.content,
            error_message=validation_result.error_message,
            system_prompts=request.system_prompts
        )
        
        if not retry_attempt:
            # Could not fix the policy
            generation_time = time.time() - start_time
            return PolicyResponse(
                success=False,
                file_path=f"{request.output_directory}/{request.output_filename}",
                content=generation_response.content,
                error_message=f"Policy generation failed validation and could not be fixed: {validation_result.error_message}",
                validation_status=ValidationStatus.FAILED,
                validation_errors=validation_result.errors,
                model_used=generation_response.model_used,
                tokens_used=generation_response.tokens_used,
                generation_time=generation_time
            )
        
        # Write fixed policy
        fixed_filename = f"fixed_{request.output_filename}"
        fixed_key = f"{request.output_directory}/{fixed_filename}"
        
        success = self.storage_backend.put_object(
            key=fixed_key,
            content=retry_attempt,
            content_type="text/plain"
        )
        
        if not success:
            generation_time = time.time() - start_time
            return PolicyResponse(
                success=False,
                error_message="Failed to write fixed policy to storage",
                model_used=generation_response.model_used,
                tokens_used=generation_response.tokens_used,
                generation_time=generation_time
            )
        
        # Validate the fixed policy
        fixed_validation = self.validator.validate_policy(retry_attempt)
        
        generation_time = time.time() - start_time
        
        if fixed_validation.is_valid:
            return PolicyResponse(
                success=True,
                file_path=fixed_key,
                content=retry_attempt,
                validation_status=ValidationStatus.FIXED,
                retry_attempts=1,
                model_used=generation_response.model_used,
                tokens_used=generation_response.tokens_used,
                generation_time=generation_time
            )
        else:
            return PolicyResponse(
                success=False,
                file_path=fixed_key,
                content=retry_attempt,
                error_message=f"Fixed policy still has validation errors: {fixed_validation.error_message}",
                validation_status=ValidationStatus.FAILED,
                validation_errors=fixed_validation.errors,
                retry_attempts=1,
                model_used=generation_response.model_used,
                tokens_used=generation_response.tokens_used,
                generation_time=generation_time
            ) 
