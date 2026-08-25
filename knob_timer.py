"""
Knob Timer
==========

A customizable full-screen visual timer designed to be driven by a cheap USB
"multimedia knob" (the kind that shows up to Windows as Volume Up / Volume Down /
Mute controls).

Most of these knobs send their commands as Windows ``WM_APPCOMMAND`` messages
(the standard mechanism for hardware media/volume keys), NOT as ordinary
keyboard scancodes. So instead of using a global keyboard hook, this app
intercepts ``WM_APPCOMMAND`` directly in the Qt window via ``nativeEvent`` and
*suppresses* the default Windows action (volume/mute) while the window is
focused. Because that message is only delivered to the focused window, the
suppression is automatically scoped to "while the app is in use" -- when the app
is in the background the knob controls Windows volume normally again.

Advantages of this approach: no administrator rights, no background listener
thread, no third-party keyboard library, and it captures both hardware knobs
*and* normal keyboard media keys.

Control mapping
---------------
    Rotate knob (Volume Up/Down) .... +/- 1 minute
    Press knob (Mute) ............... start / pause / stop-alarm  (toggle)
    Hold knob (~0.6s) ............... reset to last set value
    (Some devices report media keys as WM_APPCOMMAND instead of raw WM_KEY*
     messages; both are handled. WM_APPCOMMAND devices use a double-press for
     reset since that path can't measure hold duration.)

Keyboard fallbacks (for testing without the knob):
    Up / +  ......... +1 minute            Down / - ........ -1 minute
    Space ........... play / pause          D ............... reset (double-press)
    R ............... reset to idle         S ............... settings
    F11 ............. toggle full screen     Esc ............. leave full screen

Dependencies
------------
    pip install PyQt6

Audio uses Qt Multimedia (bundled inside the PyQt6 wheel), so there is no
separate audio dependency. It falls back to winsound beeps if Qt Multimedia or
the audio file is unavailable.
"""

import os
import sys
import time
import json
import ctypes
import threading
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout, QDialog,
    QFormLayout, QLineEdit, QSpinBox, QPushButton, QHBoxLayout, QFileDialog,
    QColorDialog, QMenu,
)

# --------------------------------------------------------------------------- #
#  Optional dependencies (imported defensively so the app degrades gracefully)
# --------------------------------------------------------------------------- #
try:
    # Qt Multimedia ships inside the PyQt6 wheel -> no extra dependency.
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtCore import QUrl
    _HAS_QTMEDIA = True
except Exception:  # pragma: no cover
    QMediaPlayer = QAudioOutput = QUrl = None
    _HAS_QTMEDIA = False

try:
    import winsound  # Windows-only fallback beeper
    _HAS_WINSOUND = True
except Exception:  # pragma: no cover
    winsound = None
    _HAS_WINSOUND = False


# --------------------------------------------------------------------------- #
#  Win32 constants for WM_APPCOMMAND handling
# --------------------------------------------------------------------------- #
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_APPCOMMAND = 0x0319

# Virtual-key codes for the media keys (the wParam of WM_KEYDOWN/WM_KEYUP).
# Many USB volume knobs emit these raw key messages rather than WM_APPCOMMAND.
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

# APPCOMMAND_* values live in the high word of lParam (used by some devices /
# by ordinary keyboard media keys instead of the raw WM_KEY* messages above).
APPCOMMAND_VOLUME_MUTE = 8
APPCOMMAND_VOLUME_DOWN = 9
APPCOMMAND_VOLUME_UP = 10
APPCOMMAND_MEDIA_PLAY_PAUSE = 14
APPCOMMAND_MEDIA_STOP = 13

# --------------------------------------------------------------------------- #
#  Low-level keyboard hook (WH_KEYBOARD_LL)
#
#  Windows changes the system volume for VK_VOLUME_* keys via its OWN low-level
#  hook, which fires *before* the key ever reaches our window. A normal window
#  message intercept is therefore too late to suppress it. Installing our own
#  WH_KEYBOARD_LL hook lets us swallow the key at that same earliest stage
#  (return 1 == "handled, stop propagation").
# --------------------------------------------------------------------------- #
WH_KEYBOARD_LL = 13
HC_ACTION = 0

