import logging
from typing import Optional, List
from ..services import AIService, GenerationRequest
from ..storage import StorageBackend

logger = logging.getLogger(__name__)

handle_error_prompt_path = "app/system_prompts/handle_error.mdx"

class ErrorHandler:
    """Handles error correction for Polar policies"""
    
    def __init__(self, ai_service: AIService, storage_backend: StorageBackend):
        self.ai_service = ai_service
        self.storage_backend = storage_backend
    
    def fix_policy(self, original_content: str, error_message: str, 
                   system_prompts: List[str]) -> Optional[str]:
        """Attempt to fix Polar policy syntax errors"""
        try:
            # Build error correction prompt
            error_prompt = self._build_error_prompt(original_content, error_message, system_prompts)
            
            if not error_prompt:
                logger.error("Failed to build error correction prompt")
                return None
            
            # Generate fix using AI service
            generation_request = GenerationRequest(
                system_prompt="You are a Polar policy syntax expert. Fix syntax errors in Polar code and return only the corrected code without any markdown formatting.",
                user_prompt=error_prompt
            )
            
            generation_response = self.ai_service.generate(generation_request)
            
            if generation_response.error:
                logger.error(f"Error correction failed: {generation_response.error}")
                return None
            
            # Clean up the response (remove markdown formatting if present)
            fixed_content = self._clean_response(generation_response.content)
            
            logger.info("Successfully generated error correction")
            return fixed_content
            
        except Exception as e:
            logger.error(f"Error in fix_policy: {e}")
            return None
    
    def _build_error_prompt(self, original_content: str, error_message: str, 
                           system_prompts: List[str]) -> Optional[str]:
        """Build prompt for error correction"""
        try:
            # Read error handling prompt
            error_handling_prompt = self._get_error_handling_prompt()
            if not error_handling_prompt:
                return None
            
            # Build the full prompt
            prompt = f"{error_handling_prompt}\n\nError: {error_message}\n\nOriginal Code:\n{original_content}"
            
            return prompt
            
        except Exception as e:
            logger.error(f"Error building error prompt: {e}")
            return None
    
    def _get_error_handling_prompt(self) -> Optional[str]:
        """Get the error handling prompt from storage"""
        try:
            # Try to find handle_error.mdx in system prompts
            storage_object = self.storage_backend.get_object(handle_error_prompt_path)
            if storage_object:
                return storage_object.content
            
            # Fallback to a default prompt
            return "Fix the following Polar syntax errors. Return only the corrected code without any markdown formatting or explanations."
            
        except Exception as e:
            logger.error(f"Error reading error handling prompt: {e}")
            return None
    
    def _clean_response(self, response: str) -> str:
        """Clean up AI response to extract just the code"""
        content = response.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```polar"):
            content = content[8:]
        elif content.startswith("```"):
            content = content[3:]
        
        if content.endswith("```"):
            content = content[:-3]
        
        return content.strip() 