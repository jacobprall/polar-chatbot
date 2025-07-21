"""
Unit tests for policy generation and validation workflows.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.services.policy_generator import PolicyGenerator, PolicyGeneratorError
from app.services.openai_service import OpenAIService, OpenAIError
from app.core.validator import PolarValidator, ValidationResult as CoreValidationResult
from app.models.session import Session, GeneratedPolicy
from app.models.policy import (
    PolicyGenerationRequest, 
    PolicyGenerationResult,
    PolicyValidationRequest,
    PolicyValidationResult
)
from app.models.config import OpenAIConfig


class TestPolicyGenerator:
    """Test cases for PolicyGenerator service."""
    
    @pytest.fixture
    def mock_openai_service(self):
        """Mock OpenAI service."""
        service = Mock(spec=OpenAIService)
        service.generate_policy.return_value = PolicyGenerationResult(
            success=True,
            policy_content="allow(user, \"read\", resource);",
            model_used="gpt-4",
            tokens_used=100,
            generation_time=2.0
        )
        service.generate_policy_stream.return_value = PolicyGenerationResult(
            success=True,
            policy_content="allow(user, \"read\", resource);",
            model_used="gpt-4",
            tokens_used=100,
            generation_time=2.0
        )
        return service
    
    @pytest.fixture
    def policy_generator(self, mock_openai_service):
        """Create PolicyGenerator instance for testing."""
        return PolicyGenerator(mock_openai_service)
    
    @pytest.fixture
    def sample_session(self):
        """Create sample session for testing."""
        session = Session.create("Test Session")
        session.requirements_text = "Allow users to read resources based on their role"
        return session
    
    @pytest.fixture
    def sample_request(self, sample_session):
        """Create sample policy generation request."""
        return PolicyGenerationRequest(
            session_id=sample_session.id,
            requirements_text=sample_session.requirements_text,
            model="gpt-4",
            temperature=0.1
        )
    
    def test_generate_policy_success(self, policy_generator, sample_request, sample_session):
        """Test successful policy generation."""
        result = policy_generator.generate_policy(sample_request, sample_session)
        
        assert result.is_successful()
        assert result.policy_content == "allow(user, \"read\", resource);"
        assert result.model_used == "gpt-4"
        assert result.tokens_used == 100
        assert result.generation_time == 2.0
        
        # Verify OpenAI service was called
        policy_generator.openai_service.generate_policy.assert_called_once()
    
    def test_generate_policy_openai_error(self, policy_generator, sample_request, sample_session):
        """Test policy generation with OpenAI error."""
        policy_generator.openai_service.generate_policy.side_effect = OpenAIError("API error")
        
        result = policy_generator.generate_policy(sample_request, sample_session)
        
        assert not result.is_successful()
        assert "API error" in result.error_message
    
    def test_generate_policy_empty_requirements(self, policy_generator, sample_session):
        """Test policy generation with empty requirements."""
        request = PolicyGenerationRequest(
            session_id=sample_session.id,
            requirements_text="",
            model="gpt-4"
        )
        
        result = policy_generator.generate_policy(request, sample_session)
        
        assert not result.is_successful()
        assert "Requirements text cannot be empty" in result.error_message
    
    def test_generate_policy_with_context(self, policy_generator, sample_request, sample_session):
        """Test policy generation with previous context."""
        # Add previous policy to session
        previous_policy = GeneratedPolicy.create(
            content="previous policy content",
            model_used="gpt-3.5-turbo"
        )
        sample_session.add_policy(previous_policy)
        
        # Add error context
        sample_request.error_context = ["Previous validation failed", "Syntax error"]
        
        result = policy_generator.generate_policy(sample_request, sample_session)
        
        assert result.is_successful()
        
        # Verify context was passed to OpenAI service
        call_args = policy_generator.openai_service.generate_policy.call_args[0][0]
        assert call_args.error_context == ["Previous validation failed", "Syntax error"]
        assert call_args.previous_policy == "previous policy content"
    
    def test_generate_policy_stream_success(self, policy_generator, sample_request, sample_session):
        """Test successful streaming policy generation."""
        stream_callback = Mock()
        
        result = policy_generator.generate_policy_stream(sample_request, sample_session, stream_callback)
        
        assert result.is_successful()
        assert result.policy_content == "allow(user, \"read\", resource);"
        
        # Verify streaming service was called
        policy_generator.openai_service.generate_policy_stream.assert_called_once()
        call_args = policy_generator.openai_service.generate_policy_stream.call_args
        assert call_args[0][1] == stream_callback  # Callback passed through
    
    def test_generate_policy_stream_callback_error(self, policy_generator, sample_request, sample_session):
        """Test streaming policy generation with callback error."""
        def failing_callback(chunk):
            raise Exception("Callback failed")
        
        policy_generator.openai_service.generate_policy_stream.side_effect = Exception("Stream error")
        
        result = policy_generator.generate_policy_stream(sample_request, sample_session, failing_callback)
        
        assert not result.is_successful()
        assert "Stream error" in result.error_message
    
    def test_generate_policy_with_custom_model(self, policy_generator, sample_request, sample_session):
        """Test policy generation with custom model settings."""
        sample_request.model = "gpt-3.5-turbo"
        sample_request.temperature = 0.5
        sample_request.max_tokens = 2000
        
        policy_generator.generate_policy(sample_request, sample_session)
        
        # Verify custom settings were passed
        call_args = policy_generator.openai_service.generate_policy.call_args[0][0]
        assert call_args.model == "gpt-3.5-turbo"
        assert call_args.temperature == 0.5
        assert call_args.max_tokens == 2000
    
    def test_generate_policy_adds_to_session(self, policy_generator, sample_request, sample_session):
        """Test that successful generation adds policy to session."""
        initial_count = len(sample_session.generated_policies)
        
        result = policy_generator.generate_policy(sample_request, sample_session)
        
        assert result.is_successful()
        assert len(sample_session.generated_policies) == initial_count + 1
        
        # Verify policy details
        new_policy = sample_session.generated_policies[-1]
        assert new_policy.content == "allow(user, \"read\", resource);"
        assert new_policy.model_used == "gpt-4"
        assert new_policy.tokens_used == 100
        assert new_policy.generation_time == 2.0
        assert new_policy.is_current is True
    
    def test_generate_policy_marks_previous_as_not_current(self, policy_generator, sample_request, sample_session):
        """Test that new policy marks previous policies as not current."""
        # Add existing policy
        existing_policy = GeneratedPolicy.create(
            content="existing policy",
            model_used="gpt-3.5-turbo"
        )
        existing_policy.is_current = True
        sample_session.add_policy(existing_policy)
        
        # Generate new policy
        result = policy_generator.generate_policy(sample_request, sample_session)
        
        assert result.is_successful()
        assert len(sample_session.generated_policies) == 2
        
        # Verify current status
        assert existing_policy.is_current is False
        assert sample_session.generated_policies[-1].is_current is True
    
    def test_generate_policy_failure_doesnt_add_to_session(self, policy_generator, sample_request, sample_session):
        """Test that failed generation doesn't add policy to session."""
        policy_generator.openai_service.generate_policy.return_value = PolicyGenerationResult(
            success=False,
            error_message="Generation failed"
        )
        
        initial_count = len(sample_session.generated_policies)
        
        result = policy_generator.generate_policy(sample_request, sample_session)
        
        assert not result.is_successful()
        assert len(sample_session.generated_policies) == initial_count
    
    def test_exception_handling(self, policy_generator, sample_request, sample_session):
        """Test handling of unexpected exceptions."""
        policy_generator.openai_service.generate_policy.side_effect = Exception("Unexpected error")
        
        result = policy_generator.generate_policy(sample_request, sample_session)
        
        assert not result.is_successful()
        assert "Unexpected error occurred" in result.error_message
        assert "Unexpected error" in result.error_message


