"""CanMV IDE entry point: USB(UART) mouse control + Wi-Fi web streaming on.

Run this file directly in CanMV IDE to demo UART mouse control (the
verified path, see run_uart.py) together with the Wi-Fi web server
(/snapshot, /stream) at the same time -- the combination run_uart.py
(web off) and run_wifi.py (mouse over UDP instead of UART) don't cover.
All AI inference, gesture recognition, OLED skeleton display, and
mouse-control logic live in smart_glass_server.py; this file only pins
that run profile (transport_kind="uart", enable_web=True). Fill in
firmware/wifi_credentials.py with the real SSID/PASSWORD first --
wifi.connect_if_needed() reuses an already-connected link as-is and only
connects if nothing is connected yet.
"""

import sys

# See run_uart.py for why this is required: CanMV does not add this
# script's own directory to sys.path, so the flat `import smart_glass_server`
# below would otherwise fail with "no module named 'smart_glass_server'".
PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import smart_glass_server

if __name__ == "__main__":
    smart_glass_server.main(transport_kind="uart", enable_web=True)
