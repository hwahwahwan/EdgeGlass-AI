"""Tests for firmware/failure_backoff.py -- pure logic, no hardware
imports, so it is tested directly against a fully-controlled fake clock
(an incrementing counter passed in) rather than real wall-clock time or
any MicroPython time.ticks_*() shim.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIRMWARE_DIR = os.path.join(_REPO_ROOT, "firmware")
if _FIRMWARE_DIR not in sys.path:
    sys.path.insert(0, _FIRMWARE_DIR)

import failure_backoff  # noqa: E402


class _FakeClock:
    def __init__(self, start=0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms


class FailureBackoffTests(unittest.TestCase):
    def test_initially_allows_an_attempt(self):
        backoff = failure_backoff.FailureBackoff(now_ms_fn=_FakeClock())
        self.assertTrue(backoff.should_attempt())

    def test_blocks_immediately_after_a_failure_until_delay_elapses(self):
        clock = _FakeClock()
        backoff = failure_backoff.FailureBackoff(
            delays_ms=(5000, 10000), max_failures=3, now_ms_fn=clock)
        backoff.record_failure()
        self.assertFalse(backoff.should_attempt())
        clock.advance(4999)
        self.assertFalse(backoff.should_attempt())
        clock.advance(2)  # now at 5001ms, past the 1st-failure 5000ms delay
        self.assertTrue(backoff.should_attempt())

    def test_second_consecutive_failure_uses_the_longer_delay(self):
        clock = _FakeClock()
        backoff = failure_backoff.FailureBackoff(
            delays_ms=(5000, 10000), max_failures=3, now_ms_fn=clock)
        backoff.record_failure()
        clock.advance(5001)
        self.assertTrue(backoff.should_attempt())
        backoff.record_failure()  # 2nd consecutive failure -> 10000ms delay
        clock.advance(5001)
        self.assertFalse(backoff.should_attempt())
        clock.advance(5000)
        self.assertTrue(backoff.should_attempt())

    def test_max_failures_permanently_blocks_until_success(self):
        clock = _FakeClock()
        backoff = failure_backoff.FailureBackoff(
            delays_ms=(1000,), max_failures=3, now_ms_fn=clock)
        backoff.record_failure()
        clock.advance(2000)
        backoff.record_failure()
        clock.advance(2000)
        backoff.record_failure()
        self.assertTrue(backoff.exhausted())
        clock.advance(10**9)  # no amount of waiting helps once exhausted
        self.assertFalse(backoff.should_attempt())

    def test_record_success_clears_everything(self):
        clock = _FakeClock()
        backoff = failure_backoff.FailureBackoff(
            delays_ms=(1000,), max_failures=2, now_ms_fn=clock)
        backoff.record_failure()
        backoff.record_failure()
        self.assertTrue(backoff.exhausted())
        backoff.record_success()
        self.assertFalse(backoff.exhausted())
        self.assertEqual(backoff.failure_count, 0)
        self.assertTrue(backoff.should_attempt())

    def test_max_failures_none_never_gives_up_just_keeps_last_delay(self):
        clock = _FakeClock()
        backoff = failure_backoff.FailureBackoff(
            delays_ms=(1000, 2000), max_failures=None, now_ms_fn=clock)
        for _ in range(10):
            backoff.record_failure()
        self.assertFalse(backoff.exhausted())
        clock.advance(2001)  # longest configured delay, reused past index 2
        self.assertTrue(backoff.should_attempt())

    def test_rejects_empty_delays(self):
        with self.assertRaises(ValueError):
            failure_backoff.FailureBackoff(delays_ms=())


if __name__ == "__main__":
    unittest.main()