class TestOpenAIService:
    """Test cases for OpenAI service integration."""
    
    @pytest.fixture
    def openai_config(self):
        """Create OpenAI configuration for testing."""
        return OpenAIConfig(
            api_key="test-api-key",
            model="gpt-4",
            temperature=0.1,
            max_tokens=1500
        )
    
    @pytest.fixture
    def openai_service(self, openai_config):
        """Create OpenAI service for testing."""
        return OpenAIService(openai_config)
    
    @pytest.fixture
    def sample_request(self):
        """Create sample generation request."""
        return PolicyGenerationRequest(
            session_id="test-session",
            requirements_text="Allow users to read resources",
            model="gpt-4",
            temperature=0.1
        )
    
    @patch('openai.ChatCompletion.create')
    def test_generate_policy_success(self, mock_openai, openai_service, sample_request):
        """Test successful OpenAI policy generation."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = {"content": "allow(user, \"read\", resource);"}
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 150
        mock_openai.return_value = mock_response
        
        result = openai_service.generate_policy(sample_request)
        
        assert result.is_successful()
        assert result.policy_content == "allow(user, \"read\", resource);"
        assert result.model_used == "gpt-4"
        assert result.tokens_used == 150
        assert result.generation_time > 0
    
    @patch('openai.ChatCompletion.create')
    def test_generate_policy_openai_error(self, mock_openai, openai_service, sample_request):
        """Test OpenAI API error handling."""
        import openai
        mock_openai.side_effect = openai.error.RateLimitError("Rate limit exceeded")
        
        result = openai_service.generate_policy(sample_request)
        
        assert not result.is_successful()
        assert "Rate limit exceeded" in result.error_message
    
    @patch('openai.ChatCompletion.create')
    def test_generate_policy_with_context(self, mock_openai, openai_service, sample_request):
        """Test policy generation with error context."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = {"content": "improved policy"}
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 200
        mock_openai.return_value = mock_response
        
        sample_request.error_context = ["Syntax error on line 1"]
        sample_request.previous_policy = "old policy content"
        
        result = openai_service.generate_policy(sample_request)
        
        assert result.is_successful()
        
        # Verify context was included in the prompt
        call_args = mock_openai.call_args
        messages = call_args[1]["messages"]
        user_message = next(msg for msg in messages if msg["role"] == "user")
        assert "Syntax error on line 1" in user_message["content"]
        assert "old policy content" in user_message["content"]
    
    @patch('openai.ChatCompletion.create')
    def test_generate_policy_stream_success(self, mock_openai, openai_service, sample_request):
        """Test successful streaming policy generation."""
        # Mock streaming response
        mock_chunks = [
            Mock(choices=[Mock(delta={"content": "allow("})]),
            Mock(choices=[Mock(delta={"content": "user, \"read\", "})]),
            Mock(choices=[Mock(delta={"content": "resource);"})]),
        ]
        mock_openai.return_value = iter(mock_chunks)
        
        stream_callback = Mock()
        
        result = openai_service.generate_policy_stream(sample_request, stream_callback)
        
        assert result.is_successful()
        assert result.policy_content == "allow(user, \"read\", resource);"
        
        # Verify callback was called for each chunk
        assert stream_callback.call_count == 3
        stream_callback.assert_any_call("allow(")
        stream_callback.assert_any_call("user, \"read\", ")
        stream_callback.assert_any_call("resource);")
    
    def test_build_prompt_basic(self, openai_service, sample_request):
        """Test basic prompt building."""
        messages = openai_service._build_prompt(sample_request)
        
        assert len(messages) >= 2  # System and user messages
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert sample_request.requirements_text in messages[-1]["content"]
    
    def test_build_prompt_with_context(self, openai_service, sample_request):
        """Test prompt building with error context."""
        sample_request.error_context = ["Error 1", "Error 2"]
        sample_request.previous_policy = "previous policy"
        
        messages = openai_service._build_prompt(sample_request)
        
        user_message = messages[-1]["content"]
        assert "Error 1" in user_message
        assert "Error 2" in user_message
        assert "previous policy" in user_message
    
    def test_extract_policy_content_clean(self, openai_service):
        """Test extracting clean policy content."""
        raw_content = """
        Here's the Polar policy:
        
        ```polar
        allow(user, "read", resource) if user.role = "admin";
        ```
        
        This policy allows admins to read resources.
        """
        
        extracted = openai_service._extract_policy_content(raw_content)
        assert extracted == 'allow(user, "read", resource) if user.role = "admin";'
    
    def test_extract_policy_content_no_code_block(self, openai_service):
        """Test extracting policy content without code blocks."""
        raw_content = 'allow(user, "read", resource);'
        
        extracted = openai_service._extract_policy_content(raw_content)
        assert extracted == 'allow(user, "read", resource);'
    
    def test_extract_policy_content_multiple_blocks(self, openai_service):
        """Test extracting policy content with multiple code blocks."""
        raw_content = """
        First attempt:
        ```polar
        # This is wrong
        allow(user, "read", resource);
        ```
        
        Corrected version:
        ```polar
        allow(user, "read", resource) if user.role = "admin";
        ```
        """
        
        # Should extract the last code block
        extracted = openai_service._extract_policy_content(raw_content)
        assert 'allow(user, "read", resource) if user.role = "admin";' in extracted


