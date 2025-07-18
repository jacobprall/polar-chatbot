"""Configuration models for the Polar Prompt Tester application."""

from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class StreamlitConfig:
    """Streamlit application configuration."""
    title: str = "Polar Prompt Tester"
    port: int = 8501
    host: str = "0.0.0.0"
    theme: str = "light"


@dataclass
class StorageConfig:
    """Storage backend configuration."""
    type: str = "local"  # "local" or "s3"
    path: str = "./test_sessions"
    
    # S3 specific settings
    bucket_name: Optional[str] = None
    region: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None


@dataclass
class SessionsConfig:
    """Session management configuration."""
    max_sessions: int = 100
    auto_save_interval: int = 30  # seconds
    session_timeout: int = 3600  # seconds


@dataclass
class OpenAIConfig:
    """OpenAI service configuration."""
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    api_key: Optional[str] = None


@dataclass
class PolarConfig:
    """Polar validation configuration."""
    cli_path: str = "oso-cloud"


@dataclass
class EventsConfig:
    """Event logging configuration."""
    batch_size: int = 100
    retention_days: int = 90
    compression: bool = True


@dataclass
class AppConfig:
    """Main application configuration."""
    streamlit: StreamlitConfig
    storage: StorageConfig
    sessions: SessionsConfig
    openai: OpenAIConfig
    polar: PolarConfig
    events: EventsConfig
    
    @classmethod
    def create_default(cls) -> 'AppConfig':
        """Create default configuration with environment variable overrides."""
        return cls(
            streamlit=StreamlitConfig(
                title=os.getenv("STREAMLIT_TITLE", "Polar Prompt Tester"),
                port=int(os.getenv("STREAMLIT_PORT", "8501")),
                host=os.getenv("STREAMLIT_HOST", "0.0.0.0"),
                theme=os.getenv("STREAMLIT_THEME", "light")
            ),
            storage=StorageConfig(
                type=os.getenv("STORAGE_TYPE", "local"),
                path=os.getenv("STORAGE_PATH", "./test_sessions"),
                bucket_name=os.getenv("S3_BUCKET_NAME"),
                region=os.getenv("S3_REGION"),
                access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
            ),
            sessions=SessionsConfig(
                max_sessions=int(os.getenv("MAX_SESSIONS", "100")),
                auto_save_interval=int(os.getenv("AUTO_SAVE_INTERVAL", "30")),
                session_timeout=int(os.getenv("SESSION_TIMEOUT", "3600"))
            ),
            openai=OpenAIConfig(
                model=os.getenv("OPENAI_MODEL", "gpt-4"),
                temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS")) if os.getenv("OPENAI_MAX_TOKENS") else None,
                api_key=os.getenv("OPENAI_API_KEY")
            ),
            polar=PolarConfig(
                cli_path=os.getenv("POLAR_CLI_PATH", "oso-cloud")
            ),
            events=EventsConfig(
                batch_size=int(os.getenv("EVENTS_BATCH_SIZE", "100")),
                retention_days=int(os.getenv("EVENTS_RETENTION_DAYS", "90")),
                compression=os.getenv("EVENTS_COMPRESSION", "true").lower() == "true"
            )
        )


# Global configuration instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global application configuration."""
    global _config
    if _config is None:
        _config = AppConfig.create_default()
    return _config


def set_config(config: AppConfig) -> None:
    """Set the global application configuration."""
    global _config
    _config = config