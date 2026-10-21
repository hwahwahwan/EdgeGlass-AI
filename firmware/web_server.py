# ============================================================
# 범용 논블로킹 HTTP 연결 처리 모듈
# ============================================================
#
# wifi_test/mjpeg_stream_test.py에서 검증된 소켓 처리 패턴(NIC 레이스
# 재시도, EAGAIN 처리, select.poll 기반 accept)을 재사용하되, 실시간
# AI/마우스 제어 루프 안에서 안전하게 섞어 쓸 수 있도록 "한 번 호출하면
# 한 번만 시도하고 즉시 반환"하는 논블로킹 스텝(step) 방식으로 바꿨다.
#
# 기존 mjpeg_stream_test.py의 send_all()/read_path()는 내부에 자체
# 재시도 루프(최대 SEND_STALL_TIMEOUT_MS=15000)가 있어, 느린 네트워크를
# 만나면 호출자를 최대 15초까지 블로킹한다. 오케스트레이터의 메인 루프는
# 매 프레임 마우스 제어를 계속해야 하므로 이 방식을 그대로 가져오면 안
# 된다. 그래서 이 모듈은 절대 내부에서 sleep/재시도 루프를 돌지 않는다.
#
# 미검증 사항: 이 논블로킹 스텝 방식은 로컬 설계 단계에서 작성한 것으로,
# 아직 실제 보드에서 실행해 본 적이 없다. 보드 연결 후 가장 먼저
# 검증해야 할 항목이다.

import socket
import select
import time


def error_code(error):
    return getattr(error, "errno", error.args[0] if error.args else None)


def http_response(status, content_type, body):
    """상태줄+헤더+본문을 하나의 bytes로 합쳐 반환한다.

    한 번의 non-blocking send 호출들로 흘려보낼 수 있도록, 호출자가
    여러 조각을 따로 만들 필요가 없게 전부 이어붙인다.
    """
    header = (
        "HTTP/1.1 %s\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        "\r\n"
    ) % (status, content_type, len(body))
    return header.encode() + body


MJPEG_STREAM_HEADER = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
    b"Connection: close\r\n\r\n"
)


def mjpeg_part(jpeg_bytes):
    """MJPEG 멀티파트 한 프레임(헤더+본문+구분자)을 하나의 bytes로 합친다."""
    part_header = (
        "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n"
        % len(jpeg_bytes)
    )
    return part_header.encode() + jpeg_bytes + b"\r\n"


class HttpServer:
    """포트 바인딩과 non-blocking accept만 담당하는 얇은 래퍼."""

    def __init__(self, port, backlog=4, bind_retry_count=20, bind_retry_delay_ms=500):
        self.port = port
        self.backlog = backlog
        self.bind_retry_count = bind_retry_count
        self.bind_retry_delay_ms = bind_retry_delay_ms
        self.sock = None
        self._poll = None

    def start(self):
        bind_addr = socket.getaddrinfo("0.0.0.0", self.port)[0][-1]
        sock = None
        for attempt in range(self.bind_retry_count):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(bind_addr)
                break
            except OSError:
                try:
                    sock.close()
                except Exception:
                    pass
                sock = None
                time.sleep_ms(self.bind_retry_delay_ms)
        if sock is None:
            raise OSError("HttpServer: bind failed after %d retries" % self.bind_retry_count)
        sock.listen(self.backlog)
        sock.setblocking(False)
        self.sock = sock
        self._poll = select.poll()
        self._poll.register(self.sock, select.POLLIN)
        return self

    def accept(self):
        """대기 중인 연결이 있으면 (socket, addr) 튜플을, 없으면 None을 반환.

        poll(0)으로 즉시 확인만 하고 절대 대기하지 않는다 — 메인 루프를
        막지 않기 위함.
        """
        if self.sock is None:
            return None
        if not self._poll.poll(0):
            return None
        try:
            conn, addr = self.sock.accept()
        except OSError as e:
            if error_code(e) != 11:
                raise
            return None
        conn.setblocking(False)
        return conn, addr

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


class ClientSession:
    """연결 하나의 상태를 들고 있는 논블로킹 세션.

    사용법:
        session = ClientSession(sock, addr)
        path = session.pump_read()       # None이면 아직 요청 안 끝남
        if path is not None:
            session.queue(http_response(...))
        while not session.pump_send():   # 매 프레임 한 번씩만 호출
            ...                            # 다 보낼 때까지 다음 루프에서 계속
    """

    STATE_READING = "reading"
    STATE_READY = "ready"
    STATE_SENDING = "sending"
    STATE_DONE = "done"

    def __init__(self, sock, addr, request_timeout_ms=3000, max_request_bytes=4096,
                 idle_timeout_ms=20000):
        self.sock = sock
        self.addr = addr
        self.request_timeout_ms = request_timeout_ms
        self.max_request_bytes = max_request_bytes
        self.idle_timeout_ms = idle_timeout_ms

        self._request_buf = bytearray()
        self._request_deadline = time.ticks_add(time.ticks_ms(), request_timeout_ms)
        self._send_view = None
        self._send_offset = 0

        self.state = self.STATE_READING
        self.path = None
        self.last_progress_ms = time.ticks_ms()

    def is_stale(self):
        return time.ticks_diff(time.ticks_ms(), self.last_progress_ms) > self.idle_timeout_ms

    def pump_read(self):
        """한 번만 non-blocking recv 시도. 요청 헤더가 다 왔으면 path를 반환.

        아직이면 None. 타임아웃/본문 과대/연결 종료는 OSError/ValueError로 알림.
        """
        if self.state != self.STATE_READING:
            return self.path
        try:
            chunk = self.sock.recv(min(256, self.max_request_bytes - len(self._request_buf)))
        except OSError as e:
            if error_code(e) != 11:
                raise
            chunk = None
        if chunk:
            self.last_progress_ms = time.ticks_ms()
            self._request_buf.extend(chunk)
            idx = self._request_buf.find(b"\r\n\r\n")
            if idx < 0:
                idx = self._request_buf.find(b"\n\n")
            if idx >= 0:
                line = bytes(self._request_buf[:idx]).split(b"\r\n", 1)[0].split()
                self.path = line[1].decode().split("?", 1)[0] if len(line) >= 2 else "/"
                self.state = self.STATE_READY
                return self.path
        elif chunk == b"":
            raise OSError("peer closed during request read")

        if len(self._request_buf) >= self.max_request_bytes:
            raise ValueError("request header too large")
        if time.ticks_diff(self._request_deadline, time.ticks_ms()) <= 0:
            raise OSError("request read timeout")
        return None

    def queue(self, data):
        """새 응답/프레임 바이트를 전송 대기열에 올린다."""
        self._send_view = memoryview(data)
        self._send_offset = 0
        self.state = self.STATE_SENDING

    def pump_send(self):
        """한 번만 non-blocking send 시도. 전부 보냈으면 True, 아니면 False.

        EAGAIN/일시적 오류는 False로 흡수(다음 루프에 재시도), 그 외
        OSError는 그대로 올린다.
        """
        if self._send_view is None:
            return True
        try:
            sent = self.sock.send(self._send_view[self._send_offset:])
        except OSError as e:
            if error_code(e) in (11, 110):
                return False
            raise
        if sent:
            self.last_progress_ms = time.ticks_ms()
            self._send_offset += sent
        if self._send_offset >= len(self._send_view):
            self._send_view = None
            self._send_offset = 0
            return True
        return False

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass
        self.state = self.STATE_DONE
