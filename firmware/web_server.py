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

# ============================================================
# 스트리밍 전송 안정화 설정 (docs/DEV_HISTORY.md 6-10)
# ============================================================
#
# 세 기능을 각각 독립적으로 끄고 켤 수 있다 -- 하나가 문제를 일으키면
# 그 상수만 False로 되돌리면 된다(별도 파일로 떼지 않은 이유는 셋 다
# ClientSession의 소켓/내부 상태를 직접 다뤄야 해서, 분리하면 오히려
# 상태를 두 곳에서 관리하게 되기 때문 -- 아래 ClientSession이 소켓
# 소유권과 종료 책임을 유일하게 가진다).

# 한 번의 non-blocking send() 호출에 넘기는 최대 바이트 수. CanMV 공식
# ai_mjpeg_web_server.py 예제와 동일한 16KiB -- 큰 JPEG 프레임 하나를
# 통째로 send()에 넘기지 않고 쪼개서, RT-Smart 소켓 계층이 큰 단일
# 버퍼를 어떻게 처리하는지에 대한 불확실성을 없앤다(실측으로 문제가
# 있었던 건 아니고, 공식 패턴을 따라가는 예방적 조치).
ENABLE_CHUNKED_SEND = True
SEND_CHUNK_BYTES = 16384

# 전송 "진행" 기준 정지 감지 -- pump_send()가 1바이트라도 보낼 때마다
# 리셋된다. 네트워크가 완전히 끊기면 이게 걸린다.
ENABLE_SEND_STALL_TIMEOUT = True
SEND_STALL_TIMEOUT_MS = 5000

