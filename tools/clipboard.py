"""
System Clipboard Tools for VAX.
Allows the assistant to inspect or update the Windows clipboard.
"""

import logging
import pyperclip

from vax.tools import tool
from vax.safety import RiskLevel

logger = logging.getLogger("VAX.Tools.Clipboard")


@tool(description="Reads the current text content from the system clipboard.", risk_level=RiskLevel.SAFE)
def read_clipboard() -> str:
    """Gets clipboard text."""
    try:
        content = pyperclip.paste()
        if not content:
            return "Clipboard is currently empty."
        if len(content) > 1500:
            return content[:1500] + "\n... [Truncated clipboard preview]"
        return content
    except Exception as e:
        return f"Failed to read clipboard: {e}"


@tool(description="Copies text to the system clipboard.", risk_level=RiskLevel.MEDIUM)
def write_clipboard(text: str) -> str:
    """Sets clipboard text."""
    try:
        pyperclip.copy(text)
        return f"Successfully copied {len(text)} characters to the clipboard."
    except Exception as e:
        return f"Failed to copy to clipboard: {e}"
