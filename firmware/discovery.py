"""Board-side UDP peer discovery: find the Mac bridge without a hardcoded IP.

Problem this solves: a phone hotspot hands out a fresh IP to the Mac on
every reconnect, so a fixed MOUSE_UDP_HOST in config.py goes stale and
mouse packets silently vanish into a dead address (UDP has no error for
"nobody is listening there"). Instead, the board repeatedly probes every
host address on its own subnet with a tiny "@HELLO|<id>" datagram; the Mac
bridge (mac_mouse_bridge.py) replies "@ACK|<id>" to whichever address the
probe actually arrived from (mac/mac_mouse_bridge.py's existing recvfrom()
already gets the real sender address for free). Whichever reply arrives
first tells the board exactly where the Mac is, no broadcast support
required -- this also means the Mac's IP changing (new hotspot session)
self-heals the next time the board re-announces.

Kept free of machine/network imports so it is importable and unit-testable
under plain CPython; the board-only bits (ifconfig, the real socket) are
supplied by the caller (smart_glass_server.py) rather than fetched here.
"""

import time

HELLO_PREFIX = "@HELLO|"
ACK_PREFIX = "@ACK|"

DEFAULT_MAX_SCAN_HOSTS = 64
DEFAULT_SCAN_INTERVAL_MS = 2000
DEFAULT_REANNOUNCE_INTERVAL_MS = 5000


def _ip_to_int(ip):
    parts = [int(part) for part in ip.split(".")]
    value = 0
    for part in parts:
        value = (value << 8) | part
    return value


def _int_to_ip(value):
    return "%d.%d.%d.%d" % (
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    )


def compute_scan_targets(ip, netmask, max_hosts=DEFAULT_MAX_SCAN_HOSTS):
    """Return every other host address on ip's subnet, own address excluded.

    Returns [] (instead of a huge list) when the subnet has more than
    ``max_hosts`` candidates, so a caller can fall back to a manually
    configured address rather than flood a large network with probes --
    this is the "자동 탐색 실패 시 수동 목적지 설정 대안" fallback point.
    """
    ip_int = _ip_to_int(ip)
    mask_int = _ip_to_int(netmask)
    network = ip_int & mask_int
    inverse = (~mask_int) & 0xFFFFFFFF
    host_count = inverse - 1  # exclude network and broadcast addresses
    if host_count <= 0:
        return []
    if host_count > max_hosts:
        return []
    targets = []
    for offset in range(1, inverse):
        candidate = network + offset
        if candidate == ip_int:
            continue
        targets.append(_int_to_ip(candidate))
    return targets


class UdpRegistry:
    """Finds and remembers the Mac bridge's (ip, port) on an unconnected socket.

    ``step()`` is meant to be called once per orchestrator loop iteration.
    It only ever does non-blocking socket calls and sends at most one burst
    of probes per call, so it cannot stall the AI inference loop even while
    no peer has been found yet.
    """

    def __init__(self, sock, targets, discovery_port,
                 scan_interval_ms=DEFAULT_SCAN_INTERVAL_MS,
                 reannounce_interval_ms=DEFAULT_REANNOUNCE_INTERVAL_MS,
                 hello_id="k230"):
        self.sock = sock
        self.targets = list(targets)
        self.discovery_port = discovery_port
        self.scan_interval_ms = scan_interval_ms
        self.reannounce_interval_ms = reannounce_interval_ms
        self.hello_id = hello_id

        self.peer = None  # (ip, port) once a Mac bridge has ACKed
        self.last_probe_ms = None
        self.on_registered = None  # optional callback(peer) set by caller

    def _send_probe_burst(self):
        hello = (HELLO_PREFIX + self.hello_id + "\r\n").encode()
        for ip in self.targets:
            try:
                self.sock.sendto(hello, (ip, self.discovery_port))
            except OSError:
                # One unreachable candidate must not stop the rest of the
                # burst or bubble up into the gesture loop.
                pass

    def step(self, now_ms=None):
        """Drain one pending reply (if any) and probe again if it's time."""
        if now_ms is None:
            now_ms = time.ticks_ms()

        try:
            data, addr = self.sock.recvfrom(256)
        except OSError:
            data = None
            addr = None

        if data:
            # This board's MicroPython bytes.decode() rejects keyword args
            # (TypeError: function doesn't take keyword arguments) -- confirmed
            # on real hardware 2026-10-23. The positional form works fine.
            text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
            if text.startswith(ACK_PREFIX):
                previous_peer = self.peer
                self.peer = addr
                if previous_peer != self.peer and self.on_registered is not None:
                    self.on_registered(self.peer)

        interval = (
            self.reannounce_interval_ms if self.peer is not None
            else self.scan_interval_ms
        )
        due = (
            self.last_probe_ms is None
            or time.ticks_diff(now_ms, self.last_probe_ms) >= interval
        )
        if due and self.targets:
            self._send_probe_burst()
            self.last_probe_ms = now_ms

    def destination(self):
        return self.peer
