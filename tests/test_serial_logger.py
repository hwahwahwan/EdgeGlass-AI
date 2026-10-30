"""Tests for mac/serial_logger.py's pure rotation/write logic and
per-tick processing. No real pyserial/filesystem access -- a fake
open_fn (an in-memory StringIO-backed stand-in) and a fake now_fn drive
everything, following the same injection pattern
tests/test_wifi_mouse_transport.py uses for mac_mouse_bridge.py.
"""

import io
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAC_DIR = os.path.join(_REPO_ROOT, "mac")
if _MAC_DIR not in sys.path:
    sys.path.insert(0, _MAC_DIR)

import serial_logger  # noqa: E402


class _FakeFile(io.StringIO):
    """io.StringIO already has write()/flush(); only close() needs to
    also record that it happened, so a test can tell a rotation really
    closed the previous file instead of leaking it open."""

    def __init__(self):
        super().__init__()
        self.closed_flag = False

    def close(self):
        self.closed_flag = True
        super().close()


class _FakeOpener:
    """Records every path opened (in order) and hands back a fresh
    _FakeFile each time, mimicking real open(path, "a", ...)."""

    def __init__(self):
        self.opened_paths = []
        self.files = []

    def __call__(self, path, mode, encoding=None, errors=None):
        self.opened_paths.append(path)
        f = _FakeFile()
        self.files.append(f)
        return f


class _FakeNow:
    def __init__(self, stamps):
        self._stamps = list(stamps)

    def __call__(self):
        return self._stamps.pop(0)


def _fake_makedirs(path, exist_ok=True):
    pass


class SerialSessionLoggerTests(unittest.TestCase):
    def _logger(self, stamps, max_bytes=1000):
        opener = _FakeOpener()
        now = _FakeNow(stamps)
        logger = serial_logger.SerialSessionLogger(
            log_dir="/fake/logs", max_bytes=max_bytes,
            open_fn=opener, now_fn=now, makedirs_fn=_fake_makedirs)
        return logger, opener

    def test_first_write_lazily_opens_a_session_file(self):
        import datetime
        logger, opener = self._logger([datetime.datetime(2026, 10, 30, 9, 0, 0)])
        path = logger.write_line("hello")
        self.assertEqual(path, os.path.join("/fake/logs", "serial_20261030_090000.log"))
        self.assertEqual(opener.opened_paths, [path])
        self.assertEqual(opener.files[0].getvalue(), "hello\n")

    def test_write_line_appends_newline_only_if_missing(self):
        import datetime
        logger, _ = self._logger([datetime.datetime(2026, 10, 30, 9, 0, 0)])
        logger.write_line("already has one\n")
        logger.write_line("does not")
        self.assertEqual(logger._file.getvalue(), "already has one\ndoes not\n")

    def test_rotates_to_a_new_file_past_max_bytes(self):
        # Rotation is checked at the *start* of write_line, against bytes
        # written so far -- so a line that itself pushes the total past
        # max_bytes is still written to the current file (a session file
        # can overshoot max_bytes by up to one line), and the *next* call
        # is what actually rotates. This matches a simple debug-log
        # rotation, not a hard per-file byte cap.
        import datetime
        logger, opener = self._logger(
            [datetime.datetime(2026, 10, 30, 9, 0, 0),
             datetime.datetime(2026, 10, 30, 9, 0, 5)],
            max_bytes=10,
        )
        logger.write_line("this line alone is already over ten bytes")
        self.assertEqual(len(opener.opened_paths), 1)
        logger.write_line("next")  # bytes_written now >= max_bytes -> rotate first
        self.assertEqual(len(opener.opened_paths), 2)
        self.assertTrue(opener.files[0].closed_flag)

    def test_close_closes_the_current_file(self):
        import datetime
        logger, opener = self._logger([datetime.datetime(2026, 10, 30, 9, 0, 0)])
        logger.write_line("x")
        logger.close()
        self.assertTrue(opener.files[0].closed_flag)

    def test_close_without_any_write_is_a_safe_noop(self):
        logger, _ = self._logger([])
        logger.close()  # must not raise


class ProcessChunkTests(unittest.TestCase):
    def _logger(self):
        import datetime
        opener = _FakeOpener()
        logger = serial_logger.SerialSessionLogger(
            log_dir="/fake/logs", open_fn=opener,
            now_fn=_FakeNow([datetime.datetime(2026, 10, 30, 9, 0, 0)]),
            makedirs_fn=_fake_makedirs)
        return logger, opener

    def test_falsy_raw_is_a_noop(self):
        logger, opener = self._logger()
        self.assertIsNone(serial_logger.process_chunk(b"", logger))
        self.assertEqual(opener.opened_paths, [])

    def test_bytes_are_decoded_before_writing(self):
        logger, _ = self._logger()
        path = serial_logger.process_chunk(b"[BOOT] hello\r\n", logger)
        self.assertIsNotNone(path)
        self.assertIn("[BOOT] hello", logger._file.getvalue())

    def test_write_failure_is_reported_not_raised(self):
        logger, _ = self._logger()

        def _boom(line):
            raise OSError("disk full")
        logger.write_line = _boom
        # Must not raise -- a logging hiccup must never crash the read loop.
        result = serial_logger.process_chunk(b"data", logger)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
