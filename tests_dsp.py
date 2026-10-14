"""SLMic DSP sanity tests. Run:  python tests_dsp.py  (exits non-zero on failure)."""
import sys
import numpy as np
from slmic.dsp import VoicePipeline, BLOCK
from slmic.rnnoise_wrap import RNNoiseDenoiser

SR = 48000
rng = np.random.default_rng(0)
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        fails.append(name)


def rms(x):
    return float(np.sqrt(np.mean(x ** 2)))


def run(pipe, x):
    n = len(x) // BLOCK * BLOCK
    return np.concatenate([pipe.process(x[i:i + BLOCK]) for i in range(0, n, BLOCK)])


# 1. Steady white noise is strongly reduced by RNNoise
n = BLOCK * 400
noise = (0.05 * rng.standard_normal(n)).astype(np.float32)
d = RNNoiseDenoiser()
y = np.concatenate([d.process(noise[i:i + BLOCK]) for i in range(0, n, BLOCK)])
ratio = rms(y[BLOCK * 100:]) / rms(noise[BLOCK * 100:])
check("RNNoise removes steady noise", ratio < 0.5, f"out/in rms = {ratio:.2f}")

# 2. Voice-like tone + hiss + hum: output finite, bounded, speech survives
t = np.arange(SR * 4) / SR
f0 = 140 + 15 * np.sin(2 * np.pi * 0.7 * t)
phase = 2 * np.pi * np.cumsum(f0) / SR
voice = sum(np.sin(k * phase) / k for k in range(1, 12))
clean = np.zeros_like(t)
clean[SR:3 * SR] = 0.3 * voice[SR:3 * SR]
noisy = (clean + 0.03 * rng.standard_normal(len(t)) + 0.02 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)
out = run(VoicePipeline(SR, BLOCK, "Pro Mic"), noisy)
check("output finite", bool(np.isfinite(out).all()))
check("output never exceeds 1.0", bool(np.abs(out).max() <= 1.0))
seg = slice(SR + 8000, 3 * SR - 8000)
check("voice still present", rms(out[seg]) > 0.05, f"voice rms = {rms(out[seg]):.3f}")

# 3. Noise removal lowers the noise in the pause
pause = slice(8000, SR - 8000)
pn = VoicePipeline(SR, BLOCK, "Pro Mic")
pn.noise_mix = 0.0
raw_pause = rms(run(pn, noisy)[pause])
clean_pause = rms(run(VoicePipeline(SR, BLOCK, "Pro Mic"), noisy)[pause])
check("noise removal lowers pause noise", clean_pause < raw_pause * 0.8,
      f"no-removal {raw_pause:.4f} -> with removal {clean_pause:.4f}")

# 4. Bypass is transparent
pb = VoicePipeline(SR, BLOCK)
pb.bypass = True
check("bypass is transparent", np.allclose(pb.process(noisy[:BLOCK]), noisy[:BLOCK], atol=1e-6))

print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
