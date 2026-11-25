"""
Keyboard, Mouse, and Screen Capture Tools for VAX.
Provides human-like desktop interaction using PyAutoGUI and PyWin32.
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import pyautogui

from vax.tools import tool
from vax.safety import RiskLevel
from vax.config import get_vax_dir

logger = logging.getLogger("VAX.Tools.KeyboardMouse")

# PyAutoGUI safety settings
pyautogui.FAILSAFE = True  # Move mouse to any corner to abort
pyautogui.PAUSE = 0.05     # Minimal delay between actions for fluidity


@tool(description="Types text into the currently focused window.", risk_level=RiskLevel.MEDIUM)
def type_text(text: str, press_enter: bool = False) -> str:
    """Types given text as keystrokes."""
    try:
        # For complex unicode characters (like Bangla script), typing via clipboard paste is much more reliable
        # than synthetic key presses which only support basic ASCII on Windows.
        has_non_ascii = any(ord(c) > 127 for c in text)
        if has_non_ascii:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.write(text, interval=0.01)

        if press_enter:
            time.sleep(0.05)
            pyautogui.press("enter")

        return f"Typed {len(text)} characters{' and pressed enter' if press_enter else ''}."
    except Exception as e:
        return f"Failed to type text: {e}"


@tool(description="Presses a single keyboard key (e.g. 'enter', 'esc', 'tab', 'backspace', 'space', 'up', 'down').", risk_level=RiskLevel.MEDIUM)
def press_key(key: str) -> str:
    """Presses a single key."""
    try:
        pyautogui.press(key.lower().strip())
        return f"Pressed key '{key}'."
    except Exception as e:
        return f"Failed to press key '{key}': {e}"


@tool(description="Sends a keyboard hotkey combination (e.g. 'ctrl+c', 'ctrl+v', 'alt+tab', 'win+d', 'ctrl+shift+esc').", risk_level=RiskLevel.MEDIUM)
def send_hotkey(keys: str) -> str:
    """Sends a hotkey combo separated by '+'."""
    try:
        parts = [k.strip().lower() for k in keys.split("+")]
        pyautogui.hotkey(*parts)
        return f"Executed hotkey '{keys}'."
    except Exception as e:
        return f"Failed to send hotkey '{keys}': {e}"


@tool(description="Clicks the mouse at specified coordinates or current position.", risk_level=RiskLevel.MEDIUM)
def mouse_click(x: int = -1, y: int = -1, button: str = "left", clicks: int = 1) -> str:
    """Clicks the mouse."""
    try:
        btn = button.lower().strip()
        if x >= 0 and y >= 0:
            pyautogui.click(x=x, y=y, clicks=clicks, button=btn)
            return f"Clicked mouse {btn} button at ({x}, {y}) {clicks} time(s)."
        else:
            pyautogui.click(clicks=clicks, button=btn)
            cur_x, cur_y = pyautogui.position()
            return f"Clicked mouse {btn} button at current position ({cur_x}, {cur_y}) {clicks} time(s)."
    except Exception as e:
        return f"Mouse click failed: {e}"


@tool(description="Moves the mouse pointer to (x, y) coordinates on the screen.", risk_level=RiskLevel.MEDIUM)
def mouse_move(x: int, y: int) -> str:
    """Moves mouse to coordinates."""
    try:
        pyautogui.moveTo(x=x, y=y, duration=0.2)
        return f"Moved mouse to ({x}, {y})."
    except Exception as e:
        return f"Mouse move failed: {e}"


@tool(description="Scrolls the mouse wheel up (positive) or down (negative).", risk_level=RiskLevel.MEDIUM)
def mouse_scroll(clicks: int) -> str:
    """Scrolls mouse wheel."""
    try:
        pyautogui.scroll(int(clicks))
        return f"Scrolled mouse wheel by {clicks} units."
    except Exception as e:
        return f"Mouse scroll failed: {e}"


@tool(description="Drags the mouse from start coordinates to end coordinates.", risk_level=RiskLevel.MEDIUM)
def mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int) -> str:
    """Drags mouse from start to end."""
    try:
        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragTo(end_x, end_y, duration=0.5, button="left")
        return f"Dragged mouse from ({start_x}, {start_y}) to ({end_x}, {end_y})."
    except Exception as e:
        return f"Mouse drag failed: {e}"


@tool(description="Captures a full screenshot of the desktop screen.", risk_level=RiskLevel.SAFE)
def take_screenshot(save_path: str = "") -> str:
    """Takes a desktop screenshot and saves it as a PNG file."""
    try:
        if not save_path:
            screenshots_dir = get_vax_dir() / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time())
            save_path = str(screenshots_dir / f"screenshot_{timestamp}.png")

        screenshot = pyautogui.screenshot()
        screenshot.save(save_path)
        width, height = screenshot.size
        return f"Screenshot saved ({width}x{height}) to: {save_path}"
    except Exception as e:
        return f"Failed to capture screenshot: {e}"
