# 🎛️ Knob Timer — Ship & Run Guide

A full-screen visual countdown timer driven by a USB volume knob.

---

## 🎮 Controls

| Input | Action |
|---|---|
| **Rotate knob** | ± 1 minute |
| **Press knob** (tap) | start / pause / stop alarm |
| **Hold knob** (~0.6s) | reset to last set value |
| `Space` | start / pause | `↑ ↓` or `+ –` | ± 1 minute |
| `R` | reset | `S` | settings |
| `F11` | full screen | `Esc` | exit full screen |
| Right-click | menu (settings / full screen / quit) | | |

While the app is in front, the knob drives the timer instead of Windows volume.
Switch to another app and the knob is a normal volume control again.

---

## 🚀 Option A — Give them a single `.exe` (recommended)

Your friend needs **no Python, no install**. You build once, hand them one file.

**On your machine (in the venv):**

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name KnobTimer knob_timer.py
```

The exe lands in **`dist\KnobTimer.exe`**. Ship that folder:

```
KnobTimer.exe        ← the app
alarm.mp3            ← optional: your alarm sound (any .mp3/.wav)
```

`config.json` is created automatically next to the exe on first run.

**On their machine:** double-click `KnobTimer.exe`. That's it.

> 💡 If Windows SmartScreen warns ("unknown publisher"), click **More info → Run
> anyway** — expected for unsigned apps. Some antivirus may flag the keyboard
> hook; it's a false positive (the hook is what suppresses the volume keys).

---

## 🐍 Option B — Run from source (they have Python 3.10+)

```powershell
# 1. Copy knob_timer.py (and optionally alarm.mp3) to a folder
# 2. In that folder:
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install PyQt6
python knob_timer.py
```

Only one dependency (`PyQt6`) — audio uses Qt Multimedia, bundled inside it.

> ⚠️ **Not** `pygame` — it won't build on Python 3.14. This app avoids it.

---

## 🎨 Customizing

Edit **`config.json`** (created on first run) or press **`S`** in the app:

| Key | Meaning |
|---|---|
| `idle_color` / `counting_color` / `paused_color` / `alarm_color` | state backgrounds |
| `text_color` | digit color |
| `audio_file_path` | path to alarm sound (e.g. `alarm.mp3`) |
| `default_minutes` | starting time |

No alarm file? It falls back to a system beep — the app still works.

---

## 🩺 Quick troubleshooting

| Symptom | Fix |
|---|---|
| Window won't open | Run with the venv active (Option B), or use the exe (Option A). |
| Knob still changes Windows volume | The hook didn't install — see the on-screen warning. Retry, or run once as admin. |
| No alarm sound | Set a valid `audio_file_path`, or drop `alarm.mp3` beside the app. |
| Knob does nothing | Run `python key_probe.py`, use the knob, send the log. |
