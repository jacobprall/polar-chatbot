import os
import time
from typing import Optional, Dict, Any, Callable
from openai import OpenAI
from ..models.policy import PolicyGenerationRequest, PolicyGenerationResult
from ..models.session import Session


class SessionAwareOpenAIService:
    """Session-aware OpenAI implementation with streaming support"""
    
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=self.api_key)
        self.default_model = default_model
    
    def generate_policy(self, request: PolicyGenerationRequest, session: Session) -> PolicyGenerationResult:
        """Generate Polar policy with session context"""
        start_time = time.time()
        
        try:
            # Build context-aware messages
            messages = self._build_session_messages(request, session)
            
            # Get model configuration
            model = request.model_config.get("model", self.default_model)
            temperature = request.model_config.get("temperature", 0.1)
            max_tokens = request.model_config.get("max_tokens")
            
            # Make API call
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            content = self._clean_polar_content(content)
            tokens_used = response.usage.total_tokens if response.usage else None
            generation_time = time.time() - start_time
            
            return PolicyGenerationResult(
                success=True,
                policy_content=content,
                model_used=model,
                tokens_used=tokens_used,
                generation_time=generation_time
            )
            
        except Exception as e:
            generation_time = time.time() - start_time
            return PolicyGenerationResult(
                success=False,
                error_message=str(e),
                model_used=request.model_config.get("model", self.default_model),
                generation_time=generation_time
            )
    
    def generate_policy_stream(self, request: PolicyGenerationRequest, session: Session, 
                             callback: Callable[[str], None]) -> PolicyGenerationResult:
        """Generate Polar policy with streaming support"""
        start_time = time.time()
        
        try:
            # Build context-aware messages
            messages = self._build_session_messages(request, session)
            
            # Get model configuration
            model = request.model_config.get("model", self.default_model)
            temperature = request.model_config.get("temperature", 0.1)
            max_tokens = request.model_config.get("max_tokens")
            
            # Make streaming API call
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            content_parts = []
            tokens_used = None
            
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    chunk_content = chunk.choices[0].delta.content
                    content_parts.append(chunk_content)
                    callback(chunk_content)
                
                # Get usage info from final chunk if available
                if hasattr(chunk, 'usage') and chunk.usage:
                    tokens_used = chunk.usage.total_tokens
            
            content = ''.join(content_parts)
            content = self._clean_polar_content(content)
            generation_time = time.time() - start_time
            
            return PolicyGenerationResult(
                success=True,
                policy_content=content,
                model_used=model,
                tokens_used=tokens_used,
                generation_time=generation_time
            )
            
        except Exception as e:
            generation_time = time.time() - start_time
            return PolicyGenerationResult(
                success=False,
                error_message=str(e),
                model_used=request.model_config.get("model", self.default_model),
                generation_time=generation_time
            )
    
    def _build_session_messages(self, request: PolicyGenerationRequest, session: Session) -> list[dict]:
        """Build context-aware messages for the API call"""
        messages = []
        
        # System prompt with session context
        system_prompt = self._build_system_prompt(session)
        messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history if there are previous policies
        if session.generated_policies:
            messages.extend(self._build_conversation_history(session))
        
        # User prompt with requirements and retry context
        user_prompt = self._build_user_prompt(request)
        messages.append({"role": "user", "content": user_prompt})
        
        return messages
    
    def _build_system_prompt(self, session: Session) -> str:
        """Build system prompt with session context"""
        base_prompt = """You are an expert in generating Polar authorization policies. 
Your task is to create syntactically correct and logically sound Polar code based on user requirements.

Key guidelines:
- Generate only valid Polar syntax
- Focus on authorization rules and resource access patterns
- Use clear, descriptive rule names
- Include appropriate comments for complex logic
- Ensure rules are testable and maintainable

Session Context:
- Session: {session_name}
- Created: {created_at}
- Previous policies generated: {policy_count}
""".format(
            session_name=session.name,
            created_at=session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            policy_count=len(session.generated_policies)
        )
        
        # Add notes context if available
        if session.notes.strip():
            base_prompt += f"\nSession Notes:\n{session.notes}\n"
        
        return base_prompt
    
    def _build_conversation_history(self, session: Session) -> list[dict]:
        """Build conversation history from previous policies"""
        messages = []
        
        # Add up to 3 most recent policy generations for context
        recent_policies = sorted(session.generated_policies, 
                               key=lambda p: p.generated_at, reverse=True)[:3]
        
        for policy in reversed(recent_policies):  # Chronological order
            # Add the policy as assistant response
            messages.append({
                "role": "assistant", 
                "content": f"Generated policy:\n```polar\n{policy.content}\n```"
            })
            
            # Add validation result if available
            validation = session.get_latest_validation(policy.id)
            if validation:
                if validation.is_valid:
                    messages.append({
                        "role": "user",
                        "content": "Policy validation: SUCCESS"
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": f"Policy validation: FAILED\nError: {validation.error_message}"
                    })
        
        return messages
    
    def _build_user_prompt(self, request: PolicyGenerationRequest) -> str:
        """Build user prompt with requirements and retry context"""
        prompt_parts = ["Requirements:\n" + request.requirements_text]
        
        # Add retry context if this is a retry attempt
        if request.retry_context:
            prompt_parts.append("\nRetry Context:\n" + request.retry_context)
        
        # Add previous errors if available
        if request.previous_errors:
            error_text = "\n".join(f"- {error}" for error in request.previous_errors)
            prompt_parts.append(f"\nPrevious Errors to Fix:\n{error_text}")
        
        prompt_parts.append("\nPlease generate a Polar policy that addresses these requirements.")
        
        return "\n".join(prompt_parts)
    
    def _clean_polar_content(self, content: str) -> str:
        """Clean generated content by removing code block markers"""
        if not content:
            return content
            
        content = content.strip()
        
        # Remove polar code block markers
        if content.startswith("```polar"):
            content = content[8:]
        elif content.startswith("```"):
            content = content[3:]
        
        if content.endswith("```"):
            content = content[:-3]
        
        return content.strip()
    
    def get_available_models(self) -> list[str]:
        """Get list of available OpenAI models"""
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k"
        ]


 