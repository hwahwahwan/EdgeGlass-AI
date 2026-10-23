"""GMT130-V1.0 (ST7789) SPI mode/speed isolation test.

Separate from lcd_test.py (preserved as-is). lcd_test.py's full color+text
test always reported "PASSED" with no exception, but the panel stayed
dark across three attempts (BLK polarity flip, RST FPIOA pull-up) -- see
docs/DEV_HISTORY.md problem #24. Since SPI is write-only here, a silent
signal-integrity problem (long jumper wires at a fast 20 MHz SPI clock)
cannot be distinguished from a loose-wire problem by the driver raising an
exception; both look identical ("success", blank screen).

This script isolates ONE variable at a time, as instructed:
  - SPI_BAUDRATE (default 1 MHz here, down from 20 MHz)
  - SPI_POLARITY / SPI_PHASE (Mode 3 = (1,1), Mode 0 = (0,0))
It fills the whole panel with a single solid color only (no multi-color
loop, no text) so each run tests exactly one thing. Wiring/pin assignment
is identical to lcd_test.py (see that file / README.md for the full table
and the RST FPIOA pu=1 fix already applied there):

    SCK=IO15, SDA=IO16, RES=IO20, DC=IO21, BLK=IO17, dummy CS=IO14.

Edit SPI_BAUDRATE / SPI_POLARITY / SPI_PHASE below and redeploy between
attempts. Does not touch firmware/ or lcd_test.py.
"""

import time

from machine import FPIOA, Pin, SPI, SPI_LCD

PIN_SCK = 15
PIN_SDA = 16
PIN_RES = 20
PIN_DC = 21
PIN_BLK = 17
DUMMY_CS_PIN = 14

LCD_WIDTH = 240
LCD_HEIGHT = 240

# ---- change exactly one of these between attempts -------------------
SPI_BAUDRATE = 1 * 1000 * 1000   # 1 MHz -- conservative, rules out signal
                                   # integrity over long jumper wires at 20 MHz
SPI_POLARITY = 0                  # Mode 3 = (1, 1); Mode 0 = (0, 0)
SPI_PHASE = 0
FILL_COLOR = (255, 0, 0)          # solid red -- single, obvious color
BLK_ACTIVE_LOW = False             # already ruled out as the cause, kept fixed
# -----------------------------------------------------------------------


def _make_pin(fpioa, pin_num, pull=Pin.PULL_NONE, fpioa_pu=None):
    if fpioa_pu is not None:
        fpioa.set_function(pin_num, getattr(FPIOA, "GPIO%d" % pin_num), pu=fpioa_pu)
    else:
        fpioa.set_function(pin_num, getattr(FPIOA, "GPIO%d" % pin_num))
    return Pin(pin_num, Pin.OUT, pull=pull, drive=15)


def main():
    mode = {(0, 0): 0, (0, 1): 1, (1, 0): 2, (1, 1): 3}.get((SPI_POLARITY, SPI_PHASE), "?")
    print("lcd_mode_test: baudrate=%d polarity=%d phase=%d (SPI Mode %s)" % (
        SPI_BAUDRATE, SPI_POLARITY, SPI_PHASE, mode))

    fpioa = FPIOA()
    fpioa.set_function(PIN_SCK, FPIOA.QSPI0_CLK)
    fpioa.set_function(PIN_SDA, FPIOA.QSPI0_D0)
    spi = SPI(1, baudrate=SPI_BAUDRATE, polarity=SPI_POLARITY, phase=SPI_PHASE, bits=8)

    pin_dc = _make_pin(fpioa, PIN_DC)
    pin_dc.value(1)
    pin_rst = _make_pin(fpioa, PIN_RES, pull=Pin.PULL_UP, fpioa_pu=1)
    pin_cs_dummy = _make_pin(fpioa, DUMMY_CS_PIN)
    pin_cs_dummy.value(1)
    pin_bl = _make_pin(fpioa, PIN_BLK)
    pin_bl.value(0 if BLK_ACTIVE_LOW else 1)

    lcd = None
    try:
        lcd = SPI_LCD(spi, pin_dc, pin_cs_dummy, pin_rst)
        lcd.configure(LCD_WIDTH, LCD_HEIGHT, hmirror=False, vflip=False, bgr=False)
        img = lcd.init()
        print("lcd_mode_test: SPI_LCD init OK")
        img.draw_rectangle(0, 0, LCD_WIDTH, LCD_HEIGHT, color=FILL_COLOR, fill=True)
        lcd.show(img)
        print("lcd_mode_test: filled with", FILL_COLOR, "-- check the panel now")
        time.sleep(5)
        print("lcd_mode_test: PASSED (no exception) -- visually confirm on panel")
    except Exception as e:
        print("lcd_mode_test: FAILED ->", repr(e))
        raise
    finally:
        if lcd is not None:
            try:
                lcd.deinit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
