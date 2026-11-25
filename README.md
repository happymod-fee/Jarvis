# Jarvis

## 🤖 VAX — Voice Assistant eXtended

> A lightweight, privacy-conscious desktop voice assistant for Windows (and Unix) that feels like Google Assistant, but with full autonomous control of your PC and real Google Chrome.  
> Supports **Bangla**, **English**, and mixed **Banglish** out of the box with zero cloud subscription fees.

---

## 🌟 Key Features

- **⚡ Ultra-Low Idle RAM:** ~97 MB idle (vs ~300+ MB for Electron apps). Heavy modules (Playwright, Vision, local Whisper) are loaded lazily only when requested.
- **🎙️ Seamless Voice Pipeline:**
  - **Wake Word:** Free, offline `openWakeWord` ("Hey Jarvis") running on a low-CPU thread.
  - **Universal Fallback:** Push-to-Talk global hotkey (`Ctrl+Space`) works anytime.
  - **VAD:** Automatic Speech Activity Detection detects when you finish speaking.
  - **STT:** Cloud Groq Whisper (ultra-fast < 1s transcription for Bangla/English) or local faster-whisper.
  - **TTS:** Microsoft Edge Neural TTS (`bn-BD-NabanitaNeural` for natural Bangla, `en-US-JennyNeural` for English).
  - **Interruptible Speech:** Interrupts voice playback immediately when you speak or press Stop.
- **🧠 Provider-Agnostic AI Brain:**
  - Works with **Groq**, **OpenAI**, **Anthropic Claude**, **Google Gemini**, **DeepSeek**, **Mistral**, **OpenRouter**, **Ollama (local)**, or any custom OpenAI-compatible endpoint.
  - Auto-detects provider from your API key format (`gsk_`, `sk-ant-`, `AIzaSy`, `sk-proj-`).
  - Bulletproof JSON fallback mode for local models without native function calling.
  - Short-term conversational memory (~10 turns) for natural follow-ups ("close that", "ota bondho koro").
- **💻 Human-Like PC Control:**
  - **Apps & System:** Open/close applications, list processes, volume control (`pycaw`), display brightness, lock workstation, restart, shutdown.
  - **Human Interaction:** Keystroke typing (with full Unicode/Bangla support), mouse moves, clicks, scrolls, drags, and hotkeys.
  - **File Operations:** Search files, read, create, copy, move, rename, zip/unzip, and **safe deletion to the Windows Recycle Bin** (never permanent).
  - **Vision Fallback:** Takes desktop screenshot and uses multimodal vision AI to locate and click UI elements when accessibility APIs fail.
- **🌐 Real Google Chrome Automation:**
  - Connects to your **real Google Chrome** instance over Chrome DevTools Protocol (CDP port 9222).
  - **Keeps all your existing logins, cookies, active sessions, and extensions.**
  - Navigates URLs, searches Google, clicks buttons/links by text or CSS selector, fills forms, and plays YouTube videos.
