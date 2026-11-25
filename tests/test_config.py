"""
Unit Tests for VAX Configuration System.
Validates TOML serialization of None values, deep-merging defaults, and DPAPI key storage.
"""

from pathlib import Path
import pytest
from vax.config import (
    DEFAULT_CONFIG,
    save_config,
    load_config,
    sanitize_for_toml,
    ConfigManager,
)


def test_sanitize_for_toml_removes_none():
    data = {
        "section": {
            "key_with_none": None,
            "key_with_str": "hello",
            "nested": {
                "inner_none": None,
                "inner_int": 42,
            },
        },
        "list_with_none": [1, None, "test", None],
    }
    sanitized = sanitize_for_toml(data)
    assert sanitized["section"]["key_with_none"] == ""
    assert sanitized["section"]["nested"]["inner_none"] == ""
    assert sanitized["section"]["nested"]["inner_int"] == 42
    assert None not in sanitized["list_with_none"]


def test_save_config_with_none_and_reload(tmp_path: Path):
    test_config_file = tmp_path / "test_config.toml"

    # Config with explicit None values (which previously crashed tomli_w)
    cfg = {
        "general": {
            "wake_word": "hey jarvis",
            "language": "auto",
        },
        "provider": {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "custom_base_url": None,
            "fallback_provider": None,
            "fallback_model": None,
        },
        "voice": {
            "mic_device_index": None,
            "tts_voice": "bn-BD-NabanitaNeural",
        },
    }

    # Must save successfully without 'TypeError: Object of type NoneType is not TOML serializable'
    success = save_config(cfg, custom_path=test_config_file)
    assert success is True, "save_config should return True"
    assert test_config_file.exists()

    # Reload config
    reloaded = load_config(custom_path=test_config_file)
    assert reloaded["provider"]["provider"] == "groq"
    # mic_device_index default is None, and saved as "" -> should reload as None
    assert reloaded["voice"]["mic_device_index"] is None
    # custom_base_url was saved as "" -> should reload without crashing
    assert reloaded["provider"]["custom_base_url"] is None
