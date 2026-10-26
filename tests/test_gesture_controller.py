import os
import random
import sys
import unittest

_FIRMWARE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware")
if _FIRMWARE_DIR not in sys.path:
    sys.path.insert(0, _FIRMWARE_DIR)

import gesture_controller as gesture


class Clock:
    now = 0

    def ticks_ms(self):
        return self.now

    def ticks_diff(self, later, earlier):
        return later - earlier


def points(index_x, index_y, pinch=False):
    values = [0] * 42
    joints = {
        0: (index_x - 20, index_y + 60),
        4: (index_x - 2, index_y + 2) if pinch else (index_x - 40, index_y + 20),
        5: (index_x - 15, index_y + 30),
        8: (index_x, index_y),
        9: (index_x + 10, index_y + 30),
        17: (index_x + 35, index_y + 30),
    }
    for joint, (x, y) in joints.items():
        values[joint * 2] = x
        values[joint * 2 + 1] = y
    return values


class GestureControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        gesture.time = self.clock
        self.controller = gesture.GestureController((640, 360))

    def frame(self, x, y, ms, pinch=False, fist=False, one=False):
        self.clock.now = ms
        return self.controller.update(points(x, y, pinch), fist, one)

    def test_first_hand_position_does_not_set_absolute_cursor_position(self):
        self.assertEqual((self.frame(100, 100, 0)["x"], self.controller.cursor_y), (320, 180))
        other = gesture.GestureController((640, 360))
        self.assertEqual((other.update(points(500, 300), False)["x"], other.cursor_y), (320, 180))

    def test_stationary_hand_has_no_long_term_drift(self):
        self.frame(200, 150, 0)
        self.frame(230, 170, 20)
        for ms in range(40, 440, 20):
            held = self.frame(230, 170, ms)
        settled = (held["x"], held["y"])
        for ms in range(440, 20440, 20):
            held = self.frame(230, 170, ms)
            self.assertEqual((held["x"], held["y"]), settled)

    def test_stationary_camera_jitter_is_suppressed(self):
        self.frame(200, 150, 0)
        random.seed(4)
        output = []
        for i in range(1, 1001):
            x = 200 + random.choice((-5, 5))
            y = 150 + random.choice((-5, 5))
            info = self.frame(x, y, i * 20)
            output.append((info["x"], info["y"]))
            self.assertEqual(info["action"], "MOVE")
        self.assertLessEqual(max(x for x, _ in output) - min(x for x, _ in output), 2)
        self.assertLessEqual(max(y for _, y in output) - min(y for _, y in output), 2)

    def test_alternating_jitter_has_no_cumulative_drift(self):
        first = self.frame(200, 150, 0)
        for i in range(1, 1001):
            offset = 5 if i % 2 else -5
            info = self.frame(200 + offset, 150 - offset, i * 20)
        self.assertEqual((info["x"], info["y"]), (first["x"], first["y"]))

    def test_directions_reversal_and_small_noise(self):
        self.frame(200, 150, 0)
        right_down = self.frame(220, 170, 20)
        self.assertGreater(right_down["x"], 320)
        self.assertGreater(right_down["y"], 180)
        left_up = self.frame(200, 150, 40)
        further_left_up = self.frame(180, 130, 60)
        self.assertLess(further_left_up["x"], left_up["x"])
        self.assertLess(further_left_up["y"], left_up["y"])
        for i in range(1, 21):
            settled = self.frame(180, 130, 60 + i * 20)
        for i in range(1, 11):
            held = self.frame(180 + (i % 2), 130 - (i % 2), 460 + i * 20)
        self.assertLessEqual(abs(held["x"] - settled["x"]), 2)
        self.assertLessEqual(abs(held["y"] - settled["y"]), 2)

    def test_sustained_slow_motion_escapes_spatial_zone(self):
        self.frame(100, 100, 0)
        for i in range(1, 81):
            info = self.frame(100 + i, 100, i * 33)
        self.assertGreaterEqual(info["x"], 390)
        self.assertLessEqual(info["x"], 400)

    def test_fast_motion_and_immediate_reversal(self):
        self.frame(200, 150, 0)
        first = self.frame(240, 150, 33)
        self.assertGreaterEqual(first["x"], 340)
        for i in range(2, 6):
            right = self.frame(200 + 40 * i, 150, i * 33)
        reversed_frame = self.frame(360, 150, 6 * 33)
        self.assertLess(reversed_frame["x"], right["x"])

    def test_clamp_and_reverse_from_edge(self):
        self.frame(200, 150, 0)
        edge = self.frame(600, 150, 20)
        for i in range(2, 15):
            edge = self.frame(600, 150, i * 20)
        self.assertEqual(edge["x"], 640)
        self.frame(580, 150, 300)
        reversed_frame = self.frame(560, 150, 320)
        self.assertLess(reversed_frame["x"], 640)

    def test_reacquisition_preserves_cursor_without_jump(self):
        self.frame(200, 150, 0)
        before = self.frame(230, 170, 20)
        self.clock.now = 40
        self.controller.no_hand()
        self.assertEqual((self.frame(500, 300, 60)["x"], self.controller.cursor_y), (before["x"], before["y"]))
        self.clock.now = 500
        self.assertEqual(self.controller.no_hand(), "STOP")
        reacquired = self.frame(100, 100, 520)
        self.assertEqual((reacquired["x"], reacquired["y"]), (before["x"], before["y"]))
        for i in range(1, 6):
            next_frame = self.frame(100 + i * 10, 100, 520 + i * 20)
        self.assertGreater(next_frame["x"], before["x"])

    def test_click_anchor_and_drag_release_keep_pointer_aligned(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 120)
        anchor = self.frame(220, 150, 140, pinch=True)
        click = self.frame(240, 150, 240, pinch=True)
        self.assertEqual(click["action"], "CLICK")
        self.assertEqual((click["x"], click["y"]), (anchor["x"], anchor["y"]))
        held = self.frame(260, 150, 260, pinch=False)
        self.assertEqual((held["x"], held["y"]), (anchor["x"], anchor["y"]))
        rearmed = self.frame(280, 150, 500)
        self.assertEqual((rearmed["x"], rearmed["y"]), (anchor["x"], anchor["y"]))
        before_fist = self.frame(280, 150, 520)
        fist_candidate = self.frame(300, 150, 540, fist=True)
        self.assertEqual((fist_candidate["x"], fist_candidate["y"]), (before_fist["x"], before_fist["y"]))
        drag_start = self.frame(300, 150, 740, fist=True)
        self.assertEqual(drag_start["action"], "DRAG")
        dragged = self.frame(320, 150, 760, fist=True)
        self.assertGreater(dragged["x"], drag_start["x"])
        self.frame(320, 150, 780, fist=False)
        last_drag = self.frame(320, 150, 980, fist=False)
        released = self.frame(320, 150, 1020, fist=False)
        self.assertEqual(released["action"], "MOVE")
        self.assertEqual((released["x"], released["y"]), (last_drag["x"], last_drag["y"]))
        self.assertEqual((int(self.controller.pointer_float_x), int(self.controller.pointer_float_y)), (released["x"], released["y"]))

    def test_click_and_fist_candidates_lock_cursor_despite_index_jitter(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 120)
        anchor = self.frame(200, 150, 140, pinch=True)
        for ms, x in ((160, 205), (180, 197), (200, 204), (220, 196)):
            candidate = self.frame(x, 150, ms, pinch=True)
            self.assertEqual((candidate["x"], candidate["y"]), (anchor["x"], anchor["y"]))
        click = self.frame(203, 150, 240, pinch=True)
        self.assertEqual(click["action"], "CLICK")
        self.assertEqual((click["x"], click["y"]), (anchor["x"], anchor["y"]))

        self.frame(200, 150, 260)
        self.frame(200, 150, 400)
        fist_anchor = self.frame(200, 150, 420, fist=True)
        for ms, x in ((440, 205), (460, 197), (480, 204), (500, 196)):
            candidate = self.frame(x, 150, ms, fist=True)
            self.assertEqual((candidate["x"], candidate["y"]), (fist_anchor["x"], fist_anchor["y"]))
        drag_start = self.frame(200, 150, 620, fist=True)
        self.assertEqual(drag_start["action"], "DRAG")
        self.assertEqual((drag_start["x"], drag_start["y"]), (fist_anchor["x"], fist_anchor["y"]))

    def test_short_fist_candidate_cancels_old_pinch_timer(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 120)
        self.frame(200, 150, 140, pinch=True)
        self.frame(200, 150, 160, pinch=True, fist=True)
        self.assertIsNone(self.controller.pinch_since)
        released = self.frame(200, 150, 240, pinch=True)
        self.assertNotEqual(released["action"], "CLICK")
        self.assertEqual(self.controller.pinch_since, 240)

    def test_short_hand_loss_cancels_old_pinch_timer(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 120)
        self.frame(200, 150, 140, pinch=True)
        self.clock.now = 160
        self.controller.no_hand()
        self.assertIsNone(self.controller.pinch_since)
        reacquired = self.frame(200, 150, 240, pinch=True)
        self.assertNotEqual(reacquired["action"], "CLICK")
        self.assertEqual(self.controller.pinch_since, 240)

    # ------------------------------------------------------------
    # STOP ("one" 제스처: 검지만 펼치기)
    # ------------------------------------------------------------

    def test_one_gesture_requires_consecutive_frames_before_stop(self):
        self.frame(200, 150, 0)
        baseline = self.frame(200, 150, 20)
        ms = 20
        held = baseline
        for _ in range(1, gesture.ONE_STOP_CONFIRM_FRAMES):
            ms += 20
            held = self.frame(200, 150, ms, one=True)
            self.assertEqual(held["action"], "MOVE")
            self.assertEqual((held["x"], held["y"]), (baseline["x"], baseline["y"]))
        ms += 20
        stopped = self.frame(200, 150, ms, one=True)
        self.assertEqual(stopped["action"], "STOP")
        self.assertEqual((stopped["x"], stopped["y"]), (baseline["x"], baseline["y"]))

    def test_stop_freezes_cursor_even_if_hand_coordinates_move(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 20)
        ms = 20
        stopped = None
        for _ in range(gesture.ONE_STOP_CONFIRM_FRAMES):
            ms += 20
            stopped = self.frame(200, 150, ms, one=True)
        self.assertEqual(stopped["action"], "STOP")

        # 카메라 재조정을 흉내낸 큰 좌표 변화 -- "one" 모양은 유지된다.
        for dx in (50, -80, 120, 0):
            ms += 20
            moved = self.frame(200 + dx, 150 + dx, ms, one=True)
            self.assertEqual(moved["action"], "STOP")
            self.assertEqual((moved["x"], moved["y"]), (stopped["x"], stopped["y"]))

    def test_stop_releases_after_consecutive_non_one_frames_with_zero_first_delta(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 20)
        ms = 20
        stopped = None
        for _ in range(gesture.ONE_STOP_CONFIRM_FRAMES):
            ms += 20
            stopped = self.frame(200, 150, ms, one=True)
        self.assertEqual(stopped["action"], "STOP")

        # STOP 중 카메라가 움직여 손 좌표가 바뀌었지만 여전히 "one" 유지.
        ms += 20
        moved_while_stopped = self.frame(260, 190, ms, one=True)
        self.assertEqual(
            (moved_while_stopped["x"], moved_while_stopped["y"]),
            (stopped["x"], stopped["y"]),
        )

        released = None
        for _ in range(gesture.ONE_STOP_RELEASE_FRAMES):
            ms += 20
            released = self.frame(260, 190, ms, one=False)
        self.assertEqual(released["action"], "MOVE")
        # 해제 직후 첫 이동량은 0 -- STOP 중 누적된 좌표 변화가 적용되지 않는다.
        self.assertEqual((released["x"], released["y"]), (stopped["x"], stopped["y"]))

        ms += 20
        next_frame = self.frame(300, 190, ms)
        self.assertGreater(next_frame["x"], released["x"])

    def test_one_candidate_blocked_while_pinching(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 20)
        ms = 20
        for _ in range(gesture.ONE_STOP_CONFIRM_FRAMES + 2):
            ms += 20
            info = self.frame(200, 150, ms, pinch=True, one=True)
            self.assertNotEqual(info["action"], "STOP")

    def test_fist_takes_priority_over_one_candidate(self):
        self.frame(200, 150, 0)
        self.frame(200, 150, 20)
        ms = 20
        for _ in range(gesture.ONE_STOP_CONFIRM_FRAMES + 2):
            ms += 20
            info = self.frame(200, 150, ms, fist=True, one=True)
            self.assertNotEqual(info["action"], "STOP")


