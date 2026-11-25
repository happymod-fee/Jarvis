"""
Chrome Browser Automation Tools for VAX.
Connects to Google Chrome over CDP (port 9222) when available, and gracefully falls back
to opening tabs/videos directly in the user's existing Chrome session without spawning
blank "New Tab" windows when Chrome is already running without remote debugging.
"""

import os
import re
import sys
import time
import asyncio
import webbrowser
import urllib.parse
import subprocess
import logging
from typing import Optional

from vax.tools import tool
from vax.safety import RiskLevel

logger = logging.getLogger("VAX.Tools.Browser")

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def _find_chrome_exe() -> Optional[str]:
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None


def _is_chrome_running() -> bool:
    """Checks if chrome.exe is currently running."""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if name == "chrome.exe":
                return True
    except Exception:
        pass
    return False


def _open_in_existing_chrome(url: str) -> None:
    """Opens a URL as a single tab in the user's existing browser without spawning blank windows."""
    chrome_exe = _find_chrome_exe()
    if chrome_exe and sys.platform == "win32":
        subprocess.Popen([chrome_exe, url])
    else:
        webbrowser.open(url)


class ChromeCDPManager:
    """
    Manages connection to Google Chrome over CDP when debugging port 9222 is active.
    """
    _instance = None

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.current_page = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ChromeCDPManager()
        return cls._instance

    async def _is_cdp_listening(self) -> bool:
        import httpx
        for host in ("127.0.0.1", "localhost"):
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    r = await client.get(f"http://{host}:9222/json/version")
                    if r.status_code == 200:
                        return True
            except Exception:
                continue
        return False

    async def _ensure_chrome_running_with_debugging(self) -> bool:
        """
        Returns True if Chrome CDP on port 9222 is ready.
        If Chrome is already running WITHOUT port 9222, returns False instead of
        spawning empty 'New Tab' windows.
        """
        if await self._is_cdp_listening():
            logger.debug("Chrome is already listening on CDP port 9222.")
            return True

        if _is_chrome_running():
            # Chrome is already open without --remote-debugging-port=9222.
            # Launching chrome.exe --remote-debugging-port=9222 would only open blank tabs!
            logger.info("Chrome is already running without CDP port 9222; using direct tab launch fallback.")
            return False

        chrome_exe = _find_chrome_exe()
        if not chrome_exe:
            return False

        logger.info("Launching Chrome with remote debugging enabled on port 9222...")
        cmd = [
            chrome_exe,
            "--remote-debugging-port=9222",
            "--restore-last-session",
        ]
        subprocess.Popen(cmd)

        for _ in range(8):
            await asyncio.sleep(0.5)
            if await self._is_cdp_listening():
                return True

        return False

    async def get_page(self):
        """Returns or acquires an active Playwright page attached to Chrome, or None if CDP unavailable."""
        cdp_ready = await self._ensure_chrome_running_with_debugging()
        if not cdp_ready:
            return None

        from playwright.async_api import async_playwright

        if self.playwright is None:
            self.playwright = await async_playwright().start()

        if self.browser is None or not self.browser.is_connected():
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            except Exception as e:
                logger.error("Failed to connect to Chrome over CDP: %s", e)
                return None

        contexts = self.browser.contexts
        if contexts:
            self.context = contexts[0]
        else:
            self.context = await self.browser.new_context()

        pages = self.context.pages
        if pages:
            self.current_page = pages[-1]
        else:
            self.current_page = await self.context.new_page()

        return self.current_page


cdp_mgr = ChromeCDPManager.get_instance()


async def _resolve_youtube_watch_url(query: str) -> Optional[str]:
    """Fetches YouTube search HTML and extracts the first video's direct watch URL."""
    import httpx
    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(search_url, headers=headers)
            if res.status_code == 200:
                match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', res.text)
                if match:
                    vid_id = match.group(1)
                    return f"https://www.youtube.com/watch?v={vid_id}"
    except Exception as e:
        logger.debug("YouTube watch URL resolution failed: %s", e)
    return None


