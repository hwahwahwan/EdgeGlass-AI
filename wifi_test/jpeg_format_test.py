import time

from media.sensor import Sensor
from media.media import *

FRAME_WIDTH = 640
FRAME_HEIGHT = 480
JPEG_QUALITY = 50
OUT_DIR = "/sdcard/wifi_test"

# No Wi-Fi / no HTTP involved. This isolates JPEG encoding correctness from
# any network transmission issue by writing the JPEG straight to the SD card.


def log(msg):
    print("[JPEGTEST]", msg)


def run_case(pixformat, pixformat_name, out_path):
    sensor = None
    try:
        sensor = Sensor()
        sensor.reset()
        sensor.set_hmirror(True)
        sensor.set_vflip(True)
        sensor.set_framesize(width=FRAME_WIDTH, height=FRAME_HEIGHT)
        sensor.set_pixformat(pixformat)
        MediaManager.init()
        sensor.run()
        for _ in range(5):
            sensor.snapshot()
        img = sensor.snapshot()
        jpeg_img = img.compress(quality=JPEG_QUALITY)
        data = jpeg_img.bytearray()
        size = len(jpeg_img)
        with open(out_path, "wb") as f:
            f.write(data)
        magic = (data[0], data[1])
        tail = (data[-2], data[-1])
        log("%s OK path=%s bytes=%d magic=%r tail=%r" % (pixformat_name, out_path, size, magic, tail))
        return True
    except Exception as e:
        log("%s FAIL %r" % (pixformat_name, e))
        return False
    finally:
        try:
            if sensor is not None:
                sensor.stop()
        except Exception as e:
            log("sensor.stop() err %r" % (e,))
        try:
            MediaManager.deinit()
        except Exception as e:
            log("MediaManager.deinit() err %r" % (e,))


log("=== RGB565 case (orientation-corrected) ===")
run_case(Sensor.RGB565, "RGB565", OUT_DIR + "/out_rgb565_fixed.jpg")
log("done")