def classifier_points(straight_fingers):
    """Build a 42-value points array with only the five finger-angle joints
    GestureController's angle math reads (wrist, j+4/j+5, j+6/j+7, j+8/j+9
    for j=i*8). Angle 0 (parallel vectors) for "straight", 180 (opposite)
    for "folded" -- real anatomical coordinates are irrelevant to is_one()
    and is_fist(), only these five finger angles are."""
    values = [0] * 42
    for i in range(5):
        j = i * 8
        values[j + 4], values[j + 5] = -10, 0
        values[j + 6], values[j + 7] = 0, 0
        values[j + 8], values[j + 9] = (-10, 0) if i in straight_fingers else (10, 0)
    return values


class GestureClassifierTests(unittest.TestCase):
    """is_one()/is_fist() angle math, independent of GestureController state."""

    def test_is_one_true_for_index_only_extended(self):
        self.assertTrue(gesture.is_one(classifier_points({1})))

    def test_is_one_false_for_fist_shape(self):
        self.assertFalse(gesture.is_one(classifier_points(set())))

    def test_is_fist_true_for_all_folded(self):
        self.assertTrue(gesture.is_fist(classifier_points(set())))

    def test_is_fist_false_for_index_only_extended(self):
        self.assertFalse(gesture.is_fist(classifier_points({1})))

    def test_is_one_false_when_other_fingers_also_extended(self):
        self.assertFalse(gesture.is_one(classifier_points({1, 2})))


if __name__ == "__main__":
    unittest.main()
