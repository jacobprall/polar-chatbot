from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml
import os

@dataclass
class AIConfig:
    """AI service configuration"""
    provider: str = "openai"
    model: str = "gpt-4"
    api_key: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: float = 0.1
    timeout: int = 30

@dataclass
class StorageConfig:
    """Storage backend configuration"""
    backend: str = "local"
    base_path: str = "./"
    # S3-specific configs
    bucket_name: Optional[str] = None
    region: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None

@dataclass
class PolarConfig:
    """Polar validation configuration"""
    cli_path: str = "oso-cloud"
    validation_timeout: int = 30
    max_retry_attempts: int = 3

@dataclass
class PathsConfig:
    """Path configuration"""
    system_prompts: str = "data/system_prompts"
    user_inputs: str = "data/user_requirements"
    results: str = "results"
    tests: str = "tests"

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None

@dataclass
class AppConfig:
    """Main application configuration"""
    ai: AIConfig = field(default_factory=AIConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    polar: PolarConfig = field(default_factory=PolarConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_file(cls, config_path: str) -> "AppConfig":
        """Load configuration from YAML file"""
        if not os.path.exists(config_path):
            return cls()
        
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        config_data["ai"]["api_key"] = os.getenv("OPENAI_API_KEY", "REMOVED")
        print(f"OpenAI API key: {config_data['ai']['api_key']}")
        return cls(
            ai=AIConfig(**config_data.get("ai", {})),
            storage=StorageConfig(**config_data.get("storage", {})),
            polar=PolarConfig(**config_data.get("polar", {})),
            paths=PathsConfig(**config_data.get("paths", {})),
            logging=LoggingConfig(**config_data.get("logging", {}))
        )
    
    def to_file(self, config_path: str) -> None:
        """Save configuration to YAML file"""
        config_data = {
            "ai": {
                "provider": self.ai.provider,
                "model": self.ai.model,
                "temperature": self.ai.temperature,
                "timeout": self.ai.timeout,
            },
            "storage": {
                "backend": self.storage.backend,
                "base_path": self.storage.base_path
            },
            "polar": {
                "cli_path": self.polar.cli_path,
                "validation_timeout": self.polar.validation_timeout,
                "max_retry_attempts": self.polar.max_retry_attempts
            },
            "paths": {
                "system_prompts": self.paths.system_prompts,
                "user_inputs": self.paths.user_inputs,
                "results": self.paths.results,
                "tests": self.paths.tests
            },
            "logging": {
                "level": self.logging.level,
                "format": self.logging.format
            }
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
