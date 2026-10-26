"""CanMV-only OLED bring-up: FPIOA + I2C init, address scan, safe SSD1306
construction/teardown.

This is the one firmware/ module among the OLED-related files that imports
`machine` -- hand_renderer.py and display_ui.py stay plain Python so they
can be unit tested on a PC without hardware or mocks (see
display/tests/test_oled_device.py for how *this* file's logic is still
exercised on a PC, using fake machine/framebuf modules the same way this
project's existing tests fake `machine` for transport.py -- see
tests/test_wifi_mouse_transport.py). display/ keeps only the PC-side test
harness (tests/, examples/) that imports these firmware/ modules directly;
firmware/ is the single source of truth for what's deployed to the board
(see docs/DEV_HISTORY.md 4-3).

Flat-import convention: deployed flat to /sdcard/smart_glass/ next to
display_config.py, ssd1306.py, display_ui.py, hand_renderer.py and the
rest of firmware/ (this project's existing firmware/ -> /sdcard/smart_glass/
convention, see /CLAUDE.md). So the imports below are flat (`import
display_config`, `from ssd1306 import SSD1306_I2C`), not package-relative.
The module is named display_config, not config, because firmware/config.py
already exists -- two modules both named config.py in the same flat
directory would shadow each other (see docs/DEV_HISTORY.md 4-3).
"""

import display_config as config


def _log(msg):
    print("[OLED]", msg)


def open_display(i2c_id=None, scl=None, sda=None, freq=None,
                  width=None, height=None, addr=None):
    """Bring up I2C and the SSD1306 driver. Never raises -- returns None on
    any failure (machine/framebuf unavailable, FPIOA error, I2C bus error,
    no device found at the expected address, driver init error) so a
    caller can treat "no display" the same whether the panel is simply not
    wired yet or something else went wrong, instead of crashing. Mirrors
    the non-fatal pattern already used for the UDP mouse transport in
    firmware/smart_glass_server.py (see docs/WORK_TRACKER.md section N)
    rather than inventing a different error-handling style for this module.
    """
    i2c_id = config.I2C_ID if i2c_id is None else i2c_id
    scl = config.PIN_SCL if scl is None else scl
    sda = config.PIN_SDA if sda is None else sda
    freq = config.I2C_FREQ if freq is None else freq
    width = config.OLED_WIDTH if width is None else width
    height = config.OLED_HEIGHT if height is None else height
    addr = config.OLED_I2C_ADDR if addr is None else addr

    try:
        from machine import FPIOA, I2C
    except ImportError as e:
        _log("machine module unavailable (not running on the board?): %r" % (e,))
        return None

    try:
        fpioa = FPIOA()
        fpioa.set_function(scl, getattr(FPIOA, "IIC%d_SCL" % i2c_id))
        fpioa.set_function(sda, getattr(FPIOA, "IIC%d_SDA" % i2c_id))
        i2c = I2C(i2c_id, freq=freq)
    except Exception as e:
        _log("I2C bring-up failed (id=%d scl=%d sda=%d): %r" % (i2c_id, scl, sda, e))
        return None

    try:
        found = i2c.scan()
    except Exception as e:
        _log("i2c.scan() failed: %r" % (e,))
        return None
    _log("i2c.scan() -> %s" % ([hex(a) for a in found],))
    if addr not in found:
        _log("no device at 0x%02X (scan found %s) -- check wiring/address" % (
            addr, [hex(a) for a in found]))
        return None

    try:
        from ssd1306 import SSD1306_I2C
    except Exception as e:
        _log("could not import ssd1306 driver: %r" % (e,))
        return None

    try:
        oled = SSD1306_I2C(width, height, i2c, addr=addr)
    except Exception as e:
        _log("SSD1306_I2C init failed: %r" % (e,))
        return None

    _log("ready (%dx%d @ 0x%02X)" % (width, height, addr))
    return oled


def close_display(oled):
    """Safe teardown -- never raises, no-op if oled is None/already dead."""
    if oled is None:
        return
    try:
        oled.poweroff()
    except Exception as e:
        _log("poweroff() err %r" % (e,))
