"""CanMV IDE entry point: USB(UART) mouse control, web/Wi-Fi off.

Run this file directly in CanMV IDE to demo the verified UART-only path.
All AI inference, gesture recognition, and mouse-control logic live in
smart_glass_server.py; this file only pins that run profile so nothing in
firmware/config.py needs to be edited to switch modes. No Wi-Fi connection
is attempted in this mode.
"""

import sys

# CanMV's default sys.path does not include the directory this script is
# running from (unlike CPython, which adds it automatically) -- same reason
# main.py and smart_glass_server.py both do this before their own flat
# imports. Without it, `import smart_glass_server` fails with
# "ImportError: no module named 'smart_glass_server'" even though the file
# is sitting right next to this one on the SD card.
PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import smart_glass_server

if __name__ == "__main__":
    smart_glass_server.main(transport_kind="uart", enable_web=False)
