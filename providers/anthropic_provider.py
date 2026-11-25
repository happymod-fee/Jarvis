"""
Anthropic Claude LLM Provider for VAX.
Implements native tool calling via Anthropic Messages API,
exponential backoff retry for 503, 429, and network errors, and friendly error translation.
"""

import time
import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
import httpx

from vax.providers.base import (
    BaseLLMProvider,
    ChatMessage,
    ToolDefinition,
    ToolCall,
    LLMResponse,
    is_retryable_error,
    format_friendly_error,
    RETRY_DELAYS,
)

logger = logging.getLogger("VAX.Providers.Anthropic")

DEFAULT_ANTHROPIC_MODELS = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]


class AnthropicProvider(BaseLLMProvider):
    """
    Direct Anthropic Messages API client using httpx with exponential backoff.
    """
    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        use_json_fallback: bool = False,
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://api.anthropic.com/v1",
            provider_name="anthropic",
            temperature=temperature,
            max_tokens=max_tokens,
            use_json_fallback=use_json_fallback,
        )

    def fetch_models(self) -> List[str]:
        """Queries the Anthropic /models endpoint or returns standard model list."""
        url = f"{self.base_url}/models"
        headers = self._build_headers()
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                    if models:
                        return sorted(models)
        except Exception as e:
            logger.warning("Could not list Anthropic models from API (%s)", e)

        return DEFAULT_ANTHROPIC_MODELS

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def _format_request_data(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> Dict[str, Any]:
        system_prompt = ""
        anthropic_messages: List[Dict[str, Any]] = []

        for m in messages:
            if m.role == "system":
                system_prompt += (m.content + "\n")

        if self.use_json_fallback and tools:
            system_prompt += self.build_json_fallback_prompt(tools)

        for m in messages:
            if m.role == "system":
                continue

            if m.role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "call_unknown",
                            "content": m.content,
                        }
                    ],
                })
            elif m.role == "assistant":
                content_blocks: List[Dict[str, Any]] = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                if m.tool_calls:
                    for tc in m.tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks if content_blocks else m.content,
                })
            else:  # user
                anthropic_messages.append({
                    "role": "user",
                    "content": m.content,
                })

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        if system_prompt.strip():
            payload["system"] = system_prompt.strip()

        if tools and not self.use_json_fallback:
            payload["tools"] = [t.to_anthropic_dict() for t in tools]

        return payload

    def _parse_response_payload(self, data: Dict[str, Any]) -> LLMResponse:
        content_blocks = data.get("content", [])
        text_parts = []
        tool_calls: List[ToolCall] = []

        for block in content_blocks:
            b_type = block.get("type")
            if b_type == "text":
                text_parts.append(block.get("text", ""))
            elif b_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", f"call_{len(tool_calls)}"),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        full_text = "\n".join(text_parts).strip()

        if not tool_calls and (self.use_json_fallback or "tool_calls" in full_text):
            fallback_calls = self.parse_json_fallback_response(full_text)
            if fallback_calls:
                tool_calls.extend(fallback_calls)

        return LLMResponse(
            content=full_text,
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason", "stop"),
            raw_response=data,
            provider_used="anthropic",
        )

    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        url = f"{self.base_url}/messages"
        headers = self._build_headers()
        payload = self._format_request_data(messages, tools)

        last_error = None
        for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
            if delay > 0:
                logger.warning("Anthropic 503/429 retry %d after %.1fs...", attempt, delay)
                time.sleep(delay)

            try:
                with httpx.Client(timeout=45.0) as client:
                    res = client.post(url, headers=headers, json=payload)
                    if res.status_code >= 400:
                        last_error = f"HTTP {res.status_code}: {res.text}"
                        if is_retryable_error(status_code=res.status_code, error_text=res.text):
                            continue
                        friendly = format_friendly_error("anthropic", res.text or str(res.status_code))
                        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used="anthropic")
                    data = res.json()
                    return self._parse_response_payload(data)
            except Exception as e:
                last_error = e
                if not is_retryable_error(exc=e):
                    break

        friendly = format_friendly_error("anthropic", last_error)
        logger.error("Anthropic generate failed: %s (%s)", friendly, last_error)
        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used="anthropic")

    async def generate_async(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        url = f"{self.base_url}/messages"
        headers = self._build_headers()
        payload = self._format_request_data(messages, tools)

        last_error = None
        for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
            if delay > 0:
                logger.warning("Anthropic 503/429 async retry %d after %.1fs...", attempt, delay)
                await asyncio.sleep(delay)

            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    res = await client.post(url, headers=headers, json=payload)
                    if res.status_code >= 400:
                        last_error = f"HTTP {res.status_code}: {res.text}"
                        if is_retryable_error(status_code=res.status_code, error_text=res.text):
                            continue
                        friendly = format_friendly_error("anthropic", res.text or str(res.status_code))
                        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used="anthropic")
                    data = res.json()
                    return self._parse_response_payload(data)
            except Exception as e:
                last_error = e
                if not is_retryable_error(exc=e):
                    break

        friendly = format_friendly_error("anthropic", last_error)
        logger.error("Anthropic generate_async failed: %s (%s)", friendly, last_error)
        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used="anthropic")

    def fetch_models(self) -> List[str]:
        """Fetches list of available models from Anthropic /v1/models endpoint."""
        url = "https://api.anthropic.com/v1/models"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    if "data" in data and isinstance(data["data"], list):
                        models = [m.get("id") for m in data["data"] if isinstance(m, dict) and "id" in m]
                        if models:
                            return sorted([str(m) for m in models if m])
        except Exception as e:
            logger.warning("Failed to fetch models from Anthropic: %s", e)
        return ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"]
