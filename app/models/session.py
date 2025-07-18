"""Session data models for the Polar Prompt Tester application."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid


@dataclass
class GeneratedPolicy:
    """Represents a generated Polar policy with metadata."""
    id: str
    content: str
    generated_at: datetime
    model_used: str
    tokens_used: Optional[int] = None
    generation_time: float = 0.0
    is_current: bool = False
    
    @classmethod
    def create(cls, content: str, model_used: str, tokens_used: Optional[int] = None, 
               generation_time: float = 0.0) -> 'GeneratedPolicy':
        """Create a new GeneratedPolicy with auto-generated ID."""
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            generated_at=datetime.utcnow(),
            model_used=model_used,
            tokens_used=tokens_used,
            generation_time=generation_time,
            is_current=True
        )


@dataclass
class ValidationResult:
    """Represents the result of Polar policy validation."""
    id: str
    policy_id: str
    is_valid: bool
    error_message: Optional[str]
    validated_at: datetime
    validation_time: float = 0.0
    
    @classmethod
    def create(cls, policy_id: str, is_valid: bool, error_message: Optional[str] = None,
               validation_time: float = 0.0) -> 'ValidationResult':
        """Create a new ValidationResult with auto-generated ID."""
        return cls(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            is_valid=is_valid,
            error_message=error_message,
            validated_at=datetime.utcnow(),
            validation_time=validation_time
        )


@dataclass
class SessionMetadata:
    """Lightweight session metadata for listing and selection."""
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    has_requirements: bool = False
    has_policies: bool = False
    policy_count: int = 0


@dataclass
class Session:
    """Complete session data model for the Polar Prompt Tester."""
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    requirements_text: str = ""
    generated_policies: List[GeneratedPolicy] = field(default_factory=list)
    validation_results: List[ValidationResult] = field(default_factory=list)
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(cls, name: str) -> 'Session':
        """Create a new session with auto-generated ID and timestamps."""
        now = datetime.utcnow()
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            created_at=now,
            updated_at=now
        )
    
    def update_timestamp(self) -> None:
        """Update the session's last modified timestamp."""
        self.updated_at = datetime.utcnow()
    
    def add_policy(self, policy: GeneratedPolicy) -> None:
        """Add a new policy and mark it as current."""
        # Mark all existing policies as not current
        for existing_policy in self.generated_policies:
            existing_policy.is_current = False
        
        # Add the new policy as current
        policy.is_current = True
        self.generated_policies.append(policy)
        self.update_timestamp()
    
    def get_current_policy(self) -> Optional[GeneratedPolicy]:
        """Get the current active policy."""
        for policy in self.generated_policies:
            if policy.is_current:
                return policy
        return None
    
    def add_validation_result(self, result: ValidationResult) -> None:
        """Add a validation result to the session."""
        self.validation_results.append(result)
        self.update_timestamp()
    
    def get_latest_validation(self, policy_id: str) -> Optional[ValidationResult]:
        """Get the most recent validation result for a specific policy."""
        policy_results = [r for r in self.validation_results if r.policy_id == policy_id]
        if policy_results:
            return max(policy_results, key=lambda r: r.validated_at)
        return None
    
    def to_metadata(self) -> SessionMetadata:
        """Convert to lightweight metadata representation."""
        return SessionMetadata(
            id=self.id,
            name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
            has_requirements=bool(self.requirements_text.strip()),
            has_policies=len(self.generated_policies) > 0,
            policy_count=len(self.generated_policies)
        )