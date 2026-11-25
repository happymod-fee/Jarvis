"""
VAX Agent Brain & Autonomous Execution Loop.
Orchestrates LLM reasoning, multi-step tool execution, short-term memory,
cancellation support, fallback provider resilience, and language-matched concise vocal replies.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable

from vax.config import config_manager
from vax.providers import create_provider, create_fallback_provider
from vax.providers.base import (
    BaseLLMProvider,
    ChatMessage,
    ToolCall,
    ToolDefinition,
    LLMResponse,
    format_friendly_error,
)
from vax.tools import registry
from vax.memory import memory_manager
# Ensure all built-in tools are registered
import vax.tools.system
import vax.tools.keyboard_mouse
import vax.tools.files
import vax.tools.browser
import vax.tools.web_info
import vax.tools.clipboard
import vax.tools.vision
import vax.tools.memory_tools

logger = logging.getLogger("VAX.Agent")

SYSTEM_PROMPT = """You are VAX (Jarvis), an all-in-one, ultra-capable AI personal desktop assistant and PC operator.
You have full control over the user's Windows computer using your tools, while strictly protecting the PC from harm.

CRITICAL INSTRUCTIONS:
1. LANGUAGE: The user may speak Bangla (বাংলা), English, or mixed Banglish (e.g., "YouTube kholo", "Bangla song play koro", "Amar PC-r obostha ki?").
   - Always reply in the exact language style the user used.
   - For Bangla/Banglish commands, give natural, warm Bangla or Banglish responses (e.g., "Notepad khulechi!", "Gaan play korechi!").
2. CONCISENESS: Spoken replies MUST BE SHORT, CLEAR, and direct (1-2 sentences maximum), unless the user asks for a detailed explanation.
3. FULL POWER & TOOL SELECTION:
   - You can open/close apps, play YouTube songs/videos directly (`play_youtube_video`), control media (`control_youtube_media`), search the web (`web_search`, `search_google`), check PC health (`get_system_health`), manage files, control volume/brightness, type/click, and inspect the screen (`click_element_by_description`).
   - Always prefer direct tools (like `play_youtube_video`, `open_app`, `set_volume`, `open_url`) over screen clicking.
4. MEMORY:
   - You have persistent memory across sessions! Whenever the user tells you their name, preferences, or asks you to remember something ("eta mone rakho"), IMMEDIATELY call `remember_user_info(key, value)` so you never forget it.
5. SAFETY (NON-NEGOTIABLE):
   - Never harm the user's PC. Dangerous actions (file deletion -> Recycle Bin only, shutdown, restart) ALWAYS require user confirmation.
   - Never reveal API keys or sensitive credentials.
