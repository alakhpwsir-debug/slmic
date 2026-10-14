# SLMic

Makes a bad laptop microphone sound crisp, clear and professional — and removes
background noise. Use it in Discord, OBS, or any app that asks for a microphone.

## How it works

Your real mic → **SLMic** (cleans the voice) → **VB-CABLE virtual mic** → Discord / OBS

Processing chain: high-pass filter (removes rumble) → noise reduction → EQ (less mud,
more presence) → noise gate (silences you when you're not talking) → compressor
(evens out loudness) → limiter (never clips).

## Setup (for users)

1. **Install VB-CABLE** (free virtual audio driver): https://vb-audio.com/Cable/
   Download it, right-click *VBCABLE_Setup_x64.exe* → *Run as administrator* → Install, then restart Windows.
2. **Run SLMic.exe.**
3. In SLMic:
   - **Microphone (input):** your laptop mic.
   - **Send to (output):** `CABLE Input (VB-Audio Virtual Cable)`.
   - Click **Start**.
   - Click **Learn room noise** and stay quiet for 2 seconds (optional, but helps a lot).
4. In **Discord**: Settings → Voice & Video → Input Device → **CABLE Output (VB-Audio Virtual Cable)**.
   In **OBS**: Settings → Audio → Mic/Auxiliary → **CABLE Output**.
   (Discord: turn off *Noise Suppression* and *Echo Cancellation* so you don't process it twice.)

### Tuning
- **Preset:** Pro Mic (default), Gaming (stronger cleanup), Light (gentle).
- **Noise reduction:** higher = less background hiss, but voice can sound "watery" if pushed too far.
- **Noise gate:** raise it (toward -30 dB) if background noise leaks in between words; lower it if your quiet words get cut.
- **Presence:** adds clarity and "radio-voice" sparkle.
- **Bypass:** hear the raw mic to compare.

## For developers

Run from source (Windows, Python 3.12):
```
pip install -r requirements.txt
python tests_dsp.py
python run_slmic.py
```

Build the exe locally:
```
pyinstaller --noconfirm --onefile --windowed --name SLMic run_slmic.py
```
The exe appears in `dist/SLMic.exe`. The GitHub Actions workflow in `.github/workflows/build-exe.yml`
does the same thing on every push to `main` and uploads the exe as a downloadable artifact.

## Project layout

```
run_slmic.py              entry point (used by PyInstaller)
slmic/dsp.py              audio processing (noise reduction, EQ, gate, compressor)
slmic/engine.py           real-time audio I/O (sounddevice)
slmic/app.py              the SLMic window (tkinter)
tests_dsp.py              DSP sanity tests (run in CI)
.github/workflows/        Windows build -> SLMic.exe
```

## Known limits
- Works best on a quiet-ish room. Heavy, changing noise (typing, fans) is reduced but not removed perfectly.
- Latency is roughly 20–30 ms plus driver latency.
- Virtual mic depends on VB-CABLE. SLMic does not install its own audio driver.
