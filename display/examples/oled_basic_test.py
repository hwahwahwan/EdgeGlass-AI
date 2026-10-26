"""Board-only basic bring-up test for the VLT-OL016 OLED.

Verified on real hardware 2026-10-26: I2C scan finds 0x3C, SSD1306
init/clear/full-on/text+shape all PASSED and were visually confirmed on
the panel (see docs/DEV_HISTORY.md 4-3). This mirrors the structure/safety
pattern of archive/st7789_lcd/lcd_test.py (the now-archived ST7789
bring-up test): print clear PASS/FAIL, never leave the bus
half-configured, and -- unlike the ST7789 driver, which crashed the whole
board if the panel was not wired -- oled_device.open_display() just
returns None instead of crashing if I2C/the panel isn't there (see
firmware/oled_device.py's docstring).

Deploy flattened next to the other firmware/ files (oled_device.py,
ssd1306.py, display_config.py are now part of firmware/, the single
source of truth for what's deployed to the board -- see
docs/DEV_HISTORY.md), i.e. to /sdcard/smart_glass/, then run this file
directly from the CanMV IDE.
"""

import sys
import time

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import oled_device


def main():
    print("oled_basic_test: starting -- make sure the panel is wired and powered")
    oled = oled_device.open_display()
    if oled is None:
        print("oled_basic_test: FAILED -- open_display() returned None, see [OLED] log above")
        return

    try:
        oled.fill(0)
        oled.show()
        print("oled_basic_test: cleared OK")
        time.sleep(1)

        oled.fill(1)
        oled.show()
        print("oled_basic_test: full-on OK")
        time.sleep(1)

        oled.fill(0)
        oled.text("EdgeGlass OLED", 0, 0, 1)
        oled.text("OK", 0, 16, 1)
        oled.rect(0, 30, 40, 20, 1)
        oled.show()
        print("oled_basic_test: text+shape OK")

        oled.contrast(255)
        print("oled_basic_test: PASSED (visually confirm on panel)")
    except Exception as e:
        print("oled_basic_test: FAILED ->", repr(e))
        raise
    finally:
        oled_device.close_display(oled)


if __name__ == "__main__":
    main()
