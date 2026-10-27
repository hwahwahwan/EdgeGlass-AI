"""Tests for firmware/web_server.py's ClientSession request parsing.

web_server.py has no hardware-only imports (only socket/select/time), so it
can run under plain CPython -- unlike firmware/smart_glass_server.py, which
imports media.sensor/media.display and can't be imported off-board (see
tests/test_wifi_mouse_transport.py's RunProfileEntryPointTests docstring).
This file covers the GET/POST/Content-Length parsing added for the
/device-info and /register routes (EdgeGlass-AI network auto-discovery,
2026-10-27) directly against ClientSession, plus a regression check that
plain GET requests (the pre-existing /health, /snapshot, /stream, default
routes) still parse exactly as before.
"""

import os
import socket as real_socket
import sys
import threading
import time as real_time
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIRMWARE_DIR = os.path.join(_REPO_ROOT, "firmware")
if _FIRMWARE_DIR not in sys.path:
    sys.path.insert(0, _FIRMWARE_DIR)

import web_server

# web_server.py is a board-only module (flat-deployed to /sdcard/smart_glass/,
# see /CLAUDE.md) that calls MicroPython's time.ticks_ms()/ticks_add()/
# ticks_diff() directly; it has never run under CPython before this file
# (no prior tests existed for it at all). Add tiny real-clock-based
# equivalents onto the actual `time` module for the duration of this file
# only -- these don't need MicroPython's 32-bit wraparound handling since
# every test here runs in well under a second.
_INSTALLED_TIME_SHIMS = []


def setUpModule():
    if not hasattr(real_time, "ticks_ms"):
        real_time.ticks_ms = lambda: int(real_time.monotonic() * 1000)
        _INSTALLED_TIME_SHIMS.append("ticks_ms")
    if not hasattr(real_time, "ticks_add"):
        real_time.ticks_add = lambda ticks, delta: ticks + delta
        _INSTALLED_TIME_SHIMS.append("ticks_add")
    if not hasattr(real_time, "ticks_diff"):
        real_time.ticks_diff = lambda later, earlier: later - earlier
        _INSTALLED_TIME_SHIMS.append("ticks_diff")


def tearDownModule():
    for name in _INSTALLED_TIME_SHIMS:
        delattr(real_time, name)
    _INSTALLED_TIME_SHIMS.clear()


def _pump_once_tolerant(session):
    """One pump_read() call, treating "no data available right now" as None.

    web_server.py's pump_read() only tolerates errno 11 (Linux/MicroPython's
    EAGAIN) from a non-blocking recv() -- pre-existing, unrelated to this
    patch, and left untouched here (board behavior, not a bug to fix as
    part of this change). On macOS the same "no data yet" condition is
    errno 35 (EWOULDBLOCK/EAGAIN), which isn't on that allow-list and would
    otherwise surface as an uncaught BlockingIOError purely from testing
    this off-board -- not a real parse failure, just "try again."
    """
    try:
        return session.pump_read()
    except BlockingIOError:
        return None


def _pump_until_ready(session, max_attempts=200, delay_s=0.005):
    """Call session.pump_read() until it returns a path (see
    _pump_once_tolerant for why transient BlockingIOError is swallowed) --
    mirrors how the real non-blocking caller (WebState.step(), called once
    per AI frame) just tries again next frame."""
    for _ in range(max_attempts):
        path = _pump_once_tolerant(session)
        if path is not None:
            return path
        real_time.sleep(delay_s)
    return None


class _ConnectedPair:
    """A real loopback TCP connection so ClientSession can recv() for real."""

    def __init__(self):
        listener = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        accepted = {}

        def _accept():
            conn, addr = listener.accept()
            accepted["conn"] = conn
            accepted["addr"] = addr

        thread = threading.Thread(target=_accept, daemon=True)
        thread.start()

        self.client = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_STREAM)
        self.client.connect(("127.0.0.1", port))
        thread.join(timeout=2)
        listener.close()

        self.server = accepted["conn"]
        self.server.setblocking(False)
        self.addr = accepted["addr"]

    def close(self):
        self.client.close()
        self.server.close()


class ClientSessionGetRegressionTests(unittest.TestCase):
    """A plain GET request must parse exactly as it did before POST/body support."""

    def test_get_request_yields_path_method_and_empty_body(self):
        pair = _ConnectedPair()
        try:
            pair.client.sendall(b"GET /snapshot HTTP/1.1\r\nHost: board\r\n\r\n")
            session = web_server.ClientSession(pair.server, pair.addr)
            path = _pump_until_ready(session)
            self.assertEqual(path, "/snapshot")
            self.assertEqual(session.method, "GET")
            self.assertEqual(session.body, b"")
            self.assertEqual(session.state, web_server.ClientSession.STATE_READY)
        finally:
            pair.close()

    def test_get_request_strips_query_string(self):
        pair = _ConnectedPair()
        try:
            pair.client.sendall(b"GET /health?x=1 HTTP/1.1\r\nHost: board\r\n\r\n")
            session = web_server.ClientSession(pair.server, pair.addr)
            path = _pump_until_ready(session)
            self.assertEqual(path, "/health")
        finally:
            pair.close()


class ClientSessionPostBodyTests(unittest.TestCase):
    """POST /register sends identity+udp_port as a JSON body with Content-Length."""

    def test_post_with_body_in_one_chunk(self):
        pair = _ConnectedPair()
        try:
            body = b'{"identity":"EDGEGLASS_USER","udp_port":9000}'
            request = (
                b"POST /register HTTP/1.1\r\nHost: board\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: %d\r\n\r\n" % len(body) + body
            )
            pair.client.sendall(request)
            session = web_server.ClientSession(pair.server, pair.addr)
            path = _pump_until_ready(session)
            self.assertEqual(path, "/register")
            self.assertEqual(session.method, "POST")
            self.assertEqual(session.body, body)
            self.assertEqual(session.state, web_server.ClientSession.STATE_READY)
        finally:
            pair.close()

    def test_post_body_arriving_in_separate_chunks(self):
        """Headers and body can land in separate TCP segments -- pump_read()
        must keep returning None until the whole Content-Length body is in,
        not just the header terminator."""
        pair = _ConnectedPair()
        try:
            body = b'{"identity":"EDGEGLASS_USER","udp_port":9000}'
            header = (
                b"POST /register HTTP/1.1\r\nHost: board\r\n"
                b"Content-Length: %d\r\n\r\n" % len(body)
            )
            session = web_server.ClientSession(pair.server, pair.addr)

            pair.client.sendall(header)
            real_time.sleep(0.02)  # let loopback deliver it before checking
            self.assertIsNone(_pump_once_tolerant(session))  # headers in, body not yet

            pair.client.sendall(body[:10])
            real_time.sleep(0.02)
            self.assertIsNone(_pump_once_tolerant(session))  # partial body only

            pair.client.sendall(body[10:])
            path = _pump_until_ready(session)
            self.assertEqual(path, "/register")
            self.assertEqual(session.body, body)
        finally:
            pair.close()

    def test_content_length_header_is_case_insensitive(self):
        pair = _ConnectedPair()
        try:
            body = b'{"identity":"EDGEGLASS_USER","udp_port":9000}'
            request = (
                b"POST /register HTTP/1.1\r\nHost: board\r\n"
                b"content-length: %d\r\n\r\n" % len(body) + body
            )
            pair.client.sendall(request)
            session = web_server.ClientSession(pair.server, pair.addr)
            _pump_until_ready(session)
            self.assertEqual(session.body, body)
        finally:
            pair.close()


if __name__ == "__main__":
    unittest.main()
