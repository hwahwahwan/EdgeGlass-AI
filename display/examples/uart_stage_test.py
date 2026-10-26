"""LED-cause isolation diagnostic, part 3: UART2 (MouseController) path --
NOT production code. All OLED stages (led_stage_test.py) and the AI/NPU
stages (ai_stage_test.py) already ran clean (LED never turned on). This
tests the one remaining untested component from the run that DID show the
LED: UART2 bring-up via MouseController/UartTransport. No OLED or AI code
in this file. Does not modify firmware/smart_glass_server.py or any
existing working feature.

STAGE controls how far the script goes (edited by hand between runs, one
step at a time, confirming with the user before advancing):
  1 = camera (chn0 OSD + chn2 AI, AI channel unused here) + OSD, same
      baseline as led_stage_test.py/ai_stage_test.py stage 1 (already
      confirmed LED-free) -- included again for a clean, self-contained run.
  2 = + MouseController(...) construction only -- opens UART2
      (machine.UART(UART.UART2, 115200, 8N1), no FPIOA pin assignment,
      fixed board pins per transport.py's UartTransport).
  3 = + a few real mouse_controller.update() calls (MOVE/CLICK/STOP),
      actually writing @MOUSE protocol lines out over UART2.

After reaching STAGE the script idles, printing a heartbeat, so there is
time to look at the board LED before stopping it from the IDE.

Deploy flattened to /sdcard/smart_glass/uart_stage_test.py (same
directory as smart_glass_server.py, so it can reuse the already-deployed
mouse_controller.py/transport.py/config.py) and run directly.
"""

from media.sensor import Sensor
from media.display import Display
from media.media import *  # noqa: F401,F403  (MediaManager, CAM_CHN_ID_*, ALIGN_UP)

import sys
import gc
import time
import image

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STAGE = 3  # <-- bump by hand before each redeploy, one step at a time

AI_RGB888P_SIZE = [640, 360]

print("UART_STAGE_TEST: STAGE=%d starting" % STAGE)

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
print("UART_STAGE_TEST: stage 1 (camera+OSD, zero UART/mouse code) up -- check LED now")

mouse_controller = None

if STAGE >= 2:
    from mouse_controller import MouseController
    mouse_controller = MouseController(AI_RGB888P_SIZE)
    print("UART_STAGE_TEST: stage 2 (MouseController constructed, UART2 opened) done -- check LED now")

if STAGE >= 3:
    mouse_controller.update("MOVE", 320, 180)
    time.sleep_ms(200)
    mouse_controller.update("CLICK")
    time.sleep_ms(200)
    mouse_controller.update("STOP")
    print("UART_STAGE_TEST: stage 3 (sent MOVE/CLICK/STOP over UART2) done -- check LED now")

print("UART_STAGE_TEST: reached target stage %d, idling -- stop from the IDE when done checking" % STAGE)
while True:
    time.sleep(2)
