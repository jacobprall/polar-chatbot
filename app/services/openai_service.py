import os
from typing import Optional, Dict, Any
from openai import OpenAI
from . import AIService, GenerationRequest, GenerationResponse

class OpenAIService(AIService):
    """OpenAI implementation of AI service"""
    
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4"):
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=self.api_key)
        self.default_model = default_model
    
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate content using OpenAI API"""
        try:
            # Use provided model config or default
            model_config = request.model_config or {}
            model = model_config.get("model", self.default_model)
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt}
                ],
                temperature=request.model_config.get("temperature", 1)
            )
            
            content = response.choices[0].message.content
            # Clean content by removing polar code block markers if present
            if content.startswith("```polar"):
                content = content[8:]  # Remove ```polar
            if content.endswith("```"):
                content = content[:-3]  # Remove ```
            tokens_used = response.usage.total_tokens if response.usage else None
            
            return GenerationResponse(
                content=content,
                model_used=model,
                tokens_used=tokens_used
            )
            
        except Exception as e:
            return GenerationResponse(
                content="",
                model_used=request.model_config.get("model", self.default_model) if request.model_config else self.default_model,
                error=str(e)
            )
    
    def get_available_models(self) -> list[str]:
        """Get list of available OpenAI models"""
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k"
        ] 