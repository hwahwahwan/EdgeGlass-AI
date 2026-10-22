"""Tests for the Wi-Fi/UDP mouse transport split (K230 side) and the Mac
bridge's DRAG link watchdog -- added alongside the existing verified UART
path without changing it. See docs/WORK_TRACKER.md / PROJECT_STATUS.md for
background; experiments/wifi_test/WIFI_TEST_REPORT.md documents the
real-hardware Wi-Fi/socket behavior this code is written against.
"""

import importlib
import os
import runpy
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

import mac_mouse_bridge


# ================================================================
# Helpers shared by the firmware (K230-side) tests below.
# ================================================================

class _FakeUart:
    """Mirrors the fake machine.UART used by tests/test_ui_transport.py."""

    def __init__(self, *args, **kwargs):
        self.sent = []
        self.deinited = False

    def write(self, data):
        self.sent.append(data)

    def deinit(self):
        self.deinited = True


def _install_fake_machine():
    machine = types.ModuleType("machine")

    class UART:
        UART2 = 2
        EIGHTBITS = 8
        PARITY_NONE = 0
        STOPBITS_ONE = 1

        def __init__(self, *args, **kwargs):
            self._impl = _FakeUart()
            self.sent = self._impl.sent

        def write(self, data):
            self._impl.write(data)

        def deinit(self):
            self._impl.deinit()

    machine.UART = UART
    return machine


def _fresh_firmware_import(name, machine_module):
    """(Re)import a firmware module with a specific fake `machine` installed.

    Firmware modules are flat-imported on the board (see firmware/CLAUDE.md
    convention), so tests/test_ui_transport.py already relies on swapping
    sys.modules['machine'] before import. Several test methods below need
    *different* fakes, so every affected module is dropped from the cache
    first -- otherwise a later test would silently reuse an earlier test's
    mock via Python's normal module cache.
    """
    for module_name in ("transport", "mouse_controller", name):
        sys.modules.pop(module_name, None)
    original = sys.modules.get("machine")
    sys.modules["machine"] = machine_module
    try:
        return importlib.import_module(name)
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


# ================================================================
# firmware/transport.py
# ================================================================

