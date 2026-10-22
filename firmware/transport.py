"""Pluggable @MOUSE transports for MouseController: UART2 (verified) and UDP/Wi-Fi.

Both transports expose the same minimal interface used by MouseController:
``write(message)`` and ``close()``. The @MOUSE/@TRACK protocol text itself is
unchanged between transports; only how the bytes leave the board differs.
"""

import time
from machine import UART


class UartTransport:
    """Existing verified path: BPI-CanMV-K230D-Zero UART2 (CH342K bridge)."""

    def __init__(self, uart=None):
        # Physically connected to the verified CH342K USB Dual_Serial data
        # port (macOS: cu.usbmodem58930597043). Leaves the CanMV USB CDC/IDE
        # channel untouched.
        self.uart = uart or UART(
            UART.UART2,
            baudrate=115200,
            bits=UART.EIGHTBITS,
            parity=UART.PARITY_NONE,
            stop=UART.STOPBITS_ONE
        )

    def write(self, message):
        self.uart.write(message)

    def close(self):
        self.uart.deinit()


class UdpTransport:
    """Unverified path: send the same protocol text as UDP datagrams.

    Fire-and-forget by design -- a lost MOVE/DRAG packet must not raise out
    of the gesture loop. Connection loss / DRAG safety is handled on the
    receiving (Mac) side by a timeout watchdog, not here.
    """

    def __init__(self, host, port, retry_attempts=20, retry_delay_ms=500,
                 socket_module=None):
        self._socket_module = socket_module or __import__("socket")
        self.sock = self._connect(host, port, retry_attempts, retry_delay_ms)

    def _connect(self, host, port, retry_attempts, retry_delay_ms):
        # Real-hardware finding (experiments/wifi_test/WIFI_TEST_REPORT.md
        # §0.3, §3-E): right after a soft reboot, wlan.isconnected() can
        # already be True while the socket layer has not yet registered the
        # NIC, so socket()/connect() raises OSError('no available NIC') for a
        # short window. Retrying a few hundred ms apart clears it.
        last_error = None
        for _ in range(retry_attempts):
            try:
                sock = self._socket_module.socket(
                    self._socket_module.AF_INET, self._socket_module.SOCK_DGRAM
                )
                sock.connect((host, port))
                sock.setblocking(False)
                return sock
            except OSError as exc:
                last_error = exc
                _sleep_ms(retry_delay_ms)
        raise OSError("UDP transport setup failed: %r" % (last_error,))

    def write(self, message):
        data = message.encode() if isinstance(message, str) else message
        try:
            self.sock.send(data)
        except OSError:
            # A single dropped datagram must not interrupt gesture control.
            pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000.0)


def wifi_is_needed(web_server_enabled, mouse_control_enabled, mouse_transport_kind):
    """True exactly when a run profile needs an active Wi-Fi link.

    Pure decision logic shared by smart_glass_server.main() (called from
    run_uart.py / run_wifi.py). Kept here, independent of any
    hardware-only module, so the uart-vs-udp / web-on-vs-off wiring stays
    unit-testable without mocking media.sensor etc.
    """
    return bool(web_server_enabled) or (
        bool(mouse_control_enabled) and mouse_transport_kind == "udp"
    )


def create_transport(kind, uart=None, udp_host=None, udp_port=None,
                      udp_retry_attempts=20, udp_retry_delay_ms=500,
                      socket_module=None):
    """Build the transport named by config.MOUSE_TRANSPORT."""
    if kind == "uart":
        return UartTransport(uart=uart)
    if kind == "udp":
        if not udp_host or not udp_port:
            raise ValueError("udp transport requires udp_host and udp_port")
        return UdpTransport(
            udp_host, udp_port,
            retry_attempts=udp_retry_attempts,
            retry_delay_ms=udp_retry_delay_ms,
            socket_module=socket_module,
        )
    raise ValueError("unknown transport kind: %r" % (kind,))
