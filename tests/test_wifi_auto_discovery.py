"""Tests for the Wi-Fi auto-discovery work on feature/wifi-auto-discovery:

- firmware/discovery.py: board-side subnet scan + @HELLO/@ACK registry.
- firmware/transport.py: AutoDiscoverUdpTransport built on top of it.
- mac/mac_mouse_bridge.py: local-IP/accessibility diagnostics and the
  Mac-side half of the @HELLO/@ACK handshake in run_udp_loop.

No real Wi-Fi/hotspot is used anywhere here -- only loopback sockets and
fakes, per this branch's "local tests only, no real hardware yet" scope.
"""

import contextlib
import importlib
import io
import os
import socket as real_socket
import sys
import tempfile
import threading
import time
import types
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("firmware", "mac"):
    _path = os.path.join(_REPO_ROOT, _sub)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import discovery
import mac_mouse_bridge


def _install_fake_machine():
    machine = types.ModuleType("machine")

    class UART:
        UART2 = 2
        EIGHTBITS = 8
        PARITY_NONE = 0
        STOPBITS_ONE = 1

        def __init__(self, *args, **kwargs):
            self.sent = []

        def write(self, data):
            self.sent.append(data)

        def deinit(self):
            pass

    machine.UART = UART
    return machine


def _fresh_transport_import():
    for name in ("transport", "discovery"):
        sys.modules.pop(name, None)
    original = sys.modules.get("machine")
    sys.modules["machine"] = _install_fake_machine()
    try:
        return importlib.import_module("transport")
    finally:
        if original is None:
            sys.modules.pop("machine", None)
        else:
            sys.modules["machine"] = original


def _free_udp_port():
    probe = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class _FakeClock:
    def __init__(self):
        self.now_ms = 0

    def ticks_ms(self):
        return self.now_ms

    def ticks_diff(self, later, earlier):
        return later - earlier

    def advance(self, ms):
        self.now_ms += ms


class _FakeDiscoverySocket:
    """Queued (data, addr) replies; sendto() just records what was sent."""

    def __init__(self, replies=None):
        self.sent = []
        self._replies = list(replies or [])

    def recvfrom(self, bufsize):
        if self._replies:
            return self._replies.pop(0)
        raise OSError(11, "EAGAIN")

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def close(self):
        pass


# ================================================================
# firmware/discovery.py: compute_scan_targets
# ================================================================

class ComputeScanTargetsTests(unittest.TestCase):
    def test_typical_hotspot_slash28_excludes_own_ip(self):
        targets = discovery.compute_scan_targets("172.20.10.3", "255.255.255.240")
        self.assertEqual(len(targets), 13)  # 14 hosts in a /28, minus self
        self.assertNotIn("172.20.10.3", targets)
        self.assertIn("172.20.10.1", targets)
        self.assertIn("172.20.10.14", targets)
        self.assertNotIn("172.20.10.0", targets)   # network address
        self.assertNotIn("172.20.10.15", targets)  # broadcast address

    def test_large_subnet_returns_empty_by_default(self):
        # /24 = 254 usable hosts, over the default 64-host cap.
        targets = discovery.compute_scan_targets("192.168.1.42", "255.255.255.0")
        self.assertEqual(targets, [])

    def test_large_subnet_allowed_with_higher_cap(self):
        targets = discovery.compute_scan_targets(
            "192.168.1.42", "255.255.255.0", max_hosts=300
        )
        # 254 usable /24 hosts minus the board's own address.
        self.assertEqual(len(targets), 253)
        self.assertNotIn("192.168.1.42", targets)

    def test_degenerate_slash32_mask_has_no_hosts(self):
        self.assertEqual(discovery.compute_scan_targets("10.0.0.1", "255.255.255.255"), [])


# ================================================================
# firmware/discovery.py: UdpRegistry
# ================================================================

