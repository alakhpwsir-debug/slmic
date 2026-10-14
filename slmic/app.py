"""
SLMic - make your bad microphone sound like a pro mic.
Run:  python -m slmic.app     (or the built SLMic.exe)
"""
import tkinter as tk
from tkinter import ttk, messagebox

from .dsp import PRESETS, db_to_lin
from .engine import AudioEngine, list_devices, find_device

BG = "#14161c"
PANEL = "#1d2029"
ACCENT = "#7c5cff"
TEXT = "#e8e8ee"
MUTED = "#8a8fa3"
GOOD = "#3ddc97"
BAD = "#ff5c7a"

VIRTUAL_KEYWORDS = ["cable input", "vb-audio", "virtual"]


class SLMicApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SLMic")
        self.geometry("560x640")
        self.minsize(520, 600)
        self.configure(bg=BG)

        self.engine = AudioEngine()
        self.inputs, self.outputs = [], []
        self.bypass_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._load_devices()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------- UI

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT)
        style.configure("Horizontal.TScale", background=PANEL)

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=20, pady=(18, 4))
        tk.Label(header, text="SLMic", font=("Segoe UI", 24, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        self.status = tk.Label(header, text="● Off", font=("Segoe UI", 11, "bold"),
                               bg=BG, fg=MUTED)
        self.status.pack(side="right")

        tk.Label(self, text="Clean, sharp, pro-sounding mic for Discord, OBS and anywhere.",
                 font=("Segoe UI", 10), bg=BG, fg=MUTED).pack(anchor="w", padx=20)

        # --- devices
        dev = self._panel("Devices")
        self.in_combo = self._combo(dev, "Microphone (input)")
        self.out_combo = self._combo(dev, "Send to (output)")
        tk.Label(dev, text="Tip: pick  CABLE Input (VB-Audio)  as the output, then choose  "
                           "CABLE Output  as the mic in Discord / OBS.",
                 font=("Segoe UI", 9), bg=PANEL, fg=MUTED, wraplength=480,
                 justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        # --- preset
        pr = self._panel("Preset")
        self.preset_var = tk.StringVar(value="Pro Mic")
        row = tk.Frame(pr, bg=PANEL)
        row.pack(fill="x", padx=12, pady=(0, 10))
        for name in PRESETS:
            tk.Radiobutton(row, text=name, value=name, variable=self.preset_var,
                           command=self._apply_preset, bg=PANEL, fg=TEXT,
                           selectcolor=ACCENT, activebackground=PANEL,
                           activeforeground=TEXT, font=("Segoe UI", 10)).pack(side="left", padx=(0, 16))

        # --- sliders
        sl = self._panel("Tuning")
        self.nr_var = self._slider(sl, "Noise removal (AI)", 0, 1.0, 1.0, self._on_nr)
        self.gate_var = self._slider(sl, "Noise gate threshold (dB)", -70, -20, -48,
                                     self._on_gate)
        self.pres_var = self._slider(sl, "Presence / clarity (dB)", 0, 8, 4, self._on_pres)
        self.gain_var = self._slider(sl, "Output volume (dB)", -12, 12, 0, self._on_gain)

        # --- meters
        me = self._panel("Levels")
        self.in_meter = self._meter(me, "Mic in")
        self.out_meter = self._meter(me, "Sent out")

        # --- buttons
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=20, pady=12)
        self.start_btn = self._button(btns, "▶  Start", ACCENT, self._toggle)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Checkbutton(btns, text="Bypass (compare)", variable=self.bypass_var,
                       command=self._on_bypass, bg=BG, fg=TEXT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 9)).pack(side="left", padx=8)

        self.hint = tk.Label(self, text="", font=("Segoe UI", 9), bg=BG, fg=MUTED,
                             wraplength=520, justify="left")
        self.hint.pack(anchor="w", padx=20, pady=(0, 10))

    def _panel(self, title):
        wrap = tk.Frame(self, bg=PANEL)
        wrap.pack(fill="x", padx=20, pady=6)
        tk.Label(wrap, text=title.upper(), font=("Segoe UI", 8, "bold"),
                 bg=PANEL, fg=MUTED).pack(anchor="w", padx=12, pady=(8, 4))
        return wrap

    def _combo(self, parent, label):
        tk.Label(parent, text=label, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 10)).pack(anchor="w", padx=12)
        c = ttk.Combobox(parent, state="readonly", width=60)
        c.pack(fill="x", padx=12, pady=(2, 8))
        return c

    def _slider(self, parent, label, lo, hi, init, cb):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=12, pady=2)
        tk.Label(row, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 10),
                 width=28, anchor="w").pack(side="left")
        var = tk.DoubleVar(value=init)
        val = tk.Label(row, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9), width=6)
        val.pack(side="right")
        s = tk.Scale(row, from_=lo, to=hi, orient="horizontal", resolution=0.1,
                     variable=var, showvalue=False, bg=PANEL, fg=TEXT,
                     troughcolor="#2b2f3b", highlightthickness=0, activebackground=ACCENT,
                     command=lambda _v, v=var, l=val: (l.config(text=f"{v.get():.1f}"), cb()))
        s.pack(side="left", fill="x", expand=True)
        val.config(text=f"{init:.1f}")
        var._scale = s
        return var

    def _meter(self, parent, label):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=12, pady=3)
        tk.Label(row, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 10),
                 width=10, anchor="w").pack(side="left")
        canvas = tk.Canvas(row, height=14, bg="#2b2f3b", highlightthickness=0)
        canvas.pack(side="left", fill="x", expand=True)
        return canvas

    def _button(self, parent, text, color, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg=TEXT,
                         activebackground=ACCENT, activeforeground=TEXT,
                         relief="flat", font=("Segoe UI", 11, "bold"), pady=10, bd=0)

    # ------------------------------------------------------ behaviour

    def _load_devices(self):
        try:
            self.inputs, self.outputs = list_devices()
        except Exception as e:
            messagebox.showerror("SLMic", f"Could not read audio devices:\n{e}")
            return
        in_names = [f"{i}: {n}" for i, n in self.inputs]
        out_names = [f"{i}: {n}" for i, n in self.outputs]
        self.in_combo["values"] = in_names
        self.out_combo["values"] = out_names
        # Sensible defaults
        if in_names:
            self.in_combo.current(0)
        vidx = find_device(self.outputs, VIRTUAL_KEYWORDS)
        if vidx is not None:
            self.out_combo.current([i for i, _ in self.outputs].index(vidx))
            self.hint.config(text="Virtual cable found. Choose CABLE Output as the mic in Discord / OBS.",
                             fg=GOOD)
        elif out_names:
            self.out_combo.current(0)
            self.hint.config(text="Virtual cable not found. Install VB-CABLE (see README), then restart SLMic.",
                             fg=BAD)

    def _selected(self, combo, devices):
        i = combo.current()
        if i < 0:
            return None
        return devices[i][0]

    def _toggle(self):
        if self.engine.running:
            self.engine.stop()
            self.start_btn.config(text="▶  Start", bg=ACCENT)
            self.status.config(text="● Off", fg=MUTED)
            return
        in_idx = self._selected(self.in_combo, self.inputs)
        out_idx = self._selected(self.out_combo, self.outputs)
        if in_idx is None or out_idx is None:
            messagebox.showwarning("SLMic", "Pick a microphone and an output device first.")
            return
        self._apply_sliders()
        self.engine.start(in_idx, out_idx)
        if self.engine.error:
            messagebox.showerror("SLMic", f"Could not start audio:\n{self.engine.error}")
            return
        self.start_btn.config(text="■  Stop", bg=BAD)
        self.status.config(text="● Live", fg=GOOD)

    def _apply_preset(self):
        p = PRESETS[self.preset_var.get()]
        self.nr_var.set(p["nr"]); self.gate_var.set(p["gate_db"])
        self.pres_var.set(p["presence_db"]); self.gain_var.set(0.0)
        self._apply_sliders()

    def _apply_sliders(self):
        pl = self.engine.pipeline
        pl.noise_mix = self.nr_var.get()
        pl.gate.threshold_db = self.gate_var.get()
        from .dsp import Biquad
        pl.presence = Biquad.peaking(pl.sr, 3000.0, self.pres_var.get(), q=0.9)
        pl.output_gain = db_to_lin(self.gain_var.get())

    def _on_nr(self):   self.engine.pipeline.noise_mix = self.nr_var.get()
    def _on_gate(self): self.engine.pipeline.gate.threshold_db = self.gate_var.get()
    def _on_pres(self):
        from .dsp import Biquad
        pl = self.engine.pipeline
        pl.presence = Biquad.peaking(pl.sr, 3000.0, self.pres_var.get(), q=0.9)
    def _on_gain(self): self.engine.pipeline.output_gain = db_to_lin(self.gain_var.get())
    def _on_bypass(self): self.engine.pipeline.bypass = self.bypass_var.get()

    def _draw_meter(self, canvas, db):
        canvas.delete("all")
        w = max(canvas.winfo_width(), 1)
        frac = min(max((db + 60) / 60, 0), 1)   # -60 dB .. 0 dB
        color = GOOD if db < -6 else ("#f5c451" if db < -1 else BAD)
        canvas.create_rectangle(0, 0, w * frac, 14, fill=color, width=0)

    def _tick(self):
        self._draw_meter(self.in_meter, self.engine.in_level_db)
        self._draw_meter(self.out_meter, self.engine.out_level_db)
        if self.engine.running and self.engine.error:
            self.status.config(text="● Error", fg=BAD)
        self.after(50, self._tick)

    def _on_close(self):
        self.engine.stop()
        self.destroy()


def main():
    SLMicApp().mainloop()


if __name__ == "__main__":
    main()
