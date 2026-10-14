"""
Minimal ctypes wrapper around RNNoise (a neural-network noise suppressor
used in real-time voice apps). The compiled library comes from the
`pyrnnoise` wheel: rnnoise.dll on Windows, librnnoise.so on Linux.

RNNoise works on 48 kHz audio in frames of 480 samples (10 ms).
"""
import ctypes
import importlib.util
import os
import platform
import sys

import numpy as np


def _library_path():
    names = {"Windows": "rnnoise.dll", "Linux": "librnnoise.so",
             "Darwin": "librnnoise.dylib"}
    candidates = []
    # When packaged with PyInstaller, data files live under sys._MEIPASS.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "pyrnnoise"))
    spec = importlib.util.find_spec("pyrnnoise")
    if spec is not None and spec.submodule_search_locations:
        candidates.extend(list(spec.submodule_search_locations))
    for folder in candidates:
        path = os.path.join(folder, names[platform.system()])
        if os.path.exists(path):
            return path
    raise OSError("RNNoise library not found. Did you install pyrnnoise?")


_lib = ctypes.CDLL(_library_path())
_lib.rnnoise_create.argtypes = [ctypes.c_void_p]
_lib.rnnoise_create.restype = ctypes.c_void_p
_lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
_lib.rnnoise_process_frame.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float)]
_lib.rnnoise_process_frame.restype = ctypes.c_float
_lib.rnnoise_get_frame_size.restype = ctypes.c_int

FRAME_SIZE = _lib.rnnoise_get_frame_size()   # 480 samples
SAMPLE_RATE = 48000


class RNNoiseDenoiser:
    """Denoise a 48 kHz mono stream. Input/output: float32 in [-1, 1], 480 samples per call."""

    def __init__(self):
        self._state = _lib.rnnoise_create(None)
        self._buf = np.zeros(FRAME_SIZE, dtype=np.float32)

    def close(self):
        if self._state:
            _lib.rnnoise_destroy(self._state)
            self._state = None

    def __del__(self):
        self.close()

    def process(self, x):
        """x: float32 array of exactly FRAME_SIZE samples -> denoised float32 array."""
        # RNNoise expects int16-scaled floats
        self._buf[:] = x * 32768.0
        ptr = self._buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        _lib.rnnoise_process_frame(self._state, ptr, ptr)
        return np.clip(self._buf / 32768.0, -1.0, 1.0).astype(np.float32)
