"""Generic repeated-failure backoff policy, no hardware imports.

Shared by two unrelated call sites in smart_glass_server.py that both need
the same shape of decision ("did this fail too many times in a row, and if
so, how long should I wait before trying again?") without duplicating the
counting/timing logic twice:

  - WebState's /stream JPEG encode path (OSError/ValueError/MemoryError --
    see docs/DEV_HISTORY.md 6-10 and section 4-8's MemoryError design).
  - Runtime Wi-Fi reconnect attempts (wlan.isconnected() polling).

Deliberately dumb: this module only counts failures and gates attempts by
time. It has no idea what it is backing off -- the caller decides what
"failure" and "success" mean and calls record_failure()/record_success()
accordingly. Pure Python (only ``time``-shaped duck typing via an injected
``now_ms`` function), so it is directly unit-testable under CPython the
same way firmware/web_server.py already is.
"""


class FailureBackoff:
    """Tracks consecutive failures and gates retries behind a growing delay.

    ``delays_ms`` is the wait applied after the Nth consecutive failure
    (1-indexed) -- e.g. ``(5000, 10000)`` means: after the 1st failure wait
    5s before allowing another attempt, after the 2nd wait 10s. Once the
    failure count exceeds ``len(delays_ms)``, ``max_failures`` controls
    whether further attempts are allowed at all:

      - ``max_failures=None`` (default): keep reusing the last delay in
        ``delays_ms`` forever (bounded, never gives up).
      - ``max_failures=N``: once the failure count reaches N, stop
        allowing any further attempts (``should_attempt()`` returns False
        permanently) until ``record_success()`` resets it. This matches
        the design's "연속 N회 실패 시 자동 재시도 일시 중단" requirement.
    """

    def __init__(self, delays_ms=(5000, 10000), max_failures=3, now_ms_fn=None):
        if not delays_ms:
            raise ValueError("delays_ms must have at least one entry")
        self.delays_ms = tuple(delays_ms)
        self.max_failures = max_failures
        self._now_ms_fn = now_ms_fn or _default_now_ms
        self.failure_count = 0
        self._blocked_until_ms = None

    def should_attempt(self, now_ms=None):
        """True if a new attempt is currently allowed."""
        if self.max_failures is not None and self.failure_count >= self.max_failures:
            return False
        if self._blocked_until_ms is None:
            return True
        now_ms = self._now_ms_fn() if now_ms is None else now_ms
        return _ticks_diff(now_ms, self._blocked_until_ms) >= 0

    def record_failure(self, now_ms=None):
        """Call once per observed failure. Extends the cooldown window."""
        now_ms = self._now_ms_fn() if now_ms is None else now_ms
        self.failure_count += 1
        delay_index = min(self.failure_count, len(self.delays_ms)) - 1
        delay_ms = self.delays_ms[delay_index]
        self._blocked_until_ms = _ticks_add(now_ms, delay_ms)

    def record_success(self):
        """Call once on a confirmed success. Clears all backoff state."""
        self.failure_count = 0
        self._blocked_until_ms = None

    def exhausted(self):
        """True if max_failures has been reached (no more auto-retries)."""
        return self.max_failures is not None and self.failure_count >= self.max_failures


def _default_now_ms():
    import time
    return time.ticks_ms()


def _ticks_diff(a, b):
    # MicroPython's time.ticks_diff() wraps; plain subtraction is correct
    # for CPython's time.time()-derived millisecond counters used in tests
    # and is what real time.ticks_diff(a, b) computes for non-wrapped
    # ranges anyway.
    try:
        import time
        if hasattr(time, "ticks_diff"):
            return time.ticks_diff(a, b)
    except ImportError:
        pass
    return a - b


def _ticks_add(a, b):
    try:
        import time
        if hasattr(time, "ticks_add"):
            return time.ticks_add(a, b)
    except ImportError:
        pass
    return a + b
