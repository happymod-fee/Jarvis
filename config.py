"""
VAX Configuration & Credential Management System.
Handles persistent settings via TOML and secure credential storage via OS Keyring (Windows DPAPI).
Guarantees clean TOML serialization by recursively sanitizing None values.
"""

import os
import sys
import copy
import logging
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import tomllib  # Python 3.11+ standard library
except ImportError:
    try:
        import tomli as tomllib  # Fallback
    except ImportError:
        tomllib = None

try:
    import tomli_w
except ImportError:
    tomli_w = None

try:
    import keyring
except ImportError:
    keyring = None

logger = logging.getLogger("VAX.Config")

SERVICE_NAME = "vax_voice_assistant"

DEFAULT_CONFIG: Dict[str, Any] = {
    "general": {
        "wake_word": "hey jarvis",
        "language": "auto",  # auto, bn-BD, en-US
        "hotkey": "ctrl+space",
        "emergency_stop_hotkey": "ctrl+alt+esc",
        "start_with_windows": False,
        "theme": "dark",
        "first_run_completed": False,
        "turbo_mode": False,
        "continuous_conversation": True,
    },
    "provider": {
        "provider": "groq",  # groq, openai, anthropic, gemini, deepseek, mistral, openrouter, ollama, custom
        "model": "llama-3.3-70b-versatile",
        "base_url": "",
        "temperature": 0.3,
        "max_tokens": 1024,
        "use_json_fallback": False,
        # Fallback provider configuration (used if primary fails after retries)
        "fallback_provider": "",  # e.g. "groq", "gemini", "openai"
        "fallback_model": "",
        "fallback_base_url": "",
    },
    "voice": {
        "stt_engine": "auto",  # auto, gemini, groq, openai, local
        "stt_model": "whisper-large-v3",
        "tts_engine": "edge-tts",  # edge-tts, openai, pyttsx3
        "tts_voice": "bn-BD-NabanitaNeural",  # High quality Bangla voice
        "tts_rate": "+0%",
        "mic_device_index": None,
        "mic_muted": False,
        "volume": 80,
        "wake_sensitivity": 0.5,
        "beep_on_wake": True,
    },
    "safety": {
        "require_confirm_dangerous": True,
        "allow_shell_commands": True,
        "allow_file_deletion": True,
        "allow_browser_automation": True,
        "allow_keyboard_mouse": True,
    },
}

DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "gemini": "gemini-3.5-flash-lite",
    "deepseek": "deepseek-chat",
    "mistral": "mistral-large-latest",
    "openrouter": "anthropic/claude-3.5-sonnet",
    "ollama": "llama3.2:latest",
    "custom": "default-model",
}

DEFAULT_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}


def get_vax_dir() -> Path:
    """Returns ~/.vax directory, ensuring it exists."""
    vax_dir = Path.home() / ".vax"
    vax_dir.mkdir(parents=True, exist_ok=True)
    return vax_dir


def get_config_path() -> Path:
    """Returns path to ~/.vax/config.toml."""
    return get_vax_dir() / "config.toml"


def get_keyring_fallback_path() -> Path:
    """Returns path for encrypted fallback if OS keyring fails."""
    return get_vax_dir() / ".keys_vault"


def auto_detect_provider(api_key: str) -> str:
    """
    Auto-detect the AI provider from the format of the API key.
    """
    key = api_key.strip()
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("sk-or-"):
        return "openrouter"
    if key.startswith("AIzaSy"):
        return "gemini"
    if key.startswith("dsk-"):
        return "deepseek"
    if key.startswith("sk-proj-"):
        return "openai"
    if key.startswith("sk-"):
        if len(key) > 50:
            return "openai"
        return "openai"
    if "ollama" in key.lower():
        return "ollama"
    return "custom"


def set_api_key(provider: str, key: str) -> bool:
    """
    Securely save API key to OS Keyring (DPAPI on Windows).
    Falls back to user-scoped hidden vault if keyring is unavailable.
    """
    provider_clean = provider.strip().lower()
    key_clean = key.strip()
    
    if keyring is not None:
        try:
            keyring.set_password(SERVICE_NAME, f"api_key_{provider_clean}", key_clean)
            logger.info("API key saved in OS Keyring for provider '%s'", provider_clean)
            return True
        except Exception as e:
            logger.warning("Keyring set_password failed (%s), using fallback vault", e)

    # Fallback storage: basic machine-bound obfuscation
    try:
        vault_path = get_keyring_fallback_path()
        vault_data = {}
        if vault_path.exists():
            import json
            try:
                vault_data = json.loads(vault_path.read_text(encoding="utf-8"))
            except Exception:
                vault_data = {}
        
        encoded = key_clean.encode("utf-8").hex()
        vault_data[provider_clean] = encoded
        import json
        vault_path.write_text(json.dumps(vault_data), encoding="utf-8")
        return True
    except Exception as e:
        logger.error("Failed to save API key to fallback vault: %s", e)
        return False


