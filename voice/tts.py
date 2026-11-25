"""
Text-to-Speech (TTS) Engine for VAX.
Uses Microsoft Edge TTS for crystal-clear, free Bangla (bn-BD-NabanitaNeural) and English voice acting.
Supports instant speech interruption, phrase caching, offline pyttsx3 fallback, and deadlock-free playback.
"""

import os
import re
import io
import time
import hashlib
import asyncio
import threading
import logging
from pathlib import Path
from typing import Optional, Callable
import soundfile as sf
import sounddevice as sd

from vax.config import config_manager, get_vax_dir

logger = logging.getLogger("VAX.Voice.TTS")

DEFAULT_BANGLA_VOICE = "bn-BD-NabanitaNeural"
DEFAULT_ENGLISH_VOICE = "en-US-JennyNeural"


def get_cache_dir() -> Path:
    cache_d = get_vax_dir() / "tts_cache"
    cache_d.mkdir(parents=True, exist_ok=True)
    return cache_d


def clean_text_for_speech(text: str) -> str:
    """Strips markdown, URLs, code fences, and emojis for natural speech."""
    if not text:
        return ""
    # Remove fallback header tags like [Answered via fallback: Groq]
    cleaned = re.sub(r"\[Answered via fallback:[^\]]+\]\s*", "", text)
    # Remove code blocks
    cleaned = re.sub(r"```[\s\S]*?```", "code block omitted", cleaned)
    # Remove URLs
    cleaned = re.sub(r"https?://\S+", "link", cleaned)
    # Remove markdown bold/italics
    cleaned = re.sub(r"[*_`#~|]", "", cleaned)
    # Remove bullet markers
    cleaned = re.sub(r"^\s*[-•*]\s+", "", cleaned, flags=re.MULTILINE)
    # Strip emojis & pictographs so Edge-TTS never rejects symbol-only fragments
    cleaned = re.sub(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\uFE0F\u200D]+",
        " ",
        cleaned,
    )
    # Collapse whitespace
    cleaned = " ".join(cleaned.split())
    return cleaned


def contains_bangla(text: str) -> bool:
    """Checks if text contains Bengali Unicode characters (\u0980-\u09FF)."""
    return any("\u0980" <= c <= "\u09ff" for c in text)


