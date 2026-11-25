"""
Speech-to-Text (STT) Engine for VAX.
Supports Google Gemini Audio Transcription, Groq Whisper API (sub-second cloud Whisper),
OpenAI Whisper API, and local offline faster-whisper.
"""

import io
import os
import time
import logging
from typing import Optional
import httpx

from vax.config import config_manager, get_api_key

logger = logging.getLogger("VAX.Voice.STT")


class SpeechToTextEngine:
    """
    Pluggable STT router supporting cloud and local transcription with smart key-aware fallback.
    """
    def __init__(self):
        self._local_model = None

    def _get_active_engine(self) -> str:
        return config_manager.get("voice", "stt_engine", "auto").lower().strip()

    def transcribe(self, wav_bytes: bytes, language: Optional[str] = None) -> str:
        """
        Transcribes WAV audio bytes to text using the best available engine.
        """
        if not wav_bytes or len(wav_bytes) < 1000:
            return ""

        engine = self._get_active_engine()
        lang_setting = language or config_manager.get("general", "language", "auto")
        lang_code = None if lang_setting == "auto" else ("bn" if "bn" in lang_setting else "en")

        logger.info("Transcribing audio using engine: %s (lang: %s)...", engine, lang_code or "auto")

        # 1. Direct engine selection if explicitly requested
        if engine == "gemini":
            return self._transcribe_gemini(wav_bytes, lang_code)
        elif engine == "groq":
            res = self._transcribe_groq(wav_bytes, lang_code)
            if res:
                return res
        elif engine == "openai":
            res = self._transcribe_openai(wav_bytes, lang_code)
            if res:
                return res
        elif engine == "local":
            return self._transcribe_local(wav_bytes, lang_code)

        # 2. Smart Fallback Chain based on whichever API key the user has configured
        gemini_key = get_api_key("gemini")
        if gemini_key:
            logger.info("Using configured Gemini key for Cloud Speech Transcription...")
            res = self._transcribe_gemini(wav_bytes, lang_code)
            if res:
                return res

        groq_key = get_api_key("groq")
        if groq_key:
            res = self._transcribe_groq(wav_bytes, lang_code)
            if res:
                return res

        openai_key = get_api_key("openai")
        if openai_key:
            res = self._transcribe_openai(wav_bytes, lang_code)
            if res:
                return res

        # 3. Ultimate Fallback: Local faster-whisper
        return self._transcribe_local(wav_bytes, lang_code)

    def _transcribe_gemini(self, wav_bytes: bytes, lang_code: Optional[str]) -> str:
        """Cloud transcription via Google Gemini Multimodal Audio."""
        api_key = get_api_key("gemini")
        if not api_key:
            logger.warning("No Gemini API key found for STT.")
            return ""

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
        lang_hint = "in Bengali (Bangla), Banglish, or English" if not lang_code else (
            "in Bengali (Bangla)" if lang_code == "bn" else "in English"
        )
        prompt = (
            f"You are a fast speech-to-text transcriber. Listen to the audio and transcribe the exact words spoken by the human user {lang_hint}.\n"
            "Output ONLY the transcribed words. Do not wrap in quotes or markdown. If there is no speech or only silence/static, output nothing."
        )

        for attempt, delay in enumerate([0.0, 1.0, 2.0]):
            if delay > 0:
                time.sleep(delay)
            try:
                response = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=[part, prompt],
                    config=types.GenerateContentConfig(
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                    ),
                )
                text = (response.text or "").strip()
                # Clean common model artifacts for silence
                if text in ("00:00", "EMPTY", "None", "none", "nothing", "...", "no speech"):
                    text = ""
                if text:
                    logger.info("Gemini STT transcription: '%s'", text)
                return text
            except Exception as e:
                err_str = str(e).lower()
                if ("503" in err_str or "429" in err_str or "unavailable" in err_str) and attempt < 2:
                    logger.warning("Gemini STT temporary spike, retrying (%d)...", attempt + 1)
                    continue
                logger.error("Gemini STT transcription error: %s", e)
                break

        return ""

    def _transcribe_groq(self, wav_bytes: bytes, lang_code: Optional[str]) -> str:
        """Cloud transcription via Groq Whisper API."""
        api_key = get_api_key("groq")
        if not api_key:
            logger.debug("No Groq API key found. Skipping Groq STT.")
            return ""

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "model": "whisper-large-v3",
            "response_format": "json",
            "temperature": "0.0",
        }
        if lang_code:
            data["language"] = lang_code

        files = {
            "file": ("speech.wav", wav_bytes, "audio/wav"),
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, headers=headers, data=data, files=files)
                if res.status_code == 200:
                    result = res.json()
                    text = result.get("text", "").strip()
                    logger.info("Groq STT transcription: '%s'", text)
                    return text
                else:
                    logger.error("Groq STT error %d: %s", res.status_code, res.text)
                    return ""
        except Exception as e:
            logger.error("Groq STT request exception: %s", e)
            return ""

    def _transcribe_openai(self, wav_bytes: bytes, lang_code: Optional[str]) -> str:
        """Cloud transcription via OpenAI Whisper API."""
        api_key = get_api_key("openai")
        if not api_key:
            logger.debug("No OpenAI API key found. Skipping OpenAI STT.")
            return ""

        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "model": "whisper-1",
            "response_format": "json",
        }
        if lang_code:
            data["language"] = lang_code

        files = {"file": ("speech.wav", wav_bytes, "audio/wav")}

        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.post(url, headers=headers, data=data, files=files)
                if res.status_code == 200:
                    text = res.json().get("text", "").strip()
                    logger.info("OpenAI STT transcription: '%s'", text)
                    return text
                else:
                    logger.error("OpenAI STT error %d: %s", res.status_code, res.text)
                    return ""
        except Exception as e:
            logger.error("OpenAI STT exception: %s", e)
            return ""

    def _transcribe_local(self, wav_bytes: bytes, lang_code: Optional[str]) -> str:
        """Local offline transcription via faster-whisper with PyAV metadata_errors compatibility patch."""
        try:
            # Patch PyAV open() if installed av does not support metadata_errors keyword (Python 3.14 compatibility)
            try:
                import av
                if not hasattr(av, "_vax_patched"):
                    _orig_av_open = av.open
                    def _safe_av_open(*args, **kwargs):
                        kwargs.pop("metadata_errors", None)
                        return _orig_av_open(*args, **kwargs)
                    av.open = _safe_av_open
                    av._vax_patched = True
            except Exception:
                pass

            from faster_whisper import WhisperModel

            if self._local_model is None:
                logger.info("Loading local faster-whisper (tiny model for low RAM)...")
                # Use int8 compute on CPU to keep memory under 100MB
                self._local_model = WhisperModel("tiny", device="cpu", compute_type="int8")

            # Feed in-memory buffer
            audio_stream = io.BytesIO(wav_bytes)
            segments, info = self._local_model.transcribe(
                audio_stream,
                language=lang_code,
                beam_size=3,
            )
            text_parts = [s.text.strip() for s in segments]
            text = " ".join(text_parts).strip()
            logger.info("Local STT transcription: '%s'", text)
            return text
        except Exception as e:
            logger.error("Local faster-whisper error: %s", e)
            return ""


stt_engine = SpeechToTextEngine()