class TestPolarValidator:
    """Test cases for Polar validator integration."""
    
    @pytest.fixture
    def validator(self):
        """Create Polar validator for testing."""
        return PolarValidator(cli_path="oso-cloud")
    
    @pytest.fixture
    def sample_policy(self):
        """Sample valid Polar policy."""
        return 'allow(user, "read", resource) if user.role = "admin";'
    
    @pytest.fixture
    def invalid_policy(self):
        """Sample invalid Polar policy."""
        return 'allow(user, "read", resource if user.role = "admin";'  # Missing closing parenthesis
    
    @patch('subprocess.run')
    def test_validate_policy_success(self, mock_subprocess, validator, sample_policy):
        """Test successful policy validation."""
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="Policy is valid",
            stderr=""
        )
        
        result = validator.validate_policy(sample_policy)
        
        assert result.is_valid is True
        assert result.error_message is None
        assert result.errors == []
    
    @patch('subprocess.run')
    def test_validate_policy_failure(self, mock_subprocess, validator, invalid_policy):
        """Test failed policy validation."""
        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Syntax error on line 1: Missing closing parenthesis"
        )
        
        result = validator.validate_policy(invalid_policy)
        
        assert result.is_valid is False
        assert "Syntax error on line 1" in result.error_message
        assert len(result.errors) > 0
    
    @patch('subprocess.run')
    def test_validate_policy_cli_not_found(self, mock_subprocess, validator, sample_policy):
        """Test validation when CLI is not found."""
        mock_subprocess.side_effect = FileNotFoundError("oso-cloud not found")
        
        result = validator.validate_policy(sample_policy)
        
        assert result.is_valid is False
        assert "oso-cloud CLI not found" in result.error_message
    
    @patch('subprocess.run')
    def test_validate_policy_timeout(self, mock_subprocess, validator, sample_policy):
        """Test validation timeout."""
        import subprocess
        mock_subprocess.side_effect = subprocess.TimeoutExpired("oso-cloud", 30)
        
        result = validator.validate_policy(sample_policy)
        
        assert result.is_valid is False
        assert "Validation timed out" in result.error_message
    
    def test_parse_validation_errors(self, validator):
        """Test parsing validation error messages."""
        error_output = """
        Error: Syntax error on line 1, column 5
        Error: Undefined variable 'user' on line 2
        Warning: Unused rule on line 3
        """
        
        errors = validator._parse_validation_errors(error_output)
        
        assert len(errors) == 3
        assert "Syntax error on line 1" in errors[0]
        assert "Undefined variable 'user'" in errors[1]
        assert "Unused rule on line 3" in errors[2]
    
    def test_create_temp_policy_file(self, validator, sample_policy):
        """Test creating temporary policy file."""
        with validator._create_temp_policy_file(sample_policy) as temp_file:
            assert temp_file.exists()
            content = temp_file.read_text()
            assert content == sample_policy
        
        # File should be cleaned up
        assert not temp_file.exists()


