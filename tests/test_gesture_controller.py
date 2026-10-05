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
        moved = self.frame(230, 170, 20)
        self.assertEqual((moved["x"], moved["y"]), (350, 200))
        for ms in range(40, 20040, 20):
            held = self.frame(230, 170, ms)
            self.assertEqual((held["x"], held["y"]), (350, 200))

    def test_directions_reversal_noise_and_slow_movement(self):
        self.frame(200, 150, 0)
        right_down = self.frame(220, 170, 20)
        self.assertEqual((right_down["x"], right_down["y"]), (340, 200))
        left_up = self.frame(200, 150, 40)
        self.assertEqual((left_up["x"], left_up["y"]), (320, 180))
        for i in range(1, 11):
            held = self.frame(200 + (i % 2), 150 - (i % 2), 40 + i * 20)
        self.assertEqual((held["x"], held["y"]), (320, 180))
        for i in range(1, 11):
            slow = self.frame(200 + i, 150, 240 + i * 20)
        self.assertGreaterEqual(slow["x"], 327)
        self.assertLessEqual(slow["x"], 330)

    def test_clamp_and_reverse_from_edge(self):
        self.frame(200, 150, 0)
        edge = self.frame(600, 150, 20)
        self.assertEqual(edge["x"], 640)
        reversed_frame = self.frame(580, 150, 40)
        self.assertEqual(reversed_frame["x"], 620)

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
        next_frame = self.frame(110, 100, 540)
        self.assertEqual((next_frame["x"], next_frame["y"]), (before["x"] + 10, before["y"]))

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


if __name__ == "__main__":
    unittest.main()
