"""LED-cause isolation diagnostic -- NOT production code, not part of the
display/ feature set. Does not modify firmware/smart_glass_server.py or
any existing working feature; this is a standalone throwaway script used
to find which exact initialization step (camera vs each OLED sub-step)
makes the board LED turn on (docs/DEV_HISTORY.md 6-7).

STAGE controls how far the script goes (edited by hand between runs, one
step at a time, confirming with the user before advancing):
  1 = camera + OSD only (same Sensor/Display setup as
      firmware/smart_glass_server.py's run_uart.py path with
      FEATURE_DISPLAY_OSD=True, FEATURE_HAND_RECOGNITION=True,
      FEATURE_WEB_SERVER=False) -- zero OLED-related code runs here.
  2 = + FPIOA.set_function(11/12, IIC2_SCL/SDA) only (no I2C object yet)
  3 = + I2C(2, freq=400000) construction (no scan yet)
  4 = + i2c.scan()
  5 = + SSD1306_I2C(128, 64, i2c, addr=0x3C) construction (this already
      runs init_display(), which does fill(0) + show() internally)
  6 = + an explicit fill(1) + show() (full white panel)

After reaching STAGE the script idles, printing a heartbeat, so there is
time to look at the board LED before stopping it from the IDE.

Deploy flattened to /sdcard/smart_glass/led_stage_test.py (same directory
as smart_glass_server.py, so it can reuse the already-deployed
oled_device/display_ui/ssd1306/display_config modules) and run directly.
"""

from media.sensor import Sensor
from media.display import Display
from media.media import *  # noqa: F401,F403  (MediaManager, CAM_CHN_ID_*, ALIGN_UP)

# Same import-order requirement as smart_glass_server.py: media.media's
# wildcard import rebinds `sys`, so `import sys` must come after it.
import sys
import gc
import time
import image

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STAGE = 6  # <-- bump by hand before each redeploy, one step at a time

AI_RGB888P_SIZE = [640, 360]

print("LED_STAGE_TEST: STAGE=%d starting" % STAGE)

# ---- camera + OSD, matching the non-OLED portion of the run that showed
# the LED (enable_display=True, enable_ai=True, enable_web=False) ----
sensor = Sensor()
sensor.reset()

Display.init(Display.ST7701, osd_num=1, to_ide=True)
display_size = [Display.width(), Display.height()]
sensor.set_framesize(w=display_size[0], h=display_size[1], chn=CAM_CHN_ID_0)
sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)

ai_w = ALIGN_UP(AI_RGB888P_SIZE[0], 16)
sensor.set_framesize(w=ai_w, h=AI_RGB888P_SIZE[1], chn=CAM_CHN_ID_2)
sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)

osd_img = image.Image(display_size[0], display_size[1], image.ARGB8888)
bind_info = sensor.bind_info(x=0, y=0, chn=CAM_CHN_ID_0)
Display.bind_layer(**bind_info, layer=Display.LAYER_VIDEO1)

sensor.run()
print("LED_STAGE_TEST: stage 1 (camera+OSD, zero OLED code) up -- check LED now")

i2c = None
oled = None

if STAGE >= 2:
    from machine import FPIOA
    fpioa = FPIOA()
    fpioa.set_function(11, FPIOA.IIC2_SCL)
    fpioa.set_function(12, FPIOA.IIC2_SDA)
    print("LED_STAGE_TEST: stage 2 (FPIOA GPIO11/12 -> IIC2_SCL/SDA) done -- check LED now")

if STAGE >= 3:
    from machine import I2C
    i2c = I2C(2, freq=400000)
    print("LED_STAGE_TEST: stage 3 (I2C(2) constructed) done -- check LED now")

if STAGE >= 4:
    found = i2c.scan()
    print("LED_STAGE_TEST: stage 4 i2c.scan() -> %s -- check LED now" % ([hex(a) for a in found],))

if STAGE >= 5:
    from ssd1306 import SSD1306_I2C
    oled = SSD1306_I2C(128, 64, i2c, addr=0x3C)
    print("LED_STAGE_TEST: stage 5 (SSD1306_I2C constructed, init_display ran) done -- check LED now")

if STAGE >= 6:
    oled.fill(1)
    oled.show()
    print("LED_STAGE_TEST: stage 6 (OLED full white) done -- check LED now")

print("LED_STAGE_TEST: reached target stage %d, idling -- stop from the IDE when done checking" % STAGE)
while True:
    time.sleep(2)