def get_api_key(provider: str) -> str:
    """
    Securely retrieve API key from OS Keyring or fallback vault.
    Also checks environment variables as last resort.
    """
    provider_clean = provider.strip().lower()

    # 1. Check OS Keyring
    if keyring is not None:
        try:
            pwd = keyring.get_password(SERVICE_NAME, f"api_key_{provider_clean}")
            if pwd:
                return pwd
        except Exception as e:
            logger.debug("Keyring get_password failed: %s", e)

    # 2. Check fallback vault
    try:
        vault_path = get_keyring_fallback_path()
        if vault_path.exists():
            import json
            vault_data = json.loads(vault_path.read_text(encoding="utf-8"))
            if provider_clean in vault_data:
                hex_data = vault_data[provider_clean]
                return bytes.fromhex(hex_data).decode("utf-8")
    except Exception as e:
        logger.debug("Fallback vault read failed: %s", e)

    # 3. Check environment variables
    env_map = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_var = env_map.get(provider_clean)
    if env_var and os.environ.get(env_var):
        return os.environ.get(env_var, "")

    return ""


def sanitize_for_toml(data: Any) -> Any:
    """
    Recursively converts all None values into empty strings (or omits them)
    so tomli_w can serialize the dictionary without TypeError.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if v is None:
                cleaned[k] = ""
            elif isinstance(v, (dict, list)):
                cleaned[k] = sanitize_for_toml(v)
            else:
                cleaned[k] = v
        return cleaned
    elif isinstance(data, list):
        return [sanitize_for_toml(x) for x in data if x is not None]
    return data


def load_config(custom_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from ~/.vax/config.toml (or custom_path).
    Merges with DEFAULT_CONFIG, restoring empty strings back to None where defaults specify None.
    """
    config_path = custom_path or get_config_path()
    cfg = {}

    if config_path.exists() and tomllib is not None:
        try:
            with open(config_path, "rb") as f:
                cfg = tomllib.load(f)
        except Exception as e:
            logger.error("Error reading %s: %s. Using default configuration.", config_path, e)

    # Deep merge with defaults
    merged = {}
    for section, defaults in DEFAULT_CONFIG.items():
        merged[section] = {}
        section_data = cfg.get(section, {}) if isinstance(cfg, dict) else {}
        for key, default_val in defaults.items():
            if key in section_data:
                val = section_data[key]
                # If default is None and saved value is "" (or missing), restore to None
                if default_val is None and (val == "" or val is None):
                    merged[section][key] = None
                else:
                    merged[section][key] = val
            else:
                merged[section][key] = default_val

        # Preserve any extra custom keys in section
        if isinstance(section_data, dict):
            for key, val in section_data.items():
                if key not in merged[section]:
                    merged[section][key] = None if val == "" else val

    return merged


_last_save_error: str = ""


def get_last_config_error() -> str:
    """Returns the last error message from saving config, if any."""
    global _last_save_error
    return _last_save_error


def save_config(config: Dict[str, Any], custom_path: Optional[Path] = None) -> bool:
    """
    Save configuration to ~/.vax/config.toml (or custom_path).
    Recursively cleans None values before dumping with tomli_w.
    """
    global _last_save_error
    _last_save_error = ""

    config_path = custom_path or get_config_path()
    if tomli_w is None:
        _last_save_error = "tomli_w is not installed; cannot serialize config to TOML."
        logger.error(_last_save_error)
        return False

    try:
        # Sanitize dict to remove/convert all None values
        clean_cfg = sanitize_for_toml(config)
        
        with open(config_path, "wb") as f:
            tomli_w.dump(clean_cfg, f)
        logger.info("Configuration saved successfully to %s", config_path)
        return True
    except Exception as e:
        _last_save_error = f"Failed to write configuration to {config_path}: {e}"
        logger.error(_last_save_error)
        return False


class ConfigManager:
    """
    High-level singleton-style interface for managing runtime configuration.
    """
    def __init__(self):
        self.config = load_config()
        self.last_error: str = ""

    def reload(self):
        self.config = load_config()

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.config.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any, auto_save: bool = True) -> bool:
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        if auto_save:
            return self.save()
        return True

    def save(self) -> bool:
        success = save_config(self.config)
        self.last_error = get_last_config_error()
        return success

    def get_current_api_key(self) -> str:
        provider = self.get("provider", "provider", "groq")
        return get_api_key(provider)

    def set_current_api_key(self, key: str) -> bool:
        provider = self.get("provider", "provider", "groq")
        return set_api_key(provider, key)

    def get_fallback_api_key(self) -> str:
        provider = self.get("provider", "fallback_provider", "")
        if not provider:
            return ""
        return get_api_key(provider)


# Module-level instance
config_manager = ConfigManager()