@tool(description="Navigates Google Chrome to the specified URL.", risk_level=RiskLevel.MEDIUM)
async def open_url(url: str) -> str:
    """Navigates browser to URL."""
    target = url.strip()
    if not (target.startswith("http://") or target.startswith("https://")):
        target = "https://" + target

    try:
        page = await cdp_mgr.get_page()
        if page is not None:
            await page.goto(target, wait_until="domcontentloaded", timeout=15000)
            title = await page.title()
            return f"Navigated Chrome to '{target}'. Title: {title}"

        _open_in_existing_chrome(target)
        return f"Opened '{target}' in Chrome."
    except Exception as e:
        _open_in_existing_chrome(target)
        return f"Opened '{target}' in Chrome (fallback: {e})."


@tool(description="Performs a Google Search in Chrome.", risk_level=RiskLevel.MEDIUM)
async def search_google(query: str) -> str:
    """Searches Google for the given query."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}"
    return await open_url(url)


@tool(description="Opens a new tab in Google Chrome.", risk_level=RiskLevel.MEDIUM)
async def new_browser_tab(url: str = "https://www.google.com") -> str:
    """Opens new browser tab."""
    try:
        page = await cdp_mgr.get_page()
        if page is not None:
            context = page.context
            new_p = await context.new_page()
            cdp_mgr.current_page = new_p
            if url and url != "about:blank":
                await new_p.goto(url, wait_until="domcontentloaded", timeout=15000)
            return f"Opened new tab ({url})."

        _open_in_existing_chrome(url)
        return f"Opened new tab ({url}) in Chrome."
    except Exception as e:
        return f"Failed to open new tab: {e}"


@tool(description="Switches active Chrome tab by index (requires Chrome debug mode).", risk_level=RiskLevel.MEDIUM)
async def switch_browser_tab(index: int) -> str:
    """Switches active tab."""
    try:
        page = await cdp_mgr.get_page()
        if page is None:
            return "Tab switching requires Chrome launched with remote debugging port 9222."
        pages = page.context.pages
        idx = int(index)
        if 0 <= idx < len(pages):
            cdp_mgr.current_page = pages[idx]
            await pages[idx].bring_to_front()
            title = await pages[idx].title()
            return f"Switched to tab {idx}: '{title}'."
        return f"Invalid tab index {idx}. Total tabs: {len(pages)}."
    except Exception as e:
        return f"Failed to switch tab: {e}"


@tool(description="Closes the currently active browser tab.", risk_level=RiskLevel.MEDIUM)
async def close_browser_tab() -> str:
    """Closes active tab."""
    try:
        page = await cdp_mgr.get_page()
        if page is not None:
            title = await page.title()
            await page.close()
            return f"Closed tab: '{title}'."
        import pyautogui
        pyautogui.hotkey("ctrl", "w")
        return "Closed active browser tab."
    except Exception as e:
        return f"Failed to close tab: {e}"


@tool(description="Reads the visible text content from the current active Chrome page (requires debug mode).", risk_level=RiskLevel.SAFE)
async def read_page_text(max_chars: int = 2500) -> str:
    """Extracts visible text of web page."""
    try:
        page = await cdp_mgr.get_page()
        if page is None:
            return "Cannot read DOM text because Chrome is running without remote debugging port 9222."
        text = await page.evaluate("() => document.body.innerText")
        cleaned = " ".join((text or "").split())
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars] + f"\n... [Truncated at {max_chars} chars]"
        return cleaned if cleaned else "Page has no visible text."
    except Exception as e:
        return f"Failed to read page text: {e}"


@tool(description="Clicks a button, link, or element on the current page by text or CSS selector.", risk_level=RiskLevel.MEDIUM)
async def click_browser_element(selector_or_text: str) -> str:
    """Clicks an element by text or selector."""
    target = selector_or_text.strip()
    try:
        page = await cdp_mgr.get_page()
        if page is None:
            return "Browser element clicking requires Chrome debugging port 9222; use click_element_by_description instead."

        locator = page.get_by_text(target, exact=False).first
        if await locator.count() > 0:
            await locator.click(timeout=5000)
            return f"Clicked element matching text '{target}'."

        role_btn = page.get_by_role("button", name=target).first
        if await role_btn.count() > 0:
            await role_btn.click(timeout=5000)
            return f"Clicked button '{target}'."

        await page.click(target, timeout=5000)
        return f"Clicked element matching selector '{target}'."
    except Exception as e:
        return f"Could not click '{target}': {e}"


@tool(description="Fills text into an input field or form in Chrome.", risk_level=RiskLevel.MEDIUM)
async def fill_browser_form(selector_or_placeholder: str, value: str) -> str:
    """Fills form field."""
    target = selector_or_placeholder.strip()
    try:
        page = await cdp_mgr.get_page()
        if page is None:
            return "Form filling requires Chrome debugging port 9222."

        ph = page.get_by_placeholder(target).first
        if await ph.count() > 0:
            await ph.fill(value)
            return f"Filled '{target}' with value."

        await page.fill(target, value)
        return f"Filled input '{target}'."
    except Exception as e:
        return f"Failed to fill form field: {e}"


@tool(description="Plays a video, song, or search query directly on YouTube in Chrome.", risk_level=RiskLevel.MEDIUM)
async def play_youtube_video(query: str) -> str:
    """Resolves and immediately plays the requested video/song on YouTube in Chrome."""
    try:
        q_clean = query.strip()
        if "youtube.com/watch" in q_clean or "youtu.be/" in q_clean:
            watch_url = q_clean
        else:
            watch_url = await _resolve_youtube_watch_url(q_clean)

        page = await cdp_mgr.get_page()
        if page is not None:
            if watch_url:
                await page.goto(watch_url, wait_until="domcontentloaded", timeout=15000)
                title = await page.title()
                return f"Playing YouTube video: '{title}'."

            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(q_clean)}"
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            first_video = page.locator("ytd-video-renderer #video-title").first
            if await first_video.count() > 0:
                title = await first_video.text_content()
                await first_video.click()
                return f"Playing YouTube video: '{title.strip() if title else q_clean}'."
            return "Loaded YouTube search results."

        # Fallback when Chrome is already open without CDP port 9222:
        # Open the resolved direct watch URL in the user's active Chrome window (auto-plays!)
        if watch_url:
            _open_in_existing_chrome(watch_url)
            return f"Playing '{q_clean}' on YouTube in Chrome ({watch_url})."

        fallback_search = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(q_clean)}"
        _open_in_existing_chrome(fallback_search)
        return f"Opened YouTube search for '{q_clean}' in Chrome."
    except Exception as e:
        return f"Failed to play YouTube video: {e}"


@tool(description="Controls active YouTube or media playback (action: 'toggle', 'play', 'pause', 'mute', 'fullscreen', 'next').", risk_level=RiskLevel.MEDIUM)
async def control_youtube_media(action: str = "toggle") -> str:
    """Controls video playback on active YouTube tab or system media."""
    act = action.lower().strip()
    try:
        page = await cdp_mgr.get_page()
        if page is not None:
            if act in ("toggle", "play", "pause"):
                await page.keyboard.press("k")
                return f"Toggled YouTube playback ({act})."
            elif act == "fullscreen":
                await page.keyboard.press("f")
                return "Toggled fullscreen."
            elif act == "mute":
                await page.keyboard.press("m")
                return "Toggled YouTube mute."
            elif act == "next":
                await page.keyboard.press("Shift+N")
                return "Skipped to next video."
            return f"Action '{act}' executed on media."

        # Fallback using global OS media/YouTube shortcuts
        import pyautogui
        if act in ("toggle", "play", "pause"):
            pyautogui.press("playpause")
        elif act == "mute":
            pyautogui.press("volumemute")
        elif act == "next":
            pyautogui.press("nexttrack")
        elif act == "fullscreen":
            pyautogui.press("f")
        return f"Executed media control '{act}'."
    except Exception as e:
        return f"Failed to control media: {e}"
