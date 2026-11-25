"""
Wake Word Detection Engine & Global Hotkey for VAX.
Uses openWakeWord (Hey Jarvis) with thread-safe audio dispatch,
universal Push-to-Talk (Ctrl+Space) fallback, and system beep cues.
"""

import sys
import time
import threading
import logging
from typing import Callable, Optional
import numpy as np

from vax.config import config_manager
from vax.voice.recorder import AudioRecorder

logger = logging.getLogger("VAX.Voice.WakeWord")


def play_wake_beep():
    """Plays an instant audio cue when wake word or push-to-talk triggers."""
    try:
        if sys.platform == "win32":
            import winsound
            winsound.Beep(1000, 140)  # 1000 Hz, 140ms
        else:
            # Fallback simple tone via terminal or bell
            print("\a", end="", flush=True)
    except Exception as e:
        logger.debug("Beep failed: %s", e)


class WakeWordEngine:
    """
    Background worker that monitors audio stream for the wake word,
    and registers global hotkey triggers.
    """
    def __init__(
        self,
        recorder: AudioRecorder,
        wake_word: str = "hey jarvis",
        sensitivity: float = 0.5,
        on_wake_detected: Optional[Callable[[], None]] = None,
        on_emergency_stop: Optional[Callable[[], None]] = None,
    ):
        self.recorder = recorder
        self.wake_word = wake_word.lower().strip()
        self.sensitivity = sensitivity
        self.on_wake_detected = on_wake_detected
        self.on_emergency_stop = on_emergency_stop

        self.oww_model = None
        self._is_running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._hotkey_registered = False

    def pause(self):
        """Pauses wake word listening to yield microphone buffer to speech capture."""
        self._paused = True
        logger.debug("WakeWordEngine paused.")

    def resume(self):
        """Resumes wake word listening when assistant returns to IDLE, clearing stale frames."""
        try:
            self.recorder.clear_queue()
        except Exception:
            pass
        if self.oww_model is not None:
            try:
                self.oww_model.reset()
            except Exception:
                pass
        self._paused = False
        logger.debug("WakeWordEngine resumed.")

    def update_config(self, wake_word: Optional[str] = None, sensitivity: Optional[float] = None):
        """Updates wake word configuration dynamically."""
        if wake_word is not None:
            self.wake_word = wake_word.lower().strip()
        if sensitivity is not None:
            self.sensitivity = sensitivity

    def _init_openwakeword(self):
        """Initializes openWakeWord ONNX inference engine."""
        try:
            import openwakeword
            from openwakeword.model import Model

            # Check if models exist, otherwise download
            try:
                self.oww_model = Model(
                    wakeword_models=["hey jarvis"],
                    inference_framework="onnx",
                )
                logger.info("Loaded openWakeWord ONNX model: 'hey jarvis'")
            except Exception as e:
                logger.warning("Could not load local onnx model, attempting download: %s", e)
                import openwakeword.utils
                openwakeword.utils.download_models(["hey_jarvis"])
                self.oww_model = Model(
                    wakeword_models=["hey jarvis"],
                    inference_framework="onnx",
                )
                logger.info("Downloaded and loaded openWakeWord model successfully.")
        except Exception as e:
            logger.error("Failed to initialize openWakeWord: %s. Push-to-Talk hotkey will remain active.", e)
            self.oww_model = None

    def _register_hotkeys(self):
        """Registers global Push-to-Talk and Emergency Stop hotkeys."""
        try:
            import keyboard
            ptt_key = config_manager.get("general", "hotkey", "ctrl+space")
            estop_key = config_manager.get("general", "emergency_stop_hotkey", "ctrl+alt+esc")

            # Push to talk
            keyboard.add_hotkey(ptt_key, self._on_push_to_talk, suppress=False)

            # Emergency Stop
            keyboard.add_hotkey(estop_key, self._on_emergency_stop_triggered, suppress=False)

            self._hotkey_registered = True
            logger.info("Registered global hotkeys: PTT=%s, EmergencyStop=%s", ptt_key, estop_key)
        except Exception as e:
            logger.warning("Failed to register global hotkeys: %s", e)

    def _on_push_to_talk(self):
        logger.info("Push-to-Talk hotkey triggered!")
        play_wake_beep()
        self.pause()
        if self.on_wake_detected:
            self.on_wake_detected()

    def _on_emergency_stop_triggered(self):
        logger.warning("Global Emergency Stop hotkey pressed!")
        if self.on_emergency_stop:
            self.on_emergency_stop()

    def _run_loop(self):
        logger.info("Wake word detection loop running...")
        while self._is_running:
            if self._paused or not self.recorder.is_available:
                time.sleep(0.1)
                continue

            if self.oww_model is None:
                self._init_openwakeword()
                if self.oww_model is None:
                    time.sleep(0.25)
                    continue

            chunk = self.recorder.read_frame(timeout=0.2)
            if chunk is None:
                continue

            if self.oww_model is not None:
                try:
                    # openWakeWord expects 16-bit PCM numpy array
                    predictions = self.oww_model.predict(chunk)
                    for mdl_name, score in predictions.items():
                        if score >= self.sensitivity:
                            logger.info("Wake word detected! Score: %.2f on %s", score, mdl_name)
                            play_wake_beep()
                            # Immediately pause wake listening and reset model state so VAD has clean mic access
                            self.pause()
                            try:
                                self.oww_model.reset()
                            except Exception:
                                pass
                            if self.on_wake_detected:
                                self.on_wake_detected()
                            break
                except Exception as e:
                    logger.debug("Prediction error: %s", e)
            else:
                # If no wake word model available, idle smoothly with tiny sleep
                time.sleep(0.05)

    def start(self):
        if self._is_running:
            return

        self._register_hotkeys()
        if self.recorder.is_available:
            self._init_openwakeword()
        else:
            logger.warning("Microphone unavailable; openWakeWord skipped until mic is connected.")
        self._is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="WakeWordLoop")
        self._thread.start()

    def stop(self):
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._hotkey_registered:
            try:
                import keyboard
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
            self._hotkey_registered = False
