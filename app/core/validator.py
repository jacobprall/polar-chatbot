import subprocess
import logging
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of Polar validation"""
    is_valid: bool
    error_message: Optional[str] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []

class PolarValidator:
    """Handles Polar syntax validation using oso-cloud CLI"""
    
    def __init__(self, cli_path: str = "oso-cloud", timeout: int = 30):
        self.cli_path = cli_path
        self.timeout = timeout
    
    def validate_policy(self, content: str) -> ValidationResult:
        """Validate Polar policy content"""
        try:
            # Write content to temporary file for validation
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.polar', delete=False) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            # Run validation command
            result = self._run_cli_command(["validate", temp_file_path])
            
            # Clean up temp file
            import os
            os.unlink(temp_file_path)
            
            if result is None:
                # No error output means validation passed
                return ValidationResult(is_valid=True)
            else:
                return ValidationResult(
                    is_valid=False,
                    error_message=result,
                    errors=[result]
                )
                
        except Exception as e:
            logger.error(f"Error during validation: {e}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Validation error: {str(e)}",
                errors=[str(e)]
            )
    
    def _run_cli_command(self, args: List[str]) -> Optional[str]:
        """Run oso-cloud CLI command and return error output if any"""
        try:
            command = [self.cli_path] + args
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True
            )
            return None  # No error
        except subprocess.CalledProcessError as e:
            logger.error(f"CLI command failed: {e}")
            return e.stderr
        except subprocess.TimeoutExpired:
            logger.error(f"CLI command timed out after {self.timeout} seconds")
            return "Command timed out"
        except FileNotFoundError:
            logger.error(f"CLI command not found: {self.cli_path}")
            return f"Command not found: {self.cli_path}"
        except Exception as e:
            logger.error(f"Unexpected error running CLI command: {e}")
            return str(e) 