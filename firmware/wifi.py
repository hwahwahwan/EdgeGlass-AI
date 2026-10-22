"""Shared Wi-Fi STA connection helper for smart_glass_server.py.

Ported from the real-hardware-verified experiments/wifi_test/net.py
(see experiments/wifi_test/WIFI_TEST_REPORT.md Section 0, items 2-3) rather
than reimplemented, so both the web server and the UDP mouse transport
reuse the exact same already-tested connect-once-then-wait behavior instead
of each growing their own Wi-Fi connection logic.
"""

import network
import time


def connect_if_needed(ssid=None, password=None, timeout_s=30):
    """Return (wlan, ifconfig) for the STA interface, connecting only if needed.

    If the interface is already connected (e.g. a prior connect survived a
    soft reboot -- confirmed real-hardware behavior on this board), this
    returns immediately without touching the existing connection. That is
    what lets the web server and the UDP mouse transport share one Wi-Fi
    link: whichever feature runs this first performs the real connect, and
    the other sees ``isconnected() == True`` and reuses it as-is.

    IMPORTANT (confirmed by diagnostic testing on this exact board): call
    wlan.connect() only ONCE, then wait passively. The association/handshake
    can legitimately take longer than a few seconds; calling connect() again
    while one is still in progress aborts it and makes every attempt look
    like a failure even though a single patient wait succeeds.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan, wlan.ifconfig()

    if not ssid:
        raise OSError(
            "Wi-Fi is not connected and no ssid configured "
            "(fill in firmware/wifi_credentials.py)"
        )

    wlan.connect(ssid, password)
    deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError("wifi connect timeout after %ds" % timeout_s)
        time.sleep_ms(500)
    return wlan, wlan.ifconfig()
