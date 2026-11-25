"""
Vision-based Screen Automation for VAX.
Allows finding and clicking UI elements on screen via LLM Multimodal Vision (Computer Use style).
Lazy-imports heavy vision dependencies to keep idle RAM under budget.
"""

import os
import base64
import json
import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import pyautogui

from vax.tools import tool
from vax.safety import RiskLevel
from vax.config import config_manager, get_api_key

logger = logging.getLogger("VAX.Tools.Vision")


def _encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


@tool(description="Finds a UI element on the screen using visual AI and clicks it. Fallback when accessibility APIs fail.", risk_level=RiskLevel.MEDIUM)
def click_element_by_description(description: str) -> str:
    """
    Takes a screenshot, identifies the requested element coordinates using vision model,
    and performs a mouse click.
    """
    screen_w, screen_h = pyautogui.size()
    temp_img = Path.home() / ".vax" / "temp_vision_screenshot.png"
    temp_img.parent.mkdir(parents=True, exist_ok=True)

    try:
        shot = pyautogui.screenshot()
        shot.save(temp_img)
    except Exception as e:
        return f"Failed to take screenshot for vision locator: {e}"

    provider = config_manager.get("provider", "provider", "gemini").lower()
    api_key = get_api_key(provider)

    if not api_key:
        return f"Cannot use vision locator: No API key configured for provider '{provider}'."

    prompt = (
        f"You are a computer UI vision locator. I need to click on: '{description}'.\n"
        "Analyze the provided screenshot. Return a JSON object ONLY with the normalized coordinates (0 to 1000 scale):\n"
        '{"x": <0-1000>, "y": <0-1000>, "found": true/false, "label": "<element text>"}\n'
        "If the element is not found on screen, return {\"found\": false}.\n"
        "Return NO explanation, ONLY the JSON."
    )

    try:
        if provider == "gemini":
            from google import genai
            from google.genai import types
            from PIL import Image

            client = genai.Client(api_key=api_key)
            img = Image.open(temp_img)
            vision_model = config_manager.get("provider", "model", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite"
            response = client.models.generate_content(
                model=vision_model,
                contents=[img, prompt],
            )
            raw_text = response.text or ""
        else:
            # OpenAI / OpenRouter vision
            import httpx
            b64_img = _encode_image_to_base64(str(temp_img))
            base_url = "https://api.openai.com/v1" if provider == "openai" else "https://openrouter.ai/api/v1"
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "model": "gpt-4o" if provider == "openai" else "google/gemini-flash-1.5",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                        ],
                    }
                ],
                "max_tokens": 150,
            }
            with httpx.Client(timeout=30.0) as client:
                res = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                data = res.json()
                raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON from vision response
        import re
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if not match:
            return f"Vision model could not detect target coordinates. Output: {raw_text[:100]}"

        data = json.loads(match.group(0))
        if not data.get("found", True):
            return f"Element '{description}' was not found on screen."

        norm_x = float(data.get("x", 500))
        norm_y = float(data.get("y", 500))

        # Convert from 0-1000 scale to screen pixels
        pixel_x = int((norm_x / 1000.0) * screen_w)
        pixel_y = int((norm_y / 1000.0) * screen_h)

        pyautogui.click(pixel_x, pixel_y)
        return f"Clicked on '{description}' at screen coordinates ({pixel_x}, {pixel_y})."

    except Exception as e:
        logger.error("Vision locator error: %s", e)
        return f"Vision locator error: {e}"
    finally:
        if temp_img.exists():
            try:
                temp_img.unlink()
            except Exception:
                pass