class TransportTests(unittest.TestCase):
    def test_uart_transport_writes_and_closes_through_machine_uart(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())
        uart_transport = transport.UartTransport()
        uart_transport.write("@MOUSE|STOP\r\n")
        self.assertEqual(uart_transport.uart.sent, ["@MOUSE|STOP\r\n"])
        uart_transport.close()
        self.assertTrue(uart_transport.uart._impl.deinited)

    def test_udp_transport_sends_real_bytes_over_loopback(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())
        server = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        port = server.getsockname()[1]
        try:
            udp_transport = transport.UdpTransport("127.0.0.1", port)
            udp_transport.write("@MOUSE|MOVE|0.5000|0.5000\r\n")
            data, _addr = server.recvfrom(1024)
            self.assertEqual(data, b"@MOUSE|MOVE|0.5000|0.5000\r\n")
            udp_transport.close()
        finally:
            server.close()

    def test_udp_transport_retries_past_transient_no_nic_error(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())

        class FakeSocket:
            def __init__(self):
                self.sent = []
                self.closed = False

            def connect(self, addr):
                self.addr = addr

            def setblocking(self, flag):
                self.blocking = flag

            def send(self, data):
                self.sent.append(data)

            def close(self):
                self.closed = True

        class FlakySocketModule:
            AF_INET = real_socket.AF_INET
            SOCK_DGRAM = real_socket.SOCK_DGRAM

            def __init__(self, fail_times):
                self.fail_times = fail_times
                self.attempts = 0
                self.created = []

            def socket(self, family, kind):
                self.attempts += 1
                if self.attempts <= self.fail_times:
                    raise OSError("no available NIC")
                sock = FakeSocket()
                self.created.append(sock)
                return sock

        flaky = FlakySocketModule(fail_times=2)
        udp_transport = transport.UdpTransport(
            "10.0.0.5", 9000, retry_attempts=5, retry_delay_ms=0, socket_module=flaky
        )
        self.assertEqual(flaky.attempts, 3)
        udp_transport.write("@MOUSE|STOP\r\n")
        self.assertEqual(flaky.created[0].sent, [b"@MOUSE|STOP\r\n"])

    def test_udp_transport_gives_up_after_exhausting_retries(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())

        class AlwaysFailsSocketModule:
            AF_INET = real_socket.AF_INET
            SOCK_DGRAM = real_socket.SOCK_DGRAM

            def socket(self, family, kind):
                raise OSError("no available NIC")

        with self.assertRaises(OSError):
            transport.UdpTransport(
                "10.0.0.5", 9000, retry_attempts=3, retry_delay_ms=0,
                socket_module=AlwaysFailsSocketModule(),
            )

    def test_udp_transport_write_swallows_send_errors(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())

        class DroppingSocket:
            def connect(self, addr):
                pass

            def setblocking(self, flag):
                pass

            def send(self, data):
                raise OSError("network unreachable")

            def close(self):
                pass

        class OneShotSocketModule:
            AF_INET = real_socket.AF_INET
            SOCK_DGRAM = real_socket.SOCK_DGRAM

            def socket(self, family, kind):
                return DroppingSocket()

        udp_transport = transport.UdpTransport(
            "10.0.0.5", 9000, socket_module=OneShotSocketModule()
        )
        udp_transport.write("@MOUSE|MOVE|0.1|0.1\r\n")  # must not raise

    def test_create_transport_selects_by_kind(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())
        self.assertIsInstance(transport.create_transport("uart"), transport.UartTransport)
        with self.assertRaises(ValueError):
            transport.create_transport("udp")  # missing host/port
        with self.assertRaises(ValueError):
            transport.create_transport("carrier_pigeon")

    def test_wifi_is_needed_for_web_server_regardless_of_mouse_transport(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())
        self.assertTrue(transport.wifi_is_needed(True, False, "uart"))
        self.assertTrue(transport.wifi_is_needed(True, True, "uart"))

    def test_wifi_is_needed_for_udp_mouse_transport_even_without_web(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())
        self.assertTrue(transport.wifi_is_needed(False, True, "udp"))

    def test_wifi_not_needed_for_uart_only_run(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())
        self.assertFalse(transport.wifi_is_needed(False, True, "uart"))
        self.assertFalse(transport.wifi_is_needed(False, False, "uart"))

    def test_wifi_not_needed_when_mouse_control_disabled_even_if_udp_selected(self):
        transport = _fresh_firmware_import("transport", _install_fake_machine())
        self.assertFalse(transport.wifi_is_needed(False, False, "udp"))


# ================================================================
# firmware/mouse_controller.py + injected transport
# ================================================================

class FakeTransport:
    def __init__(self):
        self.sent = []
        self.closed = False

    def write(self, message):
        self.sent.append(message)

    def close(self):
        self.closed = True


class MouseControllerTransportTests(unittest.TestCase):
    def setUp(self):
        self.mouse_controller = _fresh_firmware_import(
            "mouse_controller", _install_fake_machine()
        )
        self.mouse_controller.time = types.SimpleNamespace(ticks_ms=lambda: 0)

    def test_injected_transport_is_used_instead_of_default_uart(self):
        fake = FakeTransport()
        controller = self.mouse_controller.MouseController((640, 360), transport=fake)
        controller.update("MOVE", 320, 180)
        self.assertEqual(fake.sent, ["@MOUSE|MOVE|0.5000|0.5000\r\n"])
        self.assertIsNone(controller.uart)  # no UART backing a non-UART transport

    def test_close_delegates_to_injected_transport(self):
        fake = FakeTransport()
        controller = self.mouse_controller.MouseController((640, 360), transport=fake)
        controller.update("MOVE", 320, 180)
        controller.close()
        self.assertTrue(fake.closed)

    def test_drag_resends_last_point_as_keepalive_during_hand_loss_grace(self):
        """A short hand-loss grace (no_hand() with action still DRAG, x=y=None)
        must not go silent: this is what lets the Mac-side link watchdog
        stay well clear of false-triggering on a legitimate short detector
        miss, independent of which transport carries the packets."""
        fake = FakeTransport()
        controller = self.mouse_controller.MouseController((640, 360), transport=fake)
        controller.update("DRAG", 320, 180)  # DRAG_START
        controller.update("DRAG", 320, 180)  # DRAG
        fake.sent.clear()

        controller.update("DRAG")  # grace period: gesture controller sends no x/y

        self.assertEqual(fake.sent, ["@MOUSE|DRAG|0.5000|0.5000\r\n"])
        self.assertTrue(controller.dragging)

    def test_drag_end_clears_last_point_so_next_drag_cannot_reuse_stale_point(self):
        fake = FakeTransport()
        controller = self.mouse_controller.MouseController((640, 360), transport=fake)
        controller.update("DRAG", 320, 180)
        controller.update("STOP")
        self.assertIsNone(controller.last_drag_point)
        self.assertIn("@MOUSE|DRAG_END\r\n", fake.sent)


