"""
Universal OpenAI-compatible LLM Provider for VAX.
Supports: OpenAI, Groq, DeepSeek, Mistral, OpenRouter, Ollama, and any custom endpoint.
Uses httpx with exponential backoff retries (for 503, 429, timeouts) and friendly error messages.
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

logger = logging.getLogger("VAX.Providers.OpenAICompatible")

PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}

DEFAULT_PROVIDER_MODELS = {
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o1-mini",
        "gpt-3.5-turbo",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    "mistral": [
        "mistral-large-latest",
        "mistral-small-latest",
        "codestral-latest",
    ],
    "openrouter": [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
    ],
    "ollama": [
        "llama3.2:latest",
        "mistral:latest",
        "qwen2.5:latest",
    ],
}


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Provider implementation that speaks the OpenAI Chat Completions API
    with automatic exponential backoff retries on 503/429/network errors.
    """
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        provider_name: str = "custom",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        use_json_fallback: bool = False,
    ):
        p_name = provider_name.lower().strip()
        resolved_url = base_url or PROVIDER_URLS.get(p_name, "https://api.openai.com/v1")
        resolved_url = resolved_url.rstrip("/")
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=resolved_url,
            provider_name=p_name,
            temperature=temperature,
            max_tokens=max_tokens,
            use_json_fallback=use_json_fallback,
        )

    def fetch_models(self) -> List[str]:
        """Queries the provider's /models endpoint to retrieve available models."""
        url = f"{self.base_url}/models"
        headers = self._build_headers()
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    model_list = []
                    # Standard OpenAI format: {"data": [{"id": "..."}, ...]}
                    if "data" in data and isinstance(data["data"], list):
                        for item in data["data"]:
                            m_id = item.get("id")
                            if m_id:
                                model_list.append(m_id)
                    # Ollama format: {"models": [{"name": "..."}, ...]}
                    elif "models" in data and isinstance(data["models"], list):
                        for item in data["models"]:
                            m_name = item.get("name") or item.get("model")
                            if m_name:
                                model_list.append(m_name)

                    if model_list:
                        return sorted(list(set(model_list)))
        except Exception as e:
            logger.warning("Could not list models from %s (%s)", url, e)

        # Fallback to curated models for this provider
        return DEFAULT_PROVIDER_MODELS.get(self.provider_name, [self.model])

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self.provider_name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/vax-voice-assistant"
            headers["X-Title"] = "VAX Voice Assistant"

        return headers

    def _format_messages(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> List[Dict[str, Any]]:
        formatted = []
        system_suffix = ""

        if self.use_json_fallback and tools:
            system_suffix = self.build_json_fallback_prompt(tools)

        for m in messages:
            msg_dict: Dict[str, Any] = {"role": m.role}

            if m.role == "system" and system_suffix:
                msg_dict["content"] = m.content + system_suffix
                system_suffix = ""
            else:
                msg_dict["content"] = m.content

            if m.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                        },
                    }
                    for tc in m.tool_calls
                ]

            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.name:
                msg_dict["name"] = m.name

            formatted.append(msg_dict)

        if system_suffix:
            formatted.insert(0, {"role": "system", "content": system_suffix.strip()})

        return formatted

    def _parse_response_payload(self, data: Dict[str, Any]) -> LLMResponse:
        choices = data.get("choices", [])
        if not choices:
            err = format_friendly_error(self.provider_name, "Empty response choices received from LLM.")
            return LLMResponse(content=err, is_error=True, error_message=err, provider_used=self.provider_name)

        choice = choices[0]
        message_data = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")
        content = message_data.get("content") or ""
        tool_calls: List[ToolCall] = []

        raw_tool_calls = message_data.get("tool_calls")
        if raw_tool_calls:
            for item in raw_tool_calls:
                fn = item.get("function", {})
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except Exception:
                    args = {"raw_arguments": args_str}
                tool_calls.append(
                    ToolCall(
                        id=item.get("id", f"call_{len(tool_calls)}"),
                        name=name,
                        arguments=args if isinstance(args, dict) else {},
                    )
                )

        if not tool_calls and (self.use_json_fallback or "tool_calls" in content or '"tool"' in content):
            parsed_fallback = self.parse_json_fallback_response(content)
            if parsed_fallback:
                tool_calls.extend(parsed_fallback)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response=data,
            provider_used=self.provider_name,
        )

    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        formatted_messages = self._format_messages(messages, tools)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools and not self.use_json_fallback:
            payload["tools"] = [t.to_openai_dict() for t in tools]
            payload["tool_choice"] = "auto"

        last_error = None
        for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
            if delay > 0:
                logger.warning("%s 503/429 retry %d after %.1fs...", self.provider_name.capitalize(), attempt, delay)
                time.sleep(delay)

            try:
                with httpx.Client(timeout=45.0) as client:
                    res = client.post(url, headers=headers, json=payload)
                    if res.status_code >= 400:
                        last_error = f"HTTP {res.status_code}: {res.text}"
                        if is_retryable_error(status_code=res.status_code, error_text=res.text):
                            continue
                        friendly = format_friendly_error(self.provider_name, res.text or str(res.status_code))
                        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used=self.provider_name)
                    data = res.json()
                    return self._parse_response_payload(data)
            except Exception as e:
                last_error = e
                if not is_retryable_error(exc=e):
                    break

        friendly = format_friendly_error(self.provider_name, last_error)
        logger.error("%s generate failed: %s (%s)", self.provider_name, friendly, last_error)
        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used=self.provider_name)

    async def generate_async(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        formatted_messages = self._format_messages(messages, tools)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools and not self.use_json_fallback:
            payload["tools"] = [t.to_openai_dict() for t in tools]
            payload["tool_choice"] = "auto"

        last_error = None
        for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
            if delay > 0:
                logger.warning("%s 503/429 async retry %d after %.1fs...", self.provider_name.capitalize(), attempt, delay)
                await asyncio.sleep(delay)

            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    res = await client.post(url, headers=headers, json=payload)
                    if res.status_code >= 400:
                        last_error = f"HTTP {res.status_code}: {res.text}"
                        if is_retryable_error(status_code=res.status_code, error_text=res.text):
                            continue
                        friendly = format_friendly_error(self.provider_name, res.text or str(res.status_code))
                        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used=self.provider_name)
                    data = res.json()
                    return self._parse_response_payload(data)
            except Exception as e:
                last_error = e
                if not is_retryable_error(exc=e):
                    break

        friendly = format_friendly_error(self.provider_name, last_error)
        logger.error("%s generate_async failed: %s (%s)", self.provider_name, friendly, last_error)
        return LLMResponse(content=friendly, is_error=True, error_message=friendly, provider_used=self.provider_name)

    def fetch_models(self) -> List[str]:
        """Fetches list of available models from OpenAI-compatible /models endpoint."""
        url = f"{self.base_url}/models"
        headers = self._build_headers()
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    models = []
                    if "data" in data and isinstance(data["data"], list):
                        models = [m.get("id") for m in data["data"] if isinstance(m, dict) and "id" in m]
                    elif "models" in data and isinstance(data["models"], list):
                        models = [m.get("name") or m.get("id") for m in data["models"] if isinstance(m, dict)]
                    if models:
                        return sorted([str(m) for m in models if m])
        except Exception as e:
            logger.warning("Failed to fetch models from %s: %s", url, e)
        return [self.model]
