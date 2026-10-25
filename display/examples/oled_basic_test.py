"""Board-only basic bring-up test for the VLT-OL016 OLED.

NOT tested on real hardware this session -- no VLT-OL016 unit was
available (see README.md). This mirrors the structure/safety pattern of
archive/st7789_lcd/lcd_test.py (the now-archived ST7789 bring-up test):
print clear PASS/FAIL, never leave the bus half-configured, and -- unlike
the ST7789 driver, which crashed the whole board if the panel was not
wired -- oled_device.open_display() is designed to just return None
instead of crashing if I2C/the panel isn't there (see
src/oled_device.py's docstring). That said, this has not been proven on
real hardware either; treat the first run with the same caution as any
new peripheral bring-up.

Deploy flattened next to the other display/ files (see README.md "보드에서
실행할 테스트 파일"), e.g. to /sdcard/display/, then run this file directly
from the CanMV IDE.
"""

import sys
import time

PROJECT_DIR = "/sdcard/display"
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
