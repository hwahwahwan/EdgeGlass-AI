#!/usr/bin/env python3
"""Mac-side USB serial logger for EdgeGlass-AI's CanMV main USB CDC port.

docs/DEV_HISTORY.md 4-8: this targets the board's MAIN USB CDC port (the
REPL/stdout port the VS Code CanMV extension and the MCP tools connect to
-- e.g. the ``port`` field canmv_board_info reports), NOT the separate
UART2/CH342K bridge port mac_mouse_bridge.py uses for the @MOUSE protocol.
Those are two independent USB devices; this script only ever needs the
first one.

Port-sharing limitation (confirmed, not guessable from code): macOS
serial ports are normally exclusive-access. If the VS Code CanMV
extension (or any other MCP session) already has the main USB CDC port
open, this script cannot open it at the same time -- expect an
"[Errno 16] could not open port ...: Resource busy" style error. The
simplest approach (and the one assumed here) is to disconnect the
extension while using this script, then reconnect it afterward. This
script does not attempt any port-sharing trick (e.g. socat PTY
splitting) -- that was deliberately left out of scope (see the design
report this script implements).

Install (same dependency mac_mouse_bridge.py already needs):
    python3 -m pip install pyserial

Usage:
    python3 mac/serial_logger.py --port /dev/cu.usbmodemXXXXXXXX

Writes one timestamped log file per run (see SerialSessionLogger below),
rotating to a new file if a session grows past --max-bytes. Ctrl-C stops
cleanly and closes the current file. A write failure (disk full, log_dir
unwritable) is caught per-line and printed to stderr -- it never takes
down the read loop, matching the "로그 수집기 장애가 보드 실행에 영향을
주지 않도록" requirement (this process is independent of the board
either way, but it should also not crash on its own from a logging
hiccup while a crash Traceback is actively streaming in).
"""

import argparse
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# 기존 mac/mac_mouse_bridge.py의 TrackingCsvLogger는 기본 로그 경로를
# mac/logs/로 계산하지만(os.path.dirname(__file__)/logs), 실제로 로그
# 파일이 쌓여 있는 곳은 프로젝트 루트의 logs/ 디렉터리였다(확인됨,
# 2026-10-30 조사). 그 기존 불일치를 그대로 따라가지 않고, 실제 파일이
# 있는 프로젝트 루트 logs/를 기본값으로 쓴다.
DEFAULT_LOG_DIR = os.path.join(_HERE, os.pardir, "logs")
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5MB per session file before rotating
DEFAULT_BAUD = 115200
DEFAULT_POLL_TIMEOUT_S = 1.0


def _default_now():
    return datetime.datetime.now()


class SerialSessionLogger:
    """Pure rotation/write logic, no pyserial dependency -- directly
    unit-testable the same way tests/test_wifi_mouse_transport.py tests
    mac_mouse_bridge.py's TrackingCsvLogger-adjacent logic, by injecting
    a fake ``open_fn``/``now_fn`` instead of touching the real filesystem.
    """

    def __init__(self, log_dir=DEFAULT_LOG_DIR, max_bytes=DEFAULT_MAX_BYTES,
                 open_fn=None, now_fn=None, makedirs_fn=None):
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self._open_fn = open_fn or open
        self._now_fn = now_fn or _default_now
        self._makedirs_fn = makedirs_fn or os.makedirs
        self._file = None
        self._bytes_written = 0
        self.path = None

    def _new_session_path(self):
        stamp = self._now_fn().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.log_dir, "serial_%s.log" % stamp)

    def _rotate(self):
        if self._file is not None:
            self._file.close()
        self._makedirs_fn(self.log_dir, exist_ok=True)
        self.path = self._new_session_path()
        self._file = self._open_fn(self.path, "a", encoding="utf-8", errors="replace")
        self._bytes_written = 0
        return self.path

    def write_line(self, line):
        """``line``: already-decoded str (may or may not end in "\\n").
        Returns the path actually written to (useful for tests/callers
        that want to notice a rotation happened). Raises on a genuine I/O
        failure -- the caller (run_log_loop below) decides whether that
        should stop the whole process or just be reported and skipped."""
        if self._file is None or self._bytes_written >= self.max_bytes:
            self._rotate()
        if not line.endswith("\n"):
            line = line + "\n"
        self._file.write(line)
        self._file.flush()
        self._bytes_written += len(line)
        return self.path

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None


def process_chunk(raw, logger):
    """One receive-loop step. ``raw`` is new bytes from the serial port
    (falsy on a read timeout -- nothing to log, not an error). Returns
    the log path written to, or None if there was nothing to write.
    Mirrors mac_mouse_bridge.py's process_tick() shape so the two scripts
    stay recognizably similar, even though this one has no mouse/watchdog
    state to carry."""
    if not raw:
        return None
    line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    try:
        return logger.write_line(line)
    except OSError as error:
        print("[serial_logger] write failed (skipping this line): %r" % (error,),
              file=sys.stderr)
        return None


def run_log_loop(port, baud, logger, max_ticks=None,
                  poll_timeout_s=DEFAULT_POLL_TIMEOUT_S, serial_module=None):
    serial_module = serial_module or __import__("serial")
    with serial_module.Serial(port, baud, timeout=poll_timeout_s) as connection:
        print("Logging %s at %d baud to %s. Press Ctrl-C to stop." %
              (port, baud, logger.log_dir))
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            process_chunk(connection.readline(), logger)
            ticks += 1


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Record EdgeGlass-AI's CanMV main USB CDC output "
                     "(boot log, status banner, crash Tracebacks) to a "
                     "timestamped file on the Mac.")
    parser.add_argument("--port", required=True,
                         help="CanMV main USB CDC port, e.g. /dev/cu.usbmodemXXXXXXXX "
                              "(see canmv_board_info's 'port' field -- NOT the UART2 "
                              "port mac_mouse_bridge.py uses).")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                         help="Rotate to a new session file after this many bytes.")
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    logger = SerialSessionLogger(log_dir=args.log_dir, max_bytes=args.max_bytes)
    try:
        run_log_loop(args.port, args.baud, logger)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        logger.close()


if __name__ == "__main__":
    main()
