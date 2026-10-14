"""
SLMic audio engine: reads the real microphone, runs the DSP pipeline,
and writes to the output device (e.g. VB-CABLE "CABLE Input", which
Discord / OBS then use as their microphone).
"""
import threading

import numpy as np

from .dsp import VoicePipeline

SAMPLE_RATE = 48000
BLOCK = 256


def list_devices():
    """Return (inputs, outputs) as lists of (index, name)."""
    import sounddevice as sd
    inputs, outputs = [], []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            inputs.append((i, d["name"]))
        if d["max_output_channels"] > 0:
            outputs.append((i, d["name"]))
    return inputs, outputs


def find_device(devices, keywords):
    """Pick the first device whose name contains any keyword (case-insensitive)."""
    for idx, name in devices:
        low = name.lower()
        if any(k in low for k in keywords):
            return idx
    return None


class AudioEngine:
    def __init__(self):
        self.pipeline = VoicePipeline(SAMPLE_RATE, BLOCK, "Pro Mic")
        self.stream = None
        self.lock = threading.Lock()
        self.running = False
        self.in_level_db = -120.0
        self.out_level_db = -120.0
        self.error = None

    # Real-time callback: must be fast and never block.
    def _callback(self, indata, outdata, frames, time_info, status):
        x = indata[:, 0].copy()
        in_peak = float(np.max(np.abs(x))) if frames else 0.0
        with self.lock:
            y = self.pipeline.process(x)
        outdata[:, 0] = y
        if outdata.shape[1] > 1:
            outdata[:, 1:] = y[:, None]
        self.in_level_db = 20 * np.log10(in_peak + 1e-9)
        self.out_level_db = self.pipeline.level_db

    def start(self, in_index, out_index):
        import sounddevice as sd
        self.stop()
        self.error = None
        try:
            in_ch = sd.query_devices(in_index)["max_input_channels"]
            out_ch = sd.query_devices(out_index)["max_output_channels"]
            self.stream = sd.Stream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK,
                device=(in_index, out_index),
                channels=(min(1, in_ch), min(1, out_ch)),
                dtype="float32",
                callback=self._callback,
                latency="low",
            )
            self.stream.start()
            self.running = True
        except Exception as e:  # device busy, unsupported format, etc.
            self.error = str(e)
            self.stream = None
            self.running = False

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None
        self.running = False
        self.in_level_db = -120.0
        self.out_level_db = -120.0

    def learn_noise(self, seconds=2.0):
        """Ask the user to stay silent; the NR learns the room noise."""
        with self.lock:
            self.pipeline.nr.start_learning(seconds, SAMPLE_RATE)

    @property
    def learning(self):
        return self.pipeline.nr.learning
