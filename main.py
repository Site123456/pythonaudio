import tkinter as tk
import numpy as np
import sounddevice as sd
import threading
import math
import time

SAMPLE_RATE = 44100

# Synth & mixing
active_notes = []
lock = threading.Lock()

global_volume = 0.6
delay_mix = 0.18
delay_time = 0.22
delay_feedback = 0.25
reverb_mix = 0.22
distortion_amount = 0.18

delay_buffer = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)
delay_pos = 0
reverb_buffer = np.zeros(SAMPLE_RATE * 3, dtype=np.float32)
reverb_pos = 0


def karplus_strong(
    freq: float,
    duration: float = 2.0,
    decay: float = 0.997,
    pick_pos: float = 0.25,
    body_res: float = 0.45,
) -> np.ndarray:
    n_samples = int(SAMPLE_RATE * duration)
    buffer_size = max(2, int(SAMPLE_RATE / freq))

    t = np.linspace(0, 1, buffer_size, endpoint=False)
    pick_window = np.sin(math.pi * t) ** 2
    pick_window *= np.sin(2 * math.pi * pick_pos * t * buffer_size) ** 2
    buffer = np.random.uniform(-1, 1, buffer_size).astype(np.float32) * pick_window

    samples = np.zeros(n_samples, dtype=np.float32)
    prev = 0.0
    alpha = body_res * 0.3

    for i in range(n_samples):
        samples[i] = buffer[0]
        avg = decay * 0.5 * (buffer[0] + buffer[1])
        buffer = np.append(buffer[1:], avg)

        prev = (1 - alpha) * samples[i] + alpha * prev
        samples[i] = prev

    # Simple attack/decay envelope to soften onset/off
    env = np.linspace(0, 1, int(0.01 * SAMPLE_RATE))
    env = np.pad(env, (0, len(samples) - len(env)), constant_values=1)
    tail = np.linspace(1, 0, int(0.4 * SAMPLE_RATE))
    env[-len(tail) :] *= tail
    samples *= env

    return samples


def add_note(freq: float, pick_pos: float = 0.25, body_res: float = 0.5):
    wave = karplus_strong(freq, pick_pos=pick_pos, body_res=body_res)
    with lock:
        active_notes.append({"data": wave, "pos": 0})


def play_chord(freqs):
    for f in freqs:
        add_note(f)
        time.sleep(0.03)


def audio_callback(outdata, frames, time_info, status):
    global active_notes, delay_buffer, delay_pos, reverb_buffer, reverb_pos
    global global_volume, delay_mix, delay_time, delay_feedback
    global reverb_mix, distortion_amount

    mix = np.zeros(frames, dtype=np.float32)

    with lock:
        new_notes = []
        for note in active_notes:
            data = note["data"]
            pos = note["pos"]
            end = pos + frames
            chunk = data[pos:end]

            if len(chunk) < frames:
                chunk = np.pad(chunk, (0, frames - len(chunk)))
            else:
                new_notes.append({"data": data, "pos": end})

            mix += chunk

        active_notes = new_notes

    delay_samples = max(1, int(delay_time * SAMPLE_RATE))
    out = np.zeros_like(mix)

    for i in range(frames):
        dry = mix[i]

        d_idx = (delay_pos + i - delay_samples) % len(delay_buffer)
        delayed = delay_buffer[d_idx]
        delay_buffer[(delay_pos + i) % len(delay_buffer)] = dry + delayed * delay_feedback
        with_delay = dry * (1 - delay_mix) + delayed * delay_mix

        r1 = reverb_buffer[(reverb_pos + i - int(0.03 * SAMPLE_RATE)) % len(reverb_buffer)]
        r2 = reverb_buffer[(reverb_pos + i - int(0.07 * SAMPLE_RATE)) % len(reverb_buffer)]
        r3 = reverb_buffer[(reverb_pos + i - int(0.11 * SAMPLE_RATE)) % len(reverb_buffer)]
        reverb_sample = (r1 + r2 + r3) / 3.0
        reverb_buffer[(reverb_pos + i) % len(reverb_buffer)] = with_delay + reverb_sample * 0.5
        with_reverb = with_delay * (1 - reverb_mix) + reverb_sample * reverb_mix

        x = with_reverb * (1 + distortion_amount * 12)
        with_dist = np.tanh(x) if distortion_amount > 0 else with_reverb

        out[i] = with_dist

    delay_pos = (delay_pos + frames) % len(delay_buffer)
    reverb_pos = (reverb_pos + frames) % len(reverb_buffer)

    peak = np.max(np.abs(out))
    if peak > 1e-5:
        # soft limiter
        out = out / (peak * 1.1)

    out *= global_volume
    outdata[:] = out.reshape(-1, 1)


stream = sd.OutputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    callback=audio_callback,
)
stream.start()

