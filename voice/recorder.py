"""
Microphone Audio Capture for VAX.
Uses sounddevice for robust, crash-free audio streaming at 16kHz mono,
with automatic microphone detection, sample-rate adaptation, and clear error reporting.
"""

import queue
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import sounddevice as sd

logger = logging.getLogger("VAX.Voice.Recorder")

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1280  # 80ms at 16kHz (compatible with openWakeWord and VAD)


class NoMicrophoneError(RuntimeError):
    """Raised when no working microphone input device can be opened."""


def list_input_devices() -> List[Dict[str, Any]]:
    """
    Returns list of available microphone input devices.
    """
    devices = []
    try:
        all_devs = sd.query_devices()
        for idx, dev in enumerate(all_devs):
            if dev.get("max_input_channels", 0) > 0:
                devices.append({
                    "index": idx,
                    "name": dev.get("name", f"Device {idx}"),
                    "channels": dev.get("max_input_channels"),
                    "sample_rate": dev.get("default_samplerate"),
                })
    except Exception as e:
        logger.error("Error querying audio devices: %s", e)
    return devices


class AudioRecorder:
    """
    Continuous audio recording stream delivering 16kHz 16-bit PCM frames.
    Auto-detects working microphones and adapts hardware sample rates if needed.
    """
    def __init__(self, device_index: Optional[int] = None, sample_rate: int = SAMPLE_RATE):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self._hw_sample_rate = sample_rate
        self.queue: queue.Queue = queue.Queue(maxsize=100)
        self.stream: Optional[sd.InputStream] = None
        self._is_running = False
        self.is_available = False
        self.active_device_name: str = ""
        self.last_error: str = ""

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("Audio stream status: %s", status)
        if not self._is_running:
            return

        mono = indata[:, 0]
        # Resample linearly if hardware stream runs at a different rate (e.g. 44100/48000 -> 16000)
        if self._hw_sample_rate != self.sample_rate and len(mono) > 0:
            target_len = max(1, int(round(len(mono) * self.sample_rate / self._hw_sample_rate)))
            x_old = np.linspace(0.0, 1.0, len(mono), endpoint=False)
            x_new = np.linspace(0.0, 1.0, target_len, endpoint=False)
            mono = np.interp(x_new, x_old, mono)

        pcm16 = (mono * 32767).clip(-32768, 32767).astype(np.int16)
        try:
            self.queue.put_nowait(pcm16)
        except queue.Full:
            pass

    def _try_open_device(self, dev_idx: Optional[int], dev_name: str, native_rate: float) -> bool:
        """Attempts to open an InputStream at 16kHz, falling back to native_rate if rejected."""
        rates_to_try = [self.sample_rate]
        if native_rate and int(native_rate) != self.sample_rate:
            rates_to_try.append(int(native_rate))

        for rate in rates_to_try:
            block = max(256, int(round(BLOCK_SIZE * rate / self.sample_rate)))
            try:
                stream = sd.InputStream(
                    samplerate=rate,
                    channels=CHANNELS,
                    dtype="float32",
                    blocksize=block,
                    device=dev_idx,
                    callback=self._audio_callback,
                )
                stream.start()
                self.stream = stream
                self._hw_sample_rate = rate
                self.active_device_name = dev_name
                self.is_available = True
                self.last_error = ""
                logger.info("Audio recording stream started on '%s' (%d Hz)", dev_name, rate)
                return True
            except Exception as e:
                logger.debug("Could not open mic '%s' at %d Hz: %s", dev_name, rate, e)
        return False

    def start(self):
        """Auto-detects and starts the best available microphone stream."""
        if self._is_running and self.stream is not None:
            return

        self.last_error = ""
        self.is_available = False
        available = list_input_devices()

        if not available:
            self.last_error = "No microphone detected on your PC."
            logger.warning(self.last_error)
            raise NoMicrophoneError(self.last_error)

        def _is_virtual_or_mapper(dev_name: str) -> bool:
            low = dev_name.lower()
            return any(
                k in low
                for k in (
                    "mapper",
                    "primary sound",
                    "virtual",
                    "midi",
                    "audiorelay",
                    "droidcam",
                    "vb-audio",
                    "cable output",
                )
            )

        # Build prioritized candidate list
        candidates = []
        if self.device_index is not None:
            for d in available:
                if d["index"] == self.device_index:
                    candidates.append((d["index"], d["name"], d["sample_rate"]))

        # System default input device (first only if it is a physical microphone)
        try:
            default_in = sd.default.device[0]
            if default_in is not None and default_in >= 0:
                for d in available:
                    if d["index"] == default_in and not _is_virtual_or_mapper(d["name"]):
                        candidates.append((d["index"], d["name"], d["sample_rate"]))
        except Exception:
            pass

        # Real hardware mics before virtual/mapper fallbacks
        for d in available:
            if not _is_virtual_or_mapper(d["name"]):
                candidates.append((d["index"], d["name"], d["sample_rate"]))
        for d in available:
            candidates.append((d["index"], d["name"], d["sample_rate"]))

        # Deduplicate while preserving order
        seen = set()
        unique_candidates = []
        for idx, name, rate in candidates:
            if idx not in seen:
                seen.add(idx)
                unique_candidates.append((idx, name, rate))

        self._is_running = True
        for idx, name, rate in unique_candidates:
            if self._try_open_device(idx, name, rate):
                self.device_index = idx
                return

        self._is_running = False
        self.last_error = "Microphone found, but Windows/driver denied audio capture access."
        logger.error(self.last_error)
        raise NoMicrophoneError(self.last_error)

    def stop(self):
        """Stops the audio recording stream."""
        self._is_running = False
        self.is_available = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.debug("Error stopping stream: %s", e)
            self.stream = None
        self.clear_queue()

    def clear_queue(self):
        """Drains any buffered audio frames from the queue."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    def read_frame(self, timeout: float = 0.5) -> Optional[np.ndarray]:
        """Reads one frame of int16 audio from the queue."""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
