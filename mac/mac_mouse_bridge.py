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


def handle_line(line, mouse, tracking_logger):
    """Parse and dispatch exactly one decoded protocol line."""
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
    if message[0] in _LOGGED_ACTIONS:
        print("%s_RX" % message[0], "time=", time.time(),
              "packet=@MOUSE|%s" % message[0], flush=True)
    dispatch(mouse, message)


def process_tick(raw, mouse, tracking_logger, watchdog):
    """One receive-loop step, shared by the UART and UDP readers.

    ``raw`` is the newly received bytes for this tick, or falsy if nothing
    arrived (a read timeout). The watchdog is always checked so a stale
    drag is released even while the link stays completely silent.
    """
    if raw:
        watchdog.mark_received()
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        handle_line(line, mouse, tracking_logger)
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
    print("[WEB] Main:     http://%s:%d/" % (board_ip, web_port))
    print("[WEB] Stream:   http://%s:%d/stream" % (board_ip, web_port))
    print("[WEB] Snapshot: http://%s:%d/snapshot" % (board_ip, web_port))


def run_udp_loop(bind_host, bind_port, mouse, tracking_logger, watchdog, max_ticks=None,
                  poll_timeout_s=MAX_WATCHDOG_POLL_INTERVAL_S, on_board_registered=None,
                  on_board_seen=None):
    """``on_board_seen(addr)`` fires for either a discovery probe (``@HELLO``)
    or any datagram that passes the existing ``parse_message()`` validation
    -- i.e. a real board, whether it registered via auto-discovery or is
    sending straight to a fixed configured IP (no ``@HELLO`` in that mode).
    Separate from ``on_board_registered`` so existing discovery/"[MOUSE]
    Ready" behavior is untouched; this callback is only used to announce the
    web server URLs (see main()) once per board IP.
    """
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_host, bind_port))
    # Shorter than the drag watchdog timeout so a stale drag is still caught
    # promptly even with no incoming datagrams at all.
    sock.settimeout(poll_timeout_s)
    print("Listening for UDP on %s:%d. Press Ctrl-C to stop." % (bind_host, bind_port))
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

            process_tick(data, mouse, tracking_logger, watchdog)

            ticks += 1
            if ticks % LOCAL_IP_RECHECK_TICKS == 0:
                current_ip = get_local_ip()
                if current_ip and current_ip != local_ip:
                    print("[NET] Local IP changed: %s -> %s" % (local_ip, current_ip))
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
        print("[NET] Local IP: %s" % (get_local_ip() or "unknown"))
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
            print("[UDP] Listening on %s:%d" % (args.udp_bind_host, args.udp_port))
            print("[DISCOVERY] Waiting for board...")
            print("=============================================")

            registered_state = {"board_ip": None}

            def _on_board_registered(addr, _state=registered_state):
                board_ip = addr[0]
                if board_ip != _state["board_ip"]:
                    _state["board_ip"] = board_ip
                    print("[DISCOVERY] Board registered: %s" % board_ip)
                    print("[MOUSE] Ready")

            web_url_state = {"board_ip": None}

            def _on_board_seen(addr, _state=web_url_state):
                board_ip = addr[0]
                if board_ip != _state["board_ip"]:
                    _state["board_ip"] = board_ip
                    _announce_web_urls(board_ip, args.web_port)

            run_udp_loop(args.udp_bind_host, args.udp_port, mouse, tracking_logger, watchdog,
                         poll_timeout_s=poll_timeout_s, on_board_registered=_on_board_registered,
                         on_board_seen=_on_board_seen)
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
