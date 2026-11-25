"""
Unit Tests for VAX LLM Provider Layer.
Validates provider auto-detection, JSON fallback parsing, and provider factory.
"""

import pytest
from vax.config import auto_detect_provider
from vax.providers import create_provider
from vax.providers.base import ToolDefinition, BaseLLMProvider
from vax.providers.openai_compatible import OpenAICompatibleProvider
from vax.providers.anthropic_provider import AnthropicProvider
from vax.providers.gemini_provider import GeminiProvider


def test_auto_detect_provider():
    assert auto_detect_provider("gsk_test1234567890abcdef") == "groq"
    assert auto_detect_provider("sk-ant-test1234567890abcdef") == "anthropic"
    assert auto_detect_provider("sk-or-test1234567890abcdef") == "openrouter"
    assert auto_detect_provider("AIzaSyTest1234567890abcdef") == "gemini"
    assert auto_detect_provider("dsk-test1234567890abcdef") == "deepseek"
    assert auto_detect_provider("sk-proj-test1234567890abcdef") == "openai"


def test_provider_factory_instantiation():
    groq_p = create_provider(provider_name="groq", api_key="dummy_gsk")
    assert isinstance(groq_p, OpenAICompatibleProvider)
    assert groq_p.provider_name == "groq"

    anthropic_p = create_provider(provider_name="anthropic", api_key="dummy_ant")
    assert isinstance(anthropic_p, AnthropicProvider)

    gemini_p = create_provider(provider_name="gemini", api_key="dummy_gemini")
    assert isinstance(gemini_p, GeminiProvider)


def test_json_fallback_parsing():
    provider = OpenAICompatibleProvider(api_key="fake", model="llama-3.3-70b", use_json_fallback=True)

    # Test code-fenced tool call response
    sample_response = """
    I will open the calculator for you.
    ```json
    {
      "tool_calls": [
        {
          "name": "open_app",
          "arguments": {"app_name": "calc"}
        }
      ]
    }
    ```
    """
    calls = provider.parse_json_fallback_response(sample_response)
    assert calls is not None
    assert len(calls) == 1
    assert calls[0].name == "open_app"
    assert calls[0].arguments == {"app_name": "calc"}


def test_tool_definition_serialization():
    td = ToolDefinition(
        name="set_volume",
        description="Sets master audio volume",
        parameters={
            "type": "object",
            "properties": {"level": {"type": "integer"}},
            "required": ["level"],
        },
    )

    openai_dict = td.to_openai_dict()
    assert openai_dict["type"] == "function"
    assert openai_dict["function"]["name"] == "set_volume"

    anthropic_dict = td.to_anthropic_dict()
    assert anthropic_dict["name"] == "set_volume"
    assert "input_schema" in anthropic_dict
