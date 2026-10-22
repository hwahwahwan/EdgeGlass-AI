"""GMT130-V1.0 (ST7789, 240x240, SPI) standalone display test for K230D-Zero.

Independent of firmware/ (hand tracking / mouse control demo) -- this file
imports nothing from that project and does not touch UART2, the camera, or
Wi-Fi. Safe to run on its own; does not modify any existing demo code.

Wiring (7-pin header, GND/VCC/SCK/SDA/RES/DC/BLK only -- confirmed against
the real board's current FPIOA state, see experiments/lcd_test/README.md
for the full verification log and what is still unverified):

    LCD pin   K230D-Zero pin   Notes
    -------   --------------   -----
    GND       GND              --
    VCC       3V3              3.3V ONLY. Do not use 5V -- unverified for
                                this exact module; most 7-pin ST7789 boards
                                of this type are 3.3V-only and have no
                                onboard regulator.
    SCK       IO_15            FPIOA QSPI0_CLK -> hardware SPI(1) clock
    SDA       IO_16            FPIOA QSPI0_D0  -> hardware SPI(1) MOSI
    RES       IO_20            plain GPIO (reset, active low pulse)
    DC        IO_21            plain GPIO (command/data select)
    BLK       IO_17            plain GPIO (backlight). Polarity (active-high
                                vs active-low) was NOT confirmed on the real
                                panel -- this script tries HIGH=on first.
                                If the screen stays dark but color_test()
                                still reports success, flip BLK_ACTIVE_LOW.

No CS wire exists on this 7-pin module. CanMV's machine.SPI_LCD constructor
still requires a CS pin *object* -- passing cs=None crashed the real board
(soft reboot) during this session's bring-up testing. DUMMY_CS_PIN below is
therefore a spare GPIO used only as a placeholder Pin object; it is NOT
wired to anything on the LCD and carries no real chip-select signal.

IMPORTANT -- confirmed by real hardware testing in this session:
Constructing machine.SPI_LCD() while the panel is NOT physically connected
and powered caused the K230D-Zero to soft-reboot (crash) on this firmware
(CanMV v1.8-0-gc2d1f5c). This did not corrupt the SD card or any existing
firmware/ files (verified after the fact), but it means this script must
only be run AFTER the 7-pin wiring above is physically complete and the
board has power. Do not run it against an unwired board.
"""

import time

from machine import FPIOA, Pin, SPI, SPI_LCD

# ---- pin assignment (change here only, not in the functions below) -------
PIN_SCK = 15          # hardware SPI1 clock -- FPIOA QSPI0_CLK
PIN_SDA = 16          # hardware SPI1 MOSI  -- FPIOA QSPI0_D0
PIN_RES = 20          # GPIO, LCD reset
PIN_DC = 21           # GPIO, LCD data/command select
PIN_BLK = 17          # GPIO, LCD backlight
DUMMY_CS_PIN = 14     # GPIO placeholder only -- NOT wired to the LCD

LCD_WIDTH = 240
LCD_HEIGHT = 240
SPI_BAUDRATE = 20 * 1000 * 1000  # conservative; raise later once verified

BLK_ACTIVE_LOW = True  # flip to True if the backlight is inverted


def _make_pin(fpioa, pin_num, pull=Pin.PULL_NONE):
    fpioa.set_function(pin_num, getattr(FPIOA, "GPIO%d" % pin_num))
    return Pin(pin_num, Pin.OUT, pull=pull, drive=15)


def init_display():
    """Bring up the SPI bus + SPI_LCD driver. Raises on failure."""
    fpioa = FPIOA()

    # Hardware SPI1 on the shared QSPI0 clock/data-0 lines.
    fpioa.set_function(PIN_SCK, FPIOA.QSPI0_CLK)
    fpioa.set_function(PIN_SDA, FPIOA.QSPI0_D0)
    spi = SPI(1, baudrate=SPI_BAUDRATE, polarity=1, phase=1, bits=8)

    pin_dc = _make_pin(fpioa, PIN_DC)
    pin_dc.value(1)

    pin_rst = _make_pin(fpioa, PIN_RES, pull=Pin.PULL_UP)
    pin_cs_dummy = _make_pin(fpioa, DUMMY_CS_PIN)
    pin_cs_dummy.value(1)

    pin_bl = _make_pin(fpioa, PIN_BLK)
    pin_bl.value(0 if BLK_ACTIVE_LOW else 1)

    lcd = SPI_LCD(spi, pin_dc, pin_cs_dummy, pin_rst)
    lcd.configure(LCD_WIDTH, LCD_HEIGHT, hmirror=False, vflip=False, bgr=False)
    img = lcd.init()
    return lcd, img, pin_bl


def color_test(lcd, img):
    """Fill the whole panel with red, green, blue, black, then white."""
    colors = [
        ("RED", (255, 0, 0)),
        ("GREEN", (0, 255, 0)),
        ("BLUE", (0, 0, 255)),
        ("BLACK", (0, 0, 0)),
        ("WHITE", (255, 255, 255)),
    ]
    for name, rgb in colors:
        img.draw_rectangle(0, 0, LCD_WIDTH, LCD_HEIGHT, color=rgb, fill=True)
        lcd.show(img)
        print("color_test: showed", name)
        time.sleep(1)


def text_test(lcd, img):
    """Clear to black and draw a short label + a bordered rectangle."""
    img.clear()
    img.draw_string_advanced(10, 10, 24, "EdgeGlass LCD OK", color=(0, 255, 0))
    img.draw_rectangle(20, 60, 200, 120, color=(255, 255, 0), thickness=4)
    lcd.show(img)
    print("text_test: shown")


def main():
    print("lcd_test: starting -- make sure the panel is wired and powered")
    lcd = None
    try:
        lcd, img, pin_bl = init_display()
        print("lcd_test: SPI_LCD init OK ->", lcd)
        color_test(lcd, img)
        text_test(lcd, img)
        print("lcd_test: PASSED (color + text shown, visually confirm on panel)")
    except Exception as e:
        print("lcd_test: FAILED ->", repr(e))
        raise
    finally:
        if lcd is not None:
            try:
                lcd.deinit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
