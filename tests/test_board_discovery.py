"""Tests for mac/mac_mouse_bridge.py's Mac-initiated TCP board discovery
and HTTP registration (EdgeGlass-AI network auto-discovery, 2026-10-27).

Covers the Mac side of the new flow against a real, local, fake HTTP
server standing in for firmware/smart_glass_server.py's /device-info and
/register routes (no board required) -- per the request's own test list:
board discovery against a fake server, ignoring a wrong identity string,
accepting the correct EDGEGLASS_BOARD identity, the /register request
itself, and timeout/connection-refused handling.

No real Wi-Fi/hotspot is used anywhere here, only loopback sockets. The
fake server always binds to 127.0.0.1 (the only loopback address macOS
assigns to lo0 without extra `ifconfig lo0 alias` setup -- 127.0.0.2+ exist
on Linux but are NOT bindable on stock macOS, confirmed while writing
these tests). Scans that need more than one candidate host use a fictional
"own address" a few hops away in the arithmetic (compute_subnet_hosts()
never binds or connects to that address, only to the hosts it derives from
it) so the real bindable 127.0.0.1 ends up as the only actual probe
target; scans over several candidates instead fake probe_board() directly,
since binding N distinct loopback IPs is not portable.
"""

import http.server
import json
import os
import socket as real_socket
import sys
import threading
import time as real_time
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAC_DIR = os.path.join(_REPO_ROOT, "mac")
if _MAC_DIR not in sys.path:
    sys.path.insert(0, _MAC_DIR)

import mac_mouse_bridge


class _FakeBoardServer:
    """Minimal HTTP server standing in for the board's web routes.

    ``identity`` controls what GET /device-info answers with (a wrong
    value simulates some other device on the same port). ``accept_register``
    controls whether POST /register succeeds, independent of identity, so a
    "board found but registration rejected" scenario can be tested too.
    ``register_calls`` records (client_ip, payload) for every POST /register
    received, so a test can assert what the Mac actually sent.
    """

    def __init__(self, identity="EDGEGLASS_BOARD", accept_register=True, bind_ip="127.0.0.1"):
        self.identity = identity
        self.accept_register = accept_register
        self.register_calls = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def _send_json(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/device-info":
                    self._send_json(200, {"identity": outer.identity, "device": "K230D-Zero"})
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b""
                try:
                    payload = json.loads(raw.decode()) if raw else {}
                except ValueError:
                    payload = {}
                outer.register_calls.append((self.client_address[0], payload))
                valid = (
                    self.path == "/register"
                    and outer.accept_register
                    and payload.get("identity") == "EDGEGLASS_USER"
                    and isinstance(payload.get("udp_port"), int)
                )
                if valid:
                    self._send_json(200, {"identity": outer.identity, "status": "EDGEGLASS_REGISTERED"})
                else:
                    self._send_json(400, {"identity": outer.identity, "status": "EDGEGLASS_REJECTED"})

        self._httpd = http.server.HTTPServer((bind_ip, 0), Handler)
        self.ip = bind_ip
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2)


class ProbeBoardTests(unittest.TestCase):
    def test_probe_board_true_for_correct_identity(self):
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD")
        try:
            self.assertTrue(mac_mouse_bridge.probe_board(server.ip, server.port))
        finally:
            server.stop()

    def test_probe_board_false_for_wrong_identity(self):
        """A TCP connection succeeding is not enough -- some other service
        on the same port must be ignored, not mistaken for the board."""
        server = _FakeBoardServer(identity="SOME_OTHER_DEVICE")
        try:
            self.assertFalse(mac_mouse_bridge.probe_board(server.ip, server.port))
        finally:
            server.stop()

    def test_probe_board_false_and_bounded_when_nothing_is_listening(self):
        probe = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()  # nothing listening on this TCP port now
        started = real_time.monotonic()
        result = mac_mouse_bridge.probe_board("127.0.0.1", free_port, timeout_s=0.3)
        elapsed = real_time.monotonic() - started
        self.assertFalse(result)
        self.assertLess(elapsed, 2.0)  # must not hang anywhere near a full /24 scan budget


class RegisterWithBoardTests(unittest.TestCase):
    def test_register_with_board_true_on_success_and_sends_expected_payload(self):
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD", accept_register=True)
        try:
            ok = mac_mouse_bridge.register_with_board(server.ip, server.port, udp_port=9000)
            self.assertTrue(ok)
            self.assertEqual(len(server.register_calls), 1)
            _client_ip, payload = server.register_calls[0]
            self.assertEqual(payload, {"identity": "EDGEGLASS_USER", "udp_port": 9000})
        finally:
            server.stop()

    def test_register_with_board_false_when_board_rejects(self):
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD", accept_register=False)
        try:
            ok = mac_mouse_bridge.register_with_board(server.ip, server.port, udp_port=9000)
            self.assertFalse(ok)
        finally:
            server.stop()


class ComputeSubnetHostsTests(unittest.TestCase):
    def test_excludes_own_network_and_broadcast_addresses(self):
        hosts = mac_mouse_bridge.compute_subnet_hosts("127.0.0.2", "255.255.255.252")
        self.assertEqual(hosts, ["127.0.0.1"])

    def test_degenerate_32_bit_mask_yields_no_hosts(self):
        self.assertEqual(mac_mouse_bridge.compute_subnet_hosts("127.0.0.9", "255.255.255.255"), [])


