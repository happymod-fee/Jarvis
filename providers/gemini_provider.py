"""
Google Gemini LLM Provider for VAX.
Uses modern google-genai SDK (v2.x) with native function calling,
explicitly disables Automatic Function Calling (AFC) to let VAX control the tool loop,
and provides exponential backoff retry for 503, 429, and transient network errors.
"""

import time
import asyncio
import logging
from typing import List, Optional, Dict, Any

from google import genai
from google.genai import types

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

logger = logging.getLogger("VAX.Providers.Gemini")

FALLBACK_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
]


class GeminiProvider(BaseLLMProvider):
    """
    Gemini Provider implementation using google-genai with AFC disabled and retry backoff.
    """
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        use_json_fallback: bool = False,
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://generativelanguage.googleapis.com",
            provider_name="gemini",
            temperature=temperature,
            max_tokens=max_tokens,
            use_json_fallback=use_json_fallback,
        )
        self.client = genai.Client(api_key=api_key)

    def fetch_models(self) -> List[str]:
        """Queries the Google GenAI API for chat/tool-capable Gemini models."""
        try:
            results = []
            for m in self.client.models.list():
                m_name = getattr(m, "name", "")
                if m_name.startswith("models/"):
                    m_name = m_name[7:]
                actions = getattr(m, "supported_actions", []) or []
                if actions and "generateContent" not in actions:
                    continue
                low = m_name.lower()
                if any(skip in low for skip in ("embedding", "imagen", "veo", "-tts", "bidi", "aqa")):
                    continue
                if m_name:
                    results.append(m_name)

            if results:
                return sorted(
                    list(set(results)),
                    key=lambda x: (not x.startswith("gemini-3"), not x.startswith("gemini-2"), x),
                )
        except Exception as e:
            logger.warning("Could not fetch Gemini models from API (%s); returning fallback list", e)

        return ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash"]

    def _convert_messages(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> tuple[Optional[str], List[types.Content]]:
        system_instruction: Optional[str] = None
        contents: List[types.Content] = []

        system_parts = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)

        if self.use_json_fallback and tools:
            system_parts.append(self.build_json_fallback_prompt(tools))

        if system_parts:
            system_instruction = "\n\n".join(system_parts)

        for m in messages:
            if m.role == "system":
                continue

            role = "user" if m.role in ("user", "tool") else "model"

            parts = []
            if m.role == "tool":
                parts.append(
                    types.Part.from_function_response(
                        name=m.name or "unknown_function",
                        response={"result": m.content},
                    )
                )
            elif m.role == "assistant":
                if m.raw_response and hasattr(m.raw_response, "candidates") and m.raw_response.candidates:
                    cand = m.raw_response.candidates[0]
                    if hasattr(cand, "content") and cand.content:
                        contents.append(cand.content)
                        continue

                if m.content:
                    parts.append(types.Part.from_text(text=m.content))
                if m.tool_calls:
                    for tc in m.tool_calls:
                        if getattr(tc, "raw_part", None) is not None:
                            parts.append(tc.raw_part)
                        else:
                            parts.append(
                                types.Part.from_function_call(
                                    name=tc.name,
                                    args=tc.arguments,
                                )
                            )
            else:  # user
                parts.append(types.Part.from_text(text=m.content))

            if parts:
                contents.append(types.Content(role=role, parts=parts))

        return system_instruction, contents

    def _build_config(
        self,
        system_instruction: Optional[str],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> types.GenerateContentConfig:
        config_kwargs: Dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
            # CRITICAL: Disable automatic function calling (AFC) so VAX executes tools in its own loop
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }

        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        if tools and not self.use_json_fallback:
            declarations = [
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.parameters,
                )
                for t in tools
            ]
            config_kwargs["tools"] = [types.Tool(function_declarations=declarations)]

        return types.GenerateContentConfig(**config_kwargs)

    def _extract_response(self, response: Any) -> LLMResponse:
        content_text = ""
        tool_calls: List[ToolCall] = []

        try:
            if hasattr(response, "text") and response.text:
                content_text = response.text
        except Exception:
            pass

        if hasattr(response, "function_calls") and response.function_calls:
            raw_parts = []
            if hasattr(response, "candidates") and response.candidates:
                cand = response.candidates[0]
                if hasattr(cand, "content") and cand.content and cand.content.parts:
                    raw_parts = cand.content.parts

            for idx, fc in enumerate(response.function_calls):
                part_match = None
                for p in raw_parts:
                    if getattr(p, "function_call", None) and p.function_call.name == fc.name:
                        part_match = p
                        break

                tool_calls.append(
                    ToolCall(
                        id=getattr(fc, "id", None) or f"gemini_call_{idx}",
                        name=fc.name,
                        arguments=fc.args if isinstance(fc.args, dict) else dict(fc.args or {}),
                        raw_part=part_match,
                    )
                )

        if not tool_calls and (self.use_json_fallback or "tool_calls" in content_text):
            fallback = self.parse_json_fallback_response(content_text)
            if fallback:
                tool_calls.extend(fallback)

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            finish_reason="stop",
            raw_response=response,
            provider_used="gemini",
        )

    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        system_instruction, contents = self._convert_messages(messages, tools)
        config = self._build_config(system_instruction, tools)

        last_error = None
        for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
            if delay > 0:
                logger.warning("Gemini 503/429 retry %d after %.1fs...", attempt, delay)
                time.sleep(delay)

            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                return self._extract_response(response)
            except Exception as e:
                last_error = e
                status_code = getattr(e, "code", None)
                if not is_retryable_error(status_code=status_code, exc=e):
                    break

        friendly_msg = format_friendly_error("gemini", last_error)
        logger.error("Gemini generate failed after retries: %s (%s)", friendly_msg, last_error)
        return LLMResponse(
            content=friendly_msg,
            is_error=True,
            error_message=friendly_msg,
            provider_used="gemini",
        )

    async def generate_async(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        system_instruction, contents = self._convert_messages(messages, tools)
        config = self._build_config(system_instruction, tools)

        last_error = None
        for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
            if delay > 0:
                logger.warning("Gemini 503/429 async retry %d after %.1fs...", attempt, delay)
                await asyncio.sleep(delay)

            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                return self._extract_response(response)
            except Exception as e:
                last_error = e
                status_code = getattr(e, "code", None)
                if not is_retryable_error(status_code=status_code, exc=e):
                    break

        friendly_msg = format_friendly_error("gemini", last_error)
        logger.error("Gemini generate_async failed after retries: %s (%s)", friendly_msg, last_error)
        return LLMResponse(
            content=friendly_msg,
            is_error=True,
            error_message=friendly_msg,
            provider_used="gemini",
        )