class UdpRegistryTests(unittest.TestCase):
    def setUp(self):
        self.clock = _FakeClock()
        discovery.time = self.clock

    def test_first_step_sends_a_probe_to_every_target(self):
        sock = _FakeDiscoverySocket()
        registry = discovery.UdpRegistry(sock, ["10.0.0.1", "10.0.0.2"], 9000)
        registry.step(now_ms=0)
        sent_addrs = [addr for _data, addr in sock.sent]
        self.assertEqual(sent_addrs, [("10.0.0.1", 9000), ("10.0.0.2", 9000)])
        self.assertTrue(sock.sent[0][0].startswith(discovery.HELLO_PREFIX.encode()))

    def test_does_not_reprobe_before_scan_interval_elapses(self):
        sock = _FakeDiscoverySocket()
        registry = discovery.UdpRegistry(
            sock, ["10.0.0.1"], 9000, scan_interval_ms=2000
        )
        registry.step(now_ms=0)
        registry.step(now_ms=500)
        self.assertEqual(len(sock.sent), 1)  # only the first burst

    def test_ack_registers_peer_and_fires_callback_once(self):
        sock = _FakeDiscoverySocket(replies=[
            ((discovery.ACK_PREFIX + "ok").encode(), ("172.20.10.2", 9000)),
        ])
        registry = discovery.UdpRegistry(sock, ["172.20.10.2"], 9000)
        seen = []
        registry.on_registered = lambda peer: seen.append(peer)

        registry.step(now_ms=0)

        self.assertEqual(registry.destination(), ("172.20.10.2", 9000))
        self.assertEqual(seen, [("172.20.10.2", 9000)])

    def test_repeated_ack_from_same_peer_does_not_refire_callback(self):
        ack = ((discovery.ACK_PREFIX + "ok").encode(), ("172.20.10.2", 9000))
        sock = _FakeDiscoverySocket(replies=[ack, ack])
        registry = discovery.UdpRegistry(sock, ["172.20.10.2"], 9000)
        seen = []
        registry.on_registered = lambda peer: seen.append(peer)

        registry.step(now_ms=0)
        registry.step(now_ms=10)

        self.assertEqual(len(seen), 1)

    def test_ack_from_a_new_address_updates_peer_and_refires(self):
        """Covers the Mac (or board) getting a new hotspot IP mid-session."""
        sock = _FakeDiscoverySocket(replies=[
            ((discovery.ACK_PREFIX + "ok").encode(), ("172.20.10.2", 9000)),
            ((discovery.ACK_PREFIX + "ok").encode(), ("172.20.10.5", 9000)),
        ])
        registry = discovery.UdpRegistry(sock, ["172.20.10.2"], 9000)
        seen = []
        registry.on_registered = lambda peer: seen.append(peer)

        registry.step(now_ms=0)
        registry.step(now_ms=10)

        self.assertEqual(seen, [("172.20.10.2", 9000), ("172.20.10.5", 9000)])
        self.assertEqual(registry.destination(), ("172.20.10.5", 9000))

    def test_reannounces_periodically_even_after_registration(self):
        """Re-scanning after being registered is how an IP change self-heals
        -- pinging only the stale old peer would never find the new one."""
        ack = ((discovery.ACK_PREFIX + "ok").encode(), ("172.20.10.2", 9000))
        sock = _FakeDiscoverySocket(replies=[ack])
        registry = discovery.UdpRegistry(
            sock, ["172.20.10.2"], 9000,
            scan_interval_ms=2000, reannounce_interval_ms=5000,
        )
        registry.step(now_ms=0)       # initial burst + ack -> registered
        self.assertEqual(len(sock.sent), 1)
        registry.step(now_ms=2000)    # well under reannounce_interval_ms
        self.assertEqual(len(sock.sent), 1)
        registry.step(now_ms=5001)    # past reannounce_interval_ms
        self.assertEqual(len(sock.sent), 2)

    def test_empty_targets_never_sends_and_stays_unregistered(self):
        sock = _FakeDiscoverySocket()
        registry = discovery.UdpRegistry(sock, [], 9000)
        registry.step(now_ms=0)
        registry.step(now_ms=100000)
        self.assertEqual(sock.sent, [])
        self.assertIsNone(registry.destination())


# ================================================================
# firmware/transport.py: AutoDiscoverUdpTransport
# ================================================================

