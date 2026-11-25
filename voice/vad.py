"""
Voice Activity Detection (VAD) for VAX.
Detects start and end of speech with hysteresis-based adaptive energy thresholding
so natural mid-sentence pauses never prematurely cut off the user's speech,
and exports recorded audio to in-memory WAV for STT transcription.
"""

import io
import time
import wave
import logging
from typing import Optional, List
import numpy as np

logger = logging.getLogger("VAX.Voice.VAD")


class VoiceActivityDetector:
    """
    Robust adaptive VAD with dual-threshold hysteresis for speech onset and offset.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_threshold_sec: float = 1.8,
        speech_pad_sec: float = 0.4,
    ):
        self.sample_rate = sample_rate
        self.silence_threshold_sec = silence_threshold_sec
        self.speech_pad_sec = speech_pad_sec
        self.noise_floor = 120.0  # Baseline RMS energy

    def compute_energy(self, pcm_chunk: np.ndarray) -> float:
        """Calculates Root Mean Square (RMS) energy."""
        if len(pcm_chunk) == 0:
            return 0.0
        return float(np.sqrt(np.mean(pcm_chunk.astype(np.float32) ** 2)))

    def record_until_silence(
        self,
        recorder,
        max_duration_sec: float = 25.0,
        min_speech_sec: float = 0.35,
        onset_timeout_sec: Optional[float] = 10.0,
        initial_frames: Optional[List[np.ndarray]] = None,
    ) -> Optional[bytes]:
        """
        Listens to recorder stream until the user finishes speaking.
        - onset_timeout_sec: maximum time to wait for speech to BEGIN before returning None.
        - silence_threshold_sec: how much continuous silence after speech ends the capture.
        - initial_frames: optional pre-captured speech frames (e.g. from voice barge-in).
        Returns WAV bytes of the utterance, or None if no speech occurred.
        """
        frames = list(initial_frames) if initial_frames else []
        speech_started = bool(initial_frames)
        silence_start_time: Optional[float] = None
        start_time = time.time()

        # Dual-threshold hysteresis: higher to start, lower to sustain across soft syllables
        onset_threshold = max(165.0, self.noise_floor * 2.0)
        sustain_threshold = max(115.0, self.noise_floor * 1.45)

        while True:
            now = time.time()
            elapsed = now - start_time

            if elapsed >= max_duration_sec:
                break
            if not speech_started and onset_timeout_sec is not None and elapsed >= onset_timeout_sec:
                logger.debug("VAD onset timeout reached (%.1fs) without speech.", onset_timeout_sec)
                break
            if not getattr(recorder, "is_available", True):
                logger.debug("Recorder became unavailable during VAD capture.")
                break

            chunk = recorder.read_frame(timeout=0.15)
            if chunk is None:
                continue

            energy = self.compute_energy(chunk)

            # Adapt noise floor only before speech starts, capped to prevent echo spikes
            if not speech_started:
                capped_energy = min(energy, 380.0)
                self.noise_floor = 0.92 * self.noise_floor + 0.08 * capped_energy
                onset_threshold = max(165.0, self.noise_floor * 2.0)
                sustain_threshold = max(115.0, self.noise_floor * 1.45)

            active_threshold = sustain_threshold if speech_started else onset_threshold
            is_voice = energy > active_threshold

            if is_voice:
                if not speech_started:
                    speech_started = True
                    logger.debug(
                        "Speech onset detected (energy: %.1f, onset_thr: %.1f, sustain_thr: %.1f)",
                        energy,
                        onset_threshold,
                        sustain_threshold,
                    )
                silence_start_time = None
                frames.append(chunk)
            else:
                if speech_started:
                    frames.append(chunk)
                    if silence_start_time is None:
                        silence_start_time = time.time()
                    elif time.time() - silence_start_time >= self.silence_threshold_sec:
                        logger.debug(
                            "Speech offset (silence detected for %.2fs)",
                            self.silence_threshold_sec,
                        )
                        break
                else:
                    # Keep ~0.64s rolling pre-roll buffer (8 chunks * 80ms) so first syllable is never cut off
                    frames.append(chunk)
                    if len(frames) > 8:
                        frames.pop(0)

        total_audio = np.concatenate(frames) if frames else np.array([], dtype=np.int16)
        duration = len(total_audio) / self.sample_rate

        if not speech_started or duration < min_speech_sec:
            logger.debug(
                "Discarding audio segment: speech_started=%s, duration=%.2fs",
                speech_started,
                duration,
            )
            return None

        # Convert to WAV bytes
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(total_audio.tobytes())

        wav_bytes = wav_buffer.getvalue()
        logger.info("Captured speech utterance: %.2f seconds (%d bytes)", duration, len(wav_bytes))
        return wav_bytes
