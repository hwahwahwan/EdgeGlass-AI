"""Pluggable @MOUSE transports for MouseController: UART2 (verified) and UDP/Wi-Fi.

Both transports expose the same minimal interface used by MouseController:
``write(message)`` and ``close()``. The @MOUSE/@TRACK protocol text itself is
unchanged between transports; only how the bytes leave the board differs.
"""

import time
from machine import UART

import discovery


class UartTransport:
    """Existing verified path: BPI-CanMV-K230D-Zero UART2 (CH342K bridge)."""

    def __init__(self, uart=None):
        # Physically connected to the verified CH342K USB Dual_Serial data
        # port (macOS: cu.usbmodem58930597043). Leaves the CanMV USB CDC/IDE
        # channel untouched.
        self.uart = uart or UART(
            UART.UART2,
            baudrate=115200,
            bits=UART.EIGHTBITS,
            parity=UART.PARITY_NONE,
            stop=UART.STOPBITS_ONE
        )

    def write(self, message):
        self.uart.write(message)

    def close(self):
        self.uart.deinit()


class UdpTransport:
    """Unverified path: send the same protocol text as UDP datagrams.

    Fire-and-forget by design -- a lost MOVE/DRAG packet must not raise out
    of the gesture loop. Connection loss / DRAG safety is handled on the
    receiving (Mac) side by a timeout watchdog, not here.
    """

    def __init__(self, host, port, retry_attempts=20, retry_delay_ms=500,
                 socket_module=None):
        self._socket_module = socket_module or __import__("socket")
        self.sock = self._connect(host, port, retry_attempts, retry_delay_ms)

    def _connect(self, host, port, retry_attempts, retry_delay_ms):
        # Real-hardware finding (experiments/wifi_test/WIFI_TEST_REPORT.md
        # §0.3, §3-E): right after a soft reboot, wlan.isconnected() can
        # already be True while the socket layer has not yet registered the
        # NIC, so socket()/connect() raises OSError('no available NIC') for a
        # short window. Retrying a few hundred ms apart clears it.
        last_error = None
        for _ in range(retry_attempts):
            try:
                sock = self._socket_module.socket(
                    self._socket_module.AF_INET, self._socket_module.SOCK_DGRAM
                )
                sock.connect((host, port))
                sock.setblocking(False)
                return sock
            except OSError as exc:
                last_error = exc
                _sleep_ms(retry_delay_ms)
        raise OSError("UDP transport setup failed: %r" % (last_error,))

    def write(self, message):
        data = message.encode() if isinstance(message, str) else message
        try:
            self.sock.send(data)
        except OSError:
            # A single dropped datagram must not interrupt gesture control.
            pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class AutoDiscoverUdpTransport:
    """UDP transport that finds the Mac bridge instead of using a fixed IP.

    A phone hotspot reassigns the Mac's IP on every reconnect, so a static
    MOUSE_UDP_HOST (plain UdpTransport above) silently goes dead. This
    wraps discovery.UdpRegistry: it probes every host on the board's own
    subnet, learns the Mac's real (ip, port) from whichever one replies,
    and only ever sends @MOUSE packets once that peer is known -- never to
    a guessed address.

    ``step()`` must be called once per orchestrator loop iteration (it does
    only non-blocking socket I/O, so it cannot stall the AI loop).
    """

    def __init__(self, ip, netmask, discovery_port, max_scan_hosts=64,
                 retry_attempts=20, retry_delay_ms=500, socket_module=None,
                 registry_factory=None):
        # Validate before opening anything, so a too-large subnet raises
        # without leaking a socket that would never get closed.
        targets = discovery.compute_scan_targets(ip, netmask, max_hosts=max_scan_hosts)
        if not targets:
            raise ValueError(
                "auto-discovery found no usable subnet targets for %s/%s "
                "(subnet too large or degenerate mask) -- set "
                "MOUSE_UDP_AUTO_DISCOVER=False and configure a fixed "
                "MOUSE_UDP_HOST/MOUSE_UDP_PORT instead" % (ip, netmask)
            )
        self._socket_module = socket_module or __import__("socket")
        self.sock = self._open_socket(retry_attempts, retry_delay_ms)
        build_registry = registry_factory or discovery.UdpRegistry
        self.registry = build_registry(self.sock, targets, discovery_port)

    def _open_socket(self, retry_attempts, retry_delay_ms):
        # Same soft-reboot NIC race as UdpTransport._connect() above.
        last_error = None
        for _ in range(retry_attempts):
            try:
                sock = self._socket_module.socket(
                    self._socket_module.AF_INET, self._socket_module.SOCK_DGRAM
                )
                sock.setblocking(False)
                return sock
            except OSError as exc:
                last_error = exc
                _sleep_ms(retry_delay_ms)
        raise OSError("UDP discovery socket setup failed: %r" % (last_error,))

    def step(self, now_ms=None):
        self.registry.step(now_ms)

    def write(self, message):
        peer = self.registry.destination()
        if peer is None:
            # Not registered yet -- see UdpRegistry docstring: never send
            # to a guessed address.
            return
        data = message.encode() if isinstance(message, str) else message
        try:
            self.sock.sendto(data, peer)
        except OSError:
            pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class RegisteredUdpTransport:
    """UDP transport whose destination is learned from an HTTP registration,
    not discovered by the board scanning its own subnet.

    Replaces AutoDiscoverUdpTransport's board-initiated unicast scan with a
    Mac-initiated flow: the Mac bridge finds this board over TCP (HTTP
    GET /device-info) and POSTs /register with its own UDP listen port.
    smart_glass_server.py's web route calls ``register(ip, port)`` once that
    POST is verified; until then ``write()`` is a no-op, matching
    AutoDiscoverUdpTransport's "never send to a guessed address" rule.
    No scanning, no probe bursts, no step() -- there is nothing to poll.
    """

    def __init__(self, retry_attempts=20, retry_delay_ms=500, socket_module=None):
        self._socket_module = socket_module or __import__("socket")
        self.sock = self._open_socket(retry_attempts, retry_delay_ms)
        self.peer = None
        self.on_registered = None  # optional callback(peer) set by caller

    def _open_socket(self, retry_attempts, retry_delay_ms):
        # Same soft-reboot NIC race as UdpTransport._connect() above.
        last_error = None
        for _ in range(retry_attempts):
            try:
                sock = self._socket_module.socket(
                    self._socket_module.AF_INET, self._socket_module.SOCK_DGRAM
                )
                sock.setblocking(False)
                return sock
            except OSError as exc:
                last_error = exc
                _sleep_ms(retry_delay_ms)
        raise OSError("UDP transport setup failed: %r" % (last_error,))

    def register(self, ip, port):
        """Record/replace the Mac bridge's address, confirmed via HTTP /register."""
        previous = self.peer
        self.peer = (ip, port)
        if previous != self.peer and self.on_registered is not None:
            self.on_registered(self.peer)

    def write(self, message):
        if self.peer is None:
            # Not registered yet -- never send to a guessed address.
            return
        data = message.encode() if isinstance(message, str) else message
        try:
            self.sock.sendto(data, self.peer)
        except OSError:
            pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000.0)


