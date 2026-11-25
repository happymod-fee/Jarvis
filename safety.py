"""
VAX Safety Layer & Risk Assessment Engine.
Classifies actions into SAFE, MEDIUM, and DANGEROUS tiers,
enforces shell command blocklists, protects credentials, and handles confirmations.
"""

import re
import logging
from enum import Enum
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("VAX.Safety")


class RiskLevel(str, Enum):
    SAFE = "SAFE"            # Execute immediately, log silently
    MEDIUM = "MEDIUM"        # Execute immediately, notify user
    DANGEROUS = "DANGEROUS"  # Require explicit user voice or UI confirmation
    BLOCKED = "BLOCKED"      # Strictly prohibited, never execute


# Shell commands that are strictly prohibited due to critical destructive risk
DESTRUCTIVE_SHELL_PATTERNS = [
    r"\brm\s+-(?:r|f|rf|fr)\s+[/~*]",
    r"\bdel\s+/[sS]\s+/[qQ]\s+[cC]:\\",
    r"\bformat\s+[a-zA-Z]:",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bdiskpart\b",
    r"\breg\s+delete\s+HKLM\\SYSTEM\b",
    r"\b(curl|wget)\b.*\|\s*(sh|bash|powershell|cmd)\b",
    r"\bInvoke-Expression\s*\(.*New-Object\s+Net\.WebClient",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # Fork bomb
    r"\bshutdown\s+/[sS]\s+/[tT]\s+0\b",          # Direct abrupt kill without prompt
]

# Tools by risk tier
TOOL_RISK_MAP = {
    # SAFE tools
    "get_volume": RiskLevel.SAFE,
    "get_brightness": RiskLevel.SAFE,
    "list_running_apps": RiskLevel.SAFE,
    "search_files": RiskLevel.SAFE,
    "read_file": RiskLevel.SAFE,
    "read_page_text": RiskLevel.SAFE,
    "screenshot_page": RiskLevel.SAFE,
    "take_screenshot": RiskLevel.SAFE,
    "web_search": RiskLevel.SAFE,
    "get_weather": RiskLevel.SAFE,
    "get_time_date": RiskLevel.SAFE,
    "calculate": RiskLevel.SAFE,
    "translate_text": RiskLevel.SAFE,
    "read_clipboard": RiskLevel.SAFE,

    # MEDIUM tools
    "open_app": RiskLevel.MEDIUM,
    "close_app": RiskLevel.MEDIUM,
    "focus_window": RiskLevel.MEDIUM,
    "minimize_maximize": RiskLevel.MEDIUM,
    "set_volume": RiskLevel.MEDIUM,
    "mute_volume": RiskLevel.MEDIUM,
    "set_brightness": RiskLevel.MEDIUM,
    "type_text": RiskLevel.MEDIUM,
    "press_key": RiskLevel.MEDIUM,
    "send_hotkey": RiskLevel.MEDIUM,
    "mouse_click": RiskLevel.MEDIUM,
    "mouse_move": RiskLevel.MEDIUM,
    "mouse_scroll": RiskLevel.MEDIUM,
    "create_file": RiskLevel.MEDIUM,
    "create_folder": RiskLevel.MEDIUM,
    "copy_file": RiskLevel.MEDIUM,
    "move_file": RiskLevel.MEDIUM,
    "rename_file": RiskLevel.MEDIUM,
    "zip_files": RiskLevel.MEDIUM,
    "unzip_file": RiskLevel.MEDIUM,
    "write_clipboard": RiskLevel.MEDIUM,
    "open_url": RiskLevel.MEDIUM,
    "search_google": RiskLevel.MEDIUM,
    "new_browser_tab": RiskLevel.MEDIUM,
    "switch_browser_tab": RiskLevel.MEDIUM,
    "close_browser_tab": RiskLevel.MEDIUM,
    "click_browser_element": RiskLevel.MEDIUM,
    "fill_browser_form": RiskLevel.MEDIUM,
    "play_youtube_video": RiskLevel.MEDIUM,
    "control_youtube_media": RiskLevel.MEDIUM,

    # DANGEROUS tools
    "delete_file": RiskLevel.DANGEROUS,
    "delete_folder": RiskLevel.DANGEROUS,
    "system_shutdown": RiskLevel.DANGEROUS,
    "system_restart": RiskLevel.DANGEROUS,
    "system_sleep": RiskLevel.DANGEROUS,
    "lock_screen": RiskLevel.DANGEROUS,
    "run_shell_command": RiskLevel.DANGEROUS,
    "run_admin_powershell": RiskLevel.DANGEROUS,
}


