"""
VAX Desktop Voice Assistant — Main Application Entry Point.
Coordinates PySide6 GUI, background voice pipeline (Wake Word + VAD + STT + TTS),
agent execution loop, and text-only CLI mode.
"""

import sys
import os
import time
import types
import asyncio
import threading
import logging
import importlib.util
from typing import Optional

# Setup standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("VAX.Main")

# Ensure vax package works regardless of whether repo folder is named 'vax' or 'Jarvis'
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if "vax" not in sys.modules:
    try:
        _vax_spec = importlib.util.find_spec("vax")
    except ValueError:
        _vax_spec = None
    if _vax_spec is None:
        import importlib.machinery
        _vax_pkg = types.ModuleType("vax")
        _vax_pkg.__path__ = [CURRENT_DIR]
        _vax_pkg.__file__ = os.path.join(CURRENT_DIR, "__init__.py")
        _vax_pkg.__spec__ = importlib.machinery.ModuleSpec("vax", None, is_package=True)
        sys.modules["vax"] = _vax_pkg

from vax.config import config_manager
from vax.agent import AgentBrain
from vax.providers import create_provider
from vax.plugins import load_all_plugins
from vax.voice.recorder import AudioRecorder
from vax.voice.vad import VoiceActivityDetector
from vax.voice.wake_word import WakeWordEngine
from vax.voice.stt import stt_engine
from vax.voice.tts import tts_engine


