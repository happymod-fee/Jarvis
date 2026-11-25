"""
VAX LLM Provider Package.
Factory for creating the appropriate provider instance based on runtime configuration.
Supports primary and optional fallback providers, plus dynamic model discovery.
"""

from typing import Optional, Dict, Any, List
from vax.config import config_manager, get_api_key, DEFAULT_MODELS
from vax.providers.base import (
    BaseLLMProvider,
    ChatMessage,
    ToolDefinition,
    ToolCall,
    LLMResponse,
)
from vax.providers.openai_compatible import OpenAICompatibleProvider
from vax.providers.anthropic_provider import AnthropicProvider
from vax.providers.gemini_provider import GeminiProvider

__all__ = [
    "BaseLLMProvider",
    "ChatMessage",
    "ToolDefinition",
    "ToolCall",
    "LLMResponse",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "create_provider",
    "create_fallback_provider",
    "fetch_models_for_provider",
]


def create_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    use_json_fallback: Optional[bool] = None,
) -> BaseLLMProvider:
    """
    Factory function to construct the active LLM provider.
    Reads missing arguments from the current VAX config.
    """
    p_name = (provider_name or config_manager.get("provider", "provider", "groq")).lower().strip()
    key = api_key if api_key is not None else get_api_key(p_name)
    m_name = model or config_manager.get("provider", "model") or DEFAULT_MODELS.get(p_name, "llama-3.3-70b-versatile")
    b_url = base_url if base_url is not None else config_manager.get("provider", "base_url", "")
    temp = temperature if temperature is not None else config_manager.get("provider", "temperature", 0.3)
    tokens = max_tokens if max_tokens is not None else config_manager.get("provider", "max_tokens", 1024)
    json_fb = use_json_fallback if use_json_fallback is not None else config_manager.get("provider", "use_json_fallback", False)

    if p_name == "anthropic":
        return AnthropicProvider(
            api_key=key,
            model=m_name,
            temperature=temp,
            max_tokens=tokens,
            use_json_fallback=json_fb,
        )
    elif p_name == "gemini":
        return GeminiProvider(
            api_key=key,
            model=m_name,
            temperature=temp,
            max_tokens=tokens,
            use_json_fallback=json_fb,
        )
    else:
        # OpenAI, Groq, DeepSeek, Mistral, OpenRouter, Ollama, Custom
        return OpenAICompatibleProvider(
            api_key=key,
            model=m_name,
            base_url=b_url if b_url else None,
            provider_name=p_name,
            temperature=temp,
            max_tokens=tokens,
            use_json_fallback=json_fb,
        )


def create_fallback_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[BaseLLMProvider]:
    """
    Factory function to construct the fallback LLM provider if configured.
    Returns None if no fallback provider is specified.
    """
    p_name = (provider_name or config_manager.get("provider", "fallback_provider", "")).lower().strip()
    if not p_name:
        return None

    key = api_key if api_key is not None else get_api_key(p_name)
    m_name = model or config_manager.get("provider", "fallback_model") or DEFAULT_MODELS.get(p_name, "")
    b_url = base_url if base_url is not None else config_manager.get("provider", "fallback_base_url", "")
    temp = config_manager.get("provider", "temperature", 0.3)
    tokens = config_manager.get("provider", "max_tokens", 1024)
    json_fb = config_manager.get("provider", "use_json_fallback", False)

    if p_name == "anthropic":
        return AnthropicProvider(
            api_key=key,
            model=m_name or DEFAULT_MODELS.get("anthropic", "claude-3-5-sonnet-20241022"),
            temperature=temp,
            max_tokens=tokens,
            use_json_fallback=json_fb,
        )
    elif p_name == "gemini":
        return GeminiProvider(
            api_key=key,
            model=m_name or DEFAULT_MODELS.get("gemini", "gemini-2.0-flash"),
            temperature=temp,
            max_tokens=tokens,
            use_json_fallback=json_fb,
        )
    else:
        return OpenAICompatibleProvider(
            api_key=key,
            model=m_name or DEFAULT_MODELS.get(p_name, "llama-3.3-70b-versatile"),
            base_url=b_url if b_url else None,
            provider_name=p_name,
            temperature=temp,
            max_tokens=tokens,
            use_json_fallback=json_fb,
        )


def fetch_models_for_provider(
    provider_name: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> List[str]:
    """
    Queries the remote provider API to discover available models.
    """
    p_name = provider_name.lower().strip()
    key = api_key if api_key is not None else get_api_key(p_name)
    provider_inst = create_provider(
        provider_name=p_name,
        api_key=key,
        model=DEFAULT_MODELS.get(p_name, "default"),
        base_url=base_url,
    )
    return provider_inst.fetch_models()