class TestPolicyValidationWorkflow:
    """Test complete policy validation workflow."""
    
    @pytest.fixture
    def mock_validator(self):
        """Mock Polar validator."""
        validator = Mock(spec=PolarValidator)
        validator.validate_policy.return_value = CoreValidationResult(
            is_valid=True,
            error_message=None,
            errors=[]
        )
        return validator
    
    @pytest.fixture
    def sample_policy_request(self):
        """Sample policy validation request."""
        return PolicyValidationRequest(
            policy_content='allow(user, "read", resource);',
            policy_id="test-policy-123",
            session_id="test-session-456"
        )
    
    def test_validation_request_creation(self, sample_policy_request):
        """Test policy validation request creation."""
        assert sample_policy_request.policy_content == 'allow(user, "read", resource);'
        assert sample_policy_request.policy_id == "test-policy-123"
        assert sample_policy_request.session_id == "test-session-456"
    
    def test_validation_result_success(self, mock_validator, sample_policy_request):
        """Test successful validation result."""
        core_result = mock_validator.validate_policy(sample_policy_request.policy_content)
        
        # Convert to policy validation result
        result = PolicyValidationResult(
            is_valid=core_result.is_valid,
            error_message=core_result.error_message,
            error_details=core_result.errors,
            validation_time=1.5
        )
        
        assert result.is_valid is True
        assert result.error_message is None
        assert result.error_details == []
        assert result.validation_time == 1.5
    
    def test_validation_result_failure(self, mock_validator, sample_policy_request):
        """Test failed validation result."""
        mock_validator.validate_policy.return_value = CoreValidationResult(
            is_valid=False,
            error_message="Syntax error",
            errors=["Missing semicolon", "Undefined variable"]
        )
        
        core_result = mock_validator.validate_policy(sample_policy_request.policy_content)
        
        result = PolicyValidationResult(
            is_valid=core_result.is_valid,
            error_message=core_result.error_message,
            error_details=core_result.errors,
            validation_time=0.8
        )
        
        assert result.is_valid is False
        assert result.error_message == "Syntax error"
        assert result.error_details == ["Missing semicolon", "Undefined variable"]
        assert result.validation_time == 0.8
    
    def test_end_to_end_workflow(self, mock_validator):
        """Test complete end-to-end policy generation and validation workflow."""
        # 1. Create session
        session = Session.create("E2E Test Session")
        session.requirements_text = "Allow admins to read all resources"
        
        # 2. Create generation request
        gen_request = PolicyGenerationRequest(
            session_id=session.id,
            requirements_text=session.requirements_text,
            model="gpt-4"
        )
        
        # 3. Mock successful generation
        mock_openai = Mock()
        mock_openai.generate_policy.return_value = PolicyGenerationResult(
            success=True,
            policy_content='allow(user, "read", resource) if user.role = "admin";',
            model_used="gpt-4",
            tokens_used=120,
            generation_time=2.5
        )
        
        generator = PolicyGenerator(mock_openai)
        gen_result = generator.generate_policy(gen_request, session)
        
        # 4. Verify generation success
        assert gen_result.is_successful()
        assert len(session.generated_policies) == 1
        
        # 5. Create validation request
        policy = session.generated_policies[0]
        val_request = PolicyValidationRequest(
            policy_content=policy.content,
            policy_id=policy.id,
            session_id=session.id
        )
        
        # 6. Mock successful validation
        mock_validator.validate_policy.return_value = CoreValidationResult(
            is_valid=True,
            error_message=None,
            errors=[]
        )
        
        core_result = mock_validator.validate_policy(val_request.policy_content)
        val_result = PolicyValidationResult(
            is_valid=core_result.is_valid,
            error_message=core_result.error_message,
            error_details=core_result.errors,
            validation_time=1.2
        )
        
        # 7. Verify validation success
        assert val_result.is_valid is True
        
        # 8. Add validation result to session
        from app.models.session import ValidationResult
        session_val_result = ValidationResult.create(
            policy_id=policy.id,
            is_valid=val_result.is_valid,
            error_message=val_result.error_message,
            validation_time=val_result.validation_time
        )
        session.add_validation_result(session_val_result)
        
        # 9. Verify complete workflow
        assert len(session.generated_policies) == 1
        assert len(session.validation_results) == 1
        assert session.validation_results[0].is_valid is True
        assert session.validation_results[0].policy_id == policy.id


if __name__ == "__main__":
    pytest.main([__file__])