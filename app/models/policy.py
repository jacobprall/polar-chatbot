"""Policy data models for the Polar Prompt Tester application."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import uuid


class PolicyStatus(Enum):
    """Status of a generated policy."""
    GENERATED = "generated"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    REWORKED = "reworked"


class ValidationStatus(Enum):
    """Validation status enumeration."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class PolicyGenerationRequest:
    """Request for policy generation within a session context."""
    session_id: str
    requirements_text: str
    model_config: Dict[str, Any] = field(default_factory=lambda: {
        "model": "gpt-4",
        "temperature": 0.1,
        "max_tokens": None
    })
    retry_context: Optional[str] = None
    previous_errors: List[str] = field(default_factory=list)


@dataclass
class PolicyGenerationResult:
    """Result of policy generation."""
    success: bool
    policy_content: Optional[str] = None
    error_message: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    generation_time: float = 0.0
    
    def is_successful(self) -> bool:
        """Check if generation was successful."""
        return self.success and self.policy_content is not None


@dataclass
class PolicyValidationRequest:
    """Request for policy validation."""
    policy_content: str
    policy_id: str
    session_id: str


@dataclass
class PolicyValidationResult:
    """Result of policy validation."""
    is_valid: bool
    error_message: Optional[str] = None
    error_details: List[str] = field(default_factory=list)
    validation_time: float = 0.0
    
    def has_errors(self) -> bool:
        """Check if validation found errors."""
        return not self.is_valid or bool(self.error_message)
    
    def get_error_summary(self) -> str:
        """Get a summary of validation errors."""
        if not self.has_errors():
            return ""
        
        if self.error_message:
            return self.error_message
        
        if self.error_details:
            return "; ".join(self.error_details)
        
        return "Unknown validation error"


@dataclass
class PolicyRetryContext:
    """Context for policy generation retry attempts."""
    original_requirements: str
    previous_policy: str
    validation_errors: List[str]
    retry_count: int = 0
    max_retries: int = 3
    
    def can_retry(self) -> bool:
        """Check if more retries are allowed."""
        return self.retry_count < self.max_retries
    
    def increment_retry(self) -> None:
        """Increment the retry counter."""
        self.retry_count += 1
    
    def get_retry_prompt_context(self) -> str:
        """Generate context for retry prompt."""
        context_parts = [
            f"Previous attempt generated this policy:\n{self.previous_policy}",
            f"Validation failed with these errors:\n" + "\n".join(f"- {error}" for error in self.validation_errors),
            f"Please fix these issues and generate a corrected policy."
        ]
        return "\n\n".join(context_parts)