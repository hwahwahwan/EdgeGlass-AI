"""EdgeGlass-AI 통합 오케스트레이터.

기존 main.py는 그대로 둔다 (손 추적 단독 실행용). 이 파일은 같은 AI
추론 결과를 손 추적/마우스 제어(main.py와 동일), 디스플레이 OSD 표시,
웹 MJPEG 스트리밍 세 곳에서 공유하는 통합 진입점이다.

기능별 ON/OFF 스위치는 아래 FEATURE_* 상수로 제어한다. 꺼진 기능은
관련 리소스(카메라 채널, Display, UART, 소켓)를 아예 생성하지 않는다.

=== 중요: 미검증 사항 (보드 연결 후 1순위로 확인해야 함) ===
1. Sensor 채널 0(YUV420SP, 디스플레이) + 채널 1(RGB565, 웹) + 채널 2
   (RGBP888, AI)를 동시에 하나의 Sensor 인스턴스에서 여는 구성은 이번에
   새로 설계한 것으로, 아직 실제 보드에서 실행해 본 적이 없다.
   libs/PipeLine.py는 채널 0+2만 검증되어 있고(main.py가 사용 중),
   채널 1을 추가하는 부분만 이번에 새로 작성했다.
2. web_server.py의 논블로킹 ClientSession 스텝 방식도 로컬에서 설계만
   했을 뿐 보드에서 실행해 보지 않았다.
3. AI 추론(hand_det+handkp_det) 중 웹 서버가 같은 루프에서 끼어들 때
   실제 FPS/지연에 미치는 영향은 측정되지 않았다.

로컬 단계에서는 문법 검사와 모듈 임포트 가능 여부만 확인했고, 그 외
"정상 동작"은 전혀 보장하지 않는다.
"""

import gc
import sys
import time

from media.sensor import Sensor
from media.display import Display
from media.media import *  # noqa: F401,F403  (MediaManager, CAM_CHN_ID_*, ALIGN_UP)
import image

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from hand_tracker import HandTracker
from gesture_controller import GestureController, is_fist
from mouse_controller import MouseController
import ui
import web_server
import video_stream


# ============================================================
# 기능별 ON/OFF (필요한 처리/메모리 할당까지 끈다)
# ============================================================

FEATURE_HAND_RECOGNITION = True   # hand_det+handkp_det 추론
FEATURE_MOUSE_CONTROL = True      # UART2 @MOUSE 송신 (HAND_RECOGNITION 필요)
FEATURE_DISPLAY_OSD = True        # 기존 HDMI/LCD에 관절 오버레이
FEATURE_WEB_SERVER = True         # HTTP 서버 자체
FEATURE_WEB_VIDEO = True          # /snapshot, /stream (WEB_SERVER 필요)
FEATURE_WEB_JOINTS = True         # 웹 영상에 관절 오버레이 (WEB_VIDEO+HAND_RECOGNITION 필요)

WEB_PORT = 8060
WEB_FRAME_WIDTH = 640
WEB_FRAME_HEIGHT = 480
WEB_JPEG_QUALITY = 50

AI_RGB888P_SIZE = [640, 360]
DISPLAY_MODE = "auto"


def log(msg):
    print("[ORCH]", msg)


if FEATURE_MOUSE_CONTROL and not FEATURE_HAND_RECOGNITION:
    log("WARNING: FEATURE_MOUSE_CONTROL=True 인데 FEATURE_HAND_RECOGNITION=False"
        " 입니다. 마우스 제어는 손 좌표가 없어 사실상 동작하지 않습니다.")

if FEATURE_WEB_JOINTS and not (FEATURE_WEB_VIDEO and FEATURE_HAND_RECOGNITION):
    log("WARNING: FEATURE_WEB_JOINTS는 FEATURE_WEB_VIDEO와"
        " FEATURE_HAND_RECOGNITION이 모두 켜져 있어야 의미가 있습니다.")


# ============================================================
# 카메라/디스플레이 리소스 — 기능 플래그에 따라 조건부로만 연다
# ============================================================
#
# libs/PipeLine.py(main.py가 쓰는 클래스)는 채널 0(디스플레이)+2(AI)를
# 무조건 둘 다 여는 단일 경로라서, 기능별로 채널을 선택적으로 열 수
# 없다. 그래서 PipeLine 클래스 자체를 그대로 쓰는 대신, 그 안에서
# 검증된 설정값(센서/디스플레이 초기화 시퀀스)만 그대로 가져와 조건부로
# 재구성했다 — PipeLine.py 파일 자체는 수정하지 않았다.