"""


class AgentBrain:
    """
    Core autonomous loop for VAX.
    Supports primary and optional fallback providers.
    """

    def __init__(
        self,
        provider: Optional[BaseLLMProvider] = None,
        fallback_provider: Optional[BaseLLMProvider] = None,
        max_steps: int = 15,
    ):
        self.provider = provider or create_provider()
        self.fallback_provider = fallback_provider or create_fallback_provider()
        self.memory = memory_manager
        self.max_steps = max_steps
        self._cancel_requested = False
        self._pending_confirmation: Optional[Dict[str, Any]] = None

    def reload_providers(self):
        """Reloads primary and fallback providers from current configuration."""
        self.provider = create_provider()
        self.fallback_provider = create_fallback_provider()

    def request_cancel(self):
        """Immediately aborts any ongoing multi-step execution loop."""
        self._cancel_requested = True
        logger.info("Agent execution cancellation requested.")

    def set_provider(self, provider: BaseLLMProvider):
        self.provider = provider

    def set_fallback_provider(self, provider: Optional[BaseLLMProvider]):
        self.fallback_provider = provider

    async def run_command(
        self,
        user_input: str,
        on_step_update: Optional[Callable[[str, str], None]] = None,
        confirm_dangerous: bool = False,
    ) -> str:
        """
        Executes a user voice/text command through the autonomous tool calling loop.
        on_step_update(step_type, message) can be passed to update the UI live.
        """
        self._cancel_requested = False
        clean_input = user_input.strip()
        if not clean_input:
            return "Please provide a command."

        # Quick check for cancel / stop phrases
        lower_input = clean_input.lower()
        if lower_input in ("stop", "cancel", "thamo", "bondho koro", "ruk ja"):
            self.request_cancel()
            return "Stopped."

        # Check if user is confirming a pending dangerous action
        if self._pending_confirmation and lower_input in ("yes", "confirm", "proceed", "ha", "thik ache", "koro"):
            pending = self._pending_confirmation
            self._pending_confirmation = None
            if on_step_update:
                on_step_update("thinking", f"Confirmed: Executing {pending['tool_name']}...")
            res = await registry.execute(pending["tool_name"], pending["arguments"], confirmed_dangerous=True)
            return f"Action confirmed and executed: {res['message']}"
        elif self._pending_confirmation and lower_input in ("no", "cancel", "na", "korona", "abort"):
            self._pending_confirmation = None
            return "Action cancelled."

        # Build message history for this run with long-term memory & mode context
        is_turbo = bool(config_manager.get("general", "turbo_mode", False))
        mode_note = (
            "\n\n[ACTIVE MODE: TURBO ROOT-ADMIN POWER — You have full autonomous PC & OS operator authority. "
            "Execute shell/PowerShell commands (`run_shell_command`, `run_admin_powershell`), manage apps, "
            "files, processes, settings, browser, and system tasks immediately without pausing for confirmation. "
            "Respond ultra-fast in 1 short sentence.]"
            if is_turbo
            else "\n\n[ACTIVE MODE: NORMAL MODE — Balanced, careful, and helpful execution.]"
        )
        full_system = SYSTEM_PROMPT + self.memory.format_facts_for_prompt() + mode_note

        messages: List[ChatMessage] = [
            ChatMessage(role="system", content=full_system)
        ]
        # Append short-term memory
        messages.extend(self.memory.get_messages())
        # Append current user prompt
        messages.append(ChatMessage(role="user", content=clean_input))

        # Retrieve available tools
        tool_defs = registry.get_all_definitions()

        step_count = 0
        final_reply = ""
        answered_provider_name = getattr(self.provider, "provider_name", "primary")
        used_fallback = False

        if on_step_update:
            on_step_update("thinking", "Analyzing request...")

        while step_count < self.max_steps:
            if self._cancel_requested:
                return "Operation cancelled by user."

            step_count += 1
            logger.debug("Agent loop step %d/%d", step_count, self.max_steps)

            # Call LLM with primary provider
            response: Optional[LLMResponse] = None
            try:
                response = await self.provider.generate_async(
                    messages=messages,
                    tools=tool_defs,
                )
            except Exception as e:
                logger.error("Primary provider execution error: %s", e)
                p_name = getattr(self.provider, "provider_name", "provider")
                err_msg = format_friendly_error(e, p_name)
                response = LLMResponse(content=err_msg, is_error=True, error_message=err_msg)

            # Check if primary failed and try fallback provider if configured
            if response is None or response.is_error:
                if self.fallback_provider is not None:
                    fb_name = getattr(self.fallback_provider, "provider_name", "fallback")
                    logger.warning("Primary provider failed (%s). Attempting fallback: %s", response.error_message if response else "None", fb_name)
                    if on_step_update:
                        on_step_update("thinking", f"Primary provider failed. Switching to fallback ({fb_name})...")
                    try:
                        fb_response = await self.fallback_provider.generate_async(
                            messages=messages,
                            tools=tool_defs,
                        )
                        if not fb_response.is_error:
                            response = fb_response
                            used_fallback = True
                            answered_provider_name = fb_name
                        else:
                            response = fb_response
                    except Exception as fb_err:
                        logger.error("Fallback provider execution error: %s", fb_err)
                        err_msg = format_friendly_error(fb_err, fb_name)
                        response = LLMResponse(content=err_msg, is_error=True, error_message=err_msg)

            # If still error after retry and fallback, return friendly error message
            if response is None or response.is_error:
                err_text = (response.error_message if response and response.error_message else (response.content if response else "Unknown provider failure"))
                logger.error("All provider attempts failed: %s", err_text)
                return f"Error: {err_text}"

            # Check if model requested tool calls
            if response.tool_calls:
                # Add assistant message with tool calls into dialog context
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=response.content or "",
                        tool_calls=response.tool_calls,
                        raw_response=response.raw_response,
                    )
                )

                for tc in response.tool_calls:
                    if self._cancel_requested:
                        return "Operation cancelled by user."

                    tool_name = tc.name
                    args = tc.arguments

                    if on_step_update:
                        on_step_update("action", f"Executing: {tool_name}")

                    logger.info("Executing tool '%s' with args %s", tool_name, args)
                    exec_res = await registry.execute(
                        tool_name,
                        args,
                        confirmed_dangerous=(confirm_dangerous or is_turbo),
                    )

                    # Handle dangerous confirmation requirement
                    if exec_res.get("requires_confirmation"):
                        self._pending_confirmation = {
                            "tool_name": tool_name,
                            "arguments": args,
                        }
                        return f"This action is sensitive: {exec_res['message']} Please say 'confirm' or 'cancel'."

                    # Append tool response
                    tool_content = exec_res["message"]
                    messages.append(
                        ChatMessage(
                            role="tool",
                            name=tool_name,
                            tool_call_id=tc.id,
                            content=tool_content,
                        )
                    )

                    if on_step_update:
                        on_step_update("action_result", f"{tool_name}: {tool_content[:80]}")

                # Continue loop to let LLM observe tool output
                continue

            else:
                # No more tools requested - this is the final spoken response
                final_reply = response.content.strip()
                if used_fallback:
                    fb_display = answered_provider_name.title()
                    final_reply = f"[Answered via fallback: {fb_display}]\n{final_reply}"
                break

        if not final_reply and step_count >= self.max_steps:
            final_reply = "Completed maximum reasoning steps for this task."

        # Update conversation memory
        self.memory.add_user_message(clean_input)
        self.memory.add_assistant_message(final_reply)

        if on_step_update:
            on_step_update("done", final_reply)

        return final_reply
