"""
Polar Policy Generator - Main Entry Point

This module provides the main entry point for the refactored application,
maintaining backward compatibility with the original interface.
"""

import os
import logging
from typing import Optional, List
from pathlib import Path

# Import new modular components
from .models.config import AppConfig
from .models.policy_request import PolicyRequest
from .services.openai_service import OpenAIService
from .storage.local_storage import LocalStorageBackend
from .core.validator import PolarValidator
from .core.error_handler import ErrorHandler
from .core.policy_generator import PolicyGenerator

def create_policy_generator(config: Optional[AppConfig] = None) -> PolicyGenerator:
    """Create and configure the policy generator"""
    if config is None:
        config = AppConfig()
    
    # Setup AI service
    ai_service = OpenAIService(
        api_key=config.ai.api_key,
        default_model=config.ai.model
    )
    
    # Setup storage backend
    storage_backend = LocalStorageBackend(config.storage.base_path)
    
    # Setup validator
    validator = PolarValidator(
        cli_path=config.polar.cli_path,
    )
    
    # Setup error handler
    error_handler = ErrorHandler(ai_service, storage_backend)
    
    # Create generator
    return PolicyGenerator(
        ai_service=ai_service,
        storage_backend=storage_backend,
        validator=validator,
        error_handler=error_handler,
        config=config
    )
