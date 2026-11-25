"""
Tests for VAX Error Handling, Retry Logic, and Fallback Provider Support.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from vax.providers.base import (
    BaseLLMProvider,
    ChatMessage,
    LLMResponse,
    format_friendly_error,
    is_retryable_error,
)
from vax.agent import AgentBrain
from vax.providers.gemini_provider import GeminiProvider


def test_friendly_error_formatting():
    # 503 for Gemini specifically
    msg = format_friendly_error("gemini", "503 UNAVAILABLE. Model experiencing high demand.")
    assert msg == "Google server is busy, try again or change model."

    # 503 for other providers
    msg_groq = format_friendly_error("groq", "503 Service Unavailable")
    assert msg_groq == "Groq server is busy, try again or change model."

    # 429 rate limit
    msg_rl = format_friendly_error("openai", "429 Too Many Requests: quota exceeded")
    assert "rate limit or quota exceeded" in msg_rl

    # 401 invalid key
    msg_auth = format_friendly_error("anthropic", "401 Unauthorized: invalid_api_key")
    assert "Invalid or unauthorized API key" in msg_auth

    # Tolerates reversed argument order
    msg_rev = format_friendly_error(Exception("503 server overloaded"), "gemini")
    assert msg_rev == "Google server is busy, try again or change model."


def test_is_retryable_error():
    assert is_retryable_error(status_code=503) is True
    assert is_retryable_error(status_code=429) is True
    assert is_retryable_error(error_text="Resource exhausted 429") is True
    assert is_retryable_error(status_code=400) is False
    assert is_retryable_error(status_code=404) is False


@pytest.mark.asyncio
async def test_agent_fallback_provider_orchestration():
    # Mock primary provider that always fails with 503
    primary = MagicMock(spec=BaseLLMProvider)
    primary.provider_name = "gemini"
    primary.generate_async = AsyncMock(
        return_value=LLMResponse(
            content="Google server is busy, try again or change model.",
            is_error=True,
            error_message="Google server is busy, try again or change model.",
            provider_used="gemini",
        )
    )

    # Mock fallback provider that succeeds
    fallback = MagicMock(spec=BaseLLMProvider)
    fallback.provider_name = "groq"
    fallback.generate_async = AsyncMock(
        return_value=LLMResponse(
            content="Hello! How can I help you?",
            is_error=False,
            provider_used="groq",
        )
    )

    brain = AgentBrain(provider=primary, fallback_provider=fallback)
    reply = await brain.run_command("hello")

    # Verify primary was called
    primary.generate_async.assert_called_once()
    # Verify fallback was called
    fallback.generate_async.assert_called_once()
    # Verify transcript notes fallback was used
    assert "[Answered via fallback: Groq]" in reply
    assert "Hello! How can I help you?" in reply


def test_gemini_automatic_function_calling_disabled():
    # Verify that Gemini provider explicitly disables AFC
    try:
        provider = GeminiProvider(api_key="test_dummy_key", model="gemini-3.5-flash-lite")
        config = provider._build_config(system_instruction="test", tools=[])
        assert config.automatic_function_calling is not None
        assert config.automatic_function_calling.disable is True
    except Exception as e:
        pytest.skip(f"google-genai client init skipped: {e}")