# ================================================================
# firmware/wifi.py (shared STA connect-and-reuse helper)
# ================================================================

class _FakeClock:
    """Deterministic stand-in for MicroPython's time module."""

    def __init__(self):
        self.now_ms = 0

    def ticks_ms(self):
        return self.now_ms

    def ticks_diff(self, later, earlier):
        return later - earlier

    def ticks_add(self, base, delta):
        return base + delta

    def sleep_ms(self, ms):
        self.now_ms += ms


class _FakeWlan:
    """``connect_after_polls`` is the default per-network success threshold;
    ``connect_after_polls_by_ssid`` overrides it for specific SSIDs (use
    ``None`` for an SSID that must never connect), ``fail_connect_ssids``
    makes ``connect()`` itself raise for those SSIDs, and
    ``reject_connect_ssids`` makes ``connect()`` return ``False`` for those
    SSIDs (confirmed real-hardware behavior 2026-10-23: a driver-level
    rejection, e.g. wrong password, reports itself this way rather than by
    raising or by isconnected() ever turning True) -- together these model
    a home-network attempt that fails/times out before the hotspot fallback
    succeeds.
    """

    def __init__(self, already_connected=False, connect_after_polls=1,
                 connect_after_polls_by_ssid=None, fail_connect_ssids=None,
                 reject_connect_ssids=None):
        self.active_calls = []
        self.connect_calls = []
        self._already_connected = already_connected
        self._connect_after_polls = connect_after_polls
        self._connect_after_polls_by_ssid = connect_after_polls_by_ssid or {}
        self._fail_connect_ssids = set(fail_connect_ssids or ())
        self._reject_connect_ssids = set(reject_connect_ssids or ())
        self._poll_count = 0
        self._current_ssid = None

    def active(self, flag):
        self.active_calls.append(flag)

    def isconnected(self):
        if self._already_connected:
            return True
        if self._current_ssid is None:
            return False
        self._poll_count += 1
        threshold = self._connect_after_polls_by_ssid.get(
            self._current_ssid, self._connect_after_polls
        )
        if threshold is None:
            return False
        return self._poll_count > threshold

    def connect(self, ssid, password):
        self.connect_calls.append((ssid, password))
        if ssid in self._fail_connect_ssids:
            self._current_ssid = None
            raise OSError("connect failed for %r" % (ssid,))
        if ssid in self._reject_connect_ssids:
            self._current_ssid = None
            return False
        self._current_ssid = ssid
        self._poll_count = 0

    def ifconfig(self):
        return ("172.20.10.9", "255.255.255.240", "172.20.10.1", "172.20.10.1")


def _install_fake_network(wlan):
    network_module = types.ModuleType("network")
    network_module.STA_IF = 0
    network_module.WLAN = lambda iface: wlan
    return network_module


def _fresh_wifi_import(network_module):
    sys.modules.pop("wifi", None)
    original = sys.modules.get("network")
    sys.modules["network"] = network_module
    try:
        return importlib.import_module("wifi")
    finally:
        if original is None:
            sys.modules.pop("network", None)
        else:
            sys.modules["network"] = original


