"""LED-cause isolation diagnostic, part 2: AI/NPU inference path -- NOT
production code. All 6 OLED-related stages in led_stage_test.py already
ran clean (LED never turned on), so this tests the remaining suspects
from the run that DID show the LED: HandTracker model load and repeated
NPU inference. No OLED code at all in this file. Does not modify
firmware/smart_glass_server.py or any existing working feature.

STAGE controls how far the script goes (edited by hand between runs, one
step at a time, confirming with the user before advancing):
  1 = camera (chn0 OSD + chn2 AI) + OSD, same as led_stage_test.py stage 1
      (already confirmed LED-free) -- baseline, re-confirmed here.
  2 = + HandTracker(...) construction only -- loads hand_det.kmodel and
      handkp_det.kmodel onto the NPU, but does not run inference yet.
  3 = + a loop that actually calls tracker.run(ai_frame) repeatedly
      (real NPU inference, ~50 iterations then idle) -- closest
      reproduction of the real AI loop, still with zero OLED code.

After reaching STAGE the script idles, printing a heartbeat, so there is
time to look at the board LED before stopping it from the IDE.

Deploy flattened to /sdcard/smart_glass/ai_stage_test.py (same directory
as smart_glass_server.py, so it can reuse the already-deployed
hand_tracker.py/gesture_controller.py/config.py) and run directly.
"""

from media.sensor import Sensor
from media.display import Display
from media.media import *  # noqa: F401,F403  (MediaManager, CAM_CHN_ID_*, ALIGN_UP)

# Same import-order requirement as smart_glass_server.py.
import sys
import gc
import time
import image

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STAGE = 3  # <-- bump by hand before each redeploy, one step at a time

AI_RGB888P_SIZE = [640, 360]

print("AI_STAGE_TEST: STAGE=%d starting" % STAGE)

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
print("AI_STAGE_TEST: stage 1 (camera chn0+chn2 + OSD, zero AI code) up -- check LED now")

tracker = None

if STAGE >= 2:
    from hand_tracker import HandTracker
    hand_det_model = "/sdcard/examples/kmodel/hand_det.kmodel"
    hand_kp_model = "/sdcard/examples/kmodel/handkp_det.kmodel"
    tracker = HandTracker(hand_det_model, hand_kp_model, AI_RGB888P_SIZE)
    print("AI_STAGE_TEST: stage 2 (HandTracker constructed, kmodels loaded onto NPU) done -- check LED now")

if STAGE >= 3:
    print("AI_STAGE_TEST: stage 3 running ~50 real inference iterations...")
    for i in range(50):
        frame = sensor.snapshot(chn=CAM_CHN_ID_2)
        ai_frame = frame.to_numpy_ref()
        det, points, fallback = tracker.run(ai_frame)
        if i % 10 == 0:
            print("AI_STAGE_TEST: inference iter %d (hand_detected=%s)" % (i, det is not None))
    print("AI_STAGE_TEST: stage 3 (50 real NPU inference calls) done -- check LED now")

print("AI_STAGE_TEST: reached target stage %d, idling -- stop from the IDE when done checking" % STAGE)
while True:
    time.sleep(2)