class CameraRig:
    def __init__(self):
        self.sensor = None
        self.display_size = None
        self.osd_img = None
        self._display_enabled = False
        self._ai_enabled = False
        self._web_enabled = False

    def create(self, enable_display, enable_ai, enable_web,
               ai_size, web_size, display_mode="auto"):
        self._display_enabled = enable_display
        self._ai_enabled = enable_ai
        self._web_enabled = enable_web

        if not (enable_display or enable_ai or enable_web):
            log("모든 카메라 관련 기능이 꺼져 있어 센서를 열지 않습니다.")
            return

        self.sensor = Sensor()
        self.sensor.reset()

        if enable_display:
            display_map = {
                "hdmi": Display.LT9611,
                "lt9611": Display.LT9611,
                "lcd": Display.ST7701,
                "st7701": Display.ST7701,
                "virt": Display.VIRT,
            }
            display_type = display_map.get(display_mode, Display.ST7701)
            Display.init(display_type, osd_num=1, to_ide=True)
            self.display_size = [Display.width(), Display.height()]

            self.sensor.set_framesize(
                w=self.display_size[0], h=self.display_size[1], chn=CAM_CHN_ID_0)
            self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)

        if enable_ai:
            ai_w = ALIGN_UP(ai_size[0], 16)
            self.sensor.set_framesize(w=ai_w, h=ai_size[1], chn=CAM_CHN_ID_2)
            self.sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)

        if enable_web:
            # 미검증: 채널 0/2와 동시에 채널 1을 RGB565로 여는 구성.
            self.sensor.set_framesize(
                w=web_size[0], h=web_size[1], chn=CAM_CHN_ID_1)
            self.sensor.set_pixformat(Sensor.RGB565, chn=CAM_CHN_ID_1)

        MediaManager.init()

        if enable_display:
            self.osd_img = image.Image(
                self.display_size[0], self.display_size[1], image.ARGB8888)
            bind_info = self.sensor.bind_info(x=0, y=0, chn=CAM_CHN_ID_0)
            Display.bind_layer(**bind_info, layer=Display.LAYER_VIDEO1)

        self.sensor.run()

    def get_ai_frame(self):
        frame = self.sensor.snapshot(chn=CAM_CHN_ID_2)
        return frame.to_numpy_ref()

    def get_web_frame(self):
        return self.sensor.snapshot(chn=CAM_CHN_ID_1)

    def refresh_osd(self):
        Display.show_image(self.osd_img, 0, 0, Display.LAYER_OSD3)

    def destroy(self):
        import os
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        if self.sensor is not None:
            try:
                self.sensor.stop()
            except Exception as e:
                log("sensor.stop() err %r" % (e,))
        if self._display_enabled:
            try:
                Display.deinit()
            except Exception as e:
                log("Display.deinit() err %r" % (e,))
        try:
            MediaManager.deinit()
        except Exception as e:
            log("MediaManager.deinit() err %r" % (e,))


# ============================================================
# 웹 세션 상태 (스트리밍 중인 클라이언트 하나만 유지 — 단순화)
# ============================================================

class WebState:
    def __init__(self):
        self.server = None
        self.active = None          # 현재 요청 처리 중인 ClientSession
        self.streaming = False      # /stream 멀티파트 모드인지
        self.last_frame_sent_ms = 0
        self.frame_interval_ms = 0  # 0이면 매 루프마다 보냄

    def start(self, port):
        self.server = web_server.HttpServer(port).start()
        log("web server listening on port %d" % port)

    def step(self, rig, hand_result):
        """메인 루프에서 매 프레임 한 번씩 호출. 블로킹하지 않는다."""
        if self.server is None:
            return

        if self.active is None:
            accepted = self.server.accept()
            if accepted is not None:
                sock, addr = accepted
                self.active = web_server.ClientSession(sock, addr)
                self.streaming = False

        session = self.active
        if session is None:
            return

        if session.is_stale():
            log("client %r stale, dropping" % (session.addr,))
            session.close()
            self.active = None
            self.streaming = False
            return

        try:
            if session.state == web_server.ClientSession.STATE_READING:
                path = session.pump_read()
                if path is None:
                    return
                self._route(rig, hand_result, session, path)

            if session.state == web_server.ClientSession.STATE_SENDING:
                done = session.pump_send()
                if done:
                    if self.streaming:
                        # 스트리밍 모드면 다음 프레임을 준비해야 하므로
                        # READING 대신 바로 다음 프레임 큐잉 대기 상태로 둔다.
                        session.state = "stream_wait_frame"
                    else:
                        session.close()
                        self.active = None

            elif session.state == "stream_wait_frame":
                if not FEATURE_WEB_VIDEO or not self.streaming:
                    session.close()
                    self.active = None
                    return
                jpeg, encode_ms = self._capture_web_jpeg(rig, hand_result)
                session.queue(web_server.mjpeg_part(jpeg))
        except (OSError, ValueError) as e:
            log("client %r error: %r" % (session.addr, e))
            session.close()
            self.active = None
            self.streaming = False

    def _capture_web_jpeg(self, rig, hand_result):
        img = rig.get_web_frame()
        if FEATURE_WEB_JOINTS and hand_result is not None:
            det, points = hand_result
            ui.draw_landmarks(img, det, points, AI_RGB888P_SIZE,
                               [WEB_FRAME_WIDTH, WEB_FRAME_HEIGHT])
        return video_stream.encode_jpeg(img, quality=WEB_JPEG_QUALITY)

    def _route(self, rig, hand_result, session, path):
        if path == "/health":
            body = (
                '{"status":"ok","hand_recognition":%s,"web_joints":%s}'
                % (str(FEATURE_HAND_RECOGNITION).lower(),
                   str(FEATURE_WEB_JOINTS).lower())
            ).encode()
            session.queue(web_server.http_response("200 OK", "application/json", body))
        elif path == "/snapshot" and FEATURE_WEB_VIDEO:
            jpeg, encode_ms = self._capture_web_jpeg(rig, hand_result)
            session.queue(web_server.http_response("200 OK", "image/jpeg", jpeg))
        elif path == "/stream" and FEATURE_WEB_VIDEO:
            self.streaming = True
            session.queue(web_server.MJPEG_STREAM_HEADER)
        else:
            body = (
                b"<!doctype html><html><head><meta charset='utf-8'>"
                b"<title>EdgeGlass-AI</title></head><body>"
                b"<h1>EdgeGlass-AI</h1>"
                b"<img src=\"/stream\" width=\"%d\" height=\"%d\">"
                b"</body></html>" % (WEB_FRAME_WIDTH, WEB_FRAME_HEIGHT)
            )
            session.queue(web_server.http_response("200 OK", "text/html; charset=utf-8", body))


