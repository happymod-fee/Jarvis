"""
Base definitions and interfaces for LLM Providers in VAX.
Supports unified tool/function calling, automatic JSON-fallback mode,
exponential backoff retries, and friendly human-readable error reporting.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json
import logging
import re

logger = logging.getLogger("VAX.Providers.Base")

RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff in seconds


def is_retryable_error(
    status_code: Optional[int] = None,
    exc: Optional[Exception] = None,
    error_text: Optional[str] = None,
) -> bool:
    """Checks if the error condition qualifies for automatic retry."""
    if status_code in (429, 503, 502, 504):
        return True
    err_str = f"{exc or ''} {error_text or ''}".lower()
    retryable_keywords = [
        "503",
        "429",
        "overloaded",
        "service unavailable",
        "resource_exhausted",
        "rate limit",
        "timeout",
        "timed out",
        "connecterror",
        "connection error",
        "remoteprotocolerror",
    ]
    return any(k in err_str for k in retryable_keywords)


def format_friendly_error(arg1: Any, arg2: Any = None) -> str:
    """
    Translates raw API errors into clean, concise, human-friendly messages.
    Accepts (provider_name, error) or (error, provider_name).
    Specialized requirement: For 503 say: "Google server is busy, try again or change model".
    """
    if isinstance(arg1, str) and (arg2 is not None or not isinstance(arg2, str)):
        provider_name = arg1
        error = arg2
    elif isinstance(arg2, str):
        provider_name = arg2
        error = arg1
    elif isinstance(arg1, str) and arg2 is None:
        provider_name = "AI Provider"
        error = arg1
    else:
        provider_name = "AI Provider"
        error = arg1

    err_str = str(error)
    lower = err_str.lower()
    p_lower = str(provider_name).lower()
    p_display = str(provider_name).capitalize()

    if "503" in lower or "service unavailable" in lower or "overloaded" in lower or "unavailable" in lower:
        if "gemini" in p_lower or "google" in p_lower:
            return "Google server is busy, try again or change model."
        return f"{p_display} server is busy, try again or change model."

    if "429" in lower or "rate limit" in lower or "quota" in lower or "resource_exhausted" in lower:
        return f"{p_display} rate limit or quota exceeded. Please wait a moment or switch provider."

    if "401" in lower or "unauthorized" in lower or "api key not valid" in lower or "invalid_api_key" in lower or "api_key_invalid" in lower:
        return f"Invalid or unauthorized API key for {p_display}. Please check Settings."

    if "404" in lower or "model_not_found" in lower or "not found" in lower or "not supported" in lower or "no longer available" in lower:
        return f"Model not found or unavailable on {p_display}. Please select an available model in Settings."

    if "timeout" in lower or "timed out" in lower:
        return f"Request to {p_display} timed out. Check your internet connection."

    if "connect" in lower or "network" in lower:
        return f"Could not connect to {p_display}. Check your network connection."

    # General fallback: single line without huge json dump
    clean_msg = err_str.replace("\n", " ").strip()
    if len(clean_msg) > 130:
        clean_msg = clean_msg[:130] + "..."
    return f"{p_display} error: {clean_msg}"


@dataclass
class ToolDefinition:
    """Standardized representation of a tool/function definition."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema format

    def to_openai_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_dict(self) -> Dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_gemini_dict(self) -> Dict[str, Any]:
        """Convert to Gemini function declaration dict."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass
class ToolCall:
    """Standardized representation of a model-requested tool invocation."""
    id: str
    name: str
    arguments: Dict[str, Any]
    raw_part: Optional[Any] = None


@dataclass
class ChatMessage:
    """Standardized chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    raw_response: Optional[Any] = None


@dataclass
class LLMResponse:
    """Standardized response from an LLM provider."""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    raw_response: Optional[Any] = None
    is_error: bool = False
    error_message: Optional[str] = None
    provider_used: Optional[str] = None


class BaseLLMProvider(ABC):
    """
    Abstract Base Class for LLM providers.
    """
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        provider_name: str = "base",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        use_json_fallback: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.provider_name = provider_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_json_fallback = use_json_fallback

    @abstractmethod
    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        """Synchronously generate an LLM response."""
        pass

    @abstractmethod
    async def generate_async(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        """Asynchronously generate an LLM response."""
        pass

    def fetch_models(self) -> List[str]:
        """Fetches list of available models for this provider."""
        return [self.model]

    def build_json_fallback_prompt(self, tools: List[ToolDefinition]) -> str:
        """
        Creates a system instruction explaining available tools in JSON format
        for models without native tool calling.
        """
        tools_desc = []
        for t in tools:
            tools_desc.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            })

        return (
            "\n\n[AVAILABLE TOOLS]\n"
            f"{json.dumps(tools_desc, indent=2)}\n\n"
            "If you need to execute one or more tools to answer or act, you MUST respond ONLY with a JSON object:\n"
            "```json\n"
            "{\n"
            '  "tool_calls": [\n'
            '    {"name": "tool_name", "arguments": {"param1": "val1"}}\n'
            "  ]\n"
            "}\n"
            "```\n"
            "If no tool is needed, respond with normal conversational text directly.\n"
        )

    def parse_json_fallback_response(self, text: str) -> Optional[List[ToolCall]]:
        """
        Attempts to extract JSON tool calls from free-form model text.
        """
        if not text:
            return None

        candidates = []
        fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        candidates.extend(fenced)

        bare = re.findall(r"(\{[\s\S]*\})", text)
        candidates.extend(bare)

        for candidate in candidates:
            try:
                data = json.loads(candidate.strip())
                if isinstance(data, dict):
                    if "tool_calls" in data and isinstance(data["tool_calls"], list):
                        calls = []
                        for idx, item in enumerate(data["tool_calls"]):
                            if "name" in item:
                                calls.append(
                                    ToolCall(
                                        id=f"fallback_call_{idx}",
                                        name=item["name"],
                                        arguments=item.get("arguments", {}),
                                    )
                                )
                        if calls:
                            return calls
                    elif "tool" in data:
                        return [
                            ToolCall(
                                id="fallback_call_0",
                                name=data["tool"],
                                arguments=data.get("arguments", {}),
                            )
                        ]
            except Exception:
                continue

        return None