# Guitar & piano mapping
open_string_freqs = {
    "E2": 82.41,
    "A2": 110.00,
    "D3": 146.83,
    "G3": 196.00,
    "B3": 246.94,
    "E4": 329.63,
}
string_order = ["E4", "B3", "G3", "D3", "A2", "E2"]


def freq_for_fret(open_freq, fret):
    return open_freq * (2 ** (fret / 12))


# Piano-style mapping: two octaves around middle
def note_to_freq(midi_note: int) -> float:
    return 440.0 * (2 ** ((midi_note - 69) / 12))


white_low = "zxcvbnm"
white_high = "qwertyu"
black_low = "sdghj"
black_high = "23567"

key_to_midi = {}

# base at C3 (midi 48) for low row, C4 (60) for high row
white_notes = [0, 2, 4, 5, 7, 9, 11]  # C D E F G A B
black_offsets = [1, 3, 6, 8, 10]  # C#, D#, F#, G#, A#

for i, k in enumerate(white_low):
    key_to_midi[k] = 48 + white_notes[i]
for i, k in enumerate(white_high):
    key_to_midi[k] = 60 + white_notes[i]
for i, k in enumerate(black_low):
    key_to_midi[k] = 48 + black_offsets[i]
for i, k in enumerate(black_high):
    key_to_midi[k] = 60 + black_offsets[i]


def handle_key_press(ch: str):
    ch = ch.lower()
    if ch in key_to_midi:
        freq = note_to_freq(key_to_midi[ch])
        # map piano note into guitar-like behavior:
        # higher notes → closer pick position, more body resonance
        norm = min(max((freq - 82.0) / (660.0 - 82.0), 0.0), 1.0)
        pick_pos = 0.15 + 0.6 * norm
        body_res = 0.35 + 0.5 * (1 - norm)
        add_note(freq, pick_pos=pick_pos, body_res=body_res)


# Tkinter UI
root = tk.Tk()
root.overrideredirect(True)
root.geometry("1150x720")
root.configure(bg="#050509")


def start_drag(e):
    root.x = e.x
    root.y = e.y


def drag(e):
    root.geometry(f"+{e.x_root - root.x}+{e.y_root - root.y}")


title_bar = tk.Frame(root, bg="#111827", height=40)
title_bar.pack(fill="x")
title_bar.bind("<Button-1>", start_drag)
title_bar.bind("<B1-Motion>", drag)

title_label = tk.Label(
    title_bar,
    text="Python audio test",
    fg="#f9fafb",
    bg="#111827",
    font=("Segoe UI", 14, "bold"),
)
title_label.pack(side="left", padx=10)


def close_app():
    stream.stop()
    root.destroy()


close_btn = tk.Button(
    title_bar,
    text="✕",
    bg="#111827",
    fg="#f9fafb",
    bd=0,
    font=("Segoe UI", 14),
    command=close_app,
)
close_btn.pack(side="right", padx=10)

main = tk.Frame(root, bg="#050509")
main.pack(fill="both", expand=True, padx=16, pady=16)

# Left: fretboard
fretboard_frame = tk.Frame(main, bg="#0b1120", bd=2, relief="ridge")
fretboard_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

fb_header = tk.Label(
    fretboard_frame,
    text="6 × 20 Fretboard (click to play)",
    font=("Segoe UI", 13, "bold"),
    fg="#e5e7eb",
    bg="#0b1120",
)
fb_header.pack(pady=8)

fb_canvas = tk.Canvas(fretboard_frame, bg="#020617", highlightthickness=0)
fb_canvas.pack(fill="both", expand=True, padx=10, pady=10)

FB_ROWS = 6
FB_COLS = 20
fret_cells = {}


def draw_fretboard():
    fb_canvas.delete("all")
    w = fb_canvas.winfo_width()
    h = fb_canvas.winfo_height()
    if w < 100 or h < 100:
        root.after(100, draw_fretboard)
        return

    row_h = h / FB_ROWS
    col_w = w / FB_COLS

    for r, s in enumerate(string_order):
        y = (r + 0.5) * row_h
        fb_canvas.create_line(
            0,
            y,
            w,
            y,
            fill="#e5e7eb",
            width=3 if r in (0, 5) else 2,
        )

    for c in range(FB_COLS + 1):
        x = c * col_w
        fb_canvas.create_line(
            x,
            0,
            x,
            h,
            fill="#4b5563" if c else "#94a3b8",
            width=1 if c else 3,
        )

    fret_cells.clear()
    for r, s in enumerate(string_order):
        open_freq = open_string_freqs[s]
        for c in range(FB_COLS):
            x0 = c * col_w
            y0 = r * row_h
            x1 = (c + 1) * col_w
            y1 = (r + 1) * row_h

            freq = freq_for_fret(open_freq, c)
            rect = fb_canvas.create_rectangle(
                x0 + 3,
                y0 + 3,
                x1 - 3,
                y1 - 3,
                outline="",
                fill="",
                tags=("fret",),
            )
            fret_cells[rect] = (freq, r, c, s)


