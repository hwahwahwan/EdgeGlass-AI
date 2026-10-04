"""K230-side UART2 transport for already-decided Smart Glass mouse actions."""

from machine import UART


class MouseController:
    """Translate action transitions into one-line @MOUSE USB-serial records."""

    def __init__(self, pointer_size, invert_x=False, invert_y=False):
        self.pointer_width = float(pointer_size[0])
        self.pointer_height = float(pointer_size[1])
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.previous_action = "STOP"
        self.dragging = False
        # BPI-CanMV-K230D-Zero UART2 is physically connected to the verified
        # CH342K USB Dual_Serial data port (macOS: cu.usbmodem58930597043).
        # This leaves the CanMV USB CDC/IDE channel untouched.
        self.uart = UART(
            UART.UART2,
            baudrate=115200,
            bits=UART.EIGHTBITS,
            parity=UART.PARITY_NONE,
            stop=UART.STOPBITS_ONE
        )

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
        self.uart.write(message + "\r\n")

    def update(self, action, x=None, y=None):
        """Send transport events for one already-computed controller result.

        ``x`` and ``y`` are optional because ``no_hand()`` intentionally has no
        pointer coordinate.  A DRAG held during the gesture controller's hand
        loss grace period therefore remains held without inventing movement.
        """
        point = None
        if x is not None and y is not None:
            point = self._normalized_point(x, y)

        # Leaving DRAG must always release before sending the next action.
        if self.dragging and action != "DRAG":
            self._send("DRAG_END")
            self.dragging = False

        if action == "DRAG":
            if not self.dragging:
                if point is not None:
                    self._send("DRAG_START", point)
                    self.dragging = True
            elif point is not None:
                self._send("DRAG", point)

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
        if self.previous_action != "STOP":
            self._send("STOP")
        self.previous_action = "STOP"
        self.uart.deinit()