class AutoDiscoverUdpTransportTests(unittest.TestCase):
    def test_write_is_a_noop_before_registration(self):
        transport = _fresh_transport_import()
        server = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        server.settimeout(0.2)
        try:
            udp_transport = transport.AutoDiscoverUdpTransport(
                "127.0.0.1", "255.255.255.252", server.getsockname()[1],
            )
            udp_transport.write("@MOUSE|MOVE|0.5|0.5\r\n")
            with self.assertRaises(OSError):
                server.recvfrom(1024)  # nothing sent -- not registered yet
            udp_transport.close()
        finally:
            server.close()

    def test_write_sends_to_the_registered_peer_once_known(self):
        transport = _fresh_transport_import()
        mac = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
        mac.bind(("127.0.0.1", 0))
        mac.settimeout(2)
        try:
            udp_transport = transport.AutoDiscoverUdpTransport(
                "127.0.0.1", "255.255.255.252", 9  # discovery_port unused once peer is set
            )
            udp_transport.registry.peer = ("127.0.0.1", mac.getsockname()[1])
            udp_transport.write("@MOUSE|CLICK\r\n")
            data, _addr = mac.recvfrom(1024)
            self.assertEqual(data, b"@MOUSE|CLICK\r\n")
            udp_transport.close()
        finally:
            mac.close()

    def test_construction_raises_when_subnet_too_large_to_scan(self):
        transport = _fresh_transport_import()
        with self.assertRaises(ValueError):
            transport.AutoDiscoverUdpTransport("192.168.1.2", "255.255.255.0", 9000)

    def test_step_delegates_to_the_registry(self):
        transport = _fresh_transport_import()

        class FakeRegistry:
            def __init__(self, sock, targets, port):
                self.steps = []

            def step(self, now_ms=None):
                self.steps.append(now_ms)

            def destination(self):
                return None

        udp_transport = transport.AutoDiscoverUdpTransport(
            "127.0.0.1", "255.255.255.252", 9000,
            registry_factory=FakeRegistry,
        )
        udp_transport.registry.steps.append("marker")
        udp_transport.step(now_ms=123)
        self.assertEqual(udp_transport.registry.steps, ["marker", 123])
        udp_transport.close()


class CreateTransportAutoDiscoverTests(unittest.TestCase):
    def test_udp_auto_discover_returns_auto_discover_transport(self):
        transport = _fresh_transport_import()
        built = transport.create_transport(
            "udp", udp_port=9000, udp_auto_discover=True,
            udp_discovery_ip="127.0.0.1", udp_discovery_netmask="255.255.255.252",
        )
        self.assertIsInstance(built, transport.AutoDiscoverUdpTransport)
        built.close()

    def test_udp_auto_discover_requires_ip_and_netmask(self):
        transport = _fresh_transport_import()
        with self.assertRaises(ValueError):
            transport.create_transport("udp", udp_port=9000, udp_auto_discover=True)

    def test_udp_without_auto_discover_is_unchanged(self):
        transport = _fresh_transport_import()
        built = transport.create_transport(
            "udp", udp_host="127.0.0.1", udp_port=9000, udp_auto_discover=False,
        )
        self.assertIsInstance(built, transport.UdpTransport)
        built.close()

    def test_falls_back_to_fixed_host_when_subnet_too_large_for_scan(self):
        # Real-hardware finding 2026-10-23: a home router's /24 (253 hosts)
        # exceeds the default 64-host scan cap, so auto-discovery can never
        # work there. config.py documents MOUSE_UDP_HOST as the manual
        # fallback for exactly this case -- create_transport() must actually
        # use it instead of just raising and leaving mouse control disabled.
        transport = _fresh_transport_import()
        built = transport.create_transport(
            "udp", udp_host="127.0.0.1", udp_port=_free_udp_port(),
            udp_auto_discover=True,
            udp_discovery_ip="127.0.0.1", udp_discovery_netmask="255.255.255.0",
        )
        self.assertIsInstance(built, transport.UdpTransport)
        built.close()

    def test_raises_when_subnet_too_large_and_no_fixed_host_configured(self):
        transport = _fresh_transport_import()
        with self.assertRaises(ValueError):
            transport.create_transport(
                "udp", udp_port=9000, udp_auto_discover=True,
                udp_discovery_ip="127.0.0.1", udp_discovery_netmask="255.255.255.0",
            )


# ================================================================
# mac/mac_mouse_bridge.py: diagnostics + discovery reply
# ================================================================

