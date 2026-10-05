import importlib
import sys
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


if __name__ == "__main__":
    unittest.main()
