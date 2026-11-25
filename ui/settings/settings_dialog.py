"""
VAX Settings Window (5 Comprehensive Tabs).
Allows full customization of General preferences, AI Providers (with Fallback & Model Discovery),
Voice/Audio, Safety, and Plugins.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QDialog,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSlider,
    QPushButton,
    QMessageBox,
    QApplication,
)

from vax.config import (
    config_manager,
    auto_detect_provider,
    get_api_key,
    set_api_key,
    DEFAULT_MODELS,
    DEFAULT_BASE_URLS,
    get_vax_dir,
)
from vax.ui.styles import DARK_THEME_QSS
from vax.voice.recorder import list_input_devices
from vax.voice.tts import tts_engine
from vax.tools import registry
from vax.providers.base import format_friendly_error, ChatMessage
from vax.providers import create_provider, fetch_models_for_provider

logger = logging.getLogger("VAX.UI.Settings")


class _BackgroundWorker(QThread):
    """Runs network operations off the Qt main thread to prevent UI freezes."""
    finished_ok = Signal(object)
    failed = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            res = self._fn()
            self.finished_ok.emit(res)
        except Exception as e:
            self.failed.emit(e)


class SettingsDialog(QDialog):
    """
    Main Settings Dialog with 5 dedicated configuration tabs.
    """
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VAX Settings & Preferences")
        self.resize(600, 580)
        self.setStyleSheet(DARK_THEME_QSS)
        self._workers: List[QThread] = []
        self._setup_ui()
        self._load_values()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.tabs = QTabWidget(self)

        # Tab 1: General
        self.tab_general = QWidget()
        self._setup_general_tab()
        self.tabs.addTab(self.tab_general, "General")

        # Tab 2: AI Provider
        self.tab_provider = QWidget()
        self._setup_provider_tab()
        self.tabs.addTab(self.tab_provider, "AI Provider")

        # Tab 3: Voice & Audio
        self.tab_voice = QWidget()
        self._setup_voice_tab()
        self.tabs.addTab(self.tab_voice, "Voice & Audio")

        # Tab 4: Safety & Security
        self.tab_safety = QWidget()
        self._setup_safety_tab()
        self.tabs.addTab(self.tab_safety, "Safety & Control")

        # Tab 5: Plugins & Tools
        self.tab_plugins = QWidget()
        self._setup_plugins_tab()
        self.tabs.addTab(self.tab_plugins, "Plugins & Tools")

        main_layout.addWidget(self.tabs)

        # Bottom Button Bar
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Settings", self)
        self.btn_save.setStyleSheet("background-color: #00d2ff; color: #050b14; font-weight: bold; padding: 6px 16px;")
        self.btn_save.clicked.connect(self._on_save)

        btn_bar.addWidget(self.btn_cancel)
        btn_bar.addWidget(self.btn_save)
        main_layout.addLayout(btn_bar)

    # --- TAB 1: GENERAL ---
    def _setup_general_tab(self):
        layout = QFormLayout(self.tab_general)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        self.in_wake_word = QLineEdit()
        self.in_wake_word.setPlaceholderText("hey jarvis")

        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["auto (Bangla + English)", "bn-BD (Bangla Priority)", "en-US (English Priority)"])

        self.in_hotkey = QLineEdit()
        self.in_hotkey.setPlaceholderText("ctrl+space")

        self.in_estop = QLineEdit()
        self.in_estop.setPlaceholderText("ctrl+alt+esc")

        self.chk_startup = QCheckBox("Start VAX automatically when Windows boots")
        self.chk_turbo = QCheckBox("⚡ Enable Turbo Mode (ultra-fast responses & shorter speech pause)")

        layout.addRow("Wake Word Phrase:", self.in_wake_word)
        layout.addRow("Spoken Language Mode:", self.combo_lang)
        layout.addRow("Push-to-Talk Hotkey:", self.in_hotkey)
        layout.addRow("Emergency Stop Hotkey:", self.in_estop)
        layout.addRow("", self.chk_startup)
        layout.addRow("", self.chk_turbo)

    # --- TAB 2: AI PROVIDER ---
    def _setup_provider_tab(self):
        layout = QFormLayout(self.tab_provider)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Primary Provider Section
        primary_header = QLabel("<b>Primary AI Provider</b>")
        primary_header.setStyleSheet("color: #00d2ff; font-size: 13px;")
        layout.addRow(primary_header)

        self.combo_provider = QComboBox()
        self.combo_provider.addItems([
            "groq",
            "gemini",
            "openai",
            "anthropic",
            "deepseek",
            "mistral",
            "openrouter",
            "ollama",
            "custom",
        ])
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)

        # API Key field with show toggle
        key_layout = QHBoxLayout()
        self.in_api_key = QLineEdit()
        self.in_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_api_key.setPlaceholderText("Paste provider API key here...")
        self.in_api_key.textChanged.connect(self._on_api_key_pasted)

        self.btn_toggle_key = QPushButton("👁")
        self.btn_toggle_key.setFixedWidth(36)
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)

        key_layout.addWidget(self.in_api_key)
        key_layout.addWidget(self.btn_toggle_key)

        # Model selection with Fetch Models button
        model_layout = QHBoxLayout()
        self.combo_model = QComboBox()
        self.combo_model.setEditable(True)
        self.combo_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_model.setPlaceholderText("e.g. gemini-3.5-flash-lite, llama-3.3-70b-versatile")

        self.btn_fetch_models = QPushButton("🔄 Fetch Models")
        self.btn_fetch_models.setToolTip("Queries the provider API for all models accessible with your API key")
        self.btn_fetch_models.clicked.connect(self._fetch_models)

        model_layout.addWidget(self.combo_model, stretch=1)
        model_layout.addWidget(self.btn_fetch_models)

        self.in_base_url = QLineEdit()
        self.in_base_url.setPlaceholderText("Leave empty for default provider endpoint")

        self.chk_json_fallback = QCheckBox("Enable JSON Fallback (for models without native tool calling)")

        # Test Connection Button
        test_layout = QHBoxLayout()
        self.btn_test_provider = QPushButton("⚡ Test Connection")
        self.btn_test_provider.clicked.connect(self._test_provider_connection)
        self.lbl_provider_status = QLabel("")
        self.lbl_provider_status.setWordWrap(True)
        test_layout.addWidget(self.btn_test_provider)
        test_layout.addWidget(self.lbl_provider_status, stretch=1)

        layout.addRow("Provider:", self.combo_provider)
        layout.addRow("API Key:", key_layout)
        layout.addRow("Model Name:", model_layout)
        layout.addRow("Base URL:", self.in_base_url)
        layout.addRow("", self.chk_json_fallback)
        layout.addRow("", test_layout)

        # Fallback Provider Section
        fallback_header = QLabel("<b>Fallback Provider (Optional)</b><br>"
                                 "<span style='color: #94a3b8; font-size: 11px;'>Automatically invoked if primary provider fails after retries (e.g. 503 high demand).</span>")
        fallback_header.setStyleSheet("color: #fbbf24; margin-top: 10px;")
        layout.addRow(fallback_header)

        self.combo_fallback_provider = QComboBox()
        self.combo_fallback_provider.addItems([
            "(None - No Fallback)",
            "groq",
            "gemini",
            "openai",
            "anthropic",
            "deepseek",
            "mistral",
            "openrouter",
            "ollama",
            "custom",
        ])
        self.combo_fallback_provider.currentIndexChanged.connect(self._on_fallback_provider_changed)

        fb_key_layout = QHBoxLayout()
        self.in_fallback_api_key = QLineEdit()
        self.in_fallback_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_fallback_api_key.setPlaceholderText("Fallback provider API key (leave empty to reuse saved key)...")
        self.btn_toggle_fb_key = QPushButton("👁")
        self.btn_toggle_fb_key.setFixedWidth(36)
        self.btn_toggle_fb_key.clicked.connect(self._toggle_fb_key_visibility)
        fb_key_layout.addWidget(self.in_fallback_api_key)
        fb_key_layout.addWidget(self.btn_toggle_fb_key)

        fb_model_layout = QHBoxLayout()
        self.combo_fallback_model = QComboBox()
        self.combo_fallback_model.setEditable(True)
        self.combo_fallback_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_fallback_model.setPlaceholderText("e.g. llama-3.3-70b-versatile")
        self.btn_fetch_fallback_models = QPushButton("🔄 Fetch")
        self.btn_fetch_fallback_models.clicked.connect(self._fetch_fallback_models)
        fb_model_layout.addWidget(self.combo_fallback_model, stretch=1)
        fb_model_layout.addWidget(self.btn_fetch_fallback_models)

        self.in_fallback_base_url = QLineEdit()
        self.in_fallback_base_url.setPlaceholderText("Leave empty for default endpoint")

        layout.addRow("Fallback Provider:", self.combo_fallback_provider)
        layout.addRow("Fallback API Key:", fb_key_layout)
        layout.addRow("Fallback Model:", fb_model_layout)
        layout.addRow("Fallback Base URL:", self.in_fallback_base_url)

    def _toggle_key_visibility(self):
        if self.in_api_key.echoMode() == QLineEdit.EchoMode.Password:
            self.in_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.in_api_key.setEchoMode(QLineEdit.EchoMode.Password)

    def _toggle_fb_key_visibility(self):
        if self.in_fallback_api_key.echoMode() == QLineEdit.EchoMode.Password:
            self.in_fallback_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.in_fallback_api_key.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_api_key_pasted(self, text: str):
        detected = auto_detect_provider(text)
        if detected != "custom":
            idx = self.combo_provider.findText(detected)
            if idx >= 0 and self.combo_provider.currentIndex() != idx:
                self.combo_provider.setCurrentIndex(idx)
                self.lbl_provider_status.setText(f"Auto-detected provider: {detected}")

    def _on_provider_changed(self):
        p = self.combo_provider.currentText().lower()
        default_model = DEFAULT_MODELS.get(p, "default-model")
        self.combo_model.setCurrentText(default_model)
        # Load API key for this provider
        key = get_api_key(p)
        self.in_api_key.setText(key)
        # Default base URL
        self.in_base_url.setText(DEFAULT_BASE_URLS.get(p, ""))

    def _on_fallback_provider_changed(self):
        p_text = self.combo_fallback_provider.currentText().lower()
        if "(none" in p_text or not p_text:
            self.combo_fallback_model.setCurrentText("")
            self.in_fallback_api_key.setText("")
            self.in_fallback_base_url.setText("")
            return

        p = p_text.strip()
        default_model = DEFAULT_MODELS.get(p, "")
        self.combo_fallback_model.setCurrentText(default_model)
        self.in_fallback_api_key.setText(get_api_key(p))
        self.in_fallback_base_url.setText(DEFAULT_BASE_URLS.get(p, ""))

    def _start_worker(self, fn, on_ok, on_err):
        worker = _BackgroundWorker(fn, self)
        self._workers.append(worker)

        def cleanup():
            if worker in self._workers:
                self._workers.remove(worker)
            worker.deleteLater()

        worker.finished_ok.connect(on_ok)
        worker.failed.connect(on_err)
        worker.finished.connect(cleanup)
        worker.start()

    def _fetch_models(self):
        p = self.combo_provider.currentText().lower()
        key = self.in_api_key.text().strip()
        b_url = self.in_base_url.text().strip()

        self.btn_fetch_models.setEnabled(False)
        self.lbl_provider_status.setText("Fetching models from API...")

        def on_ok(models):
            try:
                current_model = self.combo_model.currentText().strip()
                self.combo_model.clear()
                for m in models:
                    self.combo_model.addItem(m)

                if current_model and self.combo_model.findText(current_model) >= 0:
                    self.combo_model.setCurrentText(current_model)
                elif models:
                    safe_default = DEFAULT_MODELS.get(p, models[0])
                    if self.combo_model.findText(safe_default) >= 0:
                        self.combo_model.setCurrentText(safe_default)
                    else:
                        self.combo_model.setCurrentIndex(0)
                self.lbl_provider_status.setText(f"✅ Found {len(models)} models for {p}.")
            finally:
                self.btn_fetch_models.setEnabled(True)

        def on_err(e):
            try:
                err = format_friendly_error(p, e)
                self.lbl_provider_status.setText(f"❌ {err}")
                QMessageBox.warning(self, "Fetch Models Failed", f"Could not list models for {p}:\n{err}")
            finally:
                self.btn_fetch_models.setEnabled(True)

        self._start_worker(
            lambda: fetch_models_for_provider(provider_name=p, api_key=key, base_url=b_url),
            on_ok,
            on_err,
        )

    def _fetch_fallback_models(self):
        p_text = self.combo_fallback_provider.currentText().lower()
        if "(none" in p_text or not p_text:
            return
        p = p_text.strip()
        key = self.in_fallback_api_key.text().strip() or get_api_key(p)
        b_url = self.in_fallback_base_url.text().strip()

        self.btn_fetch_fallback_models.setEnabled(False)

        def on_ok(models):
            try:
                current_model = self.combo_fallback_model.currentText().strip()
                self.combo_fallback_model.clear()
                for m in models:
                    self.combo_fallback_model.addItem(m)

                if current_model and self.combo_fallback_model.findText(current_model) >= 0:
                    self.combo_fallback_model.setCurrentText(current_model)
                elif models:
                    safe_default = DEFAULT_MODELS.get(p, models[0])
                    if self.combo_fallback_model.findText(safe_default) >= 0:
                        self.combo_fallback_model.setCurrentText(safe_default)
                    else:
                        self.combo_fallback_model.setCurrentIndex(0)
            finally:
                self.btn_fetch_fallback_models.setEnabled(True)

        def on_err(e):
            try:
                err = format_friendly_error(p, e)
                QMessageBox.warning(self, "Fetch Fallback Models Failed", f"Could not list models for {p}:\n{err}")
            finally:
                self.btn_fetch_fallback_models.setEnabled(True)

        self._start_worker(
            lambda: fetch_models_for_provider(provider_name=p, api_key=key, base_url=b_url),
            on_ok,
            on_err,
        )

    def _test_provider_connection(self):
        self.lbl_provider_status.setText("Testing connection...")
        self.btn_test_provider.setEnabled(False)

        p = self.combo_provider.currentText().lower()
        key = self.in_api_key.text().strip()
        model = self.combo_model.currentText().strip()
        b_url = self.in_base_url.text().strip()

        def run_test():
            prov = create_provider(
                provider_name=p,
                api_key=key,
                model=model,
                base_url=b_url,
            )
            return prov.generate([ChatMessage(role="user", content="Ping. Reply with 'OK'.")])

        def on_ok(res):
            try:
                if res.is_error:
                    err_text = format_friendly_error(p, res.error_message or res.content)
                    self.lbl_provider_status.setText(f"❌ {err_text}")
                else:
                    self.lbl_provider_status.setText("✅ Connected successfully!")
            finally:
                self.btn_test_provider.setEnabled(True)

        def on_err(e):
            try:
                err_text = format_friendly_error(p, e)
                self.lbl_provider_status.setText(f"❌ {err_text}")
            finally:
                self.btn_test_provider.setEnabled(True)

        self._start_worker(run_test, on_ok, on_err)

    # --- TAB 3: VOICE ---
    def _setup_voice_tab(self):
        layout = QFormLayout(self.tab_voice)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        self.combo_stt = QComboBox()
        self.combo_stt.addItems([
            "auto (Auto-detect from configured API key)",
            "gemini (Google Cloud Speech - Uses Gemini API key)",
            "groq (Fastest cloud Whisper)",
            "openai (OpenAI Whisper API)",
            "local (faster-whisper offline)",
        ])

        self.combo_tts = QComboBox()
        self.combo_tts.addItems(["edge-tts (Microsoft Cloud Neural - Free)", "openai", "pyttsx3"])

        self.combo_voice = QComboBox()
        self.combo_voice.addItems([
            "bn-BD-NabanitaNeural (Bangla - Female)",
            "bn-BD-PradeepNeural (Bangla - Male)",
            "en-US-JennyNeural (English - Female)",
            "en-US-GuyNeural (English - Male)",
        ])

        self.combo_mic = QComboBox()
        self._populate_mics()

        # Sensitivity slider with Qt.Orientation.Horizontal
        sens_layout = QHBoxLayout()
        self.slider_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_sens.setRange(10, 90)
        self.slider_sens.setValue(50)
        self.lbl_sens = QLabel("0.50")
        self.slider_sens.valueChanged.connect(lambda val: self.lbl_sens.setText(f"{val/100.0:.2f}"))
        sens_layout.addWidget(self.slider_sens)
        sens_layout.addWidget(self.lbl_sens)

        # Test Voice Button
        test_voice_layout = QHBoxLayout()
        self.btn_test_voice = QPushButton("🔊 Test Spoken Voice")
        self.btn_test_voice.clicked.connect(self._test_voice)
        test_voice_layout.addWidget(self.btn_test_voice)
        test_voice_layout.addStretch()

        layout.addRow("STT Transcription Engine:", self.combo_stt)
        layout.addRow("TTS Synthesis Engine:", self.combo_tts)
        layout.addRow("Voice Persona:", self.combo_voice)
        layout.addRow("Microphone Input Device:", self.combo_mic)
        layout.addRow("Wake Word Sensitivity:", sens_layout)
        layout.addRow("", test_voice_layout)

    def _populate_mics(self):
        self.combo_mic.clear()
        self.combo_mic.addItem("Default System Microphone", None)
        devices = list_input_devices()
        for d in devices:
            self.combo_mic.addItem(f"[{d['index']}] {d['name']}", d["index"])

    def _test_voice(self):
        tts_engine.speak("নমস্কার! VAX ভয়েস অ্যাসিস্ট্যান্ট সম্পূর্ণ প্রস্তুত। How can I help you today?")

    # --- TAB 4: SAFETY ---
    def _setup_safety_tab(self):
        layout = QVBoxLayout(self.tab_safety)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        info = QLabel(
            "<b>Risk & Permissions Policy</b><br>"
            "Control what tools the assistant is permitted to use on your operating system.<br>"
            "Dangerous operations (file deletion, power options) always request confirmation."
        )
        info.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        layout.addWidget(info)

        self.chk_confirm_dangerous = QCheckBox("Require voice or UI confirmation before executing DANGEROUS actions")
        self.chk_confirm_dangerous.setChecked(True)

        self.chk_allow_shell = QCheckBox("Allow shell command execution (protected by destructive command blocklist)")
        self.chk_allow_file_delete = QCheckBox("Allow file operations (deletions strictly sent to Windows Recycle Bin)")
        self.chk_allow_browser = QCheckBox("Allow controlling real Google Chrome (via Remote Debugging port 9222)")
        self.chk_allow_input = QCheckBox("Allow keyboard typing and mouse clicks")

        layout.addWidget(self.chk_confirm_dangerous)
        layout.addWidget(self.chk_allow_shell)
        layout.addWidget(self.chk_allow_file_delete)
        layout.addWidget(self.chk_allow_browser)
        layout.addWidget(self.chk_allow_input)
        layout.addStretch()

    # --- TAB 5: PLUGINS ---
    def _setup_plugins_tab(self):
        layout = QVBoxLayout(self.tab_plugins)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        lbl = QLabel("<b>Extensibility & Custom Plugins</b>")
        layout.addWidget(lbl)

        tool_count = len(registry.list_tool_names())
        self.lbl_tools_info = QLabel(f"Registered Tools: {tool_count} active tools available to the Agent.")
        self.lbl_tools_info.setStyleSheet("color: #00d2ff;")
        layout.addWidget(self.lbl_tools_info)

        btn_open_plugins = QPushButton("📁 Open Plugins Folder")
        btn_open_plugins.clicked.connect(self._open_plugins_folder)

        btn_open_logs = QPushButton("📊 Open Action History Database")
        btn_open_logs.clicked.connect(self._open_logs_folder)

        layout.addWidget(btn_open_plugins)
        layout.addWidget(btn_open_logs)
        layout.addStretch()

    def _open_plugins_folder(self):
        p_dir = Path(__file__).resolve().parent.parent.parent / "plugins"
        p_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(p_dir))

    def _open_logs_folder(self):
        v_dir = get_vax_dir()
        if sys.platform == "win32":
            os.startfile(str(v_dir))

    # --- LOAD / SAVE ---
    def _load_values(self):
        # General
        self.in_wake_word.setText(config_manager.get("general", "wake_word", "hey jarvis"))
        self.in_hotkey.setText(config_manager.get("general", "hotkey", "ctrl+space"))
        self.in_estop.setText(config_manager.get("general", "emergency_stop_hotkey", "ctrl+alt+esc"))
        self.chk_startup.setChecked(config_manager.get("general", "start_with_windows", False))
        self.chk_turbo.setChecked(config_manager.get("general", "turbo_mode", False))

        # Provider
        current_p = config_manager.get("provider", "provider", "groq")
        idx = self.combo_provider.findText(current_p)
        if idx >= 0:
            self.combo_provider.setCurrentIndex(idx)
        saved_model = config_manager.get("provider", "model", DEFAULT_MODELS.get(current_p, ""))
        self.combo_model.setCurrentText(saved_model)
        self.in_api_key.setText(get_api_key(current_p))
        self.in_base_url.setText(config_manager.get("provider", "base_url", ""))
        self.chk_json_fallback.setChecked(config_manager.get("provider", "use_json_fallback", False))

        # Fallback Provider
        fb_p = config_manager.get("provider", "fallback_provider", "")
        if fb_p:
            fb_idx = self.combo_fallback_provider.findText(fb_p)
            if fb_idx >= 0:
                self.combo_fallback_provider.setCurrentIndex(fb_idx)
            self.in_fallback_api_key.setText(get_api_key(fb_p))
        else:
            self.combo_fallback_provider.setCurrentIndex(0)

        saved_fb_model = config_manager.get("provider", "fallback_model", "")
        self.combo_fallback_model.setCurrentText(saved_fb_model or (DEFAULT_MODELS.get(fb_p, "") if fb_p else ""))
        self.in_fallback_base_url.setText(config_manager.get("provider", "fallback_base_url", ""))

        # Voice
        stt_eng = config_manager.get("voice", "stt_engine", "auto").lower()
        for i in range(self.combo_stt.count()):
            if stt_eng in self.combo_stt.itemText(i).lower():
                self.combo_stt.setCurrentIndex(i)
                break

        voice = config_manager.get("voice", "tts_voice", "bn-BD-NabanitaNeural")
        for i in range(self.combo_voice.count()):
            if voice in self.combo_voice.itemText(i):
                self.combo_voice.setCurrentIndex(i)
                break

        sens = int(config_manager.get("voice", "wake_sensitivity", 0.5) * 100)
        self.slider_sens.setValue(sens)
        self.lbl_sens.setText(f"{sens/100.0:.2f}")

        # Safety
        self.chk_confirm_dangerous.setChecked(config_manager.get("safety", "require_confirm_dangerous", True))
        self.chk_allow_shell.setChecked(config_manager.get("safety", "allow_shell_commands", True))
        self.chk_allow_file_delete.setChecked(config_manager.get("safety", "allow_file_deletion", True))
        self.chk_allow_browser.setChecked(config_manager.get("safety", "allow_browser_automation", True))
        self.chk_allow_input.setChecked(config_manager.get("safety", "allow_keyboard_mouse", True))

    def _on_save(self):
        # General
        config_manager.set("general", "wake_word", self.in_wake_word.text().strip().lower(), auto_save=False)
        config_manager.set("general", "hotkey", self.in_hotkey.text().strip().lower(), auto_save=False)
        config_manager.set("general", "emergency_stop_hotkey", self.in_estop.text().strip().lower(), auto_save=False)
        config_manager.set("general", "start_with_windows", self.chk_startup.isChecked(), auto_save=False)
        config_manager.set("general", "turbo_mode", self.chk_turbo.isChecked(), auto_save=False)

        # Provider
        prov = self.combo_provider.currentText().lower()
        config_manager.set("provider", "provider", prov, auto_save=False)
        config_manager.set("provider", "model", self.combo_model.currentText().strip(), auto_save=False)
        config_manager.set("provider", "base_url", self.in_base_url.text().strip(), auto_save=False)
        config_manager.set("provider", "use_json_fallback", self.chk_json_fallback.isChecked(), auto_save=False)

        key = self.in_api_key.text().strip()
        set_api_key(prov, key)

        # Fallback Provider
        fb_text = self.combo_fallback_provider.currentText().lower()
        fb_prov = "" if "(none" in fb_text else fb_text.strip()
        config_manager.set("provider", "fallback_provider", fb_prov, auto_save=False)
        config_manager.set("provider", "fallback_model", self.combo_fallback_model.currentText().strip(), auto_save=False)
        config_manager.set("provider", "fallback_base_url", self.in_fallback_base_url.text().strip(), auto_save=False)

        fb_key = self.in_fallback_api_key.text().strip()
        if fb_prov and fb_key:
            set_api_key(fb_prov, fb_key)

        # Voice
        stt_choice = self.combo_stt.currentText().split()[0]
        config_manager.set("voice", "stt_engine", stt_choice, auto_save=False)
        voice_choice = self.combo_voice.currentText().split()[0]
        config_manager.set("voice", "tts_voice", voice_choice, auto_save=False)
        config_manager.set("voice", "wake_sensitivity", self.slider_sens.value() / 100.0, auto_save=False)
        mic_idx = self.combo_mic.currentData()
        config_manager.set("voice", "mic_device_index", mic_idx, auto_save=False)

        # Safety
        config_manager.set("safety", "require_confirm_dangerous", self.chk_confirm_dangerous.isChecked(), auto_save=False)
        config_manager.set("safety", "allow_shell_commands", self.chk_allow_shell.isChecked(), auto_save=False)
        config_manager.set("safety", "allow_file_deletion", self.chk_allow_file_delete.isChecked(), auto_save=False)
        config_manager.set("safety", "allow_browser_automation", self.chk_allow_browser.isChecked(), auto_save=False)
        config_manager.set("safety", "allow_keyboard_mouse", self.chk_allow_input.isChecked(), auto_save=False)

        # Commit to disk
        success = config_manager.save()
        if not success:
            err = config_manager.last_error or "Failed to write configuration file."
            QMessageBox.critical(self, "Configuration Save Error", f"Could not save settings:\n{err}")
            return

        self.settings_saved.emit()
        self.accept()