def main():
    rig = CameraRig()
    gesture_controller = None
    mouse_controller = None
    tracker = None
    web_state = None

    try:
        rig.create(
            enable_display=FEATURE_DISPLAY_OSD,
            enable_ai=FEATURE_HAND_RECOGNITION,
            enable_web=FEATURE_WEB_SERVER and FEATURE_WEB_VIDEO,
            ai_size=AI_RGB888P_SIZE,
            web_size=[WEB_FRAME_WIDTH, WEB_FRAME_HEIGHT],
            display_mode=DISPLAY_MODE,
        )

        if FEATURE_HAND_RECOGNITION:
            hand_det_model = "/sdcard/examples/kmodel/hand_det.kmodel"
            hand_kp_model = "/sdcard/examples/kmodel/handkp_det.kmodel"
            tracker = HandTracker(hand_det_model, hand_kp_model, AI_RGB888P_SIZE)
            gesture_controller = GestureController(AI_RGB888P_SIZE)

        if FEATURE_MOUSE_CONTROL:
            mouse_controller = MouseController(AI_RGB888P_SIZE)

        if FEATURE_WEB_SERVER:
            web_state = WebState()
            web_state.start(WEB_PORT)

        log("EdgeGlass-AI orchestrator START")
        frame_count = 0
        last_action = None

        while True:
            frame_count += 1
            hand_result = None  # (det, points) — 웹/디스플레이가 같이 쓰는 캐시

            if FEATURE_HAND_RECOGNITION:
                ai_frame = rig.get_ai_frame()
                det, points, fallback = tracker.run(ai_frame)

                if FEATURE_DISPLAY_OSD:
                    rig.osd_img.clear()

                if det is None or points is None:
                    action = gesture_controller.no_hand() if gesture_controller else "STOP"
                    if mouse_controller is not None:
                        mouse_controller.update(action)
                    if FEATURE_DISPLAY_OSD:
                        rig.osd_img.draw_string_advanced(
                            30, 30, 40, "ACTION: " + action,
                            color=(255, 255, 0, 0))
                    if action != last_action:
                        log("ACTION: %s" % action)
                        last_action = action
                else:
                    hand_result = (det, points)
                    fist_now = is_fist(points)
                    info = gesture_controller.update(points, fist_now)
                    action = info["action"]
                    if mouse_controller is not None:
                        mouse_controller.update(action, info["x"], info["y"])
                    if FEATURE_DISPLAY_OSD:
                        ui.draw_landmarks(
                            rig.osd_img, det, points,
                            AI_RGB888P_SIZE, rig.display_size)

                if FEATURE_DISPLAY_OSD:
                    rig.refresh_osd()

            if web_state is not None:
                web_state.step(rig, hand_result)

            if frame_count % 30 == 0:
                gc.collect()

    except KeyboardInterrupt:
        log("stopped by user")
    except BaseException as error:
        sys.print_exception(error)
        raise
    finally:
        rig.destroy()
        log("cleanup done")


if __name__ == "__main__":
    main()
