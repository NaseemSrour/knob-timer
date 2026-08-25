---
name: pyqt6-nativeevent-super-crash
description: PyQt6 nativeEvent must not call super() — it causes an access-violation crash
metadata:
  type: reference
---

In PyQt6, overriding `QWidget.nativeEvent(self, eventType, message)` and ending with `return super().nativeEvent(eventType, message)` causes a **Windows fatal access violation** inside the event loop (crashes the instant native messages start flowing). Because `nativeEvent` runs for *every* Windows message, the app dies before its window even appears.

Fix: never call super; for messages you don't consume, return `(False, 0)`. Return `(True, 1)` to mark a message handled (e.g. to suppress the default Windows action for a `WM_APPCOMMAND`). Wrap the body in try/except so a malformed message can't kill the loop.

Debugging note: an offscreen Qt platform (`QT_QPA_PLATFORM=offscreen`) generates no native messages, so it will NOT reproduce this — must test on the real `windows` platform, e.g. with `python -X faulthandler`.

Relevant to [[knob-timer-project]].
