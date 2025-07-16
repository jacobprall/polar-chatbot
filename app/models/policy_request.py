from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
from enum import Enum

class ValidationStatus(Enum):
    """Validation status enumeration"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    FIXED = "fixed"

@dataclass
class PolicyRequest:
    """Request for policy generation"""
    prompt: str
    output_file_path: str
    system_prompts: List[str] = field(default_factory=list)
    model_config: Optional[Dict[str, Any]] = None
    storage_config: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Resolve the output file path to absolute path"""
        self._path = Path(self.output_file_path).resolve()
        self.output_file_path = str(self._path)
    
    @property
    def output_directory(self) -> str: return str(self._path.parent)
    
    @property
    def output_filename(self) -> str: return self._path.name

@dataclass
class PolicyResponse:
    """Response from policy generation"""
    success: bool
    file_path: Optional[str] = None
    content: Optional[str] = None
    error_message: Optional[str] = None
    validation_status: ValidationStatus = ValidationStatus.PENDING
    validation_errors: List[str] = field(default_factory=list)
    retry_attempts: int = 0
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    generation_time: Optional[float] = None
    
    def is_valid(self) -> bool:
        """Check if the policy was successfully generated and validated"""
        return (self.success and 
                self.validation_status in [ValidationStatus.SUCCESS, ValidationStatus.FIXED])
    
    def has_errors(self) -> bool:
        """Check if there are any errors"""
        return not self.success or self.validation_status == ValidationStatus.FAILED 