class MacDiagnosticsTests(unittest.TestCase):
    def test_get_local_ip_does_not_raise_and_looks_like_an_ip_or_none(self):
        ip = mac_mouse_bridge.get_local_ip()
        if ip is not None:
            parts = ip.split(".")
            self.assertEqual(len(parts), 4)
            for part in parts:
                self.assertTrue(part.isdigit())

    def test_check_accessibility_trusted_never_raises(self):
        result = mac_mouse_bridge.check_accessibility_trusted()
        self.assertIn(result, (True, False, None))


class HelloAckTests(unittest.TestCase):
    def test_handle_line_ignores_hello_without_dispatch_or_parse_failure(self):
        mouse = mac_mouse_bridge.DryRunMouse()
        logger = mac_mouse_bridge.TrackingCsvLogger(tempfile.mkdtemp())
        mac_mouse_bridge.handle_line("@HELLO|k230\r\n", mouse, logger)
        self.assertFalse(mouse.dragging)  # no dispatch happened
        logger.close()

    def test_reply_to_hello_acks_the_real_sender_and_fires_callback(self):
        board = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
        board.bind(("127.0.0.1", 0))
        board.settimeout(2)
        mac = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
        mac.bind(("127.0.0.1", 0))
        mac.settimeout(2)
        try:
            board.sendto(b"@HELLO|k230\r\n", ("127.0.0.1", mac.getsockname()[1]))
            data, addr = mac.recvfrom(1024)
            seen = []
            mac_mouse_bridge._reply_to_hello(mac, addr, lambda a: seen.append(a))
            reply, _from = board.recvfrom(1024)
            self.assertTrue(reply.startswith(mac_mouse_bridge.ACK_PREFIX.encode()))
            self.assertEqual(seen, [addr])
        finally:
            board.close()
            mac.close()

    def test_parse_failure_diagnostic_is_rate_limited(self):
        mouse = mac_mouse_bridge.DryRunMouse()
        logger = mac_mouse_bridge.TrackingCsvLogger(tempfile.mkdtemp())
        # A fresh "last_log" in the past guarantees the first call below is
        # due, regardless of what earlier tests left in this module-level
        # state.
        mac_mouse_bridge._parse_fail_state["last_log"] = 0.0

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            mac_mouse_bridge.handle_line("garbled line one\r\n", mouse, logger)
            mac_mouse_bridge.handle_line("garbled line two\r\n", mouse, logger)
        output = buffer.getvalue()

        self.assertEqual(output.count("PARSE_FAIL"), 1)  # second call rate-limited
        logger.close()

    def test_parse_failure_diagnostic_fires_again_after_the_interval(self):
        mouse = mac_mouse_bridge.DryRunMouse()
        logger = mac_mouse_bridge.TrackingCsvLogger(tempfile.mkdtemp())
        mac_mouse_bridge._parse_fail_state["last_log"] = (
            time.monotonic() - mac_mouse_bridge.PARSE_FAIL_LOG_INTERVAL_S - 1.0
        )

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            mac_mouse_bridge.handle_line("garbled line\r\n", mouse, logger)
        output = buffer.getvalue()

        self.assertEqual(output.count("PARSE_FAIL"), 1)
        logger.close()


class RunUdpLoopDiscoveryIntegrationTests(unittest.TestCase):
    def test_board_hello_gets_acked_and_registered(self):
        port = _free_udp_port()
        mouse = mac_mouse_bridge.DryRunMouse()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=5.0)
        registered = []
        with tempfile.TemporaryDirectory() as directory:
            logger = mac_mouse_bridge.TrackingCsvLogger(directory)
            thread = threading.Thread(
                target=mac_mouse_bridge.run_udp_loop,
                args=("127.0.0.1", port, mouse, logger, watchdog),
                kwargs={
                    "max_ticks": 10, "poll_timeout_s": 0.02,
                    "on_board_registered": lambda addr: registered.append(addr),
                },
                daemon=True,
            )
            thread.start()
            time.sleep(0.05)
            board = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
            try:
                board.settimeout(2)
                board.sendto(b"@HELLO|k230\r\n", ("127.0.0.1", port))
                reply, _addr = board.recvfrom(1024)
                self.assertTrue(reply.startswith(mac_mouse_bridge.ACK_PREFIX.encode()))
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(registered), 1)
                self.assertEqual(registered[0][0], "127.0.0.1")
            finally:
                board.close()
                logger.close()


if __name__ == "__main__":
    unittest.main()
