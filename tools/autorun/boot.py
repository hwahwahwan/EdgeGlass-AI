"""EdgeGlass-AI board boot stage -- deploys to /sdcard/boot.py.

Standard MicroPython semantics: boot.py runs first on every power-up
(before /sdcard/main.py), with or without a USB data connection. Kept
intentionally minimal: no camera/AI/Wi-Fi/OLED here, and no blocking
delay here either -- a crash this early, before main.py's own interrupt
window even prints anything, would be a worse failure mode to debug.

The real launch logic, the interruptible countdown, and the
/sdcard/SAFE_MODE override all live in /sdcard/main.py (see
tools/autorun/main.py) instead -- see that file's docstring and
tools/autorun/README.md for the full recovery story.
"""

print("[BOOT] EdgeGlass-AI boot.py OK")
