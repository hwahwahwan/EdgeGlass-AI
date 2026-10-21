"""교수님 시연용 Wi-Fi 연결 진입점.

CanMV REPL에서 다음 한 줄로 실행한다.
    exec(open('/sdcard/wifi_test/demo_wifi.py').read())
"""

import sys

WIFI_TEST_DIR = "/sdcard/wifi_test"
if WIFI_TEST_DIR not in sys.path:
    sys.path.insert(0, WIFI_TEST_DIR)

from net_config import SSID, PASSWORD
from net import connect


print("CONNECT_OK", connect(SSID, PASSWORD, timeout_s=60))
