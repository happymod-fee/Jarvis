# 📝 VAX Architectural Decisions & Environment Log (DECISIONS.md)

This log records every technical and design decision taken during autonomous execution.

---

### 1. Environment & Base Stack
- **OS:** Windows 10 (Build 19045), 64-bit AMD64.
- **Python Version:** Python 3.14.6 (`C:\Python314\python.exe`).
- **RAM Detected:** ~6 GB usable (~8 GB physical), with ~1.17 GB free at launch.
- **Audio Devices:** AMD High Definition Audio, DroidCam Virtual Audio, AudioRelay Virtual Mic/Speakers, High Definition Audio Device.
- **Directory Layout:** Built under `d:\CD\AI Video\vax\` as a clean, self-contained modular package.

---

### 2. Dependency Adjustments
- **Google GenAI:** Using modern `google-genai` library (v2.33.0 already present) as requested, avoiding deprecated `google-generativeai`.
- **Audio Capture:** Using `sounddevice` with NumPy/SoundFile for microphone streams (avoiding PyAudio build issues on Windows).
- **Configuration Serialization:** Using standard library `tomllib` (Python 3.11+) for parsing, and `tomli_w` for safe serialization.
- **API Key Security:** Using Windows DPAPI credential store via `keyring` library; fallback to obfuscated local storage if keyring service is unavailable.
- **Safe File Deletion:** Using `send2trash` so all deletions land in Windows Recycle Bin rather than permanently destroying user data.
- **Providers:** Consolidated into `providers/openai_compatible.py` (OpenAI, Groq, DeepSeek, Mistral, OpenRouter, Ollama, Custom), `providers/anthropic_provider.py`, and `providers/gemini_provider.py`.
- **Wake Word:** Shipped with pre-trained openWakeWord "hey jarvis" model, accompanied by a universal global Push-To-Talk hotkey (`Ctrl+Space`) and emergency kill switch (`Ctrl+Alt+Esc`).
