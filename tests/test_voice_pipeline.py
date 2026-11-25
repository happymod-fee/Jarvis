"""
Unit tests for VAX voice pipeline improvements:
- VAD hysteresis and natural pause tolerance
- TTS speech cleaning (emoji/markdown stripping)
"""

import numpy as np
from vax.voice.vad import VoiceActivityDetector
from vax.voice.tts import clean_text_for_speech


class _FakeRecorder:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.is_available = True

    def read_frame(self, timeout=0.15):
        if self._chunks:
            return self._chunks.pop(0)
        return np.zeros(1280, dtype=np.int16)


def test_vad_preserves_mid_sentence_pause():
    # Each chunk = 80ms (1280 samples @ 16kHz)
    speech_chunk = (np.ones(1280, dtype=np.int16) * 900)
    silent_chunk = np.zeros(1280, dtype=np.int16)

    # 5 speech chunks (~0.4s) + 6 silent chunks (~0.48s pause) + 5 speech chunks + 26 silent chunks (>1.8s)
    chunks = (
        [speech_chunk] * 5
        + [silent_chunk] * 6
        + [speech_chunk] * 5
        + [silent_chunk] * 26
    )
    vad = VoiceActivityDetector(silence_threshold_sec=1.8)
    wav = vad.record_until_silence(_FakeRecorder(chunks), max_duration_sec=10.0, onset_timeout_sec=2.0)
    assert wav is not None
    # Both speech halves should be included (> 16 chunks = 1.28s audio > 40KB WAV)
    assert len(wav) > 40000


def test_vad_onset_timeout_returns_none_when_silent():
    silent_chunk = np.zeros(1280, dtype=np.int16)
    rec = _FakeRecorder([silent_chunk] * 20)
    vad = VoiceActivityDetector(silence_threshold_sec=1.8)
    wav = vad.record_until_silence(rec, max_duration_sec=5.0, onset_timeout_sec=0.3)
    assert wav is None


def test_clean_text_for_speech_strips_emojis_and_markdown():
    raw = "🤖 **Chrome** খুলেছি! ✅ `done` https://example.com"
    cleaned = clean_text_for_speech(raw)
    assert "🤖" not in cleaned
    assert "✅" not in cleaned
    assert "**" not in cleaned
    assert "Chrome" in cleaned
    assert "খুলেছি!" in cleaned


def test_vad_preserves_barge_in_initial_frames():
    speech_chunk = (np.ones(1280, dtype=np.int16) * 900)
    silent_chunk = np.zeros(1280, dtype=np.int16)
    pre_frames = [speech_chunk] * 3
    rec = _FakeRecorder([speech_chunk] * 3 + [silent_chunk] * 26)
    vad = VoiceActivityDetector(silence_threshold_sec=1.8)
    wav = vad.record_until_silence(
        rec,
        max_duration_sec=10.0,
        onset_timeout_sec=2.0,
        initial_frames=pre_frames,
    )
    assert wav is not None
    assert len(wav) > 12000


def test_admin_powershell_safety_still_blocks_destructive():
    from vax.safety import safety_engine, RiskLevel
    risk, _ = safety_engine.evaluate("run_admin_powershell", {"command": "format C:"})
    assert risk == RiskLevel.BLOCKED
    risk_ok, _ = safety_engine.evaluate("run_admin_powershell", {"command": "Get-Process"})
    assert risk_ok == RiskLevel.DANGEROUS


def test_vad_energy_callback_emits_normalized_levels():
    speech_chunk = (np.ones(1280, dtype=np.int16) * 900)
    silent_chunk = np.zeros(1280, dtype=np.int16)
    levels = []
    rec = _FakeRecorder([speech_chunk] * 5 + [silent_chunk] * 26)
    vad = VoiceActivityDetector(silence_threshold_sec=1.8)
    wav = vad.record_until_silence(
        rec,
        max_duration_sec=10.0,
        onset_timeout_sec=2.0,
        on_energy_callback=levels.append,
    )
    assert wav is not None
    assert len(levels) > 0
    assert all(0.0 <= lvl <= 1.0 for lvl in levels)
