"""OLED skeleton UI: DisplayUI.update(landmarks, gesture, fps).

Owns a "canvas" (anything exposing fill(c)/pixel(x,y,c)/line(x1,y1,x2,y2,c)/
hline(x,y,w,c)/text(s,x,y,c)/show()) -- a real SSD1306_I2C
(framebuf.FrameBuffer subclass, from oled_device.open_display()) on the
board, or display/tests/virtual_oled.py's VirtualOLED on a PC. This module
itself never imports machine/framebuf, so its drawing logic is identical
and directly testable in both places (see display/tests/test_display_ui.py,
which imports this firmware/ module directly -- firmware/ is the single
source of truth for what's deployed to the board, display/ keeps only the
PC-side test harness, see docs/DEV_HISTORY.md 4-3).

Rate-limits how often it actually redraws (config.MIN_UPDATE_INTERVAL_MS)
so a caller can call update() every AI frame without that dictating the
OLED's real refresh rate -- same reasoning as
firmware/smart_glass_server.py's WEB_STREAM_MIN_INTERVAL_MS throttle
(docs/WORK_TRACKER.md section M/N): a slow peripheral's own pace shouldn't
force extra work into a hot loop more often than needed.
"""

import display_config as config
import hand_renderer

try:
    import time as _time
except ImportError:  # pragma: no cover - always available in practice
    _time = None


def _ticks_ms():
    if _time is not None and hasattr(_time, "ticks_ms"):
        return _time.ticks_ms()
    import time as _std_time
    return int(_std_time.time() * 1000)


def _ticks_diff(a, b):
    if _time is not None and hasattr(_time, "ticks_diff"):
        return _time.ticks_diff(a, b)
    return a - b


class DisplayUI:
    def __init__(self, canvas, min_interval_ms=None, joint_size=2):
        self.canvas = canvas
        self.min_interval_ms = (
            config.MIN_UPDATE_INTERVAL_MS if min_interval_ms is None else min_interval_ms
        )
        # joint_size: side length (px) of the filled square drawn at each
        # joint. 2 is the current default (see DEVELOPMENT.md 2-7); kept
        # configurable so examples/hand_demo.py can render a 2px vs 3px
        # side-by-side comparison without duplicating _draw_joint().
        self.joint_size = joint_size
        self._last_update_ms = None
        self._skeleton_area_height = config.OLED_HEIGHT - config.STATUS_BAR_HEIGHT

    def update(self, landmarks, gesture, fps=None, now_ms=None, force=False):
        """Redraw if enough time passed since the last redraw (or
        force=True). Returns True if it actually redrew, False if
        throttled or skipped. Never raises -- a canvas/I2C error is logged
        and swallowed (section 9: a broken display must not take the
        caller's loop down with it).
        """
        if self.canvas is None:
            return False
        if now_ms is None:
            now_ms = _ticks_ms()
        if not force and self._last_update_ms is not None:
            if _ticks_diff(now_ms, self._last_update_ms) < self.min_interval_ms:
                return False

        try:
            self._draw(landmarks, gesture, fps)
        except Exception as e:
            print("[OLED] update() draw failed:", repr(e))
            return False
        self._last_update_ms = now_ms
        return True

    def _draw(self, landmarks, gesture, fps):
        canvas = self.canvas
        canvas.fill(0)

        points, lines = hand_renderer.layout_skeleton(
            landmarks, config.OLED_WIDTH, self._skeleton_area_height,
            margin=config.SKELETON_MARGIN_PX,
        )
        hand_present = any(p is not None for p in points)

        for (ax, ay), (bx, by) in lines:
            canvas.line(ax, ay, bx, by, 1)
        for p in points:
            if p is not None:
                self._draw_joint(canvas, p[0], p[1])

        self._draw_status_bar(canvas, gesture, fps, hand_present)
        canvas.show()

    def _draw_joint(self, canvas, x, y):
        # A single pixel reads as part of the connecting line rather than a
        # distinct joint. joint_size (default 2) controls how large the
        # filled square is; see __init__ and DEVELOPMENT.md 2-7/2-8 for why
        # this is configurable instead of a fixed constant (clamped so it
        # never writes outside the panel for a joint sitting right on an
        # edge).
        if hasattr(canvas, "fill_rect"):
            x0 = max(x - 1, 0)
            y0 = max(y - 1, 0)
            canvas.fill_rect(x0, y0, self.joint_size, self.joint_size, 1)
        else:
            canvas.pixel(x, y, 1)

    def _draw_status_bar(self, canvas, gesture, fps, hand_present):
        bar_y = config.OLED_HEIGHT - config.STATUS_BAR_HEIGHT
        canvas.hline(0, bar_y, config.OLED_WIDTH, 1)
        text_y = bar_y + 2

        # The built-in framebuf font is a fixed 8x8 bitmap -- 128px fits at
        # most 16 characters per line. The reference mockup's
        # "MOVE    FPS 8.5    HAND OK" line (~27 chars) does not fit a
        # real 128px/8px-font row, so this is a deliberately compressed
        # layout for the real pixel budget rather than a literal copy of
        # the mockup text (see DEVELOPMENT.md).
        # str.ljust() is not available on this board's MicroPython build
        # (AttributeError on real hardware, 2026-10-26 -- CPython has it,
        # which is why this passed PC unit tests but failed on first
        # real-panel run) -- pad manually instead.
        label = (gesture or "")[:5]
        label = label + " " * (5 - len(label))
        canvas.text(label, 0, text_y, 1)

        if fps is not None:
            fps_text = ("%4.1f" % fps)[:4]
        else:
            fps_text = "  --"
        canvas.text(fps_text, 56, text_y, 1)

        canvas.text("H" if hand_present else "-", 120, text_y, 1)