class WifiReuseTests(unittest.TestCase):
    def test_already_connected_link_is_reused_without_calling_connect(self):
        wlan = _FakeWlan(already_connected=True)
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        returned_wlan, ifconfig, ssid = wifi.connect_if_needed(
            [("home", "home-pw"), ("hotspot", "hotspot-pw")]
        )
        self.assertIs(returned_wlan, wlan)
        self.assertEqual(wlan.connect_calls, [])
        self.assertEqual(ifconfig, wlan.ifconfig())
        self.assertIsNone(ssid)  # already connected -- which network is unknown

    def test_first_network_connects_without_trying_the_second(self):
        wlan = _FakeWlan(already_connected=False, connect_after_polls=3)
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        _wlan, ifconfig, ssid = wifi.connect_if_needed(
            [("home", "home-pw"), ("hotspot", "hotspot-pw")], timeout_s=30
        )
        self.assertEqual(wlan.connect_calls, [("home", "home-pw")])
        self.assertEqual(ifconfig, wlan.ifconfig())
        self.assertEqual(ssid, "home")

    def test_falls_back_to_hotspot_when_home_network_times_out(self):
        wlan = _FakeWlan(
            already_connected=False,
            connect_after_polls_by_ssid={"home": None, "hotspot": 1},
        )
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        _wlan, ifconfig, ssid = wifi.connect_if_needed(
            [("home", "home-pw"), ("hotspot", "hotspot-pw")], timeout_s=1
        )
        # IMPORTANT (see firmware/wifi.py docstring): exactly one connect()
        # call per candidate -- the home timeout must not have retried it.
        self.assertEqual(wlan.connect_calls, [("home", "home-pw"), ("hotspot", "hotspot-pw")])
        self.assertEqual(ssid, "hotspot")
        self.assertEqual(ifconfig, wlan.ifconfig())

    def test_falls_back_to_hotspot_when_home_connect_raises(self):
        wlan = _FakeWlan(
            already_connected=False,
            fail_connect_ssids={"home"},
            connect_after_polls_by_ssid={"hotspot": 0},
        )
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        _wlan, ifconfig, ssid = wifi.connect_if_needed(
            [("home", "home-pw"), ("hotspot", "hotspot-pw")]
        )
        self.assertEqual(wlan.connect_calls, [("home", "home-pw"), ("hotspot", "hotspot-pw")])
        self.assertEqual(ssid, "hotspot")
        self.assertEqual(ifconfig, wlan.ifconfig())

    def test_blank_network_entries_are_skipped(self):
        wlan = _FakeWlan(already_connected=False, connect_after_polls=0)
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        _wlan, _ifconfig, ssid = wifi.connect_if_needed(
            [(None, None), ("", ""), ("real", "real-pw")]
        )
        self.assertEqual(wlan.connect_calls, [("real", "real-pw")])
        self.assertEqual(ssid, "real")

    def test_timeout_on_every_network_raises_oserror(self):
        wlan = _FakeWlan(already_connected=False, connect_after_polls=None)
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        with self.assertRaises(OSError):
            wifi.connect_if_needed(
                [("home", "home-pw"), ("hotspot", "hotspot-pw")], timeout_s=1
            )
        self.assertEqual(wlan.connect_calls, [("home", "home-pw"), ("hotspot", "hotspot-pw")])

    def test_empty_network_list_raises_without_connecting(self):
        wlan = _FakeWlan(already_connected=False)
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        with self.assertRaises(OSError):
            wifi.connect_if_needed([])
        self.assertEqual(wlan.connect_calls, [])

    def test_driver_rejection_skips_straight_to_next_network(self):
        # Real-hardware finding 2026-10-23: wlan.connect() returning False
        # means the driver already rejected the candidate (e.g. wrong
        # password) -- this must not still burn the full per-network
        # timeout waiting for isconnected(), which would never turn True.
        wlan = _FakeWlan(
            already_connected=False,
            reject_connect_ssids={"home"},
            connect_after_polls_by_ssid={"hotspot": 0},
        )
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        _wlan, ifconfig, ssid = wifi.connect_if_needed(
            [("home", "home-pw"), ("hotspot", "hotspot-pw")], timeout_s=30
        )
        self.assertEqual(wlan.connect_calls, [("home", "home-pw"), ("hotspot", "hotspot-pw")])
        self.assertEqual(ssid, "hotspot")
        self.assertEqual(ifconfig, wlan.ifconfig())

    def test_driver_rejection_of_every_network_raises_oserror_with_reason(self):
        wlan = _FakeWlan(already_connected=False, reject_connect_ssids={"home", "hotspot"})
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        with self.assertRaises(OSError) as ctx:
            wifi.connect_if_needed(
                [("home", "home-pw"), ("hotspot", "hotspot-pw")], timeout_s=30
            )
        self.assertIn("hotspot", str(ctx.exception))
        self.assertEqual(wlan.connect_calls, [("home", "home-pw"), ("hotspot", "hotspot-pw")])

    def test_on_progress_reports_each_attempt_and_outcome(self):
        wlan = _FakeWlan(
            already_connected=False,
            reject_connect_ssids={"home"},
            connect_after_polls_by_ssid={"hotspot": 0},
        )
        wifi = _fresh_wifi_import(_install_fake_network(wlan))
        wifi.time = _FakeClock()
        messages = []
        wifi.connect_if_needed(
            [("home", "home-pw"), ("hotspot", "hotspot-pw")],
            timeout_s=30, on_progress=messages.append,
        )
        self.assertTrue(any("home" in m and "connecting" in m for m in messages))
        self.assertTrue(any("home" in m and "rejected" in m for m in messages))
        self.assertTrue(any("hotspot" in m and "connected" in m for m in messages))


