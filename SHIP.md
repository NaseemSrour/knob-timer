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

## 🚀 Option A — Give them the built folder (recommended)

Your friend needs **no Python, no install**. You build once, hand them one folder.

**On your machine (in the venv):**

```powershell
pip install pyinstaller
.\venv\Scripts\pyinstaller.exe KnobTimer.spec --noconfirm
```

The app lands in **`dist\KnobTimer\`** as a one-folder bundle. Ship the **whole
folder** (zip it), which looks like:

```
📁 KnobTimer
 ├── KnobTimer.exe      ← the app (double-click this)
 ├── _internal\         ← its runtime — must stay next to the exe
 └── alarm.mp3          ← optional: your alarm sound (any .mp3/.wav)
```

`config.json` is created automatically inside that folder on first run.

**On their machine:**

1. **Unblock the zip first** — right-click the copied `.zip` → **Properties** →
   tick **☑ Unblock** (bottom) → **Apply**. *Then* extract.
2. Open the folder, double-click `KnobTimer.exe`. That's it.

> ⚠️ **Don't skip the Unblock step.** A zip copied from another PC tags every
> extracted file with a "came from another computer" mark. Skip it and Windows
> **Smart App Control** blocks the app — especially when launched via a desktop
> shortcut. Already extracted without unblocking? Run this once in PowerShell:
> ```powershell
> Get-ChildItem "C:\path\to\KnobTimer" -Recurse | Unblock-File
> ```
> Making a desktop shortcut? Set its **"Start in"** field to the `KnobTimer`
> folder so the exe always finds `_internal\`.

> 🛡️ **Why a folder and not `--onefile`?** A one-folder build with **UPX off**
> (defined in [`KnobTimer.spec`](KnobTimer.spec)) is what clears Windows **Smart App
> Control** — the stricter successor to SmartScreen that **can't be waved through per
> app**. A `--onefile` + UPX build self-extracts to temp and gets blocked. This is the
> same recipe the tui-inventory build used to run on the same machine.
>
> 💡 Plain SmartScreen may still warn ("unknown publisher") → **More info → Run
> anyway**. Some antivirus may flag the keyboard hook — false positive (the hook is
> what suppresses the volume keys). If Smart App Control *still* blocks it, the only
> hard fix is code-signing the exe (e.g. Azure Trusted Signing).

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
