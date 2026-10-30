"""Boot-stage minimum display time helper, no hardware imports.

docs/DEV_HISTORY.md 4-8's OLED boot design needs each boot-stage screen
("CAMERA / INITIALIZING", "WIFI / CONNECTING", ...) to stay on screen at
least MIN_STAGE_DISPLAY_MS even when the real step behind it finishes
almost instantly (e.g. wifi.connect_if_needed() returning immediately
because a prior connection survived a soft reboot). This must never delay
the real work itself -- only pad the *display* dwell time, measured after
the real work has already completed.

Pure Python (time.sleep_ms-shaped duck typing via an injected sleep_fn),
directly unit-testable under CPython.
"""


class BootStageTimer:
    def __init__(self, min_display_ms, now_ms_fn=None, sleep_fn=None):
        self.min_display_ms = min_display_ms
        self._now_ms_fn = now_ms_fn or _default_now_ms
        self._sleep_fn = sleep_fn or _default_sleep_ms
        self._stage_started_ms = None

    def enter(self, now_ms=None):
        """Call the moment a new stage's screen is shown, before doing the
        real work for that stage."""
        self._stage_started_ms = self._now_ms_fn() if now_ms is None else now_ms

    def wait_min(self, now_ms=None):
        """Call after the real work for the current stage has finished.
        Sleeps only the remaining time (if any) so the screen has been up
        for at least min_display_ms in total. No-op if enter() was never
        called or the real work already took longer than min_display_ms.
        """
        if self._stage_started_ms is None:
            return
        now_ms = self._now_ms_fn() if now_ms is None else now_ms
        elapsed_ms = _ticks_diff(now_ms, self._stage_started_ms)
        remaining_ms = self.min_display_ms - elapsed_ms
        if remaining_ms > 0:
            self._sleep_fn(remaining_ms)


def _default_now_ms():
    import time
    return time.ticks_ms()


def _default_sleep_ms(ms):
    import time
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000.0)


def _ticks_diff(a, b):
    try:
        import time
        if hasattr(time, "ticks_diff"):
            return time.ticks_diff(a, b)
    except ImportError:
        pass
    return a - b
