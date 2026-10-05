import random
import unittest

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

    def frame(self, x, y, ms, pinch=False, fist=False):
        self.clock.now = ms
        return self.controller.update(points(x, y, pinch), fist)

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


if __name__ == "__main__":
    unittest.main()