class TextToSpeechEngine:
    """
    Manages speech synthesis and interruptible audio playback.
    """
    def __init__(self):
        self._is_speaking = False
        self._playback_active = False
        self._stop_requested = False
        self._generation_id = 0
        self._lock = threading.RLock()
        self._volume = float(config_manager.get("voice", "volume", 80)) / 100.0

    def is_speaking(self) -> bool:
        return self._is_speaking

    def is_playback_active(self) -> bool:
        return self._playback_active

    def set_volume(self, volume: float):
        """Set playback volume (0.0 – 1.0). Applies to next speech utterance."""
        self._volume = max(0.0, min(1.0, float(volume)))
        logger.debug("TTS volume set to %.0f%%", self._volume * 100)

    def _stop_playback_unlocked(self):
        """Stops active sounddevice output without acquiring lock."""
        self._stop_requested = True
        self._playback_active = False
        try:
            sd.stop()
        except Exception:
            pass
        self._is_speaking = False

    def stop(self):
        """Immediately interrupts any ongoing speech playback."""
        with self._lock:
            self._generation_id += 1
            self._stop_playback_unlocked()
        logger.info("TTS playback interrupted.")

    async def _synthesize_edge_tts(self, text: str, voice: str, rate: str) -> bytes:
        """Synthesizes speech using edge-tts async API with timeout protection."""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice, rate=rate)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if self._stop_requested:
                break
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
        return audio_stream.getvalue()

    def _speak_pyttsx3_fallback(self, text: str):
        """Offline TTS fallback using pyttsx3 with Windows COM thread safety."""
        com_inited = False
        try:
            if os.name == "nt":
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                    com_inited = True
                except Exception:
                    pass
            import pyttsx3
            engine = pyttsx3.init()
            try:
                engine.setProperty("volume", self._volume)
            except Exception:
                pass
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.debug("Offline pyttsx3 fallback failed: %s", e)
        finally:
            if com_inited:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def speak(self, text: str, blocking: bool = False, on_complete: Optional[Callable[[], None]] = None):
        """
        Synthesizes and speaks text asynchronously (or blocking).
        Always invokes on_complete when finished (unless superseded by a newer speak call).
        """
        clean_prompt = clean_text_for_speech(text)
        if not clean_prompt:
            if on_complete:
                try:
                    on_complete()
                except Exception:
                    pass
            return

        with self._lock:
            self._stop_playback_unlocked()
            self._generation_id += 1
            my_gen_id = self._generation_id
            self._stop_requested = False
            self._is_speaking = True

        thread = threading.Thread(
            target=self._speak_worker,
            args=(clean_prompt, my_gen_id, on_complete),
            daemon=True,
            name="TTSWorker",
        )
        thread.start()
        if blocking:
            thread.join()

    def _speak_worker(self, text: str, gen_id: int, on_complete: Optional[Callable[[], None]] = None):
        try:
            if self._stop_requested or gen_id != self._generation_id:
                return

            engine_choice = config_manager.get("voice", "tts_engine", "edge-tts").lower().strip()
            if engine_choice == "pyttsx3":
                self._speak_pyttsx3_fallback(text)
                return

            # 1. Voice selection: Bangla or English
            configured_voice = config_manager.get("voice", "tts_voice")
            if not configured_voice or configured_voice == "auto":
                voice = DEFAULT_BANGLA_VOICE if contains_bangla(text) else DEFAULT_ENGLISH_VOICE
            else:
                voice = configured_voice

            rate = config_manager.get("voice", "tts_rate", "+0%")

            # 2. Check disk cache
            cache_key = hashlib.md5(f"{text}_{voice}_{rate}".encode("utf-8")).hexdigest()
            cache_file = get_cache_dir() / f"{cache_key}.mp3"

            mp3_bytes = None
            if cache_file.exists():
                try:
                    mp3_bytes = cache_file.read_bytes()
                except Exception:
                    mp3_bytes = None

            if not mp3_bytes:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    mp3_bytes = loop.run_until_complete(
                        asyncio.wait_for(self._synthesize_edge_tts(text, voice, rate), timeout=8.0)
                    )
                except Exception as synth_err:
                    logger.warning("Edge-TTS synthesis failed (%s), falling back to pyttsx3.", synth_err)
                    mp3_bytes = None
                finally:
                    loop.close()

                # Cache if short phrase (< 120 chars)
                if len(text) < 120 and mp3_bytes:
                    try:
                        cache_file.write_bytes(mp3_bytes)
                    except Exception:
                        pass

            if self._stop_requested or gen_id != self._generation_id:
                return

            if not mp3_bytes:
                self._playback_active = True
                self._speak_pyttsx3_fallback(text)
                self._playback_active = False
                return

            # 3. Decode MP3 and play via sounddevice
            audio_io = io.BytesIO(mp3_bytes)
            data, samplerate = sf.read(audio_io, dtype="float32")

            # Apply volume scaling
            data = data * self._volume

            if self._stop_requested or gen_id != self._generation_id:
                return

            self._playback_active = True
            sd.play(data, samplerate)
            # Monitor playback for interruption with tight safety timeout
            audio_duration = len(data) / max(samplerate, 1)
            max_wait = audio_duration + 0.6
            start_play = time.time()
            while time.time() - start_play < max_wait:
                if self._stop_requested or gen_id != self._generation_id:
                    try:
                        sd.stop()
                    except Exception:
                        pass
                    break
                try:
                    stream = sd.get_stream()
                    if not stream or not stream.active:
                        break
                except Exception:
                    break
                time.sleep(0.03)

        except Exception as e:
            logger.error("TTS playback error: %s", e)
        finally:
            self._playback_active = False
            should_notify = False
            with self._lock:
                if gen_id == self._generation_id:
                    self._is_speaking = False
                    should_notify = not self._stop_requested

            if on_complete and should_notify:
                try:
                    on_complete()
                except Exception as cb_err:
                    logger.debug("TTS on_complete callback error: %s", cb_err)


tts_engine = TextToSpeechEngine()
