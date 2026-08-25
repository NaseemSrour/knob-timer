"""
Knob probe
==========

Diagnostic helper for figuring out what your USB knob actually sends.

Run it, click the window to focus it, then:
  1. Rotate the knob up a few clicks.
  2. Rotate the knob down a few clicks.
  3. Press the knob once.
  4. Press-and-hold the knob for ~1 second.

It logs BOTH ways a knob might talk to Windows:
  * WM_APPCOMMAND messages (the usual mechanism for media/volume controls), and
  * raw WM_KEYDOWN / WM_KEYUP virtual-key codes (some knobs send these instead).

Whatever shows up (or if NOTHING shows up while the volume still changes) tells
us how to map / suppress the knob. Copy the output here.

    python key_probe.py
"""

import sys
import time
from ctypes import wintypes

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPlainTextEdit, QWidget, QVBoxLayout,
)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_APPCOMMAND = 0x0319

MSG_NAMES = {
    WM_KEYDOWN: "WM_KEYDOWN", WM_KEYUP: "WM_KEYUP",
    WM_SYSKEYDOWN: "WM_SYSKEYDOWN", WM_SYSKEYUP: "WM_SYSKEYUP",
    WM_APPCOMMAND: "WM_APPCOMMAND",
}

# Virtual-key codes of interest (for the WM_KEY* path).
VK_NAMES = {
    0xAD: "VK_VOLUME_MUTE", 0xAE: "VK_VOLUME_DOWN", 0xAF: "VK_VOLUME_UP",
    0xB3: "VK_MEDIA_PLAY_PAUSE", 0xB2: "VK_MEDIA_STOP",
    0xB0: "VK_MEDIA_NEXT_TRACK", 0xB1: "VK_MEDIA_PREV_TRACK",
}

# APPCOMMAND_* names (for the WM_APPCOMMAND path).
APPCOMMAND_NAMES = {
    8: "VOLUME_MUTE", 9: "VOLUME_DOWN", 10: "VOLUME_UP",
    11: "MEDIA_NEXTTRACK", 12: "MEDIA_PREVIOUSTRACK", 13: "MEDIA_STOP",
    14: "MEDIA_PLAY_PAUSE", 46: "MEDIA_PLAY", 47: "MEDIA_PAUSE",
}


class Probe(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Knob Probe — focus me, then use the knob")
        self.resize(680, 460)
        self._t0 = time.monotonic()
        self._count = 0

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.header = QLabel(
            "Focus this window, then rotate / press / hold the knob.\n"
            "WM_APPCOMMAND and raw volume WM_KEY* messages are logged below.",
            central)
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.header)

        self.log = QPlainTextEdit(central)
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

    def _emit(self, text: str):
        self._count += 1
        dt = time.monotonic() - self._t0
        line = f"[{dt:7.3f}s] #{self._count:03d}  {text}"
        self.log.appendPlainText(line)
        print(line, flush=True)

    def nativeEvent(self, eventType, message):
        # IMPORTANT: never call super().nativeEvent in PyQt6 (it crashes).
        try:
            try:
                et = bytes(eventType)
            except Exception:
                et = eventType
            if et == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                m = msg.message
                if m == WM_APPCOMMAND:
                    cmd = (msg.lParam >> 16) & 0x0FFF
                    name = APPCOMMAND_NAMES.get(cmd, "UNKNOWN")
                    self._emit(f"WM_APPCOMMAND   cmd={cmd:<3} {name}")
                elif m in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
                    vk = msg.wParam & 0xFFFF
                    # Only report the volume/media virtual keys, ignore normal typing.
                    if vk in VK_NAMES:
                        self._emit(f"{MSG_NAMES[m]:<13} vk=0x{vk:02X} "
                                   f"{VK_NAMES[vk]}")
        except Exception as exc:
            print(f"[probe] error: {exc}", file=sys.stderr)
        return False, 0


def main():
    app = QApplication(sys.argv)
    w = Probe()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
