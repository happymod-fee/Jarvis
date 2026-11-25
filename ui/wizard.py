"""
First-Run Setup Wizard for VAX.
Streamlines initial setup in 3 dead-simple steps:
1. Paste API Key & Choose AI Provider (with auto-detection)
2. Choose Wake Word & Spoken Language
3. Quick Microphone & Audio Check -> Launch!
"""

import sys
import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QWizard,
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QProgressBar,
)

from vax.config import (
    config_manager,
    auto_detect_provider,
    set_api_key,
    DEFAULT_MODELS,
)
from vax.ui.styles import DARK_THEME_QSS
from vax.voice.tts import tts_engine
from vax.voice.recorder import list_input_devices

logger = logging.getLogger("VAX.UI.Wizard")


class ProviderPage(QWizardPage):
    """Step 1: AI Provider & API Key."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 1: Connect your AI Provider")
        self.setSubTitle("Paste your API key below. VAX will automatically detect the provider.")

        layout = QFormLayout(self)
        layout.setSpacing(14)

        self.in_key = QLineEdit(self)
        self.in_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_key.setPlaceholderText("Paste your OpenAI, Groq, Anthropic, or Gemini API key...")
        self.in_key.textChanged.connect(self._on_key_changed)

        self.combo_provider = QComboBox(self)
        self.combo_provider.addItems([
            "groq",
            "openai",
            "gemini",
            "anthropic",
            "deepseek",
            "openrouter",
            "ollama",
            "custom",
        ])

        self.lbl_detection = QLabel("Tip: Groq or OpenAI GPT-4o recommended for fastest response.", self)
        self.lbl_detection.setStyleSheet("color: #38bdf8; font-size: 11px;")

        layout.addRow("API Key:", self.in_key)
        layout.addRow("AI Provider:", self.combo_provider)
        layout.addRow("", self.lbl_detection)

        self.registerField("api_key*", self.in_key)

    def _on_key_changed(self, text: str):
        detected = auto_detect_provider(text)
        if detected != "custom":
            idx = self.combo_provider.findText(detected)
            if idx >= 0:
                self.combo_provider.setCurrentIndex(idx)
                self.lbl_detection.setText(f"✨ Auto-detected provider: <b>{detected.upper()}</b>")


class WakeWordPage(QWizardPage):
    """Step 2: Wake Word & Language."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 2: Choose your Wake Word & Language")
        self.setSubTitle("Tell VAX how you want to summon it and which languages you speak.")

        layout = QFormLayout(self)
        layout.setSpacing(14)

        self.in_wake_word = QLineEdit(self)
        self.in_wake_word.setText("hey jarvis")

        self.combo_language = QComboBox(self)
        self.combo_language.addItems([
            "auto (Bangla + English + Banglish)",
            "bn-BD (Bangla Priority)",
            "en-US (English Priority)",
        ])

        info = QLabel(
            "Push-to-talk fallback: You can also summon VAX anytime using <b>Ctrl+Space</b>.",
            self,
        )
        info.setStyleSheet("color: #94a3b8; font-size: 11px;")

        layout.addRow("Wake Word Phrase:", self.in_wake_word)
        layout.addRow("Spoken Language:", self.combo_language)
        layout.addRow("", info)

        self.registerField("wake_word", self.in_wake_word)


class MicTestPage(QWizardPage):
    """Step 3: Quick Audio & Microphone Test."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 3: Audio Verification")
        self.setSubTitle("Ensure your speakers and microphone are working properly.")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        self.combo_mic = QComboBox(self)
        self.combo_mic.addItem("Default System Microphone", None)
        devices = list_input_devices()
        for d in devices:
            self.combo_mic.addItem(f"[{d['index']}] {d['name']}", d["index"])

        btn_test_voice = QPushButton("🔊 Play Test Greeting (Bangla & English)", self)
        btn_test_voice.clicked.connect(self._play_test_voice)

        layout.addWidget(QLabel("Select Microphone:"))
        layout.addWidget(self.combo_mic)
        layout.addSpacing(10)
        layout.addWidget(btn_test_voice)
        layout.addStretch()

    def _play_test_voice(self):
        tts_engine.speak("নমস্কার! VAX সেটআপ প্রায় সম্পন্ন। Everything is ready to go.")


class FirstRunWizard(QWizard):
    """
    3-step first run wizard.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to VAX Voice Assistant")
        self.resize(520, 420)
        self.setStyleSheet(DARK_THEME_QSS)

        self.page_provider = ProviderPage(self)
        self.page_wake = WakeWordPage(self)
        self.page_audio = MicTestPage(self)

        self.addPage(self.page_provider)
        self.addPage(self.page_wake)
        self.addPage(self.page_audio)

    def accept(self):
        # Save configured values
        prov = self.page_provider.combo_provider.currentText().lower()
        key = self.page_provider.in_key.text().strip()
        wake = self.page_wake.in_wake_word.text().strip().lower()
        mic_idx = self.page_audio.combo_mic.currentData()

        config_manager.set("provider", "provider", prov, auto_save=False)
        config_manager.set("provider", "model", DEFAULT_MODELS.get(prov, "default-model"), auto_save=False)
        set_api_key(prov, key)

        config_manager.set("general", "wake_word", wake, auto_save=False)
        config_manager.set("general", "first_run_completed", True, auto_save=False)
        config_manager.set("voice", "mic_device_index", mic_idx, auto_save=False)

        config_manager.save()
        logger.info("First run wizard completed successfully.")
        super().accept()
