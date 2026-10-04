#!/usr/bin/env python3
"""Thin macOS bridge: @MOUSE serial records -> CoreGraphics mouse events.

Install only on the Mac that runs this file:
    python3 -m pip install pyserial pyobjc-framework-Quartz
"""

import argparse
import glob
import sys

PREFIX = "@MOUSE|"


def available_ports():
    """Return candidate CanMV CDC devices without guessing their role."""
    paths = []
    for pattern in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*"):
        paths.extend(glob.glob(pattern))
    return sorted(set(paths))


def parse_message(line):
    """Parse exactly one protocol line; return (action, x, y) or None."""
    line = line.strip()
    if not line.startswith(PREFIX):
        return None
    fields = line.split("|")
    if len(fields) < 2:
        return None
    action = fields[1]
    if action in ("MOVE", "DRAG_START", "DRAG"):
        if len(fields) != 4:
            return None
        try:
            x = float(fields[2])
            y = float(fields[3])
        except ValueError:
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        return action, x, y
    if action in ("CLICK", "DRAG_END", "STOP") and len(fields) == 2:
        return action, None, None
    return None


class DryRunMouse:
    """Test backend; it intentionally never moves the host cursor."""

    def __init__(self):
        self.dragging = False

    def move(self, x, y, dragged=False):
        print("EVENT %s %.4f %.4f" % ("DRAG" if dragged else "MOVE", x, y))

    def click(self):
        print("EVENT CLICK")

    def down(self, x, y):
        self.dragging = True
        print("EVENT DRAG_START %.4f %.4f" % (x, y))

    def up(self):
        if self.dragging:
            print("EVENT DRAG_END")
        self.dragging = False


class QuartzMouse:
    """CoreGraphics event sender.  Coordinates are normalized primary-screen points."""

    def __init__(self):
        try:
            import Quartz
        except ImportError as exc:
            raise RuntimeError(
                "Quartz is unavailable. Install pyobjc-framework-Quartz: "
                "python3 -m pip install pyobjc-framework-Quartz"
            ) from exc
        self.q = Quartz
        bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        self.width = bounds.size.width
        self.height = bounds.size.height
        self.dragging = False

    def _point(self, x, y):
        return (x * self.width, y * self.height)

    def _post(self, event_type, point):
        event = self.q.CGEventCreateMouseEvent(
            None, event_type, point, self.q.kCGMouseButtonLeft
        )
        self.q.CGEventPost(self.q.kCGHIDEventTap, event)

    def move(self, x, y, dragged=False):
        event_type = self.q.kCGEventLeftMouseDragged if dragged else self.q.kCGEventMouseMoved
        self._post(event_type, self._point(x, y))

    def click(self):
        point = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
        self._post(self.q.kCGEventLeftMouseDown, point)
        self._post(self.q.kCGEventLeftMouseUp, point)

    def down(self, x, y):
        self._post(self.q.kCGEventLeftMouseDown, self._point(x, y))
        self.dragging = True

    def up(self):
        if self.dragging:
            point = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
            self._post(self.q.kCGEventLeftMouseUp, point)
        self.dragging = False


def dispatch(mouse, message):
    action, x, y = message
    if action == "MOVE":
        mouse.move(x, y)
    elif action == "CLICK":
        mouse.click()
    elif action == "DRAG_START":
        # A new start is also a recovery point for a stale interrupted drag.
        mouse.up()
        mouse.down(x, y)
    elif action == "DRAG":
        if mouse.dragging:
            mouse.move(x, y, dragged=True)
    elif action in ("DRAG_END", "STOP"):
        mouse.up()


def self_test():
    mouse = DryRunMouse()
    lines = (
        "debug output ignored",
        "@MOUSE|MOVE|0.5123|0.4380",
        "@MOUSE|CLICK",
        "@MOUSE|DRAG_START|0.5123|0.4380",
        "@MOUSE|DRAG|0.5300|0.4500",
        "@MOUSE|DRAG_END",
        "@MOUSE|STOP",
    )
    for line in lines:
        parsed = parse_message(line)
        if parsed is not None:
            dispatch(mouse, parsed)
    assert not mouse.dragging
    print("Self-test passed (no OS mouse events were sent).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Explicit /dev/cu.* device to read; never auto-selected.")
    parser.add_argument("--baud", type=int, default=115200, help="CDC line setting (default: 115200).")
    parser.add_argument("--list", action="store_true", help="List candidate USB serial devices and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Parse serial input without sending OS events.")
    parser.add_argument("--self-test", action="store_true", help="Test parser and MOVE/CLICK/DRAG/STOP dispatch safely.")
    args = parser.parse_args()

    if args.list:
        ports = available_ports()
        if ports:
            print("Candidate ports (roles are not inferred):")
            for port in ports:
                print("  " + port)
        else:
            print("No /dev/cu.usbmodem* or /dev/cu.usbserial* ports found.")
        return 0
    if args.self_test:
        self_test()
        return 0
    if not args.port:
        parser.error("--port is required unless --list or --self-test is used")

    try:
        import serial
    except ImportError:
        print("Missing dependency: python3 -m pip install pyserial", file=sys.stderr)
        return 2

    try:
        mouse = DryRunMouse() if args.dry_run else QuartzMouse()
        if not args.dry_run:
            print("macOS Accessibility permission is required: System Settings > Privacy & Security > Accessibility.")
        with serial.Serial(args.port, args.baud, timeout=0.5) as connection:
            print("Reading %s at %d baud. Press Ctrl-C to stop." % (args.port, args.baud))
            while True:
                raw = connection.readline()
                if not raw:
                    continue
                message = parse_message(raw.decode("utf-8", errors="replace"))
                if message is not None:
                    dispatch(mouse, message)
    except KeyboardInterrupt:
        print("Stopping bridge.")
    except Exception as exc:
        print("Bridge error: %s" % exc, file=sys.stderr)
        print("If the port is busy, disconnect VS Code CanMV from that same CDC endpoint before retrying.", file=sys.stderr)
        return 1
    finally:
        # The local is intentionally checked because creation/open may fail.
        if "mouse" in locals():
            mouse.up()
    return 0


if __name__ == "__main__":
    sys.exit(main())
