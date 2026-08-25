---
name: knob-timer-project
description: Knob Timer — PyQt6 visual timer driven by a USB volume knob via WM_APPCOMMAND
metadata:
  type: project
---

`knob_timer.py` is a single-file PyQt6 full-screen visual timer (IDLE gray / COUNTING green / ALARM flashing red) meant to be controlled by a cheap USB "multimedia knob".

Key hardware fact (confirmed via `key_probe.py`): the user's knob sends **raw WM_KEYDOWN/WM_KEYUP virtual-keys** — VK_VOLUME_UP=0xAF, VK_VOLUME_DOWN=0xAE, VK_VOLUME_MUTE=0xAD — NOT WM_APPCOMMAND and NOT the `keyboard` library's scancodes (that lib never saw it; removed). Volume up/down do not auto-repeat (one down+up per detent); the mute press DOES report a real key-down→key-up duration, so hold-vs-tap works. Input is intercepted in `nativeEvent` (see [[pyqt6-nativeevent-super-crash]]) which returns `(True, 1)` to suppress; this auto-scopes to when the window is focused. Mapping: rotate = ±1 min, press (mute) tap = start/pause/stop, **hold ~0.6s = reset**. WM_APPCOMMAND handling is also kept for other devices (those use double-press for reset). `key_probe.py` logs both WM_APPCOMMAND and raw volume WM_KEY* messages.

RESOLVED 2026-08-24: returning `(True,1)` from nativeEvent for WM_KEYDOWN did NOT suppress volume — Windows changes volume via its own low-level hook that fires before the window proc. Fix: install our own **WH_KEYBOARD_LL hook** via ctypes (SetWindowsHookExW), return 1 to swallow VK_VOLUME_* keys. Scoped to "while the app is in use" by checking in the hook callback that `GetForegroundWindow`'s owning PID == our PID (so the knob still controls Windows volume when other apps are focused). The CFUNCTYPE wrapper must be kept referenced on the instance or it gets GC'd and the callback pointer dangles → crash. Hook installed in `showEvent`, removed in `closeEvent`/`aboutToQuit`. nativeEvent WM_KEY*/WM_APPCOMMAND handling kept as backup for when the LL hook can't install.

Environment: Windows, **Python 3.14** in a venv at `venv/`. `pygame` will NOT install on 3.14 (no wheel; source build fails on removed distutils) — audio therefore uses **Qt Multimedia** (bundled in the PyQt6 wheel), winsound beep fallback. Only dependency: `PyQt6`. User wants packages in the venv only, not global. Run with the venv activated: `python knob_timer.py`.
