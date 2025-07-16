from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from pathlib import Path

@dataclass
class GenerationRequest:
    """Request for AI model generation"""
    system_prompt: str
    user_prompt: str
    model_config: Optional[Dict[str, Any]] = None

@dataclass
class GenerationResponse:
    """Response from AI model generation"""
    content: str
    model_used: str
    tokens_used: Optional[int] = None
    error: Optional[str] = None

class AIService(ABC):
    """Abstract AI service for model agnosticism"""
    
    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate content using the AI model"""
        pass
    
    @abstractmethod
    def get_available_models(self) -> list[str]:
        """Get list of available models"""
        pass

# Import concrete implementations
from .openai_service import OpenAIService

# Export all public classes
__all__ = [
    'AIService',
    'GenerationRequest', 
    'GenerationResponse',
    'OpenAIService'
]
