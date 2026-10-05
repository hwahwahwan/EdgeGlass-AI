import csv
import importlib
import os
import sys
import tempfile
import types
import unittest

import mac_mouse_bridge
import ui


class Canvas:
    def __init__(self):
        self.circles = []

    def draw_circle(self, x, y, radius, **kwargs):
        self.circles.append((x, y, radius, kwargs.get("color")))

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class UITransportTests(unittest.TestCase):
    def test_red_tracking_point_uses_raw_index_tip(self):
        canvas = Canvas()
        pipeline = types.SimpleNamespace(osd_img=canvas)
        landmarks = [0] * 42
        landmarks[16], landmarks[17] = 120, 90
        ui.draw_hand(pipeline, [0, 0, 0, 0, 200, 180], landmarks,
                     (640, 360), (640, 360), {"x": 500, "y": 300, "action": "MOVE"})
        self.assertIn((120, 90, 10, (255, 255, 0, 0)), canvas.circles)
        self.assertNotIn((500, 300, 10, (255, 255, 0, 0)), canvas.circles)

    def test_click_transport_is_one_packet_per_action_edge(self):
        class UART:
            UART2 = 2
            EIGHTBITS = 8
            PARITY_NONE = 0
            STOPBITS_ONE = 1

            def __init__(self, *args, **kwargs):
                self.sent = []

            def write(self, data):
                self.sent.append(data)

        machine = types.ModuleType("machine")
        machine.UART = UART
        original = sys.modules.get("machine")
        sys.modules["machine"] = machine
        try:
            mouse_controller = importlib.import_module("mouse_controller")
            mouse_controller.time = types.SimpleNamespace(ticks_ms=lambda: 123)
            transport = mouse_controller.MouseController((640, 360))
            transport.update("CLICK", 320, 180)
            transport.update("CLICK", 320, 180)
            self.assertEqual(transport.uart.sent.count("@MOUSE|CLICK\r\n"), 1)
            self.assertEqual(mac_mouse_bridge.parse_message("@MOUSE|CLICK\r\n"),
                             ("CLICK", None, None))
            self.assertIsNone(mac_mouse_bridge.parse_message("@MOUSE|CLICK|0.1\r\n"))
        finally:
            if original is None:
                del sys.modules["machine"]
            else:
                sys.modules["machine"] = original

    def test_tracking_packets_are_saved_separately_from_mouse_packets(self):
        sample = [str(i) for i in range(len(mac_mouse_bridge.TRACK_FIELDS))]
        delta = [str(i) for i in range(len(mac_mouse_bridge.TRACK_FIELDS) - 2)]
        line = "@TRACK|S|123|7|%s|%s\r\n" % (
            ",".join(sample), ",".join(delta)
        )
        self.assertIsNone(mac_mouse_bridge.parse_message(line))
        with tempfile.TemporaryDirectory() as directory:
            logger = mac_mouse_bridge.TrackingCsvLogger(directory)
            logger.write(mac_mouse_bridge.parse_tracking(line))
            logger.write(mac_mouse_bridge.parse_tracking("@TRACK|L|124|8\r\n"))
            logger.close()
            self.assertRegex(os.path.basename(logger.path), r"^tracking_\d{8}_\d{6}\.csv$")
            with open(logger.path, newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["bbox_cx"], "0")
            self.assertEqual(rows[0]["fist"], "18")
            self.assertEqual(rows[0]["d_norm_index_tip_y"], "16")
            self.assertEqual(rows[1]["kind"], "L")
            self.assertEqual(rows[1]["bbox_cx"], "")

    def test_tracking_file_failure_does_not_disable_mouse_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked_path = os.path.join(directory, "not_a_directory")
            with open(blocked_path, "w") as file:
                file.write("occupied")
            logger = mac_mouse_bridge.TrackingCsvLogger(blocked_path)
            logger.write(mac_mouse_bridge.parse_tracking("@TRACK|L|124|8\r\n"))
            self.assertTrue(logger.disabled)
            self.assertEqual(mac_mouse_bridge.parse_message("@MOUSE|CLICK\r\n"),
                             ("CLICK", None, None))


if __name__ == "__main__":
    unittest.main()
