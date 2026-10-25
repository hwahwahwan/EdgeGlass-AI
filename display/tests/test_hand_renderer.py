"""Unit tests for display/src/hand_renderer.py -- pure Python, no hardware,
no mocks needed. Run with:

    cd display && python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_DISPLAY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in [_DISPLAY_ROOT, os.path.join(_DISPLAY_ROOT, "src")]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

import hand_renderer  # noqa: E402


def _flat_hand(wrist=(0, 0), scale=1.0):
    """21 synthetic (x, y) landmarks shaped roughly like an open hand,
    fingers spread, usable as a baseline fixture for several tests."""
    wx, wy = wrist
    # (dx, dy) offsets per landmark index, loosely hand-shaped.
    offsets = [
        (0, 0),  # 0 wrist
        (-8, -4), (-14, -10), (-18, -16), (-20, -20),  # 1-4 thumb
        (-6, -20), (-6, -34), (-6, -44), (-6, -52),    # 5-8 index
        (0, -22), (0, -38), (0, -48), (0, -56),        # 9-12 middle
        (6, -20), (6, -34), (6, -42), (6, -50),        # 13-16 ring
        (12, -16), (13, -28), (14, -36), (15, -42),    # 17-20 pinky
    ]
    return [(wx + dx * scale, wy + dy * scale) for dx, dy in offsets]


def _fist_hand(wrist=(0, 0)):
    """21 synthetic landmarks shaped roughly like a closed fist -- finger
    tips curled back near the palm instead of extended."""
    wx, wy = wrist
    offsets = [
        (0, 0),
        (-6, -4), (-9, -8), (-8, -10), (-5, -9),
        (-4, -10), (-5, -16), (-4, -13), (-2, -10),
        (0, -11), (-1, -18), (0, -14), (1, -10),
        (4, -10), (3, -17), (4, -13), (5, -10),
        (8, -8), (7, -14), (8, -11), (9, -8),
    ]
    return [(wx + dx, wy + dy) for dx, dy in offsets]


class LandmarksBoundsTests(unittest.TestCase):
    def test_none_for_empty_input(self):
        self.assertIsNone(hand_renderer.landmarks_bounds(None))
        self.assertIsNone(hand_renderer.landmarks_bounds([]))

    def test_none_for_too_short_input(self):
        self.assertIsNone(hand_renderer.landmarks_bounds([(0, 0)] * 5))

    def test_none_for_malformed_entry(self):
        bad = [(0, 0)] * 21
        bad[10] = "not a point"
        self.assertIsNone(hand_renderer.landmarks_bounds(bad))

    def test_bounds_of_known_hand(self):
        hand = _flat_hand()
        bounds = hand_renderer.landmarks_bounds(hand)
        self.assertIsNotNone(bounds)
        min_x, min_y, max_x, max_y = bounds
        xs = [p[0] for p in hand]
        ys = [p[1] for p in hand]
        self.assertEqual(min_x, min(xs))
        self.assertEqual(max_x, max(xs))
        self.assertEqual(min_y, min(ys))
        self.assertEqual(max_y, max(ys))


class LayoutSkeletonTests(unittest.TestCase):
    def test_no_hand_returns_all_none_points_and_no_lines(self):
        points, lines = hand_renderer.layout_skeleton(None, 128, 54)
        self.assertEqual(points, [None] * 21)
        self.assertEqual(lines, [])

    def test_malformed_hand_returns_all_none(self):
        points, lines = hand_renderer.layout_skeleton([1, 2, 3], 128, 54)
        self.assertEqual(points, [None] * 21)
        self.assertEqual(lines, [])

    def test_all_points_present_for_a_valid_open_hand(self):
        points, lines = hand_renderer.layout_skeleton(_flat_hand(), 128, 54)
        self.assertEqual(len(points), 21)
        self.assertTrue(all(p is not None for p in points))
        self.assertEqual(len(lines), len(hand_renderer.SKELETON_CONNECTIONS))

    def test_points_stay_within_area_bounds(self):
        # A hand offset far outside the AI frame / with large coordinates
        # must still land fully inside the target area (clamped), not
        # just "mostly" inside.
        hand = _flat_hand(wrist=(5000, -3000), scale=50.0)
        points, _lines = hand_renderer.layout_skeleton(hand, 128, 54, margin=2)
        for p in points:
            self.assertIsNotNone(p)
            x, y = p
            self.assertGreaterEqual(x, 0)
            self.assertLess(x, 128)
            self.assertGreaterEqual(y, 0)
            self.assertLess(y, 54)

    def test_degenerate_hand_all_same_point_does_not_crash(self):
        hand = [(42, 17)] * 21
        points, lines = hand_renderer.layout_skeleton(hand, 128, 54)
        self.assertEqual(len(points), 21)
        self.assertTrue(all(p is not None for p in points))
        # All collapsed to (effectively) the same spot -- still valid ints
        # inside the box, no exception, no NaN.
        for x, y in points:
            self.assertIsInstance(x, int)
            self.assertIsInstance(y, int)

    def test_aspect_ratio_preserved_not_stretched(self):
        # A hand twice as tall as it is wide should still end up twice as
        # tall as wide after layout (within rounding), not stretched to
        # fill a differently-shaped box.
        hand = [(0, 0)] * 21
        hand[0] = (0, 0)
        hand[8] = (10, 100)  # defines a tall, narrow bounding box
        points, _lines = hand_renderer.layout_skeleton(hand, 128, 54, margin=0)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        drawn_w = max(xs) - min(xs)
        drawn_h = max(ys) - min(ys)
        self.assertGreater(drawn_h, 0)
        source_ratio = 100.0 / 10.0
        drawn_ratio = drawn_h / max(drawn_w, 1)
        self.assertAlmostEqual(drawn_ratio, source_ratio, delta=1.5)

    def test_fist_hand_also_lays_out_without_error(self):
        points, lines = hand_renderer.layout_skeleton(_fist_hand(), 128, 54)
        self.assertTrue(all(p is not None for p in points))
        self.assertEqual(len(lines), len(hand_renderer.SKELETON_CONNECTIONS))

    def test_skeleton_connections_match_firmware_ui_topology(self):
        # Pinned regression: this list must stay identical to
        # firmware/ui.py's _SKELETON_CONNECTIONS (read-only reference, not
        # imported -- see module docstring). If this test ever needs
        # updating, firmware/ui.py changed and this file's comment claiming
        # parity needs re-checking by hand.
        expected = [
            (0, 1), (1, 2), (2, 3), (3, 4),
            (0, 5), (5, 6), (6, 7), (7, 8),
            (0, 9), (9, 10), (10, 11), (11, 12),
            (0, 13), (13, 14), (14, 15), (15, 16),
            (0, 17), (17, 18), (18, 19), (19, 20),
        ]
        self.assertEqual(hand_renderer.SKELETON_CONNECTIONS, expected)


if __name__ == "__main__":
    unittest.main()
