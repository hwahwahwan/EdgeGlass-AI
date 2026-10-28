#!/usr/bin/env python3
"""Thin macOS bridge: @MOUSE serial records -> CoreGraphics mouse events.

Install only on the Mac that runs this file:
    python3 -m pip install pyserial pyobjc-framework-Quartz
"""

import argparse
import csv
from datetime import datetime
import glob
import os
import sys
import threading
import time

PREFIX = "@MOUSE|"
TRACK_PREFIX = "@TRACK|"
HELLO_PREFIX = "@HELLO|"
ACK_PREFIX = "@ACK|"
DEFAULT_UART2_PORT = "/dev/cu.usbmodem58930597043"
DEFAULT_UDP_BIND_HOST = "0.0.0.0"
DEFAULT_UDP_PORT = 9000
# Matches firmware/smart_glass_server.py's WEB_PORT. The two processes run on
# separate machines (board vs Mac) with no shared config file, so this is
# kept in sync by convention rather than import -- override with --web-port
# if the board's WEB_PORT is ever changed.
DEFAULT_WEB_PORT = 8060
# EdgeGlass-AI 네트워크 자동 탐색/상호 식별 (2026-10-27): 보드는 더 이상 자기
# 서브넷을 스캔하지 않는다 -- 이 Mac이 능동적으로 TCP WEB_PORT로 보드를 찾고
# (GET /device-info, 식별 문자열 확인), POST /register로 자신의 UDP 포트를
# 알려준다. 암호화/인증이 아니라 다른 장치와 혼동하지 않기 위한 식별용 문자열.
DEVICE_INFO_PATH = "/device-info"
REGISTER_PATH = "/register"
BOARD_IDENTITY = "EDGEGLASS_BOARD"
USER_IDENTITY = "EDGEGLASS_USER"
# 후보 호스트 하나당 TCP 탐색 타임아웃 -- 짧게 잡아야 응답 없는 호스트
# (리스너 없음/방화벽) 때문에 /24(254개 호스트) 스캔이 몇 분씩 걸리지 않는다.
SCAN_CONNECT_TIMEOUT_S = 0.3
# ThreadPoolExecutor의 워커 수 상한 -- 소켓 connect()는 블로킹이라 동시
# 워커 수로 전체 스캔 시간이 대략 (호스트 수 / SCAN_MAX_WORKERS) *
# SCAN_CONNECT_TIMEOUT_S로 제한된다(보드가 없는 최악의 경우).
SCAN_MAX_WORKERS = 32
REGISTER_TIMEOUT_S = 2.0
# 보드를 아직 못 찾았거나(또는 로컬 IP 변경으로 재탐색할 때) 재시도 간격.
DISCOVERY_RETRY_INTERVAL_S = 5.0
# How often a repeated "couldn't parse this line" diagnostic is allowed to
# print, so a persistently garbled link doesn't flood the terminal.
PARSE_FAIL_LOG_INTERVAL_S = 2.0
# How often main()'s UDP loop re-checks the Mac's own local IP for the
# "[NET] Local IP changed" diagnostic (ticks are poll_timeout_s apart).
LOCAL_IP_RECHECK_TICKS = 150
# Easy to change via --drag-timeout. While a drag is genuinely held, the
# K230 side (mouse_controller.py) sends a DRAG packet every frame -- and a
# keep-alive at the same rate even through its own brief hand-loss grace
# period -- so a 1s silence is a reliable signal of an actually dead link,
# not just a slow frame or a short detector miss.
DEFAULT_DRAG_TIMEOUT_S = 1.0
# How often the receive loop wakes up to re-check the watchdog even with no
# incoming data. Derived from the configured timeout so a much smaller
# --drag-timeout still gets checked promptly.
MAX_WATCHDOG_POLL_INTERVAL_S = 0.2

TRACK_FIELDS = (
    "bbox_cx", "bbox_cy", "bbox_w", "bbox_h",
    "roi_cx", "roi_cy", "roi_side",
    "wrist_x", "wrist_y", "palm_x", "palm_y",
    "index_tip_x", "index_tip_y",
    "norm_wrist_x", "norm_wrist_y", "norm_index_tip_x", "norm_index_tip_y",
    "fallback", "fist",
)


