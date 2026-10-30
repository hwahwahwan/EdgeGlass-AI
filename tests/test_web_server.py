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


def _pump_send_once_tolerant(session):
    """One pump_send() call, treating "can't send right now" as False --
    mirror of _pump_once_tolerant for the send side (see its docstring for
    why macOS's errno 35 needs this and board/Linux's errno 11 doesn't)."""
    try:
        return session.pump_send()
    except BlockingIOError:
        return False


class _RecordingSocket:
    """Fake socket for pump_send()/chunking tests -- always accepts exactly
    the slice it's given (no EAGAIN simulation needed) and records each
    send() call's size, so chunk-cap behavior can be asserted directly
    without depending on real OS socket buffer sizes."""

    def __init__(self):
        self.sent_chunks = []

    def send(self, data):
        chunk = bytes(data)
        self.sent_chunks.append(chunk)
        return len(chunk)

    def close(self):
        pass


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


# ================================================================
# docs/DEV_HISTORY.md 6-10: stall timeout / frame deadline / 16KiB 분할
# 전송 -- 세 기능 모두 독립 ON/OFF 상수(web_server.ENABLE_*)로 토글
# 가능하므로, 테스트도 기능별로 분리한다(문제가 생기면 그 기능 하나만
# 되돌릴 수 있어야 한다는 요구사항).
# ================================================================

class ChunkedSendTests(unittest.TestCase):
    def setUp(self):
        self._orig_enable = web_server.ENABLE_CHUNKED_SEND
        self._orig_chunk = web_server.SEND_CHUNK_BYTES

    def tearDown(self):
        web_server.ENABLE_CHUNKED_SEND = self._orig_enable
        web_server.SEND_CHUNK_BYTES = self._orig_chunk

    def test_large_payload_is_sent_in_capped_chunks_when_enabled(self):
        web_server.ENABLE_CHUNKED_SEND = True
        web_server.SEND_CHUNK_BYTES = 100
        sock = _RecordingSocket()
        session = web_server.ClientSession(sock, ("127.0.0.1", 0))
        payload = bytes(range(256)) * 2  # 512 bytes, well over the 100-byte cap
        session.queue(payload)
        while not session.pump_send():
            pass
        self.assertTrue(all(len(c) <= 100 for c in sock.sent_chunks))
        self.assertGreater(len(sock.sent_chunks), 1)
        self.assertEqual(b"".join(sock.sent_chunks), payload)

    def test_disabling_chunking_sends_full_remaining_buffer_in_one_call(self):
        web_server.ENABLE_CHUNKED_SEND = False
        sock = _RecordingSocket()
        session = web_server.ClientSession(sock, ("127.0.0.1", 0))
        payload = bytes(range(256)) * 2
        session.queue(payload)
        done = session.pump_send()
        self.assertTrue(done)
        self.assertEqual(sock.sent_chunks, [payload])


class SendStallTimeoutTests(unittest.TestCase):
    """"전송 진행" 기준 정지 감지 -- pump_send()가 바이트를 보낼 때마다
    last_progress_ms가 리셋된다는 전제 위에서, 그 이후로 전혀 진행이
    없을 때만 걸린다."""

    def setUp(self):
        self._orig = web_server.ENABLE_SEND_STALL_TIMEOUT

    def tearDown(self):
        web_server.ENABLE_SEND_STALL_TIMEOUT = self._orig

    def test_raises_after_no_progress_past_the_limit(self):
        session = web_server.ClientSession(
            _RecordingSocket(), ("127.0.0.1", 0), send_stall_timeout_ms=50)
        session.queue(b"x" * 10)
        session.last_progress_ms = real_time.ticks_add(session.last_progress_ms, -100)
        with self.assertRaises(OSError) as ctx:
            session.check_send_timeout()
        self.assertIn("stalled", str(ctx.exception))

    def test_does_not_raise_before_the_limit(self):
        session = web_server.ClientSession(
            _RecordingSocket(), ("127.0.0.1", 0), send_stall_timeout_ms=5000)
        session.queue(b"x" * 10)
        session.check_send_timeout()  # must not raise

    def test_disabled_flag_suppresses_stall_detection(self):
        web_server.ENABLE_SEND_STALL_TIMEOUT = False
        session = web_server.ClientSession(
            _RecordingSocket(), ("127.0.0.1", 0), send_stall_timeout_ms=10)
        session.queue(b"x" * 10)
        session.last_progress_ms = real_time.ticks_add(session.last_progress_ms, -1000)
        session.check_send_timeout()  # must not raise -- feature off