_HAS_LLHOOK = False
if sys.platform == "win32":
    try:
        _user32 = ctypes.windll.user32
        _kernel32 = ctypes.windll.kernel32
        _LRESULT = ctypes.c_ssize_t
        # LowLevelKeyboardProc(nCode, wParam, lParam) -> LRESULT
        _HOOKPROC = ctypes.CFUNCTYPE(
            _LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),  # ULONG_PTR
            ]

        _user32.SetWindowsHookExW.restype = wintypes.HHOOK
        _user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        _user32.CallNextHookEx.restype = _LRESULT
        _user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        _user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        _user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        _user32.GetForegroundWindow.restype = wintypes.HWND
        _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        _user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        _HAS_LLHOOK = True
    except Exception as _exc:  # pragma: no cover
        print(f"[hook] low-level hook unavailable: {_exc}", file=sys.stderr)


# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #
CONFIG_DEFAULTS = {
    "idle_color": "#2E2E2E",      # plain dark gray
    "counting_color": "#2ECC71",  # bright green
    "paused_color": "#E67E22",    # orange
    "alarm_color": "#E74C3C",     # violent red (flashes against black)
    "text_color": "#FFFFFF",      # white digits
    "audio_file_path": "alarm.mp3",
    "default_minutes": 5,
}


