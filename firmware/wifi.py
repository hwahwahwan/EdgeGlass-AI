"""Shared Wi-Fi STA connection helper for smart_glass_server.py.

Ported from the real-hardware-verified experiments/wifi_test/net.py
(see experiments/wifi_test/WIFI_TEST_REPORT.md Section 0, items 2-3) rather
than reimplemented, so both the web server and the UDP mouse transport
reuse the exact same already-tested connect-once-then-wait behavior instead
of each growing their own Wi-Fi connection logic.
"""

import network
import time


def connect_if_needed(networks, timeout_s=30):
    """Return (wlan, ifconfig, ssid) for the STA interface, connecting only if needed.

    ``networks`` is an ordered list of ``(ssid, password)`` pairs -- e.g.
    home Wi-Fi first, phone hotspot as a fallback. Each candidate is tried
    in turn, falling through to the next on a connect error or a per-network
    timeout; an entry whose ssid is falsy is skipped (so an unfilled slot in
    wifi_credentials.py needs no special-casing by the caller). ``ssid`` in
    the return value is the one that actually succeeded (``None`` if the
    link was already connected from before -- see below).

    If the interface is already connected (e.g. a prior connect survived a
    soft reboot -- confirmed real-hardware behavior on this board), this
    returns immediately without touching the existing connection or trying
    any candidate. That is what lets the web server and the UDP mouse
    transport share one Wi-Fi link: whichever feature runs this first
    performs the real connect, and the other sees ``isconnected() == True``
    and reuses it as-is.

    IMPORTANT (confirmed by diagnostic testing on this exact board): call
    wlan.connect() only ONCE per network, then wait passively. The
    association/handshake can legitimately take longer than a few seconds;
    calling connect() again while one is still in progress aborts it and
    makes every attempt look like a failure even though a single patient
    wait succeeds. This still holds per candidate below.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan, wlan.ifconfig(), None

    last_error = None
    for ssid, password in networks:
        if not ssid:
            continue
        try:
            wlan.connect(ssid, password)
        except OSError as exc:
            last_error = exc
            continue
        deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
        while not wlan.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                last_error = OSError(
                    "wifi connect timeout after %ds (ssid=%r)" % (timeout_s, ssid)
                )
                break
            time.sleep_ms(500)
        if wlan.isconnected():
            return wlan, wlan.ifconfig(), ssid

    raise last_error or OSError(
        "Wi-Fi is not connected and no ssid configured "
        "(fill in firmware/wifi_credentials.py)"
    )
