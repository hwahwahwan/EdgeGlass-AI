"""CanMV IDE entry point: Wi-Fi(UDP) mouse control + web streaming on.

Run this file directly in CanMV IDE to demo the Wi-Fi path (unverified on
real hardware -- see experiments/wifi_test/WIFI_TEST_REPORT.md). All AI
inference, gesture recognition, and mouse-control logic live in
smart_glass_server.py; this file only pins that run profile. Fill in
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
    smart_glass_server.main(transport_kind="udp", enable_web=True)