def base_dir() -> Path:
    """Folder to store config/audio next to.

    When frozen by PyInstaller, ``__file__`` points into a temporary extraction
    directory, so we use the executable's folder instead -- that way config.json
    lives next to the shipped .exe where the user can find and edit it.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parent
    except NameError:  # pragma: no cover - interactive
        return Path.cwd()


def config_path() -> Path:
    """config.json lives next to the app (script, or .exe when frozen)."""
    return base_dir() / "config.json"


def load_config() -> dict:
    """Load config.json, creating it with defaults if missing or corrupt.

    Any missing keys are back-filled from CONFIG_DEFAULTS so upgrades are safe.
    """
    path = config_path()
    cfg = dict(CONFIG_DEFAULTS)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                user = json.load(fh)
            if isinstance(user, dict):
                cfg.update({k: user[k] for k in user if k in CONFIG_DEFAULTS})
        except (json.JSONDecodeError, OSError):
            # Corrupt file -> keep defaults but do not crash. We overwrite below.
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    """Write the config dict back to disk (pretty-printed for easy hand-editing)."""
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=4)
    except OSError as exc:  # pragma: no cover
        print(f"[config] could not save config.json: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------- #
#  Alarm sound (Qt Multimedia primary, winsound fallback)
# --------------------------------------------------------------------------- #
class AlarmSound:
    """Encapsulates looping alarm playback so the rest of the app is agnostic
    about *how* the noise is produced.

    Priority:
      1. Qt Multimedia (QMediaPlayer) looping the user's audio file (mp3/wav/ogg).
      2. winsound.Beep loop on a daemon thread (if the file/Qt Multimedia is missing).
    """

    def __init__(self):
        self._mode = None            # "qt" | "beep" | None
        self._beep_stop = threading.Event()
        self._beep_thread = None

        self._player = None
        self._audio_out = None
        if _HAS_QTMEDIA:
            try:
                self._player = QMediaPlayer()
                self._audio_out = QAudioOutput()
                self._audio_out.setVolume(1.0)
                self._player.setAudioOutput(self._audio_out)
                # Loop forever until we explicitly stop.
                self._player.setLoops(QMediaPlayer.Loops.Infinite)
            except Exception as exc:  # pragma: no cover
                print(f"[audio] Qt Multimedia init failed: {exc}", file=sys.stderr)
                self._player = None

    def start(self, audio_path: str) -> None:
        """Begin looping the alarm. Safe to call repeatedly (idempotent)."""
        if self._mode is not None:
            return  # already sounding

        path = Path(audio_path)
        if self._player is not None and path.exists():
            try:
                self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
                self._player.play()
                self._mode = "qt"
                return
            except Exception as exc:  # pragma: no cover
                print(f"[audio] Qt playback failed ({exc}); using beep.",
                      file=sys.stderr)

        # Fallback: synthesised beeping.
        self._start_beeper()

    def _start_beeper(self) -> None:
        self._mode = "beep"
        self._beep_stop.clear()
        self._beep_thread = threading.Thread(target=self._beep_loop, daemon=True)
        self._beep_thread.start()

    def _beep_loop(self) -> None:
        # Plain, dependency-light alarm: alternating tones until told to stop.
        while not self._beep_stop.is_set():
            if _HAS_WINSOUND:
                try:
                    winsound.Beep(880, 300)
                except Exception:
                    self._beep_stop.wait(0.3)
            else:  # last-ditch: terminal bell
                print("\a", end="", flush=True)
            self._beep_stop.wait(0.2)

    def stop(self) -> None:
        """Silence the alarm regardless of which backend is active."""
        if self._mode == "qt" and self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        elif self._mode == "beep":
            self._beep_stop.set()
            if self._beep_thread is not None:
                self._beep_thread.join(timeout=1.0)
        self._mode = None

    def shutdown(self) -> None:
        """Full cleanup on app exit."""
        self.stop()
        if self._player is not None:
            try:
                self._player.setSource(QUrl())  # release the file handle
            except Exception:
                pass


# --------------------------------------------------------------------------- #
#  Settings dialog (in-app editing of config.json)
# --------------------------------------------------------------------------- #
class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Knob Timer — Settings")
        self.cfg = dict(cfg)  # work on a copy; only commit on Save
        self.setMinimumWidth(420)

        form = QFormLayout(self)

        # Color pickers (each opens a QColorDialog and remembers the hex value).
        self._color_buttons = {}
        for key, label in (
            ("idle_color", "Idle background"),
            ("counting_color", "Counting background"),
            ("paused_color", "Paused background"),
            ("alarm_color", "Alarm background"),
            ("text_color", "Text color"),
        ):
            btn = QPushButton(self.cfg[key])
            btn.clicked.connect(lambda _=False, k=key: self._pick_color(k))
            self._style_color_button(btn, self.cfg[key])
            self._color_buttons[key] = btn
            form.addRow(label, btn)

        # Audio file chooser.
        audio_row = QHBoxLayout()
        self._audio_edit = QLineEdit(self.cfg["audio_file_path"])
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_audio)
        audio_row.addWidget(self._audio_edit)
        audio_row.addWidget(browse)
        form.addRow("Alarm sound", audio_row)

        # Default minutes.
        self._minutes_spin = QSpinBox()
        self._minutes_spin.setRange(0, 999)
        self._minutes_spin.setValue(int(self.cfg["default_minutes"]))
        form.addRow("Default minutes", self._minutes_spin)

        # Save / Cancel.
        buttons = QHBoxLayout()
        save = QPushButton("Save")
        cancel = QPushButton("Cancel")
        save.clicked.connect(self._on_save)
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        form.addRow(buttons)

    @staticmethod
    def _style_color_button(btn: QPushButton, hex_color: str) -> None:
        # Give the button a readable label + a swatch of the chosen color.
        text_col = "#000000" if QColor(hex_color).lightness() > 128 else "#FFFFFF"
        btn.setText(hex_color)
        btn.setStyleSheet(f"background-color: {hex_color}; color: {text_col};")

    def _pick_color(self, key: str) -> None:
        current = QColor(self.cfg[key])
        chosen = QColorDialog.getColor(current, self, "Choose color")
        if chosen.isValid():
            hex_color = chosen.name()
            self.cfg[key] = hex_color
            self._style_color_button(self._color_buttons[key], hex_color)

    def _pick_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose alarm sound", "",
            "Audio files (*.mp3 *.wav *.ogg);;All files (*.*)",
        )
        if path:
            self._audio_edit.setText(path)

    def _on_save(self) -> None:
        self.cfg["audio_file_path"] = self._audio_edit.text().strip()
        self.cfg["default_minutes"] = self._minutes_spin.value()
        self.accept()

    def result_config(self) -> dict:
        return self.cfg


# --------------------------------------------------------------------------- #
#  Main window / timer logic
# --------------------------------------------------------------------------- #
# State constants.
IDLE, COUNTING, PAUSED, ALARM = "IDLE", "COUNTING", "PAUSED", "ALARM"

VOLUME_DEBOUNCE_S = 0.015    # ignore rotate events closer than this (anti-flood)
DOUBLE_PRESS_S = 0.35        # two knob presses within this = "reset" gesture
MUTE_HOLD_S = 0.6            # holding the knob press this long = "reset" gesture
FLASH_INTERVAL_MS = 500      # alarm flash cadence
TICK_INTERVAL_MS = 100       # how often we recompute the remaining time


class KnobTimer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()

        # --- timer model ---------------------------------------------------- #
        self.state = IDLE
        self.set_seconds = int(self.cfg["default_minutes"]) * 60  # "last set value"
        self.remaining = self.set_seconds                          # what we display
        self._deadline_monotonic = None   # wall-clock target while counting (no drift)

        # --- input bookkeeping --------------------------------------------- #
        self._last_volume_ts = 0.0        # rotate debounce
        self._last_press_ts = 0.0         # knob-press double-tap detection (APPCOMMAND path)
        self._mute_down_ts = None         # knob-press hold detection (raw WM_KEY* path)

        # --- low-level keyboard hook state --------------------------------- #
        self._ll_hook = None              # HHOOK handle
        self._ll_proc_ptr = None          # keep the CFUNCTYPE alive (GC guard)
        self._pid = os.getpid()

        # --- audio ---------------------------------------------------------- #
        self.alarm = AlarmSound()

        self._build_ui()

        # --- Qt timers ------------------------------------------------------ #
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(TICK_INTERVAL_MS)
        self.countdown_timer.timeout.connect(self._on_tick)

        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(FLASH_INTERVAL_MS)
        self.flash_timer.timeout.connect(self._on_flash)
        self._flash_on = False

        self._render()

    # ------------------------------------------------------------------ UI -- #
    def _build_ui(self):
        self.setWindowTitle("Knob Timer")
        self.resize(720, 420)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.clock_label = QLabel("05:00", central)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Consolas")
        font.setBold(True)
        self.clock_label.setFont(font)
        layout.addWidget(self.clock_label)

        # Small hint / status line under the clock.
        self.hint_label = QLabel("", central)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_font = QFont("Consolas")
        hint_font.setPointSize(11)
        self.hint_label.setFont(hint_font)
        layout.addWidget(self.hint_label)

        # Right-click anywhere opens the settings menu.
        central.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        central.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Settings…", self.open_settings)
        menu.addAction("Toggle full screen (F11)", self.toggle_fullscreen)
        menu.addSeparator()
        menu.addAction("Quit", self.close)
        menu.exec(self.centralWidget().mapToGlobal(pos))

    def resizeEvent(self, event):
        # Scale the digits responsively so they always dominate the window.
        super().resizeEvent(event)
        size = max(24, min(self.width() // 5, self.height() // 2))
        f = self.clock_label.font()
        f.setPixelSize(size)
        self.clock_label.setFont(f)

    # -------------------------------------------------------------- render -- #
    def _format(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _current_bg(self) -> str:
        if self.state == IDLE:
            return self.cfg["idle_color"]
        if self.state == PAUSED:
            return self.cfg["paused_color"]
        if self.state == COUNTING:
            return self.cfg["counting_color"]
        # ALARM background is driven by the flash timer, handled in _on_flash.
        return self.cfg["alarm_color"]

    def _apply_bg(self, color: str):
        text = self.cfg["text_color"]
        self.centralWidget().setStyleSheet(f"background-color: {color};")
        self.clock_label.setStyleSheet(f"color: {text}; background: transparent;")
        self.hint_label.setStyleSheet(f"color: {text}; background: transparent;")

    def _render(self):
        """Repaint everything to match the current state + remaining time."""
        self.clock_label.setText(self._format(self.remaining))
        hints = {
            IDLE: "Rotate = set minutes · press = start",
            COUNTING: "Counting… · press = pause · hold = reset",
            PAUSED: "Paused · press = resume · hold = reset",
            ALARM: "TIME'S UP · press knob to stop & reset",
        }
        self.hint_label.setText(hints.get(self.state, ""))
        if self.state != ALARM:
            self._apply_bg(self._current_bg())

    # --------------------------------------------------------- transitions -- #
    def _enter_idle(self):
        self.state = IDLE
        self.countdown_timer.stop()
        self.flash_timer.stop()
        self.alarm.stop()
        self._deadline_monotonic = None
        self.remaining = self.set_seconds
        self._render()

    def _enter_counting(self):
        if self.remaining <= 0:
            return
        self.state = COUNTING
        self.flash_timer.stop()
        self.alarm.stop()
        # Anchor to a monotonic deadline so the countdown never drifts.
        self._deadline_monotonic = time.monotonic() + self.remaining
        self.countdown_timer.start()
        self._render()

    def _enter_paused(self):
        self.state = PAUSED
        self.countdown_timer.stop()
        self._deadline_monotonic = None
        self._render()

    def _enter_alarm(self):
        self.state = ALARM
        self.remaining = 0
        self.countdown_timer.stop()
        self._deadline_monotonic = None
        self._flash_on = True
        self.flash_timer.start()
        self._on_flash()  # paint immediately without waiting 500ms
        self.alarm.start(self.cfg["audio_file_path"])

    # -------------------------------------------------------- Qt tick/flash - #
    def _on_tick(self):
        if self.state != COUNTING or self._deadline_monotonic is None:
            return
        remaining = self._deadline_monotonic - time.monotonic()
        if remaining <= 0:
            self.remaining = 0
            self.clock_label.setText("00:00")
            self._enter_alarm()
            return
        # Show the ceiling so the very first second reads as the full value.
        self.remaining = int(remaining + 0.999)
        self.clock_label.setText(self._format(self.remaining))

    def _on_flash(self):
        # Violently alternate the whole background between alarm color and black.
        self._flash_on = not self._flash_on
        color = self.cfg["alarm_color"] if self._flash_on else "#000000"
        self._apply_bg(color)

    # ----------------------------------------------------- timer actions ---- #
    def volume_up(self):
        if self.state == ALARM or self._volume_debounced():
            return
        self._adjust(+60)

    def volume_down(self):
        if self.state == ALARM or self._volume_debounced():
            return
        self._adjust(-60)

    def _volume_debounced(self) -> bool:
        """True if this rotate event is too close to the previous one (drop it)."""
        now = time.monotonic()
        if now - self._last_volume_ts < VOLUME_DEBOUNCE_S:
            return True
        self._last_volume_ts = now
        return False

    def _adjust(self, delta_seconds: int):
        """Add/subtract a minute, clamped at zero, honoring the current state."""
        if self.state == IDLE:
            self.set_seconds = max(0, self.set_seconds + delta_seconds)
            self.remaining = self.set_seconds
        elif self.state in (COUNTING, PAUSED):
            self.remaining = max(0, self.remaining + delta_seconds)
            if self.state == COUNTING and self._deadline_monotonic is not None:
                self._deadline_monotonic = time.monotonic() + self.remaining
        self._render()

    def knob_press(self):
        """Single knob press (Mute key). A quick second press = reset gesture."""
        now = time.monotonic()
        if now - self._last_press_ts < DOUBLE_PRESS_S:
            # Second press within the window -> reset to the last set value.
            self._last_press_ts = 0.0  # consume, so a third press starts fresh
            self._reset_gesture()
        else:
            self._last_press_ts = now
            self._toggle()

    def _toggle(self):
        """Primary action: start / pause / resume / stop-alarm."""
        if self.state == IDLE:
            self._enter_counting()
        elif self.state == COUNTING:
            self._enter_paused()
        elif self.state == PAUSED:
            self._enter_counting()
        elif self.state == ALARM:
            self._enter_idle()  # stop alarm + reset

    def _reset_gesture(self):
        """Double-press: return to idle at the last set value (from any state)."""
        self._enter_idle()

    # --------------------------------------------- WM_APPCOMMAND interception #
    def nativeEvent(self, eventType, message):
        """Intercept hardware media/volume commands (WM_APPCOMMAND).

        Returning ``(True, 1)`` marks the message handled, which stops Windows
        from performing the default volume/mute action -- but only while THIS
        window is focused, since WM_APPCOMMAND is delivered to the focused
        window. When we're in the background, the message goes elsewhere and the
        knob behaves as a normal volume control.
        """
        # NOTE: never call super().nativeEvent() here -- doing so crashes PyQt6
        # with an access violation. For every message we don't consume we simply
        # return (False, 0), which tells Qt to continue its normal processing.
        try:
            try:
                et = bytes(eventType)
            except Exception:
                et = eventType
            if et == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                m = msg.message
                if m in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    # Raw media virtual-keys (how most USB knobs report).
                    if self._handle_media_vk_down(msg.wParam & 0xFFFF):
                        return True, 1
                elif m in (WM_KEYUP, WM_SYSKEYUP):
                    if self._handle_media_vk_up(msg.wParam & 0xFFFF):
                        return True, 1
                elif m == WM_APPCOMMAND:
                    # GET_APPCOMMAND_LPARAM: command is the high word minus flags.
                    cmd = (msg.lParam >> 16) & 0x0FFF
                    if self._handle_appcommand(cmd):
                        return True, 1  # suppress the default Windows action
        except Exception as exc:  # never let a bad message kill the event loop
            print(f"[nativeEvent] ignored error: {exc}", file=sys.stderr)
        return False, 0

    def _handle_media_vk_down(self, vk: int) -> bool:
        """Raw WM_KEYDOWN for a media key. Return True if consumed (suppressed)."""
        if vk == VK_VOLUME_UP:
            self.volume_up()
        elif vk == VK_VOLUME_DOWN:
            self.volume_down()
        elif vk == VK_VOLUME_MUTE:
            # Start timing the press; ignore auto-repeat "downs" while held.
            if self._mute_down_ts is None:
                self._mute_down_ts = time.monotonic()
        else:
            return False
        return True

    def _handle_media_vk_up(self, vk: int) -> bool:
        """Raw WM_KEYUP for a media key. Return True if consumed (suppressed)."""
        if vk in (VK_VOLUME_UP, VK_VOLUME_DOWN):
            return True  # already acted on key-down; just swallow the release
        if vk == VK_VOLUME_MUTE:
            if self._mute_down_ts is not None:
                held = time.monotonic() - self._mute_down_ts
                self._mute_down_ts = None
                # A long hold resets; a quick tap toggles start/pause/stop.
                if held >= MUTE_HOLD_S:
                    self._reset_gesture()
                else:
                    self._toggle()
            return True
        return False

    def _handle_appcommand(self, cmd: int) -> bool:
        """Map an APPCOMMAND_* value to a timer action. Return True if consumed."""
        if cmd == APPCOMMAND_VOLUME_UP:
            self.volume_up()
        elif cmd == APPCOMMAND_VOLUME_DOWN:
            self.volume_down()
        elif cmd in (APPCOMMAND_VOLUME_MUTE, APPCOMMAND_MEDIA_PLAY_PAUSE):
            self.knob_press()
        elif cmd == APPCOMMAND_MEDIA_STOP:
            self._enter_idle()
        else:
            return False  # not ours -> let Windows handle it normally
        return True

    # ------------------------------------------- low-level keyboard hook ---- #
    def showEvent(self, event):
        super().showEvent(event)
        self._install_ll_hook()

    def _install_ll_hook(self):
        """Install the global WH_KEYBOARD_LL hook (once). Non-fatal on failure."""
        if not _HAS_LLHOOK or self._ll_hook:
            return
        # Keep a reference to the CFUNCTYPE wrapper or it will be garbage
        # collected and the callback pointer will dangle -> crash.
        self._ll_proc_ptr = _HOOKPROC(self._ll_keyboard_proc)
        hmod = _kernel32.GetModuleHandleW(None)
        self._ll_hook = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._ll_proc_ptr, hmod, 0)
        if not self._ll_hook:
            err = ctypes.get_last_error()
            self._ll_hook = None
            self.hint_label.setText(
                "⚠ Could not install the volume-key hook — knob will still move "
                "Windows volume. (Keyboard controls work.)")
            print(f"[hook] SetWindowsHookExW failed (err={err})", file=sys.stderr)

    def _remove_ll_hook(self):
        if self._ll_hook:
            try:
                _user32.UnhookWindowsHookEx(self._ll_hook)
            except Exception:
                pass
        self._ll_hook = None
        self._ll_proc_ptr = None

    def _app_is_foreground(self) -> bool:
        """True if the foreground window belongs to THIS process.

        This is how we scope suppression to "while the app is in use": when any
        other application is in front, we let the knob control Windows volume.
        """
        try:
            fg = _user32.GetForegroundWindow()
            if not fg:
                return False
            pid = wintypes.DWORD(0)
            _user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            return pid.value == self._pid
        except Exception:
            return False

    def _ll_keyboard_proc(self, nCode, wParam, lParam):
        """The low-level hook callback (runs on the GUI thread during message
        pumping, so it may touch widgets directly)."""
        try:
            if nCode == HC_ACTION and self._app_is_foreground():
                kb = KBDLLHOOKSTRUCT.from_address(lParam)
                vk = kb.vkCode
                if vk in (VK_VOLUME_UP, VK_VOLUME_DOWN, VK_VOLUME_MUTE):
                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        self._handle_media_vk_down(vk)
                    elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                        self._handle_media_vk_up(vk)
                    return 1  # swallow the key: no volume change, no propagation
        except Exception as exc:  # never break the global keyboard pipeline
            print(f"[hook] ignored error: {exc}", file=sys.stderr)
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    # ---------------------------------------------------- keyboard fallback - #
    def keyPressEvent(self, event):
        """Keyboard controls so the app is fully usable without the knob."""
        key = event.key()
        # Allow rotate keys to auto-repeat; ignore repeats for one-shot actions.
        repeat_ok = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Plus,
                     Qt.Key.Key_Minus, Qt.Key.Key_Equal)
        if event.isAutoRepeat() and key not in repeat_ok:
            return

        if key == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.volume_up()
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Minus):
            self.volume_down()
        elif key == Qt.Key.Key_Space:
            self._toggle()
        elif key == Qt.Key.Key_D:
            self._reset_gesture()   # simulate a knob double-press
        elif key == Qt.Key.Key_R:
            self._enter_idle()
        elif key == Qt.Key.Key_S:
            self.open_settings()
        else:
            super().keyPressEvent(event)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------ settings - #
    def open_settings(self):
        dialog = SettingsDialog(self.cfg, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.cfg = dialog.result_config()
            save_config(self.cfg)
            # If we're idle, adopt the new default immediately.
            if self.state == IDLE:
                self.set_seconds = int(self.cfg["default_minutes"]) * 60
                self.remaining = self.set_seconds
            self._render()

    # ----------------------------------------------------------- shutdown -- #
    def closeEvent(self, event):
        # Robust cleanup: unhook, stop timers and all audio before exiting.
        self._remove_ll_hook()
        self.countdown_timer.stop()
        self.flash_timer.stop()
        self.alarm.shutdown()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = KnobTimer()
    window.show()
    # Belt-and-suspenders cleanup for unusual exit paths.
    app.aboutToQuit.connect(window._remove_ll_hook)
    exit_code = app.exec()
    window._remove_ll_hook()
    window.alarm.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