class ScanForBoardTests(unittest.TestCase):
    def test_scan_finds_the_board_on_a_tiny_loopback_subnet(self):
        # "own address" 127.0.0.2 only exists in the arithmetic below (never
        # bound/connected to) so the only real candidate host is 127.0.0.1,
        # which is always bindable on macOS -- see module docstring.
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD")
        try:
            found = mac_mouse_bridge.scan_for_board("127.0.0.2", "255.255.255.252", server.port)
            self.assertEqual(found, "127.0.0.1")
        finally:
            server.stop()

    def test_scan_ignores_a_wrong_identity_and_finds_nothing(self):
        server = _FakeBoardServer(identity="SOME_OTHER_DEVICE")
        try:
            found = mac_mouse_bridge.scan_for_board("127.0.0.2", "255.255.255.252", server.port)
            self.assertIsNone(found)
        finally:
            server.stop()

    def test_scan_uses_prefer_ip_without_needing_the_subnet_list(self):
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD")
        try:
            # /32 netmask -> compute_subnet_hosts() returns [] (nothing to
            # scan); only prefer_ip being checked first can find it here.
            found = mac_mouse_bridge.scan_for_board(
                "127.0.0.9", "255.255.255.255", server.port, prefer_ip=server.ip)
            self.assertEqual(found, "127.0.0.1")
        finally:
            server.stop()

    def test_scan_finds_the_right_one_among_several_candidates(self):
        """compute_subnet_hosts()+bounded-concurrency selection, with a faked
        prober -- binding several distinct loopback IPs is not portable
        (see module docstring), while the tests above already cover the
        real HTTP exchange end to end against 127.0.0.1."""
        original_probe = mac_mouse_bridge.probe_board
        probed = []

        def fake_probe(ip, port, timeout_s=None):
            probed.append(ip)
            return ip == "10.0.0.7"

        mac_mouse_bridge.probe_board = fake_probe
        try:
            found = mac_mouse_bridge.scan_for_board("10.0.0.1", "255.255.255.240", 8060)
            self.assertEqual(found, "10.0.0.7")
            self.assertIn("10.0.0.7", probed)
            self.assertNotIn("10.0.0.1", probed)  # own address excluded from candidates
        finally:
            mac_mouse_bridge.probe_board = original_probe

    def test_scan_returns_none_when_nobody_on_the_subnet_answers(self):
        original_probe = mac_mouse_bridge.probe_board
        mac_mouse_bridge.probe_board = lambda ip, port, timeout_s=None: False
        try:
            found = mac_mouse_bridge.scan_for_board("10.0.0.1", "255.255.255.240", 8060)
            self.assertIsNone(found)
        finally:
            mac_mouse_bridge.probe_board = original_probe


class DiscoverAndRegisterBoardTests(unittest.TestCase):
    def test_full_success_path_scans_and_registers(self):
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD")
        statuses = []
        original = mac_mouse_bridge.get_local_ip_and_netmask
        mac_mouse_bridge.get_local_ip_and_netmask = lambda **_kw: ("127.0.0.2", "255.255.255.252")
        try:
            board_ip = mac_mouse_bridge.discover_and_register_board(
                server.port, udp_port=9000, on_status=statuses.append)
            self.assertEqual(board_ip, "127.0.0.1")
            self.assertEqual(len(server.register_calls), 1)
            self.assertTrue(any("registered" in msg for msg in statuses))
        finally:
            mac_mouse_bridge.get_local_ip_and_netmask = original
            server.stop()

    def test_returns_none_and_reports_status_when_registration_is_rejected(self):
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD", accept_register=False)
        statuses = []
        original = mac_mouse_bridge.get_local_ip_and_netmask
        mac_mouse_bridge.get_local_ip_and_netmask = lambda **_kw: ("127.0.0.2", "255.255.255.252")
        try:
            board_ip = mac_mouse_bridge.discover_and_register_board(
                server.port, udp_port=9000, on_status=statuses.append)
            self.assertIsNone(board_ip)
            self.assertTrue(any("did not confirm" in msg for msg in statuses))
        finally:
            mac_mouse_bridge.get_local_ip_and_netmask = original
            server.stop()

    def test_returns_none_when_no_local_ip_route(self):
        statuses = []
        original = mac_mouse_bridge.get_local_ip_and_netmask
        mac_mouse_bridge.get_local_ip_and_netmask = lambda **_kw: (None, None)
        try:
            board_ip = mac_mouse_bridge.discover_and_register_board(
                8060, udp_port=9000, on_status=statuses.append)
            self.assertIsNone(board_ip)
            self.assertTrue(any("no local IP route" in msg for msg in statuses))
        finally:
            mac_mouse_bridge.get_local_ip_and_netmask = original


class TcpDiscoveryLoopTests(unittest.TestCase):
    def test_stops_retrying_once_found_and_calls_on_found(self):
        server = _FakeBoardServer(identity="EDGEGLASS_BOARD")
        found_calls = []
        original = mac_mouse_bridge.get_local_ip_and_netmask
        mac_mouse_bridge.get_local_ip_and_netmask = lambda **_kw: ("127.0.0.2", "255.255.255.252")
        try:
            result = mac_mouse_bridge._tcp_discovery_loop(
                server.port, udp_port=9000, retry_interval_s=0.01,
                on_found=found_calls.append, max_attempts=3,
            )
            self.assertEqual(result, "127.0.0.1")
            self.assertEqual(found_calls, ["127.0.0.1"])
        finally:
            mac_mouse_bridge.get_local_ip_and_netmask = original
            server.stop()

    def test_gives_up_after_max_attempts_when_nothing_is_found(self):
        original = mac_mouse_bridge.get_local_ip_and_netmask
        mac_mouse_bridge.get_local_ip_and_netmask = lambda **_kw: ("127.0.0.2", "255.255.255.252")
        try:
            result = mac_mouse_bridge._tcp_discovery_loop(
                8060, udp_port=9000, retry_interval_s=0.01, max_attempts=2,
            )
            self.assertIsNone(result)
        finally:
            mac_mouse_bridge.get_local_ip_and_netmask = original


if __name__ == "__main__":
    unittest.main()