- **🛡️ Multi-Tier Safety & Audit Log:**
  - Action risk classification: `SAFE`, `MEDIUM`, and `DANGEROUS`.
  - Dangerous actions (shutdown, restart, file deletion) require voice or UI confirmation.
  - Shell command blocklist prevents destructive commands (`rm -rf`, `format`, `del /s /q C:\`).
  - Emergency stop button and global kill switch (`Ctrl+Alt+Esc`).
  - All operations are permanently audited in a local SQLite database (`~/.vax/action_history.db`).
- **🧩 1-Click Extensibility:**
  - Drop any Python file with the `@tool` decorator into `plugins/` and it is auto-loaded into the assistant.

---

## 🚀 Quick Start Guide

### Step 1: Install Requirements
Ensure Python 3.11+ is installed. Open PowerShell or Command Prompt:

```bash
cd "d:\CD\AI Video\vax"
python -m pip install -r requirements.txt
```

### Step 2: Launch VAX
To launch the full desktop GUI with the floating animated orb and system tray:

```bash
python main.py
```
*(Or double-click `run.bat`)*

To run text-only CLI mode without voice or audio hardware:
```bash
python main.py --cli
```

### Step 3: First-Run Wizard
On your first launch, VAX opens a 3-step setup wizard:
1. **Paste your API key:** (e.g. your Groq or Gemini key). VAX auto-detects the provider and encrypts your key directly into the Windows Credential Store (DPAPI Keyring).
2. **Choose Wake Word:** Default is `"hey jarvis"`.
3. **Audio Test:** Click "Play Test Greeting" to verify audio output.

---

## 🔑 How to Get API Keys

| Provider | Where to get key | Format | Recommended Model |
|---|---|---|---|
| **Groq (Recommended)** | [console.groq.com](https://console.groq.com/keys) | `gsk_...` | `llama-3.3-70b-versatile` |
| **Google Gemini** | [aistudio.google.com](https://aistudio.google.com/apikey) | `AIzaSy...` | `gemini-2.5-flash` |
| **OpenAI** | [platform.openai.com](https://platform.openai.com/api-keys) | `sk-proj-...` | `gpt-4o` |
| **Anthropic Claude** | [console.anthropic.com](https://console.anthropic.com) | `sk-ant-...` | `claude-3-5-sonnet-20241022` |
| **DeepSeek** | [platform.deepseek.com](https://platform.deepseek.com) | `dsk-...` | `deepseek-chat` |
| **OpenRouter** | [openrouter.ai](https://openrouter.ai/keys) | `sk-or-...` | `anthropic/claude-3.5-sonnet` |
| **Ollama (Local/Free)** | Download from [ollama.ai](https://ollama.ai) | None needed | `llama3.2:latest` |

---

## 🗣️ Voice Commands Examples

You can speak in **Bangla**, **English**, or mixed **Banglish**:

### PC & Apps:
- *"Notepad kholo"* -> Opens Notepad.
- *"Calculator open koro"* -> Opens Calculator.
- *"Close Chrome"* -> Closes Google Chrome.
- *"Volume 50% kore dao"* -> Sets system volume to 50%.
- *"Screen lock koro"* -> Locks Windows workstation.

### Chrome & Web:
- *"YouTube-e Bangla news chalo"* -> Opens YouTube and plays first video matching "Bangla news".
- *"Search Google for Python documentation"* -> Searches Google in Chrome.
- *"Pause video"* -> Pauses active YouTube playback.
- *"Read this page"* -> Reads visible text of the active Chrome tab.

### Files & Search:
- *"Amar desktop-e project namer file khujo"* -> Searches for matching files.
- *"What's the weather in Dhaka?"* -> Retrieves live weather for Dhaka.
- *"Calculate 25 into 80 plus 500"* -> Computes math expression.
- *"Todo list-e add koro: buy milk"* -> Adds item via Todo plugin.

---

## 🧩 Adding Custom Plugins

Create any Python file in `vax/plugins/` (or `~/.vax/plugins/`):

```python
# vax/plugins/my_custom_tool.py
from vax.tools import tool
from vax.safety import RiskLevel

@tool(description="Sends an alert chime and displays a desktop popup.", risk_level=RiskLevel.MEDIUM)
def send_chime(message: str) -> str:
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, message, "VAX Chime", 0x40)
    return f"Chime popup displayed: {message}"
```

That's it! When VAX starts, `send_chime` is automatically registered and the LLM agent can invoke it whenever relevant.

---

## 🛠️ Troubleshooting

### 1. Microphone not picking up speech
- Open Settings (gear icon in VAX HUD or tray menu).
- Go to **Voice & Audio** tab.
- In the **Microphone Input Device** dropdown, explicitly select your active headset or microphone instead of default.
- Click **Test Spoken Voice** to verify audio output.

### 2. Chrome automation not connecting
- VAX will automatically attempt to launch Chrome with `--remote-debugging-port=9222`.
- If you already had Chrome open before starting VAX, close all Chrome instances and let VAX start it, or launch your shortcut with:
  `chrome.exe --remote-debugging-port=9222`

### 3. Wake word sensitivity
- If VAX triggers too easily, go to **Settings -> Voice & Audio** and lower the **Wake Word Sensitivity** slider (e.g. from 0.50 to 0.40).
- If your room is noisy or the microphone is far, use the universal **Push-to-Talk** hotkey: `Ctrl+Space`.

### 4. Emergency Stop
- If the assistant is executing a task you want to stop immediately, press `Ctrl+Alt+Esc` or click the bright red **STOP** button on the floating HUD.

---

## 🧪 Running Automated Tests

Run the full test suite with pytest:

```bash
python -m pytest "d:\CD\AI Video\vax\tests" -v
```
*(All 14 unit and integration tests validate safety blocklists, provider auto-detection, JSON fallback parsing, and tools)*