class SafetyEngine:
    """
    Evaluates requested tool executions against security policies and user settings.
    """
    BROWSER_TOOLS = {
        "open_url", "search_google", "new_browser_tab", "switch_browser_tab",
        "close_browser_tab", "click_browser_element", "fill_browser_form",
        "read_page_text", "screenshot_page", "play_youtube_video", "control_youtube_media",
    }
    INPUT_TOOLS = {
        "type_text", "press_key", "send_hotkey", "mouse_click", "mouse_move", "mouse_scroll",
    }

    def __init__(self, require_confirm_dangerous: Optional[bool] = None):
        self._explicit_confirm = require_confirm_dangerous

    def _get_safety_flag(self, key: str, default: bool = True) -> bool:
        try:
            from vax.config import config_manager
            return bool(config_manager.get("safety", key, default))
        except Exception:
            return default

    @property
    def require_confirm_dangerous(self) -> bool:
        if self._explicit_confirm is not None:
            return self._explicit_confirm
        return self._get_safety_flag("require_confirm_dangerous", True)

    def evaluate(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[RiskLevel, str]:
        """
        Returns (RiskLevel, reason_or_warning_message).
        """
        # 1. Check shell / PowerShell command safety specifically
        if tool_name in ("run_shell_command", "run_admin_powershell"):
            cmd = arguments.get("command", "").strip()
            if not cmd:
                return RiskLevel.SAFE, "Empty shell command."

            # Inspect against destructive blocklist
            for pattern in DESTRUCTIVE_SHELL_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    logger.warning("Blocked destructive shell command pattern: %s in %s", pattern, cmd)
                    return (
                        RiskLevel.BLOCKED,
                        f"Blocked command for safety: Destructive pattern detected ('{cmd}').",
                    )

            # Check if command attempts to expose sensitive environment keys
            if re.search(r"(\$env:|env:|Get-ChildItem\s+env|\bset\b|\benv\b)", cmd, re.IGNORECASE) and re.search(r"(KEY|TOKEN|SECRET|PASSWORD)", cmd, re.IGNORECASE):
                return (
                    RiskLevel.BLOCKED,
                    "Blocked command: Attempt to inspect secret API keys or credentials.",
                )

            if not self._get_safety_flag("allow_shell_commands", True):
                return RiskLevel.BLOCKED, "Shell command execution is disabled in Safety Settings."

            return (
                RiskLevel.DANGEROUS if self.require_confirm_dangerous else RiskLevel.MEDIUM,
                f"Executing shell command: `{cmd}`",
            )

        # 2. Check deletion safety
        if tool_name in ("delete_file", "delete_folder"):
            if not self._get_safety_flag("allow_file_deletion", True):
                return RiskLevel.BLOCKED, "File/folder deletion is disabled in Safety Settings."
            target_path = arguments.get("path", "")
            return (
                RiskLevel.DANGEROUS if self.require_confirm_dangerous else RiskLevel.MEDIUM,
                f"Are you sure you want to move '{target_path}' to the Recycle Bin?",
            )

        # 3. Check browser / input toggles
        if tool_name in self.BROWSER_TOOLS and not self._get_safety_flag("allow_browser_automation", True):
            return RiskLevel.BLOCKED, "Browser automation is disabled in Safety Settings."

        if tool_name in self.INPUT_TOOLS and not self._get_safety_flag("allow_keyboard_mouse", True):
            return RiskLevel.BLOCKED, "Keyboard & mouse automation is disabled in Safety Settings."

        # 4. Check system power commands
        if tool_name in ("system_shutdown", "system_restart"):
            action = "shut down" if tool_name == "system_shutdown" else "restart"
            return (
                RiskLevel.DANGEROUS if self.require_confirm_dangerous else RiskLevel.MEDIUM,
                f"Are you sure you want to {action} your computer?",
            )

        # Default classification from map
        level = TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)
        return level, ""

    def sanitize_for_output(self, text: str) -> str:
        """
        Strips potential API keys or passwords from text before logging or vocalizing.
        """
        if not text:
            return ""
        # Mask OpenAI / Anthropic / Groq keys
        text = re.sub(r"(gsk_[a-zA-Z0-9_-]{20,})", r"gsk_***[REDACTED]***", text)
        text = re.sub(r"(sk-ant-[a-zA-Z0-9_-]{20,})", r"sk-ant-***[REDACTED]***", text)
        text = re.sub(r"(sk-[a-zA-Z0-9_-]{20,})", r"sk-***[REDACTED]***", text)
        text = re.sub(r"(AIzaSy[a-zA-Z0-9_-]{20,})", r"AIzaSy***[REDACTED]***", text)
        return text


safety_engine = SafetyEngine()
