"""Transport-agnostic sender for already-decided Smart Glass mouse actions.

GestureController remains the sole owner of AI, gesture recognition, state
transitions, and pointer smoothing. This module only turns an action
transition into one @MOUSE protocol line and hands it to a transport
(UART2 by default; see transport.py for the Wi-Fi/UDP alternative)."""

import time
from transport import UartTransport


class MouseController:
    """Translate action transitions into one-line @MOUSE protocol records."""

    def __init__(self, pointer_size, invert_x=False, invert_y=False, transport=None):
        self.pointer_width = float(pointer_size[0])
        self.pointer_height = float(pointer_size[1])
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.previous_action = "STOP"
        self.dragging = False
        self.last_drag_point = None
        self.transport = transport or UartTransport()

    @property
    def uart(self):
        """Backward-compatible access to the UART2 handle when active."""
        return getattr(self.transport, "uart", None)

    def _normalized_point(self, x, y):
        """Clamp an existing K230 pointer position to the 0.0..1.0 protocol."""
        if self.pointer_width <= 0 or self.pointer_height <= 0:
            return None

        nx = float(x) / self.pointer_width
        ny = float(y) / self.pointer_height

        if nx < 0.0:
            nx = 0.0
        elif nx > 1.0:
            nx = 1.0

        if ny < 0.0:
            ny = 0.0
        elif ny > 1.0:
            ny = 1.0

        if self.invert_x:
            nx = 1.0 - nx
        if self.invert_y:
            ny = 1.0 - ny

        return nx, ny

    def _send(self, action, point=None):
        if point is None:
            message = "@MOUSE|" + action
        else:
            message = "@MOUSE|%s|%.4f|%.4f" % (action, point[0], point[1])
        self.transport.write(message + "\r\n")
        if action == "CLICK":
            print("CLICK_TX", "ms=", time.ticks_ms(), "packet=", message)

    def update(self, action, x=None, y=None):
        """Send transport events for one already-computed controller result.

        ``x`` and ``y`` are optional because ``no_hand()`` intentionally has no
        pointer coordinate.  A DRAG held during the gesture controller's hand
        loss grace period therefore remains held without inventing movement,
        but still re-sends the last known point as a keep-alive so a
        receiver-side link watchdog (Wi-Fi/UDP) never mistakes that grace
        period for a dead connection.
        """
        point = None
        if x is not None and y is not None:
            point = self._normalized_point(x, y)

        # Leaving DRAG must always release before sending the next action.
        if self.dragging and action != "DRAG":
            self._send("DRAG_END")
            self.dragging = False
            self.last_drag_point = None

        if action == "DRAG":
            if not self.dragging:
                if point is not None:
                    self._send("DRAG_START", point)
                    self.dragging = True
                    self.last_drag_point = point
            elif point is not None:
                self._send("DRAG", point)
                self.last_drag_point = point
            elif self.last_drag_point is not None:
                self._send("DRAG", self.last_drag_point)

        elif action == "CLICK":
            # GestureController displays CLICK over multiple frames.  Emit only
            # on the action edge so the Mac receives one physical click.
            if self.previous_action != "CLICK":
                self._send("CLICK")

        elif action == "MOVE":
            if point is not None:
                self._send("MOVE", point)

        elif action == "STOP":
            if self.previous_action != "STOP":
                self._send("STOP")

        self.previous_action = action

    def close(self):
        """Fail safe: never leave a drag button down when this app exits."""
        if self.dragging:
            self._send("DRAG_END")
            self.dragging = False
            self.last_drag_point = None
        if self.previous_action != "STOP":
            self._send("STOP")
        self.previous_action = "STOP"
        self.transport.close()