# 전송 "시작 시점" 기준 고정 데드라인 -- 중간에 바이트가 나가도 절대
# 리셋되지 않는다. 네트워크가 완전히 끊기지 않고 아주 조금씩만("트리클")
# 나가서 위 stall timeout이 영원히 리셋되는 경우를 잡아낸다. 초기
# 테스트값 5000ms, 실측 결과에 따라 조정 가능.
ENABLE_FRAME_DEADLINE = True
FRAME_DEADLINE_MS = 5000


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
        # 2026-10-21: 3채널(웹 RGB565 포함) + Wi-Fi 연결된 상태에서도 bind()가
        # 20회 모두 실패하는 사례가 재현되어, 어떤 OSError가 반복되는지
        # 확인하기 위해 마지막 실패 원인만 최소한으로 남긴다(루프를
        # 바꾸거나 타임아웃을 추가하지는 않음 — 기존 구조 그대로).
        bind_addr = socket.getaddrinfo("0.0.0.0", self.port)[0][-1]
        sock = None
        last_err = None
        for attempt in range(self.bind_retry_count):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(bind_addr)
                break
            except OSError as e:
                last_err = e
                try:
                    sock.close()
                except Exception:
                    pass
                sock = None
                time.sleep_ms(self.bind_retry_delay_ms)
        if sock is None:
            raise OSError("HttpServer: bind failed after %d retries, last_err=%r"
                           % (self.bind_retry_count, last_err))
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
                 idle_timeout_ms=20000, send_stall_timeout_ms=SEND_STALL_TIMEOUT_MS,
                 frame_deadline_ms=FRAME_DEADLINE_MS):
        self.sock = sock
        self.addr = addr
        self.request_timeout_ms = request_timeout_ms
        self.max_request_bytes = max_request_bytes
        self.idle_timeout_ms = idle_timeout_ms
        # 둘 다 전송(STATE_SENDING) 전용 -- is_stale()의 idle_timeout_ms와는
        # 별개다. send_stall_timeout_ms: 마지막으로 바이트가 조금이라도
        # 나간 시점부터 몇 ms(진행 기준, pump_send가 보낼 때마다 리셋).
        # frame_deadline_ms: 이번 전송을 시작한 시점부터 몇 ms(고정 기준,
        # 중간에 바이트가 나가도 절대 리셋 안 됨) -- 네트워크가 완전히
        # 끊기진 않고 아주 조금씩만("트리클") 나가면 진행 기준 타이머는
        # 계속 리셋돼서 영원히 안 걸리므로, 이 고정 데드라인이 그 경우를
        # 잡아낸다(docs/DEV_HISTORY.md 6-10 참고).
        self.send_stall_timeout_ms = send_stall_timeout_ms
        self.frame_deadline_ms = frame_deadline_ms

        self._request_buf = bytearray()
        self._request_deadline = time.ticks_add(time.ticks_ms(), request_timeout_ms)
        self._send_view = None
        self._send_offset = 0
        self._send_frame_started_ms = None
        self._headers_parsed = False
        self._body_start = 0

        self.state = self.STATE_READING
        self.method = None
        self.path = None
        self.content_length = 0
        self.body = b""
        self.created_ms = time.ticks_ms()
        self.last_progress_ms = self.created_ms

    def is_stale(self):
        return time.ticks_diff(time.ticks_ms(), self.last_progress_ms) > self.idle_timeout_ms

    def check_send_timeout(self):
        """STATE_SENDING일 때만 의미가 있다. 둘 중 하나라도 넘으면
        OSError를 던진다(호출자가 이미 OSError/ValueError를 세션 종료
        신호로 처리하고 있으므로 그대로 재사용) -- 메시지에 어느 기준을
        넘었는지와 진단용 프레임 크기/전송량을 그대로 담아, 호출자가
        추가 가공 없이 로그만 남기면 두 원인이 구분된다.
        """
        if self.state != self.STATE_SENDING or self._send_frame_started_ms is None:
            return
        if not (ENABLE_SEND_STALL_TIMEOUT or ENABLE_FRAME_DEADLINE):
            return
        now_ms = time.ticks_ms()
        frame_size = len(self._send_view) if self._send_view is not None else 0
        if ENABLE_SEND_STALL_TIMEOUT:
            since_progress_ms = time.ticks_diff(now_ms, self.last_progress_ms)
            if since_progress_ms > self.send_stall_timeout_ms:
                raise OSError(
                    "send stalled: no progress for %dms (limit %dms), frame_size=%d sent=%d"
                    % (since_progress_ms, self.send_stall_timeout_ms, frame_size, self._send_offset)
                )
        if ENABLE_FRAME_DEADLINE:
            since_start_ms = time.ticks_diff(now_ms, self._send_frame_started_ms)
            if since_start_ms > self.frame_deadline_ms:
                raise OSError(
                    "send frame deadline exceeded: %dms total (limit %dms), frame_size=%d sent=%d"
                    % (since_start_ms, self.frame_deadline_ms, frame_size, self._send_offset)
                )

    def pump_read(self):
        """한 번만 non-blocking recv 시도. 요청(헤더+본문)이 다 왔으면 path를 반환.

        GET처럼 본문이 없는 요청은 헤더 구분자(\\r\\n\\r\\n)만 찾으면 바로
        끝나던 예전 동작 그대로다. POST처럼 Content-Length가 있는 요청은
        헤더를 다 받은 뒤에도 본문 바이트가 그만큼 모일 때까지 계속
        READING 상태로 남아 다음 recv를 기다린다(self.body로 접근).
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
        elif chunk == b"":
            raise OSError("peer closed during request read")

        if not self._headers_parsed:
            idx = self._request_buf.find(b"\r\n\r\n")
            sep_len = 4
            if idx < 0:
                idx = self._request_buf.find(b"\n\n")
                sep_len = 2
            if idx < 0:
                if len(self._request_buf) >= self.max_request_bytes:
                    raise ValueError("request header too large")
                if time.ticks_diff(self._request_deadline, time.ticks_ms()) <= 0:
                    raise OSError("request read timeout")
                return None
            header_lines = bytes(self._request_buf[:idx]).split(b"\r\n")
            request_line = header_lines[0].split()
            self.method = request_line[0].decode() if len(request_line) >= 1 else "GET"
            self.path = request_line[1].decode().split("?", 1)[0] if len(request_line) >= 2 else "/"
            for header_line in header_lines[1:]:
                name, sep, value = header_line.partition(b":")
                if sep and name.strip().lower() == b"content-length":
                    try:
                        self.content_length = int(value.strip())
                    except ValueError:
                        self.content_length = 0
                    break
            self._headers_parsed = True
            self._body_start = idx + sep_len

        body_so_far = len(self._request_buf) - self._body_start
        if body_so_far < self.content_length:
            if len(self._request_buf) >= self.max_request_bytes:
                raise ValueError("request body too large")
            if time.ticks_diff(self._request_deadline, time.ticks_ms()) <= 0:
                raise OSError("request read timeout")
            return None

        self.body = bytes(self._request_buf[self._body_start:self._body_start + self.content_length])
        self.state = self.STATE_READY
        return self.path

    def queue(self, data):
        """새 응답/프레임 바이트를 전송 대기열에 올린다.

        ``_send_frame_started_ms``와 ``last_progress_ms``를 여기서 같은
        시점으로 리셋한다 -- frame_deadline_ms는 "이번 전송이 시작된
        시점" 기준이어야 하므로, 이전 전송의 흔적이 남아있으면 안 된다.
        """
        self._send_view = memoryview(data)
        self._send_offset = 0
        self.state = self.STATE_SENDING
        now_ms = time.ticks_ms()
        self._send_frame_started_ms = now_ms
        self.last_progress_ms = now_ms

    def pump_send(self):
        """한 번만 non-blocking send 시도. 전부 보냈으면 True, 아니면 False.

        EAGAIN/일시적 오류는 False로 흡수(다음 루프에 재시도), 그 외
        OSError는 그대로 올린다. ENABLE_CHUNKED_SEND가 켜져 있으면 한
        번에 SEND_CHUNK_BYTES까지만 send()에 넘긴다.
        """
        if self._send_view is None:
            return True
        try:
            if ENABLE_CHUNKED_SEND:
                end = min(self._send_offset + SEND_CHUNK_BYTES, len(self._send_view))
                sent = self.sock.send(self._send_view[self._send_offset:end])
            else:
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
