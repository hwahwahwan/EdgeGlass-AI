import network
import time


def connect(ssid, password, timeout_s=30):
    # IMPORTANT (confirmed by diagnostic testing): call wlan.connect() only
    # ONCE, then wait passively. The association/handshake can legitimately
    # take longer than a few seconds; calling connect() again while one is
    # still in progress aborts it and makes every attempt look like a
    # failure even though a single patient wait succeeds. An earlier version
    # of this function retried connect() every few seconds and reproduced a
    # 100% failure rate for that exact reason.
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan.ifconfig()
    wlan.connect(ssid, password)
    deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError("wifi connect timeout after %ds" % timeout_s)
        time.sleep_ms(500)
    return wlan.ifconfig()