class FrameDeadlineTests(unittest.TestCase):
    """docs/DEV_HISTORY.md 6-10의 핵심 시나리오: 네트워크가 완전히 끊기지
    않고 아주 조금씩만("트리클") 나가면 진행 기준 stall timeout의
    last_progress_ms는 계속 리셋돼서 영원히 안 걸린다 -- 전송 "시작
    시점" 기준으로 절대 리셋되지 않는 이 데드라인만이 그 경우를 잡는다."""

    def setUp(self):
        self._orig = web_server.ENABLE_FRAME_DEADLINE

    def tearDown(self):
        web_server.ENABLE_FRAME_DEADLINE = self._orig

    def test_raises_when_total_time_exceeds_deadline_even_with_fresh_progress(self):
        session = web_server.ClientSession(
            _RecordingSocket(), ("127.0.0.1", 0), frame_deadline_ms=50)
        session.queue(b"x" * 10)
        # last_progress_ms는 queue()가 방금 리셋해서 "진행 중"처럼 보인다
        # -- stall timeout 혼자서는 절대 못 잡는, 트리클 상황을 흉내낸다.
        session._send_frame_started_ms = real_time.ticks_add(
            session._send_frame_started_ms, -100)
        with self.assertRaises(OSError) as ctx:
            session.check_send_timeout()
        self.assertIn("deadline", str(ctx.exception))

    def test_does_not_raise_before_the_deadline(self):
        session = web_server.ClientSession(
            _RecordingSocket(), ("127.0.0.1", 0), frame_deadline_ms=5000)
        session.queue(b"x" * 10)
        session.check_send_timeout()  # must not raise

    def test_disabled_flag_suppresses_deadline_detection(self):
        web_server.ENABLE_FRAME_DEADLINE = False
        session = web_server.ClientSession(
            _RecordingSocket(), ("127.0.0.1", 0), frame_deadline_ms=10)
        session.queue(b"x" * 10)
        session._send_frame_started_ms = real_time.ticks_add(
            session._send_frame_started_ms, -1000)
        session.check_send_timeout()  # must not raise -- feature off


class StreamStallRecoveryIntegrationTests(unittest.TestCase):
    """사용자가 적용 전 반드시 확인하라고 요구한 안전성 검증: 멈춘 세션을
    강제로 닫았을 때 (1) self.active 역할의 상태가 정상적으로 None으로
    돌아가는지, (2) 리스닝 소켓이 살아남아 새 연결을 받을 수 있는지,
    (3) 그 새 연결이 끝까지 정상 응답을 받는지 -- 전부 실제 loopback
    소켓으로 검증한다(가짜 소켓이 아님). smart_glass_server.py의
    WebState는 media.sensor 의존성 때문에 이 환경에서 못 띄우므로,
    그 핵심 오류 처리 규약(OSError/ValueError -> session.close() +
    active=None, 그 다음 step()에서 재accept)만 그대로 재현한다.
    """

    def test_listener_survives_a_forced_close_and_serves_a_new_client(self):
        server = web_server.HttpServer(0).start()
        port = server.sock.getsockname()[1]
        active = {"session": None}

        def step():
            if active["session"] is None:
                accepted = server.accept()
                if accepted is not None:
                    sock, addr = accepted
                    active["session"] = web_server.ClientSession(
                        sock, addr, idle_timeout_ms=50)
                return
            session = active["session"]
            if session.is_stale():
                session.close()
                active["session"] = None
                return
            try:
                if session.state == web_server.ClientSession.STATE_READING:
                    path = _pump_once_tolerant(session)
                    if path is None:
                        return
                    session.queue(web_server.http_response(
                        "200 OK", "text/plain", b"ok"))
                if session.state == web_server.ClientSession.STATE_SENDING:
                    if _pump_send_once_tolerant(session):
                        session.close()
                        active["session"] = None
            except (OSError, ValueError):
                session.close()
                active["session"] = None

        try:
            # 클라이언트 A: 연결만 하고 일부러 아무것도 안 보낸다 --
            # 멈춘/맛이 간 브라우저 연결과 동일한 상황. is_stale()의
            # 50ms 기준으로 강제 정리되는 과정을 그대로 거친다.
            client_a = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_STREAM)
            client_a.connect(("127.0.0.1", port))

            deadline = real_time.monotonic() + 2.0
            while active["session"] is None and real_time.monotonic() < deadline:
                step()
                real_time.sleep(0.005)
            self.assertIsNotNone(active["session"], "server never accepted client A")

            real_time.sleep(0.08)  # is_stale()의 50ms 기준을 실제로 넘김
            closed = False
            deadline = real_time.monotonic() + 2.0
            while real_time.monotonic() < deadline:
                step()
                if active["session"] is None:
                    closed = True
                    break
                real_time.sleep(0.005)
            self.assertTrue(closed, "stalled session was never cleaned up")

            # 서버가 실제로 소켓을 끊었다는 걸 클라이언트 쪽에서도 확인
            # -- 실제 브라우저의 onerror가 반응할 수 있는 바로 그 신호.
            client_a.settimeout(2)
            self.assertEqual(client_a.recv(16), b"")
            client_a.close()

            # 핵심 검증: 리스닝 소켓이 여전히 살아있고, 새 클라이언트의
            # 요청을 끝까지 정상적으로 처리하는지. client_b는 non-blocking
            # 으로 두고 매번 즉시 재시도한다 -- blocking recv(timeout=...)를
            # 매 반복마다 쓰면 그 자체가 idle_timeout_ms(50ms)를 넘겨버려
            # 서버가 요청을 읽기도 전에 세션을 "정체"로 판정해버린다(실제로
            # 겪은 레이스 -- 제품 코드 문제가 아니라 이 폴링 루프 자체의
            # 버그였다).
            client_b = real_socket.socket(real_socket.AF_INET, real_socket.SOCK_STREAM)
            client_b.connect(("127.0.0.1", port))
            client_b.sendall(b"GET / HTTP/1.1\r\nHost: board\r\n\r\n")
            client_b.setblocking(False)

            response = b""
            deadline = real_time.monotonic() + 2.0
            while real_time.monotonic() < deadline and b"ok" not in response:
                step()
                try:
                    chunk = client_b.recv(4096)
                    if chunk:
                        response += chunk
                except (BlockingIOError, real_socket.timeout):
                    pass
                real_time.sleep(0.002)
            client_b.close()
            self.assertIn(b"200 OK", response)
            self.assertIn(b"ok", response)
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
