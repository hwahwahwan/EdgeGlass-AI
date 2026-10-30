"""Tests for firmware/boot_stage.py -- pure logic, no hardware imports.
Uses an injected fake clock and a recording fake sleep_fn so the test
never actually sleeps and never touches the real `time` module.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIRMWARE_DIR = os.path.join(_REPO_ROOT, "firmware")
if _FIRMWARE_DIR not in sys.path:
    sys.path.insert(0, _FIRMWARE_DIR)

import boot_stage  # noqa: E402


class _FakeClock:
    def __init__(self, start=0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms


class BootStageTimerTests(unittest.TestCase):
    def test_sleeps_the_remaining_time_when_work_finished_early(self):
        clock = _FakeClock()
        sleeps = []
        timer = boot_stage.BootStageTimer(
            min_display_ms=400, now_ms_fn=clock, sleep_fn=sleeps.append)
        timer.enter()
        clock.advance(120)  # the real work only took 120ms
        timer.wait_min()
        self.assertEqual(sleeps, [280])

    def test_does_not_sleep_when_work_already_took_longer_than_the_minimum(self):
        clock = _FakeClock()
        sleeps = []
        timer = boot_stage.BootStageTimer(
            min_display_ms=400, now_ms_fn=clock, sleep_fn=sleeps.append)
        timer.enter()
        clock.advance(900)
        timer.wait_min()
        self.assertEqual(sleeps, [])

    def test_wait_min_without_enter_is_a_safe_noop(self):
        sleeps = []
        timer = boot_stage.BootStageTimer(
            min_display_ms=400, now_ms_fn=_FakeClock(), sleep_fn=sleeps.append)
        timer.wait_min()  # never entered any stage
        self.assertEqual(sleeps, [])

    def test_each_enter_restarts_the_window(self):
        clock = _FakeClock()
        sleeps = []
        timer = boot_stage.BootStageTimer(
            min_display_ms=400, now_ms_fn=clock, sleep_fn=sleeps.append)
        timer.enter()
        clock.advance(400)
        timer.wait_min()
        self.assertEqual(sleeps, [])

        timer.enter()  # second stage, independent window
        clock.advance(50)
        timer.wait_min()
        self.assertEqual(sleeps, [350])


if __name__ == "__main__":
    unittest.main()
