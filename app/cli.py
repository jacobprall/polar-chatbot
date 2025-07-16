import click
import logging
from pathlib import Path
from typing import List

from .models.config import AppConfig
from .models.policy_request import PolicyRequest
from .services.openai_service import OpenAIService
from .storage.local_storage import LocalStorageBackend
from .core.validator import PolarValidator
from .core.error_handler import ErrorHandler
from .core.policy_generator import PolicyGenerator

def setup_logging(config: AppConfig):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format=config.logging.format,
        filename=config.logging.file
    )

def create_generator(config: AppConfig) -> PolicyGenerator:
    """Create and configure the policy generator"""
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
        timeout=config.polar.validation_timeout
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

@click.group()
@click.option('--config', default='config.yaml', help='Configuration file path')
@click.pass_context
def cli(ctx, config):
    """Polar Policy Generator CLI"""
    ctx.ensure_object(dict)
    ctx.obj['config'] = AppConfig.from_file(config)
    setup_logging(ctx.obj['config'])

@cli.command()
@click.option('--prompt-file', required=True, help='Path to prompt file')
@click.option('--system-prompts', multiple=True, help='System prompt files')
@click.option('--output-dir', default='./results', help='Output directory')
@click.option('--output-filename', default='generated_policy.polar', help='Output filename')
@click.option('--model', help='AI model to use')
@click.option('--temperature', type=float, help='AI temperature setting')
@click.pass_context
def generate(ctx, prompt_file, system_prompts, output_dir, output_filename, model, temperature):
    """Generate a Polar policy from a prompt file"""
    config = ctx.obj['config']
    
    # Read prompt file
    storage_backend = LocalStorageBackend()
    prompt_obj = storage_backend.get_object(prompt_file)
    if not prompt_obj:
        click.echo(f"Error: Could not read prompt file '{prompt_file}'")
        return
    
    # Use default system prompts if none provided
    if not system_prompts:
        system_prompts = [
            "data/system_prompts/output_instructions.mdx",
            "data/system_prompts/polar_reference.mdx",
            "data/system_prompts/polar_syntax.mdx",
            "data/system_prompts/sample_1.polar"
        ]
    
    # Build model config
    model_config = {}
    if model:
        model_config['model'] = model
    if temperature is not None:
        model_config['temperature'] = temperature
    
    # Create request
    request = PolicyRequest(
        prompt=prompt_obj.content,
        system_prompts=list(system_prompts),
        output_file_path=f"{output_dir}/{output_filename}",
        model_config=model_config
    )
    
    # Generate policy
    generator = create_generator(config)
    response = generator.generate_policy(request)
    
    # Display results
    if response.is_valid():
        click.echo(f"✅ Policy generated successfully!")
        click.echo(f"📁 File: {response.file_path}")
        if response.model_used:
            click.echo(f"🤖 Model: {response.model_used}")
        if response.tokens_used:
            click.echo(f"🔢 Tokens used: {response.tokens_used}")
        if response.generation_time:
            click.echo(f"⏱️  Generation time: {response.generation_time:.2f}s")
    else:
        click.echo(f"❌ Policy generation failed!")
        if response.error_message:
            click.echo(f"Error: {response.error_message}")
        if response.validation_errors:
            click.echo("Validation errors:")
            for error in response.validation_errors:
                click.echo(f"  - {error}")

@cli.command()
@click.option('--policy-file', required=True, help='Path to policy file to validate')
@click.pass_context
def validate(ctx, policy_file):
    """Validate a Polar policy file"""
    config = ctx.obj['config']
    
    # Read policy file
    storage_backend = LocalStorageBackend()
    policy_obj = storage_backend.get_object(policy_file)
    if not policy_obj:
        click.echo(f"Error: Could not read policy file '{policy_file}'")
        return
    
    # Validate policy
    validator = PolarValidator(
        cli_path=config.polar.cli_path,
        timeout=config.polar.validation_timeout
    )
    
    result = validator.validate_policy(policy_obj.content)
    
    if result.is_valid:
        click.echo("✅ Policy is valid!")
    else:
        click.echo("❌ Policy validation failed!")
        if result.error_message:
            click.echo(f"Error: {result.error_message}")

@cli.command()
@click.pass_context
def list_models(ctx):
    """List available AI models"""
    config = ctx.obj['config']
    ai_service = OpenAIService(
        api_key=config.ai.api_key,
        default_model=config.ai.model
    )
    
    models = ai_service.get_available_models()
    click.echo("Available models:")
    for model in models:
        click.echo(f"  - {model}")

@cli.command()
@click.option('--config-file', default='config.yaml', help='Configuration file to create')
@click.pass_context
def init(ctx, config_file):
    """Initialize a new configuration file"""
    config = AppConfig()
    config.to_file(config_file)
    click.echo(f"✅ Configuration file created: {config_file}")

if __name__ == '__main__':
    cli() 