def wifi_is_needed(web_server_enabled, mouse_control_enabled, mouse_transport_kind):
    """True exactly when a run profile needs an active Wi-Fi link.

    Pure decision logic shared by smart_glass_server.main() (called from
    run_uart.py / run_wifi.py). Kept here, independent of any
    hardware-only module, so the uart-vs-udp / web-on-vs-off wiring stays
    unit-testable without mocking media.sensor etc.
    """
    return bool(web_server_enabled) or (
        bool(mouse_control_enabled) and mouse_transport_kind == "udp"
    )


def create_transport(kind, uart=None, udp_host=None, udp_port=None,
                      udp_retry_attempts=20, udp_retry_delay_ms=500,
                      socket_module=None, udp_auto_discover=False,
                      udp_discovery_ip=None, udp_discovery_netmask=None,
                      udp_max_scan_hosts=64, udp_use_http_registration=False):
    """Build the transport named by config.MOUSE_TRANSPORT.

    ``udp_use_http_registration`` (config.MOUSE_UDP_USE_HTTP_REGISTRATION)
    picks RegisteredUdpTransport: the board does no scanning at all, and the
    Mac bridge finds it over TCP (HTTP GET /device-info) and POSTs /register
    with its own UDP port. This takes priority over ``udp_auto_discover``
    when both happen to be set, and ignores udp_host/udp_port/discovery_ip
    /discovery_netmask/max_scan_hosts entirely -- they only matter to the
    two branches below.

    ``udp_auto_discover`` switches the "udp" kind from the fixed-IP
    UdpTransport to AutoDiscoverUdpTransport (config.MOUSE_UDP_AUTO_DISCOVER).
    ``udp_host``/``udp_port`` stay the manual fallback: set
    udp_auto_discover=False to go back to exactly the old fixed-address
    behavior with no other code changes.

    If auto-discovery is on but the connected network's subnet has more
    host addresses than ``udp_max_scan_hosts`` (confirmed real-hardware
    case 2026-10-23: a home router's /24, 253 hosts, versus the default
    cap of 64), this now falls back to the fixed-IP UdpTransport using
    ``udp_host``/``udp_port`` instead of raising and leaving mouse control
    disabled for the whole run -- matching config.py's own documented
    "자동 탐색이 안 되는 환경의 수동 대안" intent for MOUSE_UDP_HOST. It
    still raises if no udp_host is configured either, since there is then
    truly nothing usable to fall back to.
    """
    if kind == "uart":
        return UartTransport(uart=uart)
    if kind == "udp":
        if udp_use_http_registration:
            return RegisteredUdpTransport(
                retry_attempts=udp_retry_attempts,
                retry_delay_ms=udp_retry_delay_ms,
                socket_module=socket_module,
            )
        if udp_auto_discover:
            if not udp_discovery_ip or not udp_discovery_netmask:
                raise ValueError(
                    "udp auto-discovery requires udp_discovery_ip and "
                    "udp_discovery_netmask (the board's own ifconfig)"
                )
            try:
                return AutoDiscoverUdpTransport(
                    udp_discovery_ip, udp_discovery_netmask, udp_port,
                    max_scan_hosts=udp_max_scan_hosts,
                    retry_attempts=udp_retry_attempts,
                    retry_delay_ms=udp_retry_delay_ms,
                    socket_module=socket_module,
                )
            except ValueError:
                if not udp_host:
                    raise
                return UdpTransport(
                    udp_host, udp_port,
                    retry_attempts=udp_retry_attempts,
                    retry_delay_ms=udp_retry_delay_ms,
                    socket_module=socket_module,
                )
        if not udp_host or not udp_port:
            raise ValueError("udp transport requires udp_host and udp_port")
        return UdpTransport(
            udp_host, udp_port,
            retry_attempts=udp_retry_attempts,
            retry_delay_ms=udp_retry_delay_ms,
            socket_module=socket_module,
        )
    raise ValueError("unknown transport kind: %r" % (kind,))
