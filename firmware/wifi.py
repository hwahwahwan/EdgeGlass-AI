"""Shared Wi-Fi STA connection helper for smart_glass_server.py.

Ported from the real-hardware-verified experiments/wifi_test/net.py
(see experiments/wifi_test/WIFI_TEST_REPORT.md Section 0, items 2-3) rather
than reimplemented, so both the web server and the UDP mouse transport
reuse the exact same already-tested connect-once-then-wait behavior instead
of each growing their own Wi-Fi connection logic.
"""

import network
import time


def connect_if_needed(networks, timeout_s=30, on_progress=None):
    """Return (wlan, ifconfig, ssid) for the STA interface, connecting only if needed.

    ``networks`` is an ordered list of ``(ssid, password)`` pairs -- e.g.
    home Wi-Fi first, phone hotspot as a fallback. Each candidate is tried
    in turn, falling through to the next on a connect error, a driver
    rejection, or a per-network timeout; an entry whose ssid is falsy is
    skipped (so an unfilled slot in wifi_credentials.py needs no
    special-casing by the caller). ``ssid`` in the return value is the one
    that actually succeeded (``None`` if the link was already connected
    from before -- see below).

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

    ``on_progress(message)``, if given, is called with a short status
    string as each candidate is tried/fails, so a caller can show the user
    what is happening and why instead of going silent for the whole
    (sometimes tens-of-seconds-long) attempt.

    IMPORTANT (confirmed on real hardware 2026-10-23): ``wlan.connect()``
    itself returns ``False`` (rather than raising, and without
    ``isconnected()`` ever turning True) when this board's driver rejects a
    candidate outright -- e.g. a wrong password or an unsupported security
    mode. The original version of this function ignored that return value
    and always fell through to the ``isconnected()`` wait/timeout loop
    below, silently wasting the full ``timeout_s`` on a candidate that had
    already failed. Checking it here skips straight to the next candidate.
    """
    def _report(message):
        if on_progress is not None:
            on_progress(message)

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan, wlan.ifconfig(), None

    last_error = None
    for ssid, password in networks:
        if not ssid:
            continue
        _report("connecting to %r..." % (ssid,))
        try:
            result = wlan.connect(ssid, password)
        except OSError as exc:
            last_error = exc
            _report("%r raised %r, trying next network" % (ssid, exc))
            continue
        if result is False:
            last_error = OSError(
                "wifi connect rejected by driver (ssid=%r) -- check the "
                "password and security mode in wifi_credentials.py" % (ssid,)
            )
            _report("%r rejected by the Wi-Fi driver (wrong password or "
                     "unsupported security mode?), trying next network" % (ssid,))
            continue
        deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
        while not wlan.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                last_error = OSError(
                    "wifi connect timeout after %ds (ssid=%r)" % (timeout_s, ssid)
                )
                _report("%r timed out after %ds, trying next network" % (ssid, timeout_s))
                break
            time.sleep_ms(500)
        if wlan.isconnected():
            _report("connected to %r" % (ssid,))
            return wlan, wlan.ifconfig(), ssid

    raise last_error or OSError(
        "Wi-Fi is not connected and no ssid configured "
        "(fill in firmware/wifi_credentials.py)"
    )
