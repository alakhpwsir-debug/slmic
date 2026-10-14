"""
SLMic DSP core - pure numpy/scipy, no audio hardware needed.

Signal chain (per audio block, real-time safe):
  1. High-pass filter      -> removes rumble, desk bumps, AC hum
  2. Noise reduction       -> spectral subtraction with adaptive noise floor
  3. EQ                    -> mud cut, presence boost, air boost
  4. Noise gate            -> silences the mic when you're not talking
  5. Compressor            -> evens out loud/quiet speech (the "pro mic" feel)
  6. Makeup gain + limiter -> loud, clean output that never clips
"""
import numpy as np
from scipy.signal import lfilter


# ---------------------------------------------------------------- utilities

def db_to_lin(db):
    return 10.0 ** (db / 20.0)


def lin_to_db(x):
    return 20.0 * np.log10(np.maximum(x, 1e-12))


class Biquad:
    """Streaming RBJ biquad filter (keeps state between blocks)."""

    def __init__(self, b, a):
        self.b = np.asarray(b, dtype=np.float64)
        self.a = np.asarray(a, dtype=np.float64)
        self.zi = np.zeros(2)

    def process(self, x):
        y, self.zi = lfilter(self.b, self.a, x, zi=self.zi)
        return y

    @staticmethod
    def highpass(sr, f0, q=0.707):
        w0 = 2 * np.pi * f0 / sr
        cs, alpha = np.cos(w0), np.sin(w0) / (2 * q)
        b = [(1 + cs) / 2, -(1 + cs), (1 + cs) / 2]
        a = [1 + alpha, -2 * cs, 1 - alpha]
        return Biquad(np.array(b) / a[0], np.array(a) / a[0])

    @staticmethod
    def peaking(sr, f0, gain_db, q=1.0):
        A = 10 ** (gain_db / 40)
        w0 = 2 * np.pi * f0 / sr
        cs, alpha = np.cos(w0), np.sin(w0) / (2 * q)
        b = [1 + alpha * A, -2 * cs, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cs, 1 - alpha / A]
        return Biquad(np.array(b) / a[0], np.array(a) / a[0])


class NoiseGate:
    """Block-wise gate with hysteresis and smooth open/close."""

    def __init__(self, sr, block, threshold_db=-50.0, depth_db=-40.0):
        self.threshold_db = threshold_db
        self.depth = db_to_lin(depth_db)
        self.gain = 1.0
        self.open = False
        # one-block smoothing coefficients (block-rate ~ sr/block per second)
        rate = sr / block
        self.a_open = np.exp(-1.0 / (0.005 * rate))    # 5 ms opening
        self.a_close = np.exp(-1.0 / (0.150 * rate))   # 150 ms release

    def process(self, x):
        level = lin_to_db(np.sqrt(np.mean(x ** 2)) + 1e-12)
        if self.open and level < self.threshold_db - 4:   # hysteresis
            self.open = False
        elif not self.open and level > self.threshold_db:
            self.open = True
        target = 1.0 if self.open else self.depth
        a = self.a_open if target > self.gain else self.a_close
        self.gain = a * self.gain + (1 - a) * target
        return x * self.gain


class Compressor:
    """Feed-forward compressor with block-rate envelope and makeup gain."""

    def __init__(self, sr, block, threshold_db=-24.0, ratio=3.0, makeup_db=6.0):
        self.threshold = threshold_db
        self.ratio = ratio
        self.makeup = db_to_lin(makeup_db)
        self.env_db = -60.0
        rate = sr / block
        self.a_att = np.exp(-1.0 / (0.010 * rate))  # 10 ms attack
        self.a_rel = np.exp(-1.0 / (0.150 * rate))  # 150 ms release

    def process(self, x):
        level = lin_to_db(np.sqrt(np.mean(x ** 2)) + 1e-12)
        a = self.a_att if level > self.env_db else self.a_rel
        self.env_db = a * self.env_db + (1 - a) * level
        over = max(0.0, self.env_db - self.threshold)
        gain_db = -over * (1 - 1 / self.ratio)
        return x * db_to_lin(gain_db) * self.makeup