# ================================================================
# mac/mac_mouse_bridge.py: DragWatchdog + receive-loop plumbing
# ================================================================

class _FakeMonotonic:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class DragWatchdogTests(unittest.TestCase):
    def test_noop_when_not_dragging(self):
        clock = _FakeMonotonic()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=1.0, clock=clock)
        mouse = mac_mouse_bridge.DryRunMouse()
        clock.advance(10.0)
        self.assertFalse(watchdog.check(mouse))
        self.assertFalse(mouse.dragging)

    def test_does_not_release_before_timeout(self):
        clock = _FakeMonotonic()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=1.0, clock=clock)
        mouse = mac_mouse_bridge.DryRunMouse()
        mouse.down(0.5, 0.5)
        clock.advance(0.9)
        self.assertFalse(watchdog.check(mouse))
        self.assertTrue(mouse.dragging)

    def test_releases_after_silence_past_timeout(self):
        clock = _FakeMonotonic()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=1.0, clock=clock)
        mouse = mac_mouse_bridge.DryRunMouse()
        mouse.down(0.5, 0.5)
        clock.advance(1.1)
        self.assertTrue(watchdog.check(mouse))
        self.assertFalse(mouse.dragging)

    def test_mark_received_resets_the_timer(self):
        clock = _FakeMonotonic()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=1.0, clock=clock)
        mouse = mac_mouse_bridge.DryRunMouse()
        mouse.down(0.5, 0.5)
        clock.advance(0.8)
        watchdog.mark_received()  # a DRAG keep-alive packet just arrived
        clock.advance(0.8)
        self.assertFalse(watchdog.check(mouse))
        self.assertTrue(mouse.dragging)


class ProcessTickTests(unittest.TestCase):
    def test_any_raw_data_marks_received_even_if_not_a_mouse_packet(self):
        clock = _FakeMonotonic()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=1.0, clock=clock)
        mouse = mac_mouse_bridge.DryRunMouse()
        mouse.down(0.5, 0.5)
        with tempfile.TemporaryDirectory() as directory:
            logger = mac_mouse_bridge.TrackingCsvLogger(directory)
            clock.advance(0.9)
            mac_mouse_bridge.process_tick(b"@TRACK|L|1|1\r\n", mouse, logger, watchdog)
            clock.advance(0.9)
            # Elapsed since epoch is now 1.8s (> the 1.0s timeout), but only
            # 0.9s since the TRACK packet reset the watchdog -- it must not
            # release yet.
            self.assertFalse(watchdog.check(mouse))
            self.assertTrue(mouse.dragging)
            logger.close()

    def test_no_data_tick_still_checks_the_watchdog(self):
        clock = _FakeMonotonic()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=1.0, clock=clock)
        mouse = mac_mouse_bridge.DryRunMouse()
        mouse.down(0.5, 0.5)
        with tempfile.TemporaryDirectory() as directory:
            logger = mac_mouse_bridge.TrackingCsvLogger(directory)
            clock.advance(1.5)
            mac_mouse_bridge.process_tick(None, mouse, logger, watchdog)
            self.assertFalse(mouse.dragging)
            logger.close()


