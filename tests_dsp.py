"""SLMic DSP sanity tests. Run:  python tests_dsp.py  (exits non-zero on failure)."""
import sys
import numpy as np
from slmic.dsp import VoicePipeline, SpectralNoiseReducer

SR, BLK = 48000, 256
rng = np.random.default_rng(0)
fails = []

def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        fails.append(name)

def rms(x): return float(np.sqrt(np.mean(x ** 2)))

# 1. Noise reducer removes steady noise
n = BLK * 1600
x = 0.05 * rng.standard_normal(n)
nr = SpectralNoiseReducer(BLK); nr.set_strength(1.0); nr.start_learning(0.5, SR)
y = np.concatenate([nr.process(x[i:i+BLK]) for i in range(0, n, BLK)])
ratio = rms(y[BLK*800:]) / rms(x[BLK*800:])
check("noise reducer cuts steady noise", ratio < 0.75, f"out/in rms = {ratio:.2f}")

# 2. Voice + hum + hiss: pipeline output is finite, bounded and speech survives
t = np.arange(SR * 4) / SR
f0 = 140 + 15 * np.sin(2 * np.pi * 0.7 * t)
voice = sum(np.sin(k * 2 * np.pi * np.cumsum(f0) / SR) / k for k in range(1, 12))
clean = np.zeros_like(t); clean[SR:3*SR] = 0.3 * voice[SR:3*SR]
noisy = (clean + 0.03 * rng.standard_normal(len(t)) + 0.02 * np.sin(2*np.pi*60*t)).astype(np.float32)
p = VoicePipeline(SR, BLK, "Pro Mic")
out = np.concatenate([p.process(noisy[i:i+BLK]) for i in range(0, len(noisy) - BLK + 1, BLK)])
check("output finite", np.isfinite(out).all())
check("output never clips past 1.0", np.abs(out).max() <= 1.0)
check("speech still present", rms(out[SR*1+4000:SR*3-4000]) > 0.05,
      f"speech rms = {rms(out[SR*1+4000:SR*3-4000]):.3f}")

# 3. Bypass passes audio through unchanged (apart from the input gain of 1.0)
pb = VoicePipeline(SR, BLK); pb.bypass = True
check("bypass is transparent", np.allclose(pb.process(noisy[:BLK]), noisy[:BLK], atol=1e-6))

print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
