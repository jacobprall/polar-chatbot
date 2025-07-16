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

@dataclass
class PolicyRequest:
    prompt: str
    system_prompts: List[str]
    output_directory: str = "./results"
    output_filename: str = "generated_policy.polar"
    
@dataclass
class PolicyResponse:
    success: bool
    file_path: Optional[Path] = None
    error_message: Optional[str] = None
    validation_passed: bool = False
    retry_attempts: int = 0 