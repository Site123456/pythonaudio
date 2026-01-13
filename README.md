# pythonaudio
A simple, real‑time guitar synthesizer built with Python for testing audio for another project.
Includes a 6×20 fretboard, piano‑style keyboard shortcuts, reverb, delay, distortion, pick‑position modeling, and body‑resonance simulation.
Note: Feel free to use and modify.

# Render preview
![Guitar Synth Preview](https://github.com/Site123456/pythonaudio/blob/main/pyrendercosomforengine.png)

#🚀 Features
- 🎸 6×20 clickable fretboard

- 🎹 Piano‑style keyboard shortcuts (white + black keys)

- 🔊 Polyphonic audio engine (multiple notes at once)

- 🎛️ Effects:

   - Reverb

   - Delay

   - Distortion

- 🪵 Pick‑position modeling

- 🪘 Body resonance simulation

- 🎚️ Master volume control

- 🪟 Modern draggable UI

- ⚡ Low‑latency real‑time synthesis


Important helpers:
- Keyboard Shortcuts

| Keys             | Notes           | Octave |
|------------------|-----------------|--------|
| Z X C V B N M    | C D E F G A B   | Low    |
| Q W E R T Y U    | C D E F G A B   | High   |



Sharps/flats

| Keys     | Notes            |
|----------|------------------|
| S D      | C# D#            |
| G H J    | F# G# A#         |
| 2 3      | C# D# (high)     |
| 5 6 7    | F# G# A# (high)  |




# Get started:

###### 1 Install dependencies 
```pip install sounddevice numpy mido python-rtmidi```
###### 2 Run it with: python 3.10+
```python main.py```