def parse_tracking(line):
    """Parse a diagnostic record without treating it as a mouse action."""
    fields = line.strip().split("|")
    if len(fields) == 4 and fields[:2] == ["@TRACK", "L"]:
        return "L", fields[2], fields[3], (), ()
    if len(fields) != 6 or fields[:2] != ["@TRACK", "S"]:
        return None
    sample = fields[4].split(",")
    delta = () if not fields[5] else fields[5].split(",")
    if len(sample) != len(TRACK_FIELDS) or len(delta) not in (0, len(TRACK_FIELDS) - 2):
        return None
    return "S", fields[2], fields[3], sample, delta


class TrackingCsvLogger:
    """Lazy, best-effort Mac-side sink for UART tracking records."""

    def __init__(self, log_dir=None):
        self.log_dir = log_dir or os.path.join(os.path.dirname(__file__), "logs")
        self.file = None
        self.writer = None
        self.disabled = False
        self.path = None

    def write(self, record):
        if record is None or self.disabled:
            return
        try:
            if self.file is None:
                os.makedirs(self.log_dir, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.path = os.path.join(self.log_dir, "tracking_%s.csv" % stamp)
                needs_header = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
                self.file = open(self.path, "a", newline="")
                self.writer = csv.writer(self.file)
                if needs_header:
                    self.writer.writerow(
                        ["received_at", "kind", "board_ms", "frame"]
                        + list(TRACK_FIELDS)
                        + ["d_" + name for name in TRACK_FIELDS[:-2]]
                    )
            kind, board_ms, frame, sample, delta = record
            self.writer.writerow(
                [datetime.now().isoformat(timespec="milliseconds"), kind, board_ms, frame]
                + list(sample) + [""] * (len(TRACK_FIELDS) - len(sample))
                + list(delta) + [""] * (len(TRACK_FIELDS) - 2 - len(delta))
            )
            self.file.flush()
        except OSError as exc:
            self.disabled = True
            print("Tracking CSV disabled: %s" % exc, file=sys.stderr)
            self.close()

    def close(self):
        if self.file is not None:
            try:
                self.file.close()
            except OSError:
                pass
            self.file = None


def available_ports():
    """Return candidate CanMV CDC devices without guessing their role."""
    paths = []
    for pattern in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*"):
        paths.extend(glob.glob(pattern))
    return sorted(set(paths))


def get_local_ip():
    """Return this Mac's current outbound-route IP, no interface name assumed.

    Standard portable trick: a UDP "connect" never actually sends a packet
    or requires reachability, it only asks the OS to pick the local address
    it would use to reach that destination -- so this works for Wi-Fi,
    Ethernet, USB tethering, whatever interface currently has the default
    route, and even with no real internet access (a hotspot's own gateway
    is enough). Returns None rather than raising if there is no route at
    all (e.g. Wi-Fi fully off).
    """
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def check_accessibility_trusted():
    """Best-effort macOS Accessibility trust check, distinct from network issues.

    Returns True/False when the platform API is available, or None when it
    isn't (missing optional dependency, non-macOS) -- callers should treat
    None as "unknown", not "denied".
    """
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        return None
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return None


def parse_message(line):
    """Parse exactly one protocol line; return (action, x, y) or None."""
    line = line.strip()
    if not line.startswith(PREFIX):
        return None
    fields = line.split("|")
    if len(fields) < 2:
        return None
    action = fields[1]
    if action in ("MOVE", "DRAG_START", "DRAG"):
        if len(fields) != 4:
            return None
        try:
            x = float(fields[2])
            y = float(fields[3])
        except ValueError:
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        return action, x, y
    if action in ("CLICK", "DRAG_END", "STOP") and len(fields) == 2:
        return action, None, None
    return None


class DragWatchdog:
    """Fail-safe release when no packet arrives while a drag is held.

    Covers Wi-Fi/UDP link loss or packet loss where even DRAG_END never
    arrives: without this, a dropped connection would leave the OS mouse
    button held down forever. Any successfully received byte (mouse or
    tracking) counts as proof the link is alive and resets the timer; only
    a held drag with no proof-of-life for ``timeout_s`` is force-released.
    """

    def __init__(self, timeout_s=DEFAULT_DRAG_TIMEOUT_S, clock=time.monotonic):
        self.timeout_s = timeout_s
        self._clock = clock
        self.last_rx = clock()

    def mark_received(self):
        self.last_rx = self._clock()

    def check(self, mouse):
        """Return True if a stale drag was just force-released."""
        if mouse.dragging and (self._clock() - self.last_rx) > self.timeout_s:
            print("DRAG_WATCHDOG", "no packet for >%.2fs, releasing drag" % self.timeout_s,
                  file=sys.stderr)
            mouse.up()
            self.mark_received()
            return True
        return False


# Edge-triggered mouse commands worth a one-line confirmation; MOVE/DRAG are
# intentionally excluded since they arrive every frame and would otherwise
# flood the terminal (see requirement: don't let repeated MOVE logging do
# that).
_LOGGED_ACTIONS = ("CLICK", "DRAG_START", "DRAG_END", "STOP")

# Mutable module-level state (not a constant) so handle_line's rate limiter
# survives across calls without needing a class just for this.
_parse_fail_state = {"last_log": 0.0}


def _log_parse_failure(line):
    now = time.monotonic()
    if now - _parse_fail_state["last_log"] < PARSE_FAIL_LOG_INTERVAL_S:
        return
    _parse_fail_state["last_log"] = now
    print("PARSE_FAIL", "line=%r" % (line,), file=sys.stderr)


def handle_line(line, mouse, tracking_logger, on_mouse_packet=None):
    """Parse and dispatch exactly one decoded protocol line.

    ``on_mouse_packet()``, if given, fires on every line that parses as a
    valid @MOUSE action (MOVE/CLICK/DRAG*/STOP alike) -- main() uses this,
    deduped to the first call only, for the concise "[UDP] 마우스 패킷
    수신 시작" status line.
    """
    if line.startswith(TRACK_PREFIX):
        tracking_logger.write(parse_tracking(line))
        return
    if line.startswith(HELLO_PREFIX):
        # Discovery probes are replied to separately in run_udp_loop (the
        # reply needs the sender address, which only recvfrom() has) --
        # here they are just a known, expected prefix, not parse garbage.
        return
    message = parse_message(line)
    if message is None:
        _log_parse_failure(line)
        return
    if on_mouse_packet is not None:
        on_mouse_packet()
    if message[0] in _LOGGED_ACTIONS:
        print("%s_RX" % message[0], "time=", time.time(),
              "packet=@MOUSE|%s" % message[0], flush=True)
    dispatch(mouse, message)


def process_tick(raw, mouse, tracking_logger, watchdog, on_mouse_packet=None):
    """One receive-loop step, shared by the UART and UDP readers.

    ``raw`` is the newly received bytes for this tick, or falsy if nothing
    arrived (a read timeout). The watchdog is always checked so a stale
    drag is released even while the link stays completely silent.
    """
    if raw:
        watchdog.mark_received()
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        handle_line(line, mouse, tracking_logger, on_mouse_packet=on_mouse_packet)
    watchdog.check(mouse)


def run_uart_loop(port, baud, mouse, tracking_logger, watchdog, max_ticks=None,
                   poll_timeout_s=MAX_WATCHDOG_POLL_INTERVAL_S):
    import serial
    with serial.Serial(port, baud, timeout=poll_timeout_s) as connection:
        print("Reading %s at %d baud. Press Ctrl-C to stop." % (port, baud))
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            process_tick(connection.readline(), mouse, tracking_logger, watchdog)
            ticks += 1


def _reply_to_hello(sock, addr, on_registered):
    """Ack a board's discovery probe directly back to its real address.

    recvfrom() already told us exactly where this came from -- no
    broadcast or pre-shared address needed. Idempotent: replies every time
    so a board that restarts (or whose IP changes on hotspot reconnect)
    re-registers automatically the next time it probes, with no special
    "already registered" branch to get wrong.
    """
    try:
        sock.sendto((ACK_PREFIX + "ok\r\n").encode(), addr)
    except OSError:
        return
    if on_registered is not None:
        on_registered(addr)


def _announce_web_urls(board_ip, web_port):
    """Print the board's web server URLs once its address is known."""
    print("[WEB] Main:   http://%s:%d/" % (board_ip, web_port))
    print("[WEB] Stream: http://%s:%d/stream" % (board_ip, web_port))


def _hexmask_to_dotted(hexmask):
    """Convert macOS ifconfig's '0xffffff00'-style netmask to dotted form."""
    value = int(hexmask, 16)
    return "%d.%d.%d.%d" % (
        (value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def get_local_ip_and_netmask(ip=None):
    """Return (ip, netmask) for this Mac's current outbound interface.

    ``ip`` lets a caller reuse an already-known get_local_ip() result
    instead of probing twice. The netmask comes from parsing `ifconfig`
    (stdlib-only subprocess call, no extra dependency) for the line
    matching that same IP; returns (ip, None) if ifconfig is unavailable or
    the IP isn't found there (non-macOS, odd network setup), so a caller
    can treat "no netmask" as "can't scan" instead of crashing.
    """
    import subprocess

    local_ip = get_local_ip() if ip is None else ip
    if local_ip is None:
        return None, None
    try:
        output = subprocess.check_output(["ifconfig"], text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return local_ip, None
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "inet" and parts[1] == local_ip and "netmask" in parts:
            hexmask = parts[parts.index("netmask") + 1]
            try:
                return local_ip, _hexmask_to_dotted(hexmask)
            except ValueError:
                return local_ip, None
    return local_ip, None


def _ip_to_int(ip):
    parts = [int(part) for part in ip.split(".")]
    value = 0
    for part in parts:
        value = (value << 8) | part
    return value


def _int_to_ip(value):
    return "%d.%d.%d.%d" % (
        (value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def compute_subnet_hosts(ip, netmask):
    """Return every other host address on ip's subnet, own address excluded.

    Mac-side counterpart of firmware/discovery.py's compute_scan_targets(),
    deliberately not imported from there -- mac/ stays independent of
    firmware/ (see /CLAUDE.md directory separation), and this one has no
    host-count cap: the board does no scanning at all any more, only the
    Mac does, with bounded concurrency (see scan_for_board()).
    """
    ip_int = _ip_to_int(ip)
    mask_int = _ip_to_int(netmask)
    network = ip_int & mask_int
    inverse = (~mask_int) & 0xFFFFFFFF
    if inverse <= 1:
        return []
    hosts = []
    for offset in range(1, inverse):
        candidate = network + offset
        if candidate == ip_int:
            continue
        hosts.append(_int_to_ip(candidate))
    return hosts


def _http_exchange(ip, port, request_bytes, timeout_s):
    """Send one HTTP/1.1 request over a fresh TCP connection, return the raw
    response bytes, or None on any connect/timeout/read error."""
    import socket as socket_module
    try:
        with socket_module.create_connection((ip, port), timeout=timeout_s) as sock:
            sock.settimeout(timeout_s)
            sock.sendall(request_bytes)
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
    except (OSError, socket_module.timeout):
        return None
    return b"".join(chunks) or None


def _http_response_body(raw):
    if raw is None:
        return None
    _head, _sep, body = raw.partition(b"\r\n\r\n")
    return body


def probe_board(ip, port, timeout_s=SCAN_CONNECT_TIMEOUT_S):
    """True iff ip:port answers GET /device-info with identity=EDGEGLASS_BOARD.

    A bare TCP connect succeeding is not enough to call this the board --
    some other device/service could be listening on that port too, so the
    identity string in the response body is what actually confirms it
    (see firmware/smart_glass_server.py's /device-info route).
    """
    import json as json_module

    request = (
        "GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n" % (DEVICE_INFO_PATH, ip)
    ).encode()
    body = _http_response_body(_http_exchange(ip, port, request, timeout_s))
    if not body:
        return False
    try:
        payload = json_module.loads(body.decode())
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("identity") == BOARD_IDENTITY


def register_with_board(board_ip, board_port, udp_port, timeout_s=REGISTER_TIMEOUT_S):
    """POST /register; True iff the board confirms EDGEGLASS_REGISTERED."""
    import json as json_module

    body = json_module.dumps({"identity": USER_IDENTITY, "udp_port": udp_port}).encode()
    request = (
        "POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n"
        "Content-Length: %d\r\nConnection: close\r\n\r\n" % (REGISTER_PATH, board_ip, len(body))
    ).encode() + body
    resp_body = _http_response_body(_http_exchange(board_ip, board_port, request, timeout_s))
    if not resp_body:
        return False
    try:
        payload = json_module.loads(resp_body.decode())
    except (ValueError, UnicodeDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("identity") == BOARD_IDENTITY
        and payload.get("status") == "EDGEGLASS_REGISTERED"
    )


def scan_for_board(local_ip, netmask, port, prefer_ip=None,
                    timeout_s=SCAN_CONNECT_TIMEOUT_S, max_workers=SCAN_MAX_WORKERS):
    """Return the board's IP on this subnet, or None if nothing answered.

    Checks ``prefer_ip`` (the last address that worked) by itself first --
    cheap, and usually right after a reconnect -- before falling back to
    scanning every other host address on the subnet with bounded
    concurrency (never the full 254-host /24 sequentially one at a time).
    """
    if prefer_ip is not None and probe_board(prefer_ip, port, timeout_s):
        return prefer_ip

    hosts = compute_subnet_hosts(local_ip, netmask)
    if prefer_ip in hosts:
        hosts.remove(prefer_ip)
    if not hosts:
        return None

    import concurrent.futures

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = {pool.submit(probe_board, ip, port, timeout_s): ip for ip in hosts}
        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    return futures[future]
            except Exception:
                continue
        return None
    finally:
        # wait=False: don't block on in-flight probes once we already have
        # an answer (or scanned everything) -- cancel_futures drops the
        # ones that never got a worker thread yet.
        pool.shutdown(wait=False, cancel_futures=True)


def discover_and_register_board(web_port, udp_port, prefer_ip=None,
                                 timeout_s=SCAN_CONNECT_TIMEOUT_S,
                                 max_workers=SCAN_MAX_WORKERS, on_status=None):
    """One discovery attempt: scan this Mac's subnet for the board over TCP,
    then register this Mac's UDP listen port with it over HTTP. Returns the
    board's IP on success, None otherwise (the reason goes to ``on_status``).
    """
    def _status(msg):
        if on_status is not None:
            on_status(msg)

    local_ip, netmask = get_local_ip_and_netmask()
    if local_ip is None:
        _status("[DISCOVERY] no local IP route found -- check Wi-Fi/hotspot connection")
        return None
    if netmask is None:
        _status("[DISCOVERY] could not determine subnet mask for %s -- scan skipped" % local_ip)
        return None

    _status("[DISCOVERY] scanning %s/%s for the board (TCP %d)..." % (local_ip, netmask, web_port))
    board_ip = scan_for_board(local_ip, netmask, web_port, prefer_ip=prefer_ip,
                               timeout_s=timeout_s, max_workers=max_workers)
    if board_ip is None:
        _status("[DISCOVERY] no device answered %s as %s on this subnet "
                 "(client/AP isolation on the router or hotspot can also cause this)"
                 % (DEVICE_INFO_PATH, BOARD_IDENTITY))
        return None

    _status("[DISCOVERY] board found at %s -- registering (UDP port %d)..." % (board_ip, udp_port))
    if not register_with_board(board_ip, web_port, udp_port, timeout_s=REGISTER_TIMEOUT_S):
        _status("[DISCOVERY] board at %s did not confirm EDGEGLASS_REGISTERED" % board_ip)
        return None

    _status("[DISCOVERY] board registered: %s" % board_ip)
    return board_ip


def _tcp_discovery_loop(web_port, udp_port, prefer_ip=None,
                         retry_interval_s=DISCOVERY_RETRY_INTERVAL_S,
                         on_status=None, on_found=None, on_attempt_failed=None,
                         max_attempts=None):
    """Retry discover_and_register_board() until it succeeds once, then
    return. Meant to run in a daemon thread (see main()) so it never blocks
    run_udp_loop's receiving of mouse packets -- scanning a /24 subnet takes
    a few seconds, every retry included, and must not stall anything else.

    ``on_attempt_failed(reason)`` fires after each failed attempt with the
    last status message discover_and_register_board() reported (its last
    message before returning None is always the actual failure reason) --
    main() uses this for a deduped, concise "[BOARD] 탐색 실패" line,
    independent of ``on_status``'s full per-attempt detail (debug-only).
    """
    attempts = 0
    while max_attempts is None or attempts < max_attempts:
        attempts += 1
        last_message = {"text": None}

        def _capture_status(msg, _store=last_message):
            _store["text"] = msg
            if on_status is not None:
                on_status(msg)

        board_ip = discover_and_register_board(
            web_port, udp_port, prefer_ip=prefer_ip, on_status=_capture_status)
        if board_ip is not None:
            if on_found is not None:
                on_found(board_ip)
            return board_ip
        if on_attempt_failed is not None:
            on_attempt_failed(last_message["text"])
        time.sleep(retry_interval_s)
    return None


def run_udp_loop(bind_host, bind_port, mouse, tracking_logger, watchdog, max_ticks=None,
                  poll_timeout_s=MAX_WATCHDOG_POLL_INTERVAL_S, on_board_registered=None,
                  on_board_seen=None, on_local_ip_changed=None, on_mouse_packet=None):
    """``on_board_seen(addr)`` fires for either a discovery probe (``@HELLO``)
    or any datagram that passes the existing ``parse_message()`` validation
    -- i.e. a real board, whether it registered via auto-discovery or is
    sending straight to a fixed configured IP (no ``@HELLO`` in that mode).
    Separate from ``on_board_registered`` so existing discovery/"[MOUSE]
    Ready" behavior is untouched; this callback is only used to announce the
    web server URLs (see main()) once per board IP.

    ``on_local_ip_changed(old_ip, new_ip)``, if given, fires whenever this
    Mac's own IP changes (e.g. a Wi-Fi/hotspot network switch) -- used by
    main() to trigger a fresh TCP-discovery rescan, since the old
    registration's peer address may no longer be reachable. All
    presentation (what to print, if anything) is left to the caller -- this
    function performs no printing of its own for this event.

    ``on_mouse_packet()``, if given, fires on every tick whose datagram
    parses as a valid @MOUSE action -- main() dedups this to the first call
    for the "[UDP] 마우스 패킷 수신 시작" status line.
    """
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_host, bind_port))
    # Shorter than the drag watchdog timeout so a stale drag is still caught
    # promptly even with no incoming datagrams at all.
    sock.settimeout(poll_timeout_s)
    local_ip = get_local_ip()
    try:
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                data, addr = None, None

            if data and data.startswith(HELLO_PREFIX.encode()):
                _reply_to_hello(sock, addr, on_board_registered)
                if on_board_seen is not None:
                    on_board_seen(addr)
            elif data and on_board_seen is not None:
                line = data.decode("utf-8", "replace")
                if parse_message(line) is not None:
                    on_board_seen(addr)

            process_tick(data, mouse, tracking_logger, watchdog, on_mouse_packet=on_mouse_packet)

            ticks += 1
            if ticks % LOCAL_IP_RECHECK_TICKS == 0:
                current_ip = get_local_ip()
                if current_ip and current_ip != local_ip:
                    if on_local_ip_changed is not None:
                        on_local_ip_changed(local_ip, current_ip)
                    local_ip = current_ip
    finally:
        sock.close()


class DryRunMouse:
    """Test backend; it intentionally never moves the host cursor."""

    def __init__(self):
        self.dragging = False

    def move(self, x, y, dragged=False):
        print("EVENT %s %.4f %.4f" % ("DRAG" if dragged else "MOVE", x, y))

    def click(self):
        print("EVENT CLICK")

    def down(self, x, y):
        self.dragging = True
        print("EVENT DRAG_START %.4f %.4f" % (x, y))

    def up(self):
        if self.dragging:
            print("EVENT DRAG_END")
        self.dragging = False


class QuartzMouse:
    """CoreGraphics event sender.  Coordinates are normalized primary-screen points."""

    def __init__(self):
        try:
            import Quartz
        except ImportError as exc:
            raise RuntimeError(
                "Quartz is unavailable. Install pyobjc-framework-Quartz: "
                "python3 -m pip install pyobjc-framework-Quartz"
            ) from exc
        self.q = Quartz
        bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        self.width = bounds.size.width
        self.height = bounds.size.height
        self.dragging = False

    def _point(self, x, y):
        return (x * self.width, y * self.height)

    def _post(self, event_type, point):
        event = self.q.CGEventCreateMouseEvent(
            None, event_type, point, self.q.kCGMouseButtonLeft
        )
        self.q.CGEventPost(self.q.kCGHIDEventTap, event)

    def move(self, x, y, dragged=False):
        event_type = self.q.kCGEventLeftMouseDragged if dragged else self.q.kCGEventMouseMoved
        self._post(event_type, self._point(x, y))

    def click(self):
        point = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
        self._post(self.q.kCGEventLeftMouseDown, point)
        self._post(self.q.kCGEventLeftMouseUp, point)

    def down(self, x, y):
        self._post(self.q.kCGEventLeftMouseDown, self._point(x, y))
        self.dragging = True

    def up(self):
        if self.dragging:
            point = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
            self._post(self.q.kCGEventLeftMouseUp, point)
        self.dragging = False


def dispatch(mouse, message):
    action, x, y = message
    if action == "MOVE":
        mouse.move(x, y)
    elif action == "CLICK":
        mouse.click()
    elif action == "DRAG_START":
        # A new start is also a recovery point for a stale interrupted drag.
        mouse.up()
        mouse.down(x, y)
    elif action == "DRAG":
        if mouse.dragging:
            mouse.move(x, y, dragged=True)
    elif action in ("DRAG_END", "STOP"):
        mouse.up()


def self_test():
    mouse = DryRunMouse()
    lines = (
        "debug output ignored",
        "@MOUSE|MOVE|0.5123|0.4380",
        "@MOUSE|CLICK",
        "@MOUSE|DRAG_START|0.5123|0.4380",
        "@MOUSE|DRAG|0.5300|0.4500",
        "@MOUSE|DRAG_END",
        "@MOUSE|STOP",
    )
    for line in lines:
        parsed = parse_message(line)
        if parsed is not None:
            dispatch(mouse, parsed)
    assert not mouse.dragging
    print("Self-test passed (no OS mouse events were sent).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport",
        choices=("uart", "udp"),
        default="uart",
        help="Receive @MOUSE records over UART2 (verified) or UDP/Wi-Fi (unverified) (default: %(default)s)."
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_UART2_PORT,
        help="Verified K230 UART2 port, used when --transport=uart (default: %(default)s)."
    )
    parser.add_argument("--baud", type=int, default=115200, help="CDC line setting (default: 115200).")
    parser.add_argument(
        "--udp-bind-host",
        default=DEFAULT_UDP_BIND_HOST,
        help="Local address to listen on, used when --transport=udp (default: %(default)s)."
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=DEFAULT_UDP_PORT,
        help="Local UDP port to listen on, used when --transport=udp (default: %(default)s)."
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=DEFAULT_WEB_PORT,
        help="Board's web server port, used only to print its URL once the "
             "board's IP is known via --transport=udp (default: %(default)s)."
    )
    parser.add_argument(
        "--no-tcp-discovery",
        action="store_true",
        help="Disable the Mac-initiated TCP scan/HTTP registration (GET /device-info, "
             "POST /register) and rely only on the board-initiated @HELLO/@ACK path, "
             "used when --transport=udp (default: enabled)."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print per-attempt TCP-discovery scan/request detail in addition to the "
             "default concise [Wi-Fi]/[BOARD]/[UDP] connection-status lines."
    )
    parser.add_argument(
        "--drag-timeout",
        type=float,
        default=DEFAULT_DRAG_TIMEOUT_S,
        help="Seconds without any packet before a held DRAG is force-released (default: %(default)s)."
    )
    parser.add_argument("--list", action="store_true", help="List candidate USB serial devices and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Parse input without sending OS events.")
    parser.add_argument("--self-test", action="store_true", help="Test parser and MOVE/CLICK/DRAG/STOP dispatch safely.")
    args = parser.parse_args()

    if args.list:
        ports = available_ports()
        if ports:
            print("Candidate ports (roles are not inferred):")
            for port in ports:
                print("  " + port)
        else:
            print("No /dev/cu.usbmodem* or /dev/cu.usbserial* ports found.")
        return 0
    if args.self_test:
        self_test()
        return 0

    tracking_logger = TrackingCsvLogger()
    watchdog = DragWatchdog(timeout_s=args.drag_timeout)

    if args.transport == "uart":
        try:
            import serial  # noqa: F401  (import error checked below)
        except ImportError:
            print("Missing dependency: python3 -m pip install pyserial", file=sys.stderr)
            return 2

    try:
        mouse = DryRunMouse() if args.dry_run else QuartzMouse()

        print("========== EdgeGlass-AI Mac Bridge ==========")
        startup_ip = get_local_ip()
        if startup_ip:
            print("[Wi-Fi] 네트워크 연결 완료")
            if args.debug:
                print("[DEBUG] local IP: %s" % startup_ip)
        else:
            print("[Wi-Fi] 연결 실패 - 로컬 네트워크 경로를 찾을 수 없음")
        if args.dry_run:
            print("[PERMISSION] Accessibility: skipped (--dry-run sends no OS events)")
        else:
            trusted = check_accessibility_trusted()
            if trusted is True:
                print("[PERMISSION] Accessibility: granted")
            elif trusted is False:
                print("[PERMISSION] Accessibility: NOT granted -- "
                      "System Settings > Privacy & Security > Accessibility")
            else:
                print("[PERMISSION] Accessibility: unknown (ApplicationServices not available)")

        poll_timeout_s = min(MAX_WATCHDOG_POLL_INTERVAL_S, args.drag_timeout / 5.0)
        if args.transport == "udp":
            if args.debug:
                print("[DEBUG] UDP listening on %s:%d" % (args.udp_bind_host, args.udp_port))

            def _debug_status(msg):
                if args.debug:
                    print(msg)

            registered_state = {"board_ip": None}

            def _on_board_registered(addr, _state=registered_state):
                # Legacy board-initiated @HELLO/@ACK path (pre-2026-10-27) --
                # dormant by default now that config.py's
                # MOUSE_UDP_USE_HTTP_REGISTRATION defaults to True, kept
                # working for boards still on the old firmware. Detail only
                # under --debug so it doesn't compete with the new concise
                # [BOARD] line below for the same real-world event.
                board_ip = addr[0]
                if board_ip != _state["board_ip"]:
                    _state["board_ip"] = board_ip
                    if args.debug:
                        print("[DEBUG] legacy @HELLO/@ACK registration: %s" % board_ip)

            # Shared by both discovery paths (old passive @HELLO/@ACK and the
            # new active TCP scan below) so the [WEB] URL block only ever
            # prints once per board IP, however it was found.
            web_url_state = {"board_ip": None}

            def _announce_web_urls_once(board_ip, _state=web_url_state):
                if board_ip != _state["board_ip"]:
                    _state["board_ip"] = board_ip
                    print()
                    _announce_web_urls(board_ip, args.web_port)

            def _on_board_seen(addr):
                _announce_web_urls_once(addr[0])

            # Mac-initiated discovery (2026-10-27): the board no longer scans
            # its own subnet. This Mac finds it over TCP (GET /device-info)
            # and confirms it with POST /register before any @MOUSE packet
            # can even be sent (RegisteredUdpTransport.write() is a no-op
            # until the board's own HTTP route calls .register()). Runs in a
            # daemon thread so scanning a /24 subnet never blocks
            # run_udp_loop's receiving below.
            tcp_discovery_state = {"last_board_ip": None}
            board_fail_state = {"last_reason": None}

            def _on_tcp_discovery_found(board_ip, _state=tcp_discovery_state):
                _state["last_board_ip"] = board_ip
                board_fail_state["last_reason"] = None
                print("[BOARD] EdgeGlass-AI 탐색 및 등록 완료")
                _announce_web_urls_once(board_ip)

            def _on_board_discovery_failed(reason, _state=board_fail_state):
                # Deduped on the reason text so a retry every
                # DISCOVERY_RETRY_INTERVAL_S with the SAME cause stays
                # silent after the first notice; a new/different reason
                # (or a flip back to failing after a prior success) is
                # reported again.
                if reason != _state["last_reason"]:
                    _state["last_reason"] = reason
                    # discover_and_register_board()'s on_status messages are
                    # already prefixed "[DISCOVERY] " for the --debug view;
                    # strip it here so the concise line doesn't show it twice.
                    clean_reason = reason
                    if clean_reason and clean_reason.startswith("[DISCOVERY] "):
                        clean_reason = clean_reason[len("[DISCOVERY] "):]
                    print("[BOARD] 탐색 실패 - %s" % (clean_reason or "알 수 없는 오류"))

            def _start_tcp_discovery(_state=tcp_discovery_state):
                threading.Thread(
                    target=_tcp_discovery_loop,
                    args=(args.web_port, args.udp_port),
                    kwargs={
                        "prefer_ip": _state["last_board_ip"],
                        "on_status": _debug_status,
                        "on_found": _on_tcp_discovery_found,
                        "on_attempt_failed": _on_board_discovery_failed,
                    },
                    daemon=True,
                ).start()

            def _on_local_ip_changed(old_ip, new_ip):
                if args.debug:
                    print("[DEBUG] local IP changed: %s -> %s" % (old_ip, new_ip))
                if not args.no_tcp_discovery:
                    print("[Wi-Fi] 네트워크 재연결 완료")
                    _start_tcp_discovery()

            udp_rx_state = {"started": False}

            def _on_mouse_packet(_state=udp_rx_state):
                if not _state["started"]:
                    _state["started"] = True
                    print("[UDP] 마우스 패킷 수신 시작")

            if not args.no_tcp_discovery:
                _start_tcp_discovery()

            run_udp_loop(args.udp_bind_host, args.udp_port, mouse, tracking_logger, watchdog,
                         poll_timeout_s=poll_timeout_s, on_board_registered=_on_board_registered,
                         on_board_seen=_on_board_seen, on_local_ip_changed=_on_local_ip_changed,
                         on_mouse_packet=_on_mouse_packet)
        else:
            print("[UART] Port: %s @ %d baud" % (args.port, args.baud))
            print("[MOUSE] Ready")
            print("=============================================")
            run_uart_loop(args.port, args.baud, mouse, tracking_logger, watchdog,
                          poll_timeout_s=poll_timeout_s)
    except KeyboardInterrupt:
        print("Stopping bridge.")
    except Exception as exc:
        print("Bridge error: %s" % exc, file=sys.stderr)
        if args.transport == "uart":
            print("If the port is busy, disconnect VS Code CanMV from that same CDC endpoint before retrying.", file=sys.stderr)
        return 1
    finally:
        tracking_logger.close()
        # The local is intentionally checked because creation/open may fail.
        if "mouse" in locals():
            mouse.up()
    return 0


if __name__ == "__main__":
    sys.exit(main())