class AsyncWorkerThread(threading.Thread):
    """
    Dedicated worker thread hosting an asyncio event loop for running agent tool pipelines.
    """
    def __init__(self):
        super().__init__(daemon=True, name="AsyncAgentWorker")
        self.loop = asyncio.new_event_loop()
        self._is_ready = threading.Event()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self._is_ready.set()
        self.loop.run_forever()

    def wait_until_ready(self):
        self._is_ready.wait()

    def run_coroutine(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


def run_cli_mode():
    """
    Text-only interactive CLI mode for terminal usage and automated testing.
    """
    print("\n" + "=" * 60)
    print("🤖 VAX VOICE ASSISTANT — TEXT CLI MODE")
    print("Type your commands in Bangla, English, or Banglish.")
    print("Type 'exit' or 'quit' to close. Press Ctrl+C to abort.")
    print("=" * 60 + "\n")

    load_all_plugins()
    brain = AgentBrain()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            user_input = input("\nYou > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting VAX CLI. Goodbye!")
                break

            print("VAX (thinking)...")

            def on_step(step_type, msg):
                if step_type == "action":
                    print(f"  [Tool Action] -> {msg}")
                elif step_type == "action_result":
                    print(f"  [Tool Output] -> {msg}")

            reply = loop.run_until_complete(
                brain.run_command(user_input, on_step_update=on_step)
            )
            print(f"\nVAX > {reply}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting VAX CLI.")
            break
        except Exception as e:
            print(f"\nError: {e}")


def run_gui_mode():
    """
    Full Desktop GUI Mode with Floating Orb HUD and System Tray.
    """
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QObject, Signal, Slot
    from vax.ui.mini_window import MiniWindow
    from vax.ui.tray import TrayIconManager
    from vax.ui.settings import SettingsDialog
    from vax.ui.wizard import FirstRunWizard
    from vax.ui.log_viewer import LogViewerDialog

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    load_all_plugins()

    # Check if first run wizard is needed
    if not config_manager.get("general", "first_run_completed", False):
        wizard = FirstRunWizard()
        if wizard.exec() != FirstRunWizard.Accepted:
            logger.info("First-run wizard cancelled by user. Exiting.")
            return

    # Start Async Worker Thread
    async_worker = AsyncWorkerThread()
    async_worker.start()
    async_worker.wait_until_ready()

    # Initialize Agent Brain
    brain = AgentBrain()

    # GUI Components
    mini_win = MiniWindow()
    tray_mgr = TrayIconManager()
    settings_dlg = SettingsDialog()
    log_dlg = LogViewerDialog()

    mini_win.show()

    # Audio & Voice Components
    mic_idx = config_manager.get("voice", "mic_device_index")
    recorder = AudioRecorder(device_index=mic_idx)
    is_turbo = bool(config_manager.get("general", "turbo_mode", False))
    vad = VoiceActivityDetector(silence_threshold_sec=1.1 if is_turbo else 1.8)
    wake_engine = None

    # Signal Bridge for Cross-Thread UI Updates
    class UISignalBridge(QObject):
        transcript_signal = Signal(str, str, str)  # sender, text, color
        mic_status_signal = Signal(bool, str)
        state_listening = Signal()
        state_followup_listening = Signal()
        state_thinking = Signal(str)
        state_speaking = Signal()
        state_idle = Signal()

    bridge = UISignalBridge()
    bridge.transcript_signal.connect(mini_win.append_transcript)
    bridge.mic_status_signal.connect(mini_win.set_microphone_status)
    bridge.state_listening.connect(lambda: mini_win.set_state_listening(is_followup=False))
    bridge.state_followup_listening.connect(lambda: mini_win.set_state_listening(is_followup=True))
    bridge.state_thinking.connect(mini_win.set_state_thinking)
    bridge.state_speaking.connect(mini_win.set_state_speaking)

    def on_idle_state():
        mini_win.set_state_idle()
        if wake_engine is not None and not mini_win.is_mic_muted():
            wake_engine.resume()

    bridge.state_idle.connect(on_idle_state)

    _STOP_CONVERSATION_PHRASES = {
        "stop", "cancel", "bye", "goodbye", "exit", "quit",
        "thamo", "bondho koro", "ruk ja", "thank you", "thanks", "dhonnobad",
    }

    # Core Execution Routine
    def execute_user_query(text: str, from_voice: bool = False):
        bridge.state_thinking.emit("Processing command...")

        def on_step(step_type, message):
            if step_type == "action":
                bridge.transcript_signal.emit("Action", message, "#fbbf24")
            elif step_type == "action_result":
                bridge.transcript_signal.emit("Result", message, "#94a3b8")

        future = async_worker.run_coroutine(
            brain.run_command(text, on_step_update=on_step)
        )

        def on_done(fut):
            try:
                try:
                    reply = fut.result()
                except Exception as e:
                    reply = f"Error: {e}"

                reply_str = str(reply)
                if reply_str.startswith("Error:"):
                    bridge.transcript_signal.emit("Error", reply_str[6:].strip(), "#f87171")
                else:
                    bridge.transcript_signal.emit("VAX", reply_str, "#34d399")
                bridge.state_speaking.emit()

                clean_q = text.strip().lower().rstrip(".!?")
                should_followup = (
                    from_voice
                    and bool(config_manager.get("general", "continuous_conversation", True))
                    and not mini_win.is_mic_muted()
                    and recorder.is_available
                    and clean_q not in _STOP_CONVERSATION_PHRASES
                    and not brain._cancel_requested
                )

                def on_tts_finished():
                    if should_followup and not mini_win.is_mic_muted():
                        def start_followup():
                            time.sleep(0.28)  # Guard against speaker echo
                            if not _is_capturing.is_set() and not tts_engine.is_speaking() and not mini_win.is_mic_muted():
                                on_voice_wake_triggered(is_followup=True)
                        threading.Thread(target=start_followup, daemon=True, name="FollowUpTrigger").start()
                    else:
                        bridge.state_idle.emit()

                # Vocalize reply via TTS with follow-up or idle callback
                tts_engine.speak(reply_str, on_complete=on_tts_finished)

                # Hands-free Voice Barge-In monitor: interrupts VAX mid-speech if user starts speaking
                if (
                    bool(config_manager.get("voice", "barge_in_enabled", True))
                    and recorder.is_available
                    and not mini_win.is_mic_muted()
                ):
                    def barge_in_monitor():
                        time.sleep(0.22)  # Avoid click/transient at start
                        recorder.clear_queue()
                        playback_started_at: Optional[float] = None
                        echo_peak = 0.0
                        consec_frames = 0
                        pre_frames = []

                        while tts_engine.is_speaking() and not _is_capturing.is_set() and not mini_win.is_mic_muted():
                            chunk = recorder.read_frame(timeout=0.08)
                            if chunk is None:
                                continue

                            energy = vad.compute_energy(chunk)
                            is_playing = tts_engine.is_playback_active()

                            if is_playing:
                                now = time.time()
                                if playback_started_at is None:
                                    playback_started_at = now
                                    echo_peak = 0.0
                                    consec_frames = 0
                                    pre_frames.clear()

                                # First 0.30s of playback: calibrate speaker bleed into mic
                                if now - playback_started_at < 0.30:
                                    echo_peak = max(echo_peak, min(energy, 900.0))
                                    continue

                                thr = max(420.0, vad.noise_floor * 3.0, echo_peak * 1.65)
                            else:
                                # Still synthesizing (silent speaker) -> very responsive barge-in
                                playback_started_at = None
                                thr = max(230.0, vad.noise_floor * 2.2)

                            if energy > thr:
                                consec_frames += 1
                                pre_frames.append(chunk)
                                if consec_frames >= 3:
                                    logger.info(
                                        "Voice barge-in detected (energy=%.1f > thr=%.1f)! Interrupting TTS.",
                                        energy,
                                        thr,
                                    )
                                    tts_engine.stop()
                                    on_voice_wake_triggered(is_followup=True, initial_frames=pre_frames)
                                    return
                            else:
                                consec_frames = 0
                                pre_frames.clear()

                    threading.Thread(target=barge_in_monitor, daemon=True, name="BargeInMonitor").start()
            except Exception as top_err:
                logger.error("Error in on_done callback: %s", top_err)
                bridge.state_idle.emit()

        future.add_done_callback(on_done)

    # Voice Activation Routine
    _is_capturing = threading.Event()

    def on_voice_wake_triggered(is_followup: bool = False, initial_frames=None):
        if mini_win.is_mic_muted():
            logger.debug("Mic is muted; ignoring wake/PTT trigger.")
            return
        if _is_capturing.is_set():
            logger.debug("Speech capture already in progress. Ignoring duplicate trigger.")
            return

        # Allow instant interruption (barge-in) if user triggers PTT/Wake while TTS is playing
        if tts_engine.is_speaking():
            tts_engine.stop()

        # If microphone was missing earlier, try auto-detecting again on PTT/Wake
        if not recorder.is_available:
            try:
                recorder.start()
                bridge.mic_status_signal.emit(True, recorder.active_device_name)
            except Exception as mic_err:
                err_txt = str(mic_err) or "No microphone detected on this PC."
                bridge.mic_status_signal.emit(False, err_txt)
                bridge.transcript_signal.emit(
                    "Error",
                    f"Microphone nei / pawa jayni ({err_txt}). Doya kore mic connect korun ba niche type korun.",
                    "#f87171",
                )
                bridge.state_idle.emit()
                return

        _is_capturing.set()
        if wake_engine is not None:
            wake_engine.pause()
        logger.info("%s trigger fired! Starting speech capture...", "Follow-up" if is_followup else "Wake")
        if is_followup:
            bridge.state_followup_listening.emit()
        else:
            bridge.state_listening.emit()

        def capture_and_process():
            try:
                if not initial_frames:
                    time.sleep(0.10)
                    recorder.clear_queue()
                wav_data = vad.record_until_silence(
                    recorder,
                    max_duration_sec=25.0,
                    onset_timeout_sec=6.5 if is_followup else 10.0,
                    initial_frames=initial_frames,
                )
                if not wav_data:
                    logger.info("No speech detected by VAD (%s).", "follow-up timeout" if is_followup else "wake")
                    if not is_followup:
                        bridge.transcript_signal.emit("System", "Kono kotha shona jayni (No speech detected).", "#94a3b8")
                    bridge.state_idle.emit()
                    return

                bridge.state_thinking.emit("Transcribing voice...")
                transcript = stt_engine.transcribe(wav_data)

                if transcript:
                    bridge.transcript_signal.emit("You (Voice)", transcript, "#38bdf8")
                    execute_user_query(transcript, from_voice=True)
                else:
                    logger.info("STT returned empty transcript.")
                    if not is_followup:
                        bridge.transcript_signal.emit(
                            "Warning",
                            "Voice bujhte parini (STT empty/API busy). Abar bolun ba text korun.",
                            "#fbbf24",
                        )
                    bridge.state_idle.emit()
            except Exception as e:
                logger.error("Error in speech capture: %s", e)
                bridge.transcript_signal.emit("Error", f"Speech capture failed: {e}", "#f87171")
                bridge.state_idle.emit()
            finally:
                _is_capturing.clear()

        threading.Thread(target=capture_and_process, daemon=True, name="SpeechCaptureThread").start()

    # Emergency Stop Routine
    def on_emergency_stop():
        logger.warning("Emergency Stop requested!")
        _is_capturing.clear()
        brain.request_cancel()
        tts_engine.stop()
        bridge.transcript_signal.emit("System", "Emergency Stop Executed.", "#ef4444")
        bridge.state_idle.emit()

    # Wake Word Background Engine
    wake_engine = WakeWordEngine(
        recorder=recorder,
        wake_word=config_manager.get("general", "wake_word", "hey jarvis"),
        sensitivity=config_manager.get("voice", "wake_sensitivity", 0.5),
        on_wake_detected=on_voice_wake_triggered,
        on_emergency_stop=on_emergency_stop,
    )

    if not mini_win.is_mic_muted():
        try:
            recorder.start()
            mini_win.set_microphone_status(True, recorder.active_device_name)
        except Exception as e:
            logger.error("Failed to start audio recording: %s", e)
            mini_win.set_microphone_status(False, str(e))
            mini_win.append_transcript(
                "Error",
                f"Microphone chalu hoyni: {e}. Doya kore microphone connect korun ba text-e command din.",
                "#f87171",
            )
            mini_win.set_state_idle()
    else:
        tray_mgr.set_listening_status(False)

    try:
        wake_engine.start()
        if mini_win.is_mic_muted():
            wake_engine.pause()
    except Exception as e:
        logger.error("Failed to start wake/hotkey engine: %s", e)
        mini_win.append_transcript("Warning", f"Global hotkey/wake engine error: {e}", "#fbbf24")

    # Connect UI Events
    mini_win.command_submitted.connect(lambda txt: execute_user_query(txt, from_voice=False))
    mini_win.emergency_stop_clicked.connect(on_emergency_stop)
    mini_win.settings_requested.connect(settings_dlg.show)
    mini_win.logs_requested.connect(log_dlg.show)
    mini_win.ptt_clicked.connect(lambda: on_voice_wake_triggered(is_followup=False))
    mini_win.clear_memory_requested.connect(brain.memory.clear_history)
    mini_win.turbo_toggled.connect(lambda t: setattr(vad, "silence_threshold_sec", 1.1 if t else 1.8))

    # --- NEW: Mic mute toggle from MiniWindow header ---
    def on_mic_mute_toggled(muted: bool):
        try:
            if muted:
                wake_engine.pause()
                recorder.stop()
                tray_mgr.set_listening_status(False)
                logger.info("Microphone muted by user.")
            else:
                recorder.start()
                wake_engine.resume()
                tray_mgr.set_listening_status(True)
                available = recorder.is_available
                detail = recorder.active_device_name or ("No mic" if not available else "")
                mini_win.set_microphone_status(available, detail)
                logger.info("Microphone unmuted. Device: %s", detail)
        except Exception as e:
            logger.error("Error toggling mic mute: %s", e)
            mini_win.append_transcript("Error", f"Mic toggle failed: {e}", "#f87171")

    mini_win.mic_mute_toggled.connect(on_mic_mute_toggled)

    # --- NEW: Volume slider → TTS engine ---
    def on_volume_changed(value: int):
        try:
            tts_engine.set_volume(value / 100.0)
        except Exception:
            pass  # TTS may not support set_volume, silently ignore

    mini_win.volume_changed.connect(on_volume_changed)

    tray_mgr.show_window_requested.connect(mini_win.show)
    tray_mgr.settings_requested.connect(settings_dlg.show)
    tray_mgr.logs_requested.connect(log_dlg.show)
    tray_mgr.quit_requested.connect(app.quit)

    def on_toggle_listening():
        mini_win.set_mic_muted(not mini_win.is_mic_muted())

    tray_mgr.toggle_listening_requested.connect(on_toggle_listening)

    def on_settings_saved():
        # Reload primary/fallback providers, turbo state, and wake word config
        brain.reload_providers()
        is_turbo = bool(config_manager.get("general", "turbo_mode", False))
        vad.silence_threshold_sec = 1.1 if is_turbo else 1.8
        mini_win.sync_turbo_ui(is_turbo)
        if wake_engine is not None:
            wake_engine.update_config(
                wake_word=config_manager.get("general", "wake_word", "hey jarvis"),
                sensitivity=config_manager.get("voice", "wake_sensitivity", 0.5),
            )
        logger.info("Settings reloaded into runtime agent.")

    settings_dlg.settings_saved.connect(on_settings_saved)

    logger.info("VAX Voice Assistant is now running.")
    exit_code = app.exec()

    # Clean shutdown
    tts_engine.stop()
    wake_engine.stop()
    recorder.stop()
    async_worker.loop.call_soon_threadsafe(async_worker.loop.stop)
    sys.exit(exit_code)


def main():
    if "--cli" in sys.argv:
        run_cli_mode()
    else:
        run_gui_mode()


if __name__ == "__main__":
    main()
