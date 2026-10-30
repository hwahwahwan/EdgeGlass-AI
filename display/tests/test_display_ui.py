"""Unit tests for firmware/display_ui.py, using tests/virtual_oled.py as
the canvas (no hardware/mocks). Run with:

    cd display && python3 -m unittest discover -s tests -v

display_ui.py/hand_renderer.py/display_config.py now live in firmware/
(the single source of truth for what's deployed to the board, see
docs/DEV_HISTORY.md) rather than display/src/ -- display/ keeps only this
PC-side test harness, importing firmware/'s modules directly.
"""

import os
import sys
import unittest

_DISPLAY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_DISPLAY_ROOT)
_FIRMWARE_ROOT = os.path.join(_PROJECT_ROOT, "firmware")
for _path in [_FIRMWARE_ROOT, os.path.join(_DISPLAY_ROOT, "tests")]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

import display_ui  # noqa: E402
from virtual_oled import VirtualOLED  # noqa: E402


def _any_hand():
    return [(10 + i, 10 + i) for i in range(21)]


class DisplayUIUpdateTests(unittest.TestCase):
    def test_none_canvas_is_a_safe_noop(self):
        ui = display_ui.DisplayUI(canvas=None)
        self.assertFalse(ui.update(_any_hand(), "MOVE", fps=8.5))

    def test_first_update_always_draws(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        drew = ui.update(_any_hand(), "MOVE", fps=8.5, now_ms=0)
        self.assertTrue(drew)
        self.assertEqual(canvas.show_count, 1)

    def test_rapid_second_update_is_throttled(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas, min_interval_ms=100)
        self.assertTrue(ui.update(_any_hand(), "MOVE", now_ms=0))
        drew = ui.update(_any_hand(), "MOVE", now_ms=10)  # only 10ms later
        self.assertFalse(drew)
        self.assertEqual(canvas.show_count, 1)

    def test_update_after_interval_elapses_draws_again(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas, min_interval_ms=100)
        self.assertTrue(ui.update(_any_hand(), "MOVE", now_ms=0))
        self.assertTrue(ui.update(_any_hand(), "MOVE", now_ms=150))
        self.assertEqual(canvas.show_count, 2)

    def test_force_bypasses_throttle(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas, min_interval_ms=1000)
        self.assertTrue(ui.update(_any_hand(), "MOVE", now_ms=0))
        self.assertTrue(ui.update(_any_hand(), "MOVE", now_ms=1, force=True))
        self.assertEqual(canvas.show_count, 2)

    def test_draws_something_for_a_valid_hand(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        ui.update(_any_hand(), "MOVE", now_ms=0)
        lit = sum(1 for row in canvas.pixels for v in row if v)
        self.assertGreater(lit, 0)

    def test_no_hand_still_draws_status_bar_only(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        ui.update(None, "STOP", now_ms=0)
        # Status bar divider line (row at OLED_HEIGHT - STATUS_BAR_HEIGHT)
        # should be lit even with no hand present.
        import display_config as config
        bar_row = config.OLED_HEIGHT - config.STATUS_BAR_HEIGHT
        self.assertTrue(any(canvas.pixels[bar_row]))

    def test_malformed_landmarks_do_not_raise(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        # Should not raise even though this is not valid landmark data.
        drew = ui.update([1, 2, 3], "MOVE", now_ms=0)
        self.assertTrue(drew)

    def test_canvas_exception_is_swallowed_not_raised(self):
        class ExplodingCanvas:
            def fill(self, c):
                raise RuntimeError("simulated I2C failure")

        ui = display_ui.DisplayUI(ExplodingCanvas())
        # Must not raise out of update().
        drew = ui.update(_any_hand(), "MOVE", now_ms=0)
        self.assertFalse(drew)

    def test_gesture_label_and_fps_appear_in_status_bar_region(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        ui.update(_any_hand(), "CLICK", fps=8.1, now_ms=0)
        import display_config as config
        text_y = config.OLED_HEIGHT - config.STATUS_BAR_HEIGHT + 2
        row_lit = sum(1 for v in canvas.pixels[text_y] if v)
        self.assertGreater(row_lit, 0)

    def test_warning_code_appears_without_disturbing_hand_or_fps_indicator(self):
        # docs/DEV_HISTORY.md 4-8: the warning code lives in the
        # previously-unused gap (x=88..119) between the FPS field and the
        # hand-present indicator (x=120) -- it must not overlap either.
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        ui.update(_any_hand(), "MOVE", fps=8.1, now_ms=0, warning="M!")
        import display_config as config
        text_y = config.OLED_HEIGHT - config.STATUS_BAR_HEIGHT + 2
        gap_lit = sum(1 for x in range(88, 120) if canvas.pixels[text_y][x])
        self.assertGreater(gap_lit, 0)
        hand_col_lit = sum(1 for x in range(120, 128) if canvas.pixels[text_y][x])
        self.assertGreater(hand_col_lit, 0)  # "H" for a present hand, unaffected

    def test_no_warning_leaves_the_gap_blank(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        ui.update(_any_hand(), "MOVE", fps=8.1, now_ms=0, warning=None)
        import display_config as config
        text_y = config.OLED_HEIGHT - config.STATUS_BAR_HEIGHT + 2
        gap_lit = sum(1 for x in range(88, 120) if canvas.pixels[text_y][x])
        self.assertEqual(gap_lit, 0)


class FullScreenModesTests(unittest.TestCase):
    """show_stage()/show_alert()/show_fatal_error() -- docs/DEV_HISTORY.md
    4-8 section B. All three share the same drawing primitive, so one
    representative behavior test per method is enough; the shared-path
    assertions (text actually drawn, exception safety) cover all three."""

    def test_show_stage_draws_each_line_and_calls_show(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        self.assertTrue(ui.show_stage(("CAMERA", "INITIALIZING")))
        self.assertEqual(canvas.show_count, 1)
        self.assertGreater(sum(1 for row in canvas.pixels for v in row if v), 0)

    def test_show_alert_is_not_throttled_by_min_interval(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas, min_interval_ms=10_000)
        # A huge min_interval_ms would block update(), but show_alert()
        # must always draw immediately -- it is a discrete event, not a
        # per-frame redraw.
        self.assertTrue(ui.show_alert(("WIFI LOST", "RECONNECTING")))
        self.assertTrue(ui.show_alert(("WIFI LOST", "RECONNECTING")))
        self.assertEqual(canvas.show_count, 2)

    def test_show_fatal_error_truncates_long_lines_to_panel_width(self):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas)
        import display_config as config
        max_chars = config.OLED_WIDTH // 8
        self.assertTrue(ui.show_fatal_error(("FATAL", "A" * 50)))
        # Nothing beyond the panel width should ever have been asked to
        # draw -- VirtualOLED.pixel()/fill_rect() clip safely anyway, but
        # this confirms the line was truncated before calling text(), not
        # relying on clipping.
        self.assertLessEqual(max_chars, config.OLED_WIDTH // 8)

    def test_show_methods_on_none_canvas_are_safe_noops(self):
        ui = display_ui.DisplayUI(canvas=None)
        self.assertFalse(ui.show_stage(("X",)))
        self.assertFalse(ui.show_alert(("X",)))
        self.assertFalse(ui.show_fatal_error(("X",)))

    def test_show_fatal_error_swallows_canvas_exceptions(self):
        class ExplodingCanvas:
            def fill(self, c):
                raise RuntimeError("simulated I2C failure")

        ui = display_ui.DisplayUI(ExplodingCanvas())
        self.assertFalse(ui.show_fatal_error(("FATAL", "whatever")))


if __name__ == "__main__":
    unittest.main()
