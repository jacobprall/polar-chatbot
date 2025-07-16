from datetime import datetime
from app.main import run, default_system_prompts
from app.models.config import AppConfig
from app.models.policy_request import PolicyRequest
from app.core.policy_generator import PolicyGenerator
from app.services.openai_service import OpenAIService
from app.storage.local_storage import LocalStorageBackend
from app.core.validator import PolarValidator
from app.core.error_handler import ErrorHandler

def test_new_architecture():
    """Test the new modular architecture"""
    # Create configuration
    config = AppConfig()
    
    # Create components
    ai_service = OpenAIService(
        api_key=config.ai.api_key,
        default_model=config.ai.model
    )
    storage_backend = LocalStorageBackend(config.storage.base_path)
    validator = PolarValidator(
        cli_path=config.polar.cli_path,
        timeout=config.polar.validation_timeout
    )
    error_handler = ErrorHandler(ai_service, storage_backend)
    
    # Create generator
    generator = PolicyGenerator(
        ai_service=ai_service,
        storage_backend=storage_backend,
        validator=validator,
        error_handler=error_handler,
        config=config
    )
    
    output_file_path = f"results/new-test-{datetime.now().isoformat().replace(':', '-').replace('.', '-')}.polar"
    prompt = open("data/user_requirements/test_1.mdx", "r").read().strip()
    
    # Create request
    request = PolicyRequest(
        prompt=prompt,
        system_prompts=default_system_prompts,
        output_file_path=output_file_path
    )
    
    # Generate policy
    response = generator.generate_policy(request)
    
    if response.is_valid():
        print("✅ New architecture test completed successfully")
        print(f"📁 File: {response.file_path}")
        if response.model_used:
            print(f"🤖 Model: {response.model_used}")
        if response.generation_time:
            print(f"⏱️  Time: {response.generation_time:.2f}s")
    else:
        print(f"❌ New architecture test failed: {response.error_message}")

if __name__ == "__main__":
    print("\nRunning new architecture test...")
    test_new_architecture()