def soft_limit(x, ceiling=0.89):
    """Transparent-ish limiter: linear below ceiling, smooth tanh above."""
    y = np.where(np.abs(x) < ceiling, x,
                 np.sign(x) * (ceiling + (1 - ceiling) * np.tanh((np.abs(x) - ceiling) / (1 - ceiling))))
    return np.clip(y, -1.0, 1.0)


# --------------------------------------------------------------- pipeline

PRESETS = {
    "Pro Mic": dict(nr=1.0, gate_db=-42, presence_db=4.0, mud_db=-3.0,
                    air_db=2.0, comp_ratio=3.0, comp_db=-22, makeup_db=4.0),
    "Gaming":  dict(nr=1.0, gate_db=-38, presence_db=3.0, mud_db=-2.0,
                    air_db=1.0, comp_ratio=2.5, comp_db=-20, makeup_db=4.0),
    "Light":   dict(nr=0.6, gate_db=-50, presence_db=2.0, mud_db=-1.5,
                    air_db=1.0, comp_ratio=2.0, comp_db=-26, makeup_db=2.0),
}

BLOCK = 480  # RNNoise frame size (10 ms at 48 kHz)


class VoicePipeline:
    """Full chain. Input/output: float32 mono blocks of BLOCK samples at 48 kHz."""

    def __init__(self, sr=48000, block=BLOCK, preset="Pro Mic"):
        from .rnnoise_wrap import RNNoiseDenoiser
        assert block == BLOCK and sr == 48000, "RNNoise requires 48 kHz and 480-sample blocks"
        self.sr = sr
        self.block = block
        self.bypass = False
        self.input_gain = 1.0
        self.output_gain = 1.0
        self.denoiser = RNNoiseDenoiser()
        self.noise_mix = 1.0           # 0 = no removal, 1 = full removal
        self.hpf = Biquad.highpass(sr, 80.0)
        self.mud = Biquad.peaking(sr, 250.0, -3.0, q=1.0)
        self.presence = Biquad.peaking(sr, 3000.0, 4.0, q=0.9)
        self.air = Biquad.peaking(sr, 10000.0, 2.0, q=0.7)
        self.gate = NoiseGate(sr, block)
        self.comp = Compressor(sr, block)
        self.level_db = -120.0   # for the GUI meter
        self.apply_preset(preset)

    def apply_preset(self, name):
        p = PRESETS[name]
        self.noise_mix = p["nr"]
        self.gate.threshold_db = p["gate_db"]
        self.presence = Biquad.peaking(self.sr, 3000.0, p["presence_db"], q=0.9)
        self.mud = Biquad.peaking(self.sr, 250.0, p["mud_db"], q=1.0)
        self.air = Biquad.peaking(self.sr, 10000.0, p["air_db"], q=0.7)
        self.comp.threshold = p["comp_db"]
        self.comp.ratio = p["comp_ratio"]
        self.comp.makeup = db_to_lin(p["makeup_db"])

    def process(self, x):
        """x: float32 mono block of BLOCK samples -> processed block."""
        x = x.astype(np.float64) * self.input_gain
        if self.bypass:
            y = x
        else:
            y = self.hpf.process(x)
            den = self.denoiser.process(y.astype(np.float32)).astype(np.float64)
            m = float(np.clip(self.noise_mix, 0.0, 1.0))
            y = m * den + (1.0 - m) * y           # wet/dry mix
            y = self.mud.process(y)
            y = self.presence.process(y)
            y = self.air.process(y)
            y = self.gate.process(y)
            y = self.comp.process(y)
            y = soft_limit(y * self.output_gain)
        peak = np.max(np.abs(y)) if len(y) else 0.0
        self.level_db = float(lin_to_db(peak))
        return np.clip(y, -1, 1).astype(np.float32)