def on_fret_click(event):
    items = fb_canvas.find_withtag("current")
    if not items:
        return
    item = items[0]
    if item not in fret_cells:
        return
    freq, row, col, sname = fret_cells[item]
    pick_pos = 0.18 + 0.5 * (row / (FB_ROWS - 1))
    body_res = 0.4 + 0.5 * (col / (FB_COLS - 1))

    add_note(freq, pick_pos=pick_pos, body_res=body_res)
    fb_canvas.itemconfig(item, fill="#fbbf24")
    fb_canvas.after(140, lambda i=item: fb_canvas.itemconfig(i, fill=""))


fb_canvas.bind("<Button-1>", on_fret_click)
fb_canvas.bind("<Configure>", lambda e: draw_fretboard())

# Right: controls and keyboard legend
side = tk.Frame(main, bg="#050509")
side.pack(side="right", fill="y", padx=(10, 0))

controls = tk.LabelFrame(
    side,
    text="Sound Controls",
    bg="#050509",
    fg="#e5e7eb",
    font=("Segoe UI", 11, "bold"),
    labelanchor="n",
)
controls.pack(fill="x", pady=8)


def on_volume(v):
    global global_volume
    global_volume = float(v)


def on_delay_mix(v):
    global delay_mix
    delay_mix = float(v)


def on_reverb_mix(v):
    global reverb_mix
    reverb_mix = float(v)


def on_distortion(v):
    global distortion_amount
    distortion_amount = float(v)


def slider(parent, label, from_, to, var, command):
    s = tk.Scale(
        parent,
        from_=from_,
        to=to,
        resolution=0.01,
        orient="horizontal",
        label=label,
        bg="#050509",
        fg="#e5e7eb",
        troughcolor="#1f2937",
        highlightthickness=0,
        command=command,
    )
    s.set(var)
    s.pack(fill="x", padx=10, pady=3)
    return s


slider(controls, "Volume", 0.0, 1.0, global_volume, on_volume)
slider(controls, "Delay mix", 0.0, 0.7, delay_mix, on_delay_mix)
slider(controls, "Reverb mix", 0.0, 0.7, reverb_mix, on_reverb_mix)
slider(controls, "Distortion", 0.0, 0.5, distortion_amount, on_distortion)

chords_frame = tk.LabelFrame(
    side,
    text="Quick chords",
    bg="#050509",
    fg="#e5e7eb",
    font=("Segoe UI", 11, "bold"),
    labelanchor="n",
)
chords_frame.pack(fill="x", pady=8)

CHORDS = {
    "C": [note_to_freq(n) for n in [60, 64, 67, 72]],
    "G": [note_to_freq(n) for n in [55, 59, 62, 67]],
    "D": [note_to_freq(n) for n in [62, 66, 69]],
    "Em": [note_to_freq(n) for n in [52, 55, 59, 64]],
}


def hover_on(btn):
    btn.config(bg="#fbbf24", fg="#0f172a")


def hover_off(btn):
    btn.config(bg="#111827", fg="#e5e7eb")


for name, freqs in CHORDS.items():
    b = tk.Button(
        chords_frame,
        text=name,
        font=("Segoe UI", 11, "bold"),
        width=6,
        bg="#111827",
        fg="#e5e7eb",
        relief="flat",
        command=lambda f=freqs: threading.Thread(
            target=play_chord, args=(f,), daemon=True
        ).start(),
    )
    b.pack(side="left", padx=4, pady=6)
    b.bind("<Enter>", lambda e, x=b: hover_on(x))
    b.bind("<Leave>", lambda e, x=b: hover_off(x))

legend = tk.LabelFrame(
    side,
    text="Keyboard (piano layout)",
    bg="#050509",
    fg="#e5e7eb",
    font=("Segoe UI", 11, "bold"),
    labelanchor="n",
)
legend.pack(fill="x", pady=8)

tk.Label(
    legend,
    text="White keys:\n  Z X C V B N M  (low)\n  Q W E R T Y U  (high)",
    bg="#050509",
    fg="#e5e7eb",
    justify="left",
    font=("Segoe UI", 9),
).pack(anchor="w", padx=8, pady=2)

tk.Label(
    legend,
    text="Black keys:\n  S D   G H J    (low sharps)\n  2 3   5 6 7   (high sharps)",
    bg="#050509",
    fg="#e5e7eb",
    justify="left",
    font=("Segoe UI", 9),
).pack(anchor="w", padx=8, pady=2)

info = tk.Label(
    side,
    text="Play with mouse (fretboard)\nor keys (piano layout).\nPolyphonic, with FX & soft limiting.",
    bg="#050509",
    fg="#9ca3af",
    justify="left",
    font=("Segoe UI", 9),
)
info.pack(pady=8, anchor="w")


def on_key_press(event):
    if event.char:
        handle_key_press(event.char)


root.bind("<KeyPress>", on_key_press)

root.mainloop()