class UdpLoopIntegrationTests(unittest.TestCase):
    """Real loopback sockets + a real background thread; no board required.

    run_udp_loop() blocks for its whole tick budget, so these tests start it
    on a thread and wait for it to actually bind before sending anything --
    sending to a UDP port before any socket is bound to it is a real race
    (the datagram can be dropped), not just a test artifact.
    """

    def _start_server(self, port, mouse, logger, watchdog, max_ticks, poll_timeout_s=0.02):
        thread = threading.Thread(
            target=mac_mouse_bridge.run_udp_loop,
            args=("127.0.0.1", port, mouse, logger, watchdog),
            kwargs={"max_ticks": max_ticks, "poll_timeout_s": poll_timeout_s},
            daemon=True,
        )
        thread.start()
        time.sleep(0.05)  # let the server bind before the test sends anything
        return thread

    def test_run_udp_loop_dispatches_and_watchdog_releases_on_silence(self):
        port = _free_udp_port()
        mouse = mac_mouse_bridge.DryRunMouse()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=0.05)
        with tempfile.TemporaryDirectory() as directory:
            logger = mac_mouse_bridge.TrackingCsvLogger(directory)
            client = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
            try:
                thread = self._start_server(port, mouse, logger, watchdog, max_ticks=12)
                client.sendto(b"@MOUSE|DRAG_START|0.5000|0.5000\r\n", ("127.0.0.1", port))
                # DRAG_START lands on an early tick; every later tick sees
                # silence for well over the 0.05s timeout, so the drag must
                # self-release before the thread's tick budget runs out.
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
                self.assertFalse(mouse.dragging)
            finally:
                client.close()
                logger.close()

    def test_run_udp_loop_keeps_drag_alive_while_packets_keep_arriving(self):
        port = _free_udp_port()
        mouse = mac_mouse_bridge.DryRunMouse()
        watchdog = mac_mouse_bridge.DragWatchdog(timeout_s=0.05)
        with tempfile.TemporaryDirectory() as directory:
            logger = mac_mouse_bridge.TrackingCsvLogger(directory)
            client = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_DGRAM)
            try:
                thread = self._start_server(port, mouse, logger, watchdog, max_ticks=6)
                client.sendto(b"@MOUSE|DRAG_START|0.5000|0.5000\r\n", ("127.0.0.1", port))
                for _ in range(5):
                    time.sleep(0.01)  # well under the 0.05s watchdog timeout
                    client.sendto(b"@MOUSE|DRAG|0.5100|0.5100\r\n", ("127.0.0.1", port))
                # Every tick marks the watchdog alive, so it must never fire
                # even though each individual gap is small relative to the
                # short 0.05s timeout.
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
                self.assertTrue(mouse.dragging)
            finally:
                client.close()
                logger.close()


# ================================================================
# firmware/run_uart.py, firmware/run_wifi.py: thin CanMV IDE entry points
# ================================================================

class RunProfileEntryPointTests(unittest.TestCase):
    """Verify each entry point pins the right run profile, without ever
    importing the real smart_glass_server.py (which requires hardware-only
    media.* modules not available off-board)."""

    def _run_entry_point(self, filename):
        calls = []

        def fake_main(transport_kind=None, enable_web=None):
            calls.append({"transport_kind": transport_kind, "enable_web": enable_web})

        fake_module = types.ModuleType("smart_glass_server")
        fake_module.main = fake_main
        original = sys.modules.get("smart_glass_server")
        sys.modules["smart_glass_server"] = fake_module
        try:
            path = os.path.join(_REPO_ROOT, "firmware", filename)
            runpy.run_path(path, run_name="__main__")
        finally:
            if original is None:
                sys.modules.pop("smart_glass_server", None)
            else:
                sys.modules["smart_glass_server"] = original
        return calls

    def test_run_uart_pins_uart_transport_and_disables_web(self):
        calls = self._run_entry_point("run_uart.py")
        self.assertEqual(calls, [{"transport_kind": "uart", "enable_web": False}])

    def test_run_wifi_pins_udp_transport_and_enables_web(self):
        calls = self._run_entry_point("run_wifi.py")
        self.assertEqual(calls, [{"transport_kind": "udp", "enable_web": True}])


if __name__ == "__main__":
    unittest.main()
