<h1 align="center">🎛️ Knob Timer</h1>

<p align="center">
  <em>Your USB volume knob has been changing the volume its whole life.<br>
  Yalla, time for a real career: running a big, beautiful countdown.</em>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%E2%80%933.14-blue">
  <img alt="PyQt6" src="https://img.shields.io/badge/GUI-PyQt6-41cd52">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows-0078d6">
  <img alt="Dependencies" src="https://img.shields.io/badge/dependencies-1%20bas-brightgreen">
</p>

---

You bought a cheap USB knob to nudge the volume up and down. Habibi, that knob is
overqualified. **Knob Timer** gives it a serious job: **twist** for minutes,
**press** to start, **hold** to reset. A giant clock takes over the screen so you
can read it from across the room — even over the neighbor's generator.

Twist it, slap it, watch the numbers, get things done. Khalas.

## What it does

- 🟢 **Four states you can read from the balcony:**
  - **Idle** — calm gray, twist to set the time
  - **Counting** — confident green, *masha*, everything's fine
  - **Paused** — a thoughtful orange
  - **Time's up** — a *violently* flashing red/black meltdown with a looping alarm.
    Consider it your polite **2awwis** before the deadline cuts you off.
- 🎚️ **The knob drives the timer, not your speakers.** While the app is focused it
  quietly intercepts the volume keys, so nothing touches your volume slider.
- 🤝 **Karam included:** switch to another app and it hands the knob right back.
  It knows when it's a guest.
- 🎨 **3a zaw2ak:** every color, the alarm sound, and the default minutes live in a
  friendly `config.json` — or just press `S` in the app.
- 📦 **Ships as one folder, zero Python.** Hand your friend the `KnobTimer`
  folder and they double-click. Ma fi ta32eed.

## Controls

| Do this | Get this |
|---|---|
| 🔄 **Rotate knob** | ± 1 minute |
| 👆 **Press knob** (tap) | start / pause / stop the alarm |
| ✊ **Hold knob** (~0.6s) | reset — back to your last set time |
| `Space` | start / pause |
| `↑ ↓` or `+ –` | ± 1 minute |
| `R` | reset · `S` settings · `F11` full screen · `Esc` windowed |

> No knob? Ma3lesh — every action has a keyboard twin. The knob is just more fun.

## Quick start

**Just want to use it →** grab the whole `KnobTimer` folder, open it, and
double-click `KnobTimer.exe`. W bass. (Drop an `alarm.mp3` next to the exe
first if you want a custom sound.)

**Running from source →**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install PyQt6          # that's the whole dependency list, wallah — one, bas
python knob_timer.py
```

**Building your own `.exe` →**

```powershell
pip install pyinstaller
.\venv\Scripts\pyinstaller.exe KnobTimer.spec --noconfirm
# → dist\KnobTimer\  (ship the whole folder, not just the exe)
```

> 🛡️ The build uses [`KnobTimer.spec`](KnobTimer.spec) on purpose: a **one-folder**
> bundle with **UPX off**. That's the recipe that gets past Windows **Smart App
> Control** — `--onefile` + UPX is exactly what it blocks. Don't go back to onefile.

See [`REBUILD.html`](REBUILD.html) for the illustrated version and
[`SHIP.md`](SHIP.md) for handing it to a friend.

## Configuration

`config.json` shows up on first launch. Tweak away, 3a raa7tak:

```json
{
    "idle_color": "#2E2E2E",
    "counting_color": "#2ECC71",
    "paused_color": "#E67E22",
    "alarm_color": "#E74C3C",
    "text_color": "#FFFFFF",
    "audio_file_path": "alarm.mp3",
    "default_minutes": 5
}
```

## Field notes (a.k.a. things that fought back)

Building this was a small odyssey. In case you're tempted down the same road —
inshallah you're not:

- 🧨 **`pygame` refuses to build on Python 3.14** — it keeps reaching for a
  `distutils` that packed up and left, mitl l-dawle. Audio now rides on **Qt
  Multimedia**, bundled inside PyQt6. One dependency, zero regrets.
- 💥 **`super().nativeEvent()` in PyQt6 doesn't throw — it hands you an access
  violation** and the app just vanishes, bala wda3. We return `(False, 0)` and live.
- 🕵️ **The knob doesn't send `WM_APPCOMMAND` like a polite media key** — it fires
  raw `VK_VOLUME_*` messages, and Windows changes the volume from its *own*
  low-level hook *before* any window sees the key. The fix: out-hook the hook with
  our own `WH_KEYBOARD_LL`. B'nar l-nar btintafe — fight fire with fire.

The full "why did we do it this way" trail lives in [`memory/`](memory/) — yes,
the robot took notes. Akhad l-mawdou3 3a jadd.

---

<p align="center"><sub>Rotate = ±1 min · Press = start/pause · Hold = reset · Your volume = bi amen Allah</sub></p>
