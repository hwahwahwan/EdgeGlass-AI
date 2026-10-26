"""EdgeGlass-AI 통합 오케스트레이터.

기존 main.py는 그대로 둔다 (손 추적 단독 실행용). 이 파일은 같은 AI
추론 결과를 손 추적/마우스 제어(main.py와 동일), 디스플레이 OSD 표시,
웹 MJPEG 스트리밍, VLT-OL016 OLED 손 관절 스켈레톤 표시 네 곳에서
공유하는 통합 진입점이다. OLED 경로(FEATURE_DISPLAY_OLED)는 display/의
독립 모듈(oled_device/display_ui, 평탄화 배포)을 그대로 가져다 쓰며,
display/examples/*_demo.py의 더미 합성 데이터가 아니라 매 프레임
hand_tracker.py가 낸 실제 21개 관절 좌표를 그대로 넘긴다(docs/DEV_HISTORY.md
4-3 "실제 AI 추론 루프 연결 방법 분석" 참고). 2026-10-26 기준: OLED
자체의 I2C bring-up/화면 출력은 실기기로 검증됐지만, 이 통합 경로
(hand_tracker -> smart_glass_server.py -> DisplayUI)는 아직 실기기 검증
전이다.

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

from media.sensor import Sensor
from media.display import Display
from media.media import *  # noqa: F401,F403  (MediaManager, CAM_CHN_ID_*, ALIGN_UP)

# IMPORTANT: import sys/gc/time/image AFTER the media.media wildcard import,
# not before. main.py does the same (see its import order). media.media's
# namespace rebinds the name `sys` as a side effect of `import *`, so
# `import sys` placed earlier gets silently shadowed and `sys.path` breaks
# with "AttributeError: 'module' object has no attribute 'path'" (observed
# on real hardware 2026-10-21, fixed by reordering to match main.py).
import sys
import gc
import time
import image

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from hand_tracker import HandTracker
from gesture_controller import GestureController, is_fist, is_one
from mouse_controller import MouseController
import config
import transport
import wifi
import ui
import web_server
import video_stream

# OLED(VLT-OL016) 손 관절 스켈레톤 표시 -- display/의 독립 모듈(평탄화
# 배포, docs/DEV_HISTORY.md 4-3 참고). 모듈이 이 run에 배포되지 않았거나
# import가 실패해도(예: display/ 없이 firmware/만 올린 구버전 SD카드)
# 오케스트레이터 전체가 죽어서는 안 되므로 가드한다 -- FEATURE_DISPLAY_OLED
# 가 켜져 있어도 이 import가 실패하면 OLED만 조용히 비활성화된다.
try:
    import oled_device
    import display_ui
except ImportError:
    oled_device = None
    display_ui = None


# ============================================================
# 기능별 ON/OFF (필요한 처리/메모리 할당까지 끈다)
# ============================================================

FEATURE_HAND_RECOGNITION = True   # hand_det+handkp_det 추론
FEATURE_MOUSE_CONTROL = True      # UART2 @MOUSE 송신 (HAND_RECOGNITION 필요)
FEATURE_DISPLAY_OSD = True        # 기존 HDMI/LCD에 관절 오버레이
FEATURE_DISPLAY_OLED = True        # VLT-OL016 I2C OLED에 손 관절 스켈레톤 표시
                                    # (OSD와는 별개의 물리 디스플레이 -- 동시에 켤 수 있다.
                                    # oled_device/display_ui가 배포 안 됐거나 open_display()가
                                    # 실패하면(패널 미연결 등) 자동으로 비활성화되며 크래시하지 않는다.)
# 2026-10-21 1단계(채널0+2, 웹 OFF) 실기기 검증 성공, 재검증(270+프레임,
# FPS~20, 메모리 안정)도 완료. 2단계 재시도: 이번엔 핫스팟을 켠 상태에서
# 진행한다(이전 시도는 핫스팟이 꺼진 상태였고, 그것이 원인이었는지가
# 이번 재시도의 핵심 확인 사항이다). tools/DEPLOY.md §11 참고.
FEATURE_WEB_SERVER = True         # HTTP 서버 자체
FEATURE_WEB_VIDEO = True          # /snapshot, /stream (WEB_SERVER 필요)
FEATURE_WEB_JOINTS = True         # 웹 영상에 관절 오버레이 (WEB_VIDEO+HAND_RECOGNITION 필요)

WEB_PORT = 8060
WEB_FRAME_WIDTH = 640
WEB_FRAME_HEIGHT = 480
WEB_JPEG_QUALITY = 50
# Minimum ms between /stream MJPEG frames. Real-hardware finding 2026-10-23
# (docs/WORK_TRACKER.md): encode_jpeg() (img.compress()) runs synchronously
# in the same single-threaded loop as hand_det/handkp_det inference and
# gesture_controller.update(); baseline AI-only frame time on this board is
# already ~90-95ms, and a JPEG encode (worse yet on the frequent
# "Compression Failed" retry path) adds enough extra, irregular delay to
# this shared loop to push many frames past gesture_controller.py's
# wall-clock confirm windows (click_confirm_ms=90, fist_confirm_ms=180),
# which real production logs showed correlating with spurious CLICK
# triggers. Throttling how often a new frame is even encoded -- instead of
# every loop iteration the network can keep up with -- directly reduces how
# often the AI loop takes that hit, without touching any gesture-recognition
# code. (This was already a planned WebState.frame_interval_ms field; it
# was simply never wired up to anything -- see WebState below.)
WEB_STREAM_MIN_INTERVAL_MS = 200

AI_RGB888P_SIZE = [640, 360]
DISPLAY_MODE = "auto"


def log(msg):
    print("[ORCH]", msg)


def banner_print(msg):
    """No "[ORCH]" prefix -- this is the clean status block the terminal
    output requirement asks for, meant to stay readable next to the
    existing [ORCH]-prefixed diagnostics rather than replace them."""
    print(msg)


def debug_log(msg):
    """STEP:/mem_free/FPS-style noise; silenced by default (config.VERBOSE_ORCHESTRATOR_LOGS)
    so the Wi-Fi/WEB/UDP status banner stays the thing actually visible on
    the CanMV IDE terminal."""
    if config.VERBOSE_ORCHESTRATOR_LOGS:
        log(msg)


def log_mem(label):
    debug_log("%s mem_free=%d" % (label, gc.mem_free()))


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

        debug_log("STEP: Sensor() construct")
        self.sensor = Sensor()
        debug_log("STEP: sensor.reset()")
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
            debug_log("STEP: Display.init()")
            Display.init(display_type, osd_num=1, to_ide=True)
            self.display_size = [Display.width(), Display.height()]
            debug_log("STEP: Display.init() done, size=%r" % (self.display_size,))

            debug_log("STEP: sensor chn0 framesize/pixformat")
            self.sensor.set_framesize(
                w=self.display_size[0], h=self.display_size[1], chn=CAM_CHN_ID_0)
            self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)
            debug_log("STEP: sensor chn0 done")

        if enable_ai:
            debug_log("STEP: sensor chn2 framesize/pixformat")
            ai_w = ALIGN_UP(ai_size[0], 16)
            self.sensor.set_framesize(w=ai_w, h=ai_size[1], chn=CAM_CHN_ID_2)
            self.sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)
            debug_log("STEP: sensor chn2 done")

        if enable_web:
            # 미검증: 채널 0/2와 동시에 채널 1을 RGB565로 여는 구성.
            log_mem("STEP: before sensor chn1 (web)")
            debug_log("STEP: sensor chn1 framesize/pixformat (web, unverified)")
            self.sensor.set_framesize(
                w=web_size[0], h=web_size[1], chn=CAM_CHN_ID_1)
            self.sensor.set_pixformat(Sensor.RGB565, chn=CAM_CHN_ID_1)
            log_mem("STEP: sensor chn1 done")

        # IMPORTANT (found 2026-10-21 on real hardware): MediaManager.init()
        # is documented as deprecated (media/media.pyi: "Deprecated media
        # manager initializer"). libs/PipeLine.py (main.py's proven working
        # path) never calls it when using Display.init() - Display.init()
        # appears to bring up the media subsystem itself. Calling the
        # deprecated MediaManager.init() in addition to Display.init() hung
        # the board indefinitely (observed: board became unresponsive after
        # the chn0 setup log line, required a physical power cycle to
        # recover). experiments/wifi_test/mjpeg_stream_test.py, which never
        # calls Display.init(), DOES need MediaManager.init() and that
        # combination works. So: only call it when Display is not in use.
        if not enable_display:
            debug_log("STEP: MediaManager.init() (no Display in use)")
            MediaManager.init()
            debug_log("STEP: MediaManager.init() done")
        else:
            debug_log("STEP: skipping MediaManager.init() (Display.init() already handles it)")

        if enable_display:
            debug_log("STEP: osd_img create")
            self.osd_img = image.Image(
                self.display_size[0], self.display_size[1], image.ARGB8888)
            debug_log("STEP: bind_info/bind_layer")
            bind_info = self.sensor.bind_info(x=0, y=0, chn=CAM_CHN_ID_0)
            Display.bind_layer(**bind_info, layer=Display.LAYER_VIDEO1)
            debug_log("STEP: bind_layer done")

        debug_log("STEP: sensor.run()")
        self.sensor.run()
        log_mem("STEP: sensor.run() done")

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
        else:
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
        self.frame_interval_ms = WEB_STREAM_MIN_INTERVAL_MS  # 0이면 매 루프마다 보냄
        self._stream_frame_count = 0
        self._stream_start_ms = 0

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
                now_ms = time.ticks_ms()
                if (self.frame_interval_ms > 0
                        and time.ticks_diff(now_ms, self.last_frame_sent_ms) < self.frame_interval_ms):
                    # Not time for the next MJPEG frame yet. Skip the JPEG
                    # encode this loop iteration (state stays
                    # "stream_wait_frame") so the AI/gesture loop gets
                    # uninterrupted frames in between -- see
                    # WEB_STREAM_MIN_INTERVAL_MS above for why this matters.
                    return
                jpeg, encode_ms = self._capture_web_jpeg(rig, hand_result)
                self.last_frame_sent_ms = now_ms
                self._stream_frame_count += 1
                if self._stream_frame_count <= 3 or self._stream_frame_count % 10 == 0:
                    elapsed_ms = time.ticks_diff(time.ticks_ms(), self._stream_start_ms)
                    fps = (self._stream_frame_count * 1000.0 / elapsed_ms) if elapsed_ms > 0 else 0.0
                    debug_log("/stream frame=%d bytes=%d encode_ms=%d elapsed_ms=%d fps=%.1f mem_free=%d" % (
                        self._stream_frame_count, len(jpeg), encode_ms, elapsed_ms, fps, gc.mem_free()))
                session.queue(web_server.mjpeg_part(jpeg))
        except (OSError, ValueError) as e:
            if self.streaming:
                elapsed_ms = time.ticks_diff(time.ticks_ms(), self._stream_start_ms)
                log("/stream ended frames=%d elapsed_ms=%d err=%r" % (
                    self._stream_frame_count, elapsed_ms, e))
            else:
                log("client %r error: %r" % (session.addr, e))
            session.close()
            self.active = None
            self.streaming = False

    def _capture_web_jpeg(self, rig, hand_result):
        for attempt in range(2):
            img = rig.get_web_frame()
            if FEATURE_WEB_JOINTS and hand_result is not None:
                det, points = hand_result
                ui.draw_landmarks(img, det, points, AI_RGB888P_SIZE,
                                  [WEB_FRAME_WIDTH, WEB_FRAME_HEIGHT])
            try:
                return video_stream.encode_jpeg(img, quality=WEB_JPEG_QUALITY)
            except OSError as e:
                if attempt != 0 or "Compression Failed" not in str(e):
                    raise
                log("JPEG compression failed once; retrying with a new frame")
                gc.collect()

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
            debug_log("/snapshot bytes=%d encode_ms=%d request_to_ready_ms=%d" % (
                len(jpeg), encode_ms,
                time.ticks_diff(time.ticks_ms(), session.created_ms)))
            session.queue(web_server.http_response("200 OK", "image/jpeg", jpeg))
        elif path == "/stream" and FEATURE_WEB_VIDEO:
            log("/stream start")
            self.streaming = True
            self._stream_frame_count = 0
            self._stream_start_ms = time.ticks_ms()
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


def main(transport_kind=None, enable_web=None):
    """Run the orchestrator loop.

    ``transport_kind`` ("uart"/"udp") and ``enable_web`` let a thin entry
    point (run_uart.py / run_wifi.py) pin the run profile explicitly,
    without editing config.py or the FEATURE_* constants above. Calling
    main() with no arguments (e.g. running this file directly) keeps the
    previous config.py-driven behavior.
    """
    global FEATURE_WEB_SERVER
    if enable_web is not None:
        FEATURE_WEB_SERVER = enable_web
    mouse_transport_kind = transport_kind or config.MOUSE_TRANSPORT

    rig = CameraRig()
    gesture_controller = None
    mouse_controller = None
    tracker = None
    web_state = None
    wlan = None
    oled = None
    oled_ui = None

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

        if FEATURE_DISPLAY_OLED:
            if oled_device is not None and display_ui is not None:
                oled = oled_device.open_display()
                if oled is not None:
                    oled_ui = display_ui.DisplayUI(oled)
                else:
                    log("OLED open_display() returned None -- OLED display disabled "
                        "for this run (see [OLED] log above for the reason)")
            else:
                log("OLED modules (oled_device/display_ui) not deployed -- "
                    "OLED display disabled for this run")

        ifconfig = None
        banner_lines = []

        if transport.wifi_is_needed(FEATURE_WEB_SERVER, FEATURE_MOUSE_CONTROL, mouse_transport_kind):
            # One shared STA connection for both the web server and the UDP
            # mouse transport. wifi.connect_if_needed() reuses an already
            # connected link as-is (e.g. the other feature connected first,
            # or a prior connect survived a soft reboot) instead of forcing
            # a second connect -- see firmware/wifi.py. Home Wi-Fi is tried
            # first, phone hotspot as fallback (firmware/wifi_credentials.py).
            try:
                import wifi_credentials
                wifi_networks = [
                    (getattr(wifi_credentials, "HOME_SSID", None),
                     getattr(wifi_credentials, "HOME_PASSWORD", None)),
                    (getattr(wifi_credentials, "HOTSPOT_SSID", None),
                     getattr(wifi_credentials, "HOTSPOT_PASSWORD", None)),
                ]
            except ImportError:
                wifi_networks = []
            try:
                wlan, ifconfig, connected_ssid = wifi.connect_if_needed(
                    wifi_networks,
                    on_progress=lambda msg: banner_print("[Wi-Fi] " + msg),
                )
            except OSError as error:
                banner_print("[Wi-Fi] Connection failed: %s" % (error,))
                raise
            debug_log("WLAN ready ifconfig=%r ssid=%r" % (ifconfig, connected_ssid))
            banner_lines.append("[Wi-Fi] Connected" + (
                " (%s)" % connected_ssid if connected_ssid else ""
            ))
            banner_lines.append("[Wi-Fi] Board IP: %s" % ifconfig[0])

        if FEATURE_MOUSE_CONTROL:
            # A UDP/discovery setup failure (e.g. subnet too large, no NIC
            # yet) must not take camera/AI/web down with it -- it only means
            # this run has no mouse control. See docs/WORK_TRACKER.md
            # 2026-10-23 real-hardware diagnostic entry.
            try:
                mouse_controller = MouseController(
                    AI_RGB888P_SIZE,
                    transport=transport.create_transport(
                        mouse_transport_kind,
                        udp_host=config.MOUSE_UDP_HOST,
                        udp_port=config.MOUSE_UDP_PORT,
                        udp_retry_attempts=config.MOUSE_UDP_RETRY_ATTEMPTS,
                        udp_retry_delay_ms=config.MOUSE_UDP_RETRY_DELAY_MS,
                        udp_auto_discover=config.MOUSE_UDP_AUTO_DISCOVER,
                        udp_discovery_ip=ifconfig[0] if ifconfig else None,
                        udp_discovery_netmask=ifconfig[1] if ifconfig else None,
                        udp_max_scan_hosts=config.MOUSE_UDP_MAX_SCAN_HOSTS,
                    ),
                )
            except (OSError, ValueError) as error:
                banner_print("[MOUSE] transport setup failed, mouse control disabled: %s" % (error,))
                mouse_controller = None

            if mouse_controller is not None:
                udp_registry = getattr(mouse_controller.transport, "registry", None)
                if udp_registry is not None:
                    def _on_mac_registered(peer, _log=banner_print):
                        _log("[UDP] Mac registered: %s:%d" % (peer[0], peer[1]))
                        _log("[UDP] Mouse control ready")
                    udp_registry.on_registered = _on_mac_registered
                    banner_lines.append("[UDP] Waiting for Mac registration...")
                elif mouse_transport_kind == "udp":
                    banner_lines.append(
                        "[UDP] Fixed target: %s:%s" % (config.MOUSE_UDP_HOST, config.MOUSE_UDP_PORT)
                    )

        if FEATURE_WEB_SERVER:
            web_state = WebState()
            web_state.start(WEB_PORT)
            banner_lines.append("[WEB] Server started")
            if ifconfig:
                banner_lines.append("[WEB] URL: http://%s:%d/" % (ifconfig[0], WEB_PORT))

        if FEATURE_HAND_RECOGNITION:
            banner_lines.append("[AI] Gesture tracking started")

        if FEATURE_DISPLAY_OLED:
            banner_lines.append(
                "[OLED] display ready" if oled_ui is not None
                else "[OLED] not available (disabled for this run)"
            )

        banner_print("========== EdgeGlass-AI ==========")
        for line in banner_lines:
            banner_print(line)
        banner_print("==================================")

        log_mem("STEP: after all init, before loop")
        frame_count = 0
        last_action = None
        last_fps = None  # 30프레임마다만 갱신, OLED 상태줄에는 그 사이 마지막 값을 보여준다
        loop_start_ms = time.ticks_ms()

        while True:
            frame_count += 1
            hand_result = None  # (det, points) — 웹/디스플레이가 같이 쓰는 캐시

            # Non-blocking: drains at most one pending reply and sends at
            # most one probe burst, so a Mac that hasn't registered yet (or
            # never will) cannot stall the inference loop.
            if mouse_controller is not None and hasattr(mouse_controller.transport, "step"):
                try:
                    mouse_controller.transport.step()
                except Exception as error:
                    # A transport-layer bug (e.g. the discovery ACK decode
                    # TypeError found on real hardware 2026-10-23) must not
                    # take camera/AI/web down with it -- disable stepping
                    # from here on instead of crashing the whole loop.
                    sys.print_exception(error)
                    banner_print(
                        "[UDP] transport.step() failed, disabling further "
                        "UDP discovery for this run: %s" % (error,)
                    )
                    mouse_controller.transport.step = lambda now_ms=None: None

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
                    if oled_ui is not None:
                        # landmarks=None -- hand_renderer.layout_skeleton()
                        # treats this as "no hand" and draws nothing but the
                        # status bar (canvas.fill(0) runs first every call),
                        # so no stale skeleton from a previous frame lingers.
                        oled_ui.update(None, action, fps=last_fps)
                    if action != last_action:
                        log("ACTION: %s" % action)
                        last_action = action
                else:
                    hand_result = (det, points)
                    fist_now = is_fist(points)
                    one_now = is_one(points)
                    info = gesture_controller.update(points, fist_now, one_now)
                    action = info["action"]
                    if mouse_controller is not None:
                        mouse_controller.update(action, info["x"], info["y"])
                    if FEATURE_DISPLAY_OSD:
                        ui.draw_landmarks(
                            rig.osd_img, det, points,
                            AI_RGB888P_SIZE, rig.display_size)
                    if oled_ui is not None:
                        # points is a flat [x0,y0,x1,y1,...,x20,y20] array
                        # (see hand_tracker.py's HandKeypoint.postprocess());
                        # hand_renderer expects 21 (x,y) pairs.
                        oled_landmarks = [(points[i * 2], points[i * 2 + 1]) for i in range(21)]
                        oled_ui.update(oled_landmarks, action, fps=last_fps)

                if FEATURE_DISPLAY_OSD:
                    rig.refresh_osd()

            if web_state is not None:
                web_state.step(rig, hand_result)

            if frame_count % 30 == 0:
                gc.collect()
                elapsed_ms = time.ticks_diff(time.ticks_ms(), loop_start_ms)
                fps = (frame_count * 1000.0 / elapsed_ms) if elapsed_ms > 0 else 0.0
                last_fps = fps
                log_mem("main_loop frame=%d fps=%.1f" % (frame_count, fps))

    except KeyboardInterrupt:
        log("stopped by user")
    except BaseException as error:
        sys.print_exception(error)
        raise
    finally:
        # main.py already does this in its own finally block; smart_glass_server.py
        # was missing it, which could leave a DRAG held on the Mac side if this
        # script stops (IDE interrupt, exception, Ctrl-C) while mid-drag.
        if mouse_controller is not None:
            mouse_controller.close()
        if oled is not None:
            oled_device.close_display(oled)
        rig.destroy()
        log("cleanup done")


if __name__ == "__main__":
    main()
