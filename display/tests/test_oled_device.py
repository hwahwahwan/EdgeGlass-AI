"""Unit tests for firmware/oled_device.py.

oled_device.py defers its `from machine import ...` / `from ssd1306
import ...` to inside open_display() (not at module level), specifically
so the module itself always imports cleanly under plain CPython. That
means:

  - "machine isn't available" (test_returns_none_without_machine_module)
    needs NO faking at all -- running this under plain CPython already
    exercises the real ImportError path honestly, not a simulated one.
  - The "device found, driver constructed" happy path needs `machine` and
    `framebuf` faked in sys.modules (the same way this project's existing
    tests fake `machine` for firmware/transport.py -- see
    tests/test_wifi_mouse_transport.py's _install_fake_machine()), so the
    real firmware/ssd1306.py driver can run against a fake I2C bus
    instead of a mocked-out driver.

oled_device.py/ssd1306.py now live in firmware/ (single source of truth
for what's deployed to the board) rather than display/src|drivers/.

Run with:
    cd display && python3 -m unittest discover -s tests -v
"""

import importlib
import os
import sys
import types
import unittest

_DISPLAY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIRMWARE_ROOT = os.path.join(os.path.dirname(_DISPLAY_ROOT), "firmware")
if _FIRMWARE_ROOT not in sys.path:
    sys.path.insert(0, _FIRMWARE_ROOT)

import oled_device  # noqa: E402


class _FakeFrameBuffer:
    """Minimal enough for ssd1306.SSD1306(framebuf.FrameBuffer) to
    subclass and for SSD1306.init_display()'s fill(0)/show() calls to
    succeed -- not a pixel-accurate framebuf, see tests/virtual_oled.py
    for that (used by test_display_ui.py instead)."""

    def __init__(self, buffer, width, height, fmt):
        self._buffer = buffer
        self._width = width
        self._height = height

    def fill(self, col):
        pass

    def pixel(self, x, y, col=None):
        return 0

    def line(self, *a):
        pass

    def hline(self, *a):
        pass

    def vline(self, *a):
        pass

    def rect(self, *a):
        pass

    def fill_rect(self, *a):
        pass

    def text(self, *a):
        pass

    def scroll(self, *a):
        pass


def _install_fake_framebuf():
    mod = types.ModuleType("framebuf")
    mod.FrameBuffer = _FakeFrameBuffer
    mod.MONO_VLSB = 0
    return mod


class _FakeFPIOA:
    IIC2_SCL = 100
    IIC2_SDA = 101

    def __init__(self):
        self.calls = []

    def set_function(self, pin, func, **kw):
        self.calls.append((pin, func, kw))


class _FakeI2C:
    def __init__(self, id, freq=400000, found_addrs=(0x3C,), raise_on_scan=None):
        self.id = id
        self.freq = freq
        self._found_addrs = list(found_addrs)
        self._raise_on_scan = raise_on_scan
        self.writes = []
        self.vwrites = []

    def scan(self):
        if self._raise_on_scan is not None:
            raise self._raise_on_scan
        return list(self._found_addrs)

    def writeto(self, addr, buf, stop=True):
        self.writes.append((addr, bytes(buf)))
        return len(buf)

    def writevto(self, addr, vector, stop=True):
        self.vwrites.append((addr, [bytes(v) for v in vector]))
        return sum(len(v) for v in vector)


def _install_fake_machine(found_addrs=(0x3C,), raise_on_scan=None):
    mod = types.ModuleType("machine")
    mod.FPIOA = _FakeFPIOA

    def _make_i2c(id, freq=400000, **kw):
        return _FakeI2C(id, freq=freq, found_addrs=found_addrs, raise_on_scan=raise_on_scan)

    mod.I2C = _make_i2c
    return mod


class OpenDisplayWithoutMachineTests(unittest.TestCase):
    def test_returns_none_without_machine_module(self):
        # No faking at all -- plain CPython genuinely has no `machine`
        # module, so this exercises the real code path, not a simulation.
        self.assertNotIn("machine", sys.modules)
        result = oled_device.open_display()
        self.assertIsNone(result)


class OpenDisplayWithFakeMachineTests(unittest.TestCase):
    def setUp(self):
        self._orig_machine = sys.modules.get("machine")
        self._orig_framebuf = sys.modules.get("framebuf")
        self._orig_ssd1306 = sys.modules.get("ssd1306")
        sys.modules.pop("ssd1306", None)
        sys.modules["framebuf"] = _install_fake_framebuf()

    def tearDown(self):
        for name, value in (
            ("machine", self._orig_machine),
            ("framebuf", self._orig_framebuf),
            ("ssd1306", self._orig_ssd1306),
        ):
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value

    def test_device_found_constructs_driver(self):
        sys.modules["machine"] = _install_fake_machine(found_addrs=(0x3C,))
        oled = oled_device.open_display()
        self.assertIsNotNone(oled)
        # init_display() must have sent at least the "display on" command.
        self.assertTrue(oled.i2c.writes)

    def test_device_not_found_at_expected_address_returns_none(self):
        sys.modules["machine"] = _install_fake_machine(found_addrs=(0x3D,))  # wrong addr
        oled = oled_device.open_display(addr=0x3C)
        self.assertIsNone(oled)

    def test_scan_failure_returns_none_not_raises(self):
        sys.modules["machine"] = _install_fake_machine(raise_on_scan=OSError("bus error"))
        oled = oled_device.open_display()
        self.assertIsNone(oled)

    def test_fpioa_error_returns_none_not_raises(self):
        class ExplodingFPIOA(_FakeFPIOA):
            def set_function(self, pin, func, **kw):
                raise OSError("pin already claimed")

        mod = types.ModuleType("machine")
        mod.FPIOA = ExplodingFPIOA
        mod.I2C = lambda id, freq=400000, **kw: _FakeI2C(id)
        sys.modules["machine"] = mod

        oled = oled_device.open_display()
        self.assertIsNone(oled)

    def test_close_display_is_safe_with_none(self):
        oled_device.close_display(None)  # must not raise

    def test_close_display_calls_poweroff(self):
        sys.modules["machine"] = _install_fake_machine(found_addrs=(0x3C,))
        oled = oled_device.open_display()
        self.assertIsNotNone(oled)
        before = len(oled.i2c.writes)
        oled_device.close_display(oled)
        self.assertGreater(len(oled.i2c.writes), before)


if __name__ == "__main__":
    unittest.main()
