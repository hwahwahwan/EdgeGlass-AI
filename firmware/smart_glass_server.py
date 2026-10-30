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
import json

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
import failure_backoff
import boot_stage

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
FEATURE_WEB_VIDEO = True          # /stream (WEB_SERVER 필요)
FEATURE_WEB_JOINTS = True         # 웹 영상에 관절 오버레이 (WEB_VIDEO+HAND_RECOGNITION 필요)

# Mac이 TCP 8060으로 GET /device-info 를 보내 이 식별 문자열을 확인하고
# (다른 장치의 응답은 무시), POST /register 로 자신의 UDP 포트를 알려주면
# 그 요청의 송신자 IP를 등록한다(RegisteredUdpTransport.register()) --
# config.MOUSE_UDP_USE_HTTP_REGISTRATION 참고. 암호화/인증이 아니라 다른
# 장치와 혼동하지 않기 위한 식별용 문자열이다.
BOARD_IDENTITY = "EDGEGLASS_BOARD"
USER_IDENTITY = "EDGEGLASS_USER"

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

# 부팅 단계 OLED 화면 하나당 최소 표시 시간(ms) -- display_config.py의
# MIN_STAGE_DISPLAY_MS와 같은 의도(firmware/boot_stage.py 참고). OLED
# 전용 상수 파일에 두지 않고 여기에 중복해 둔 이유: 이 값을 쓰는 코드
# (아래 _boot_stage_enter/_boot_stage_exit)가 display_config를 몰라도
#되게 하기 위함 -- OLED가 배포 안 된 SD카드에서도 이 파일 자체의 import는
# 깨지면 안 된다(기존 oled_device/display_ui try/except 가드와 같은 이유).
BOOT_MIN_STAGE_MS = 400

# Wi-Fi가 이만큼(ms) 연속으로 끊긴 상태면 OLED가 상태줄 경고 대신 전체화면
# "WIFI LOST" 알림으로 전환한다(docs/DEV_HISTORY.md 4-8 섹션 B의 상태
# 우선순위표: 지속적 장애는 전체화면, 일시적 장애는 상태줄).
WIFI_LOST_ALERT_MS = 5000

# 카메라 chn(2) snapshot()이 이 횟수만큼 연속으로 실패하면(docs/DEV_HISTORY.md
# 6-11, 실기기에서 RuntimeError("...failed(3)")로 재현됨) 더 이상 자동으로
# 재시도하지 않고 "이번 실행 동안 카메라/AI만 영구 비활성화"로 전환한다.
# 처음엔 이 한도 도달 시 메인 루프 전체를 break로 끝냈으나(2026-10-30
# 실기기에서 실제 재현, 섹션 6-11), 그러면 자체 오류가 없는 마우스(UART)/
# OLED까지 finally에서 같이 종료돼 다른 기능들의 "그 기능만 끄고 계속
# 돈다" 격리 정책과 불일치한다는 게 밝혀져(사용자 지적) 지금 방식으로
# 바꿨다 -- 무한정 조용히 프레임을 건너뛰며 "멈춘 것처럼 보이는" 상태로
# 남기지도 않고, 다른 무고한 기능까지 끌고 내려가지도 않는다. 10은 첫
# 추정치로, 일시적인 드라이버 hiccup 몇 번은 허용하면서도 진짜 복구
# 불가능한 상태를 오래 끌지 않도록 잡았다 -- 실기기 재발 패턴을 더 보면
# 조정 가능.
AI_FRAME_FAILURE_LIMIT = 10


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
# 부팅 단계 OLED 표시 / 런타임 OLED 표시 우선순위 헬퍼
# (docs/DEV_HISTORY.md 4-8 섹션 B/C)
# ============================================================

def _boot_stage_enter(oled_ui, stage_timer, lines):
    """부팅 단계 화면을 보여주고 최소 표시 시간 타이머를 시작한다.
    oled_ui가 None이어도(OLED 미배포/초기화 실패) 타이머는 그대로
    동작시킨다 -- 호출하는 쪽은 매 단계마다 _boot_stage_exit()과 항상
    짝을 맞춰 호출하면 되고, OLED 유무를 신경 쓸 필요가 없다."""
    stage_timer.enter()
    if oled_ui is not None:
        oled_ui.show_stage(lines)


def _boot_stage_exit(stage_timer):
    """바로 앞서 _boot_stage_enter()로 들어간 단계의 남은 최소 표시
    시간만큼만 대기한다(실제 초기화 작업이 이미 끝난 뒤에 호출되므로,
    작업 자체를 지연시키지 않는다 -- firmware/boot_stage.py 참고)."""
    stage_timer.wait_min()


def _update_oled(oled_ui, wifi_alert_active, landmarks, action, fps, warning):
    """메인 루프 두 분기(손 있음/없음)가 공유하는 단일 OLED 호출 지점.
    지속적 Wi-Fi 단절 중에는 정상 스켈레톤+상태줄 화면 대신 전체화면
    경고로 바꿔치기한다 -- 이 "누가 우선인가" 판단을 한 곳에만 둔다.
    카메라/AI가 영구 비활성화된 뒤에는(docs/DEV_HISTORY.md 6-11)
    main()이 이 함수를 더 이상 호출하지 않고 "CAMERA ERROR" 정적
    화면을 전환 시점에 한 번만 직접 그린다 -- 매 루프 다시 그릴
    내용이 없는 정적 화면이라, 여기서 매번 우선순위를 또 판단하게
    하지 않는다."""
    if oled_ui is None:
        return
    if wifi_alert_active:
        oled_ui.show_alert(("WIFI LOST", "RECONNECTING"))
    else:
        oled_ui.update(landmarks, action, fps=fps, warning=warning)


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
        self.enabled = False      # start()가 성공해야 True (bind 실패 시 False로 남음)
        self.start_error = None   # start() 실패 사유(repr) -- OLED/로그/REPL 재시작 판단용
        self._port = None
        # /stream의 MemoryError(JPEG 인코더 전용 버퍼 풀 고갈 가설,
        # docs/DEV_HISTORY.md 4-8) 전용 백오프 -- 일반 OSError/ValueError
        # (TCP 리셋/stall/deadline)는 세지 않는다. 연속 3회면 자동
        # 재시도를 멈춘다(무제한 재압축으로 상황을 악화시키지 않기 위함).
        self._video_backoff = failure_backoff.FailureBackoff(
            delays_ms=(5000, 10000), max_failures=3)

    def start(self, port):
        """bind/listen 실패(OSError)를 여기서 끝낸다 -- main()까지
        전파되지 않으므로 AI/마우스/OLED는 전혀 영향받지 않는다
        (docs/DEV_HISTORY.md 4-8 섹션 F)."""
        self._port = port
        try:
            self.server = web_server.HttpServer(port).start()
        except OSError as e:
            self.enabled = False
            self.start_error = repr(e)
            log("web server failed to start on port %d: %r "
                "(web disabled for this run -- AI/mouse/OLED unaffected)" % (port, e))
            return
        self.enabled = True
        self.start_error = None
        log("web server listening on port %d" % port)

    def restart(self, port=None):
        """수동 복구 경로 -- USB REPL에서 bind 실패 원인을 해결한 뒤
        직접 호출한다(docs/DEV_HISTORY.md 4-8 섹션 E). 이 객체 자신의
        TCP 리스닝 소켓만 다루며, 카메라/AI/마우스/OLED는 전혀
        건드리지 않는다. 별도 프로세스를 새로 띄우는 방식이 아니다
        (MicroPython 단일 실행 환경이라 그런 개념이 없음)."""
        if self.server is not None:
            self.server.close()
            self.server = None
        self.active = None
        self.streaming = False
        self.start(port if port is not None else self._port)
        return self.enabled

    def warning_code(self):
        """OLED 상태줄용 짧은 코드(DisplayUI.update()의 warning 인자,
        docs/DEV_HISTORY.md 4-8 섹션 B)."""
        if not self.enabled:
            return "WX"
        if self._video_backoff.exhausted():
            return "M!"
        if self._video_backoff.failure_count > 0:
            return "W!"
        return None

    def step(self, rig, hand_result, mouse_controller=None):
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
                self._route(rig, hand_result, session, path, mouse_controller)

            if session.state == web_server.ClientSession.STATE_SENDING:
                # 진행이 아예 없거나(stall), 조금씩만 나가서(trickle) stall
                # 기준은 계속 리셋되지만 전체 소요 시간이 데드라인을 넘긴
                # 경우를 잡아낸다 -- docs/DEV_HISTORY.md 6-10 참고. OSError를
                # 던지면 바로 아래 except에서 session.close()+self.active=None
                # 으로 정리되고, 다음 step() 호출에서 HttpServer.accept()가
                # 새 연결을 다시 받는다(리스닝 소켓은 세션과 독립적으로 계속
                # 살아있음 -- tests/test_web_server.py의 재연결 통합 테스트로
                # 확인함).
                session.check_send_timeout()
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
                self._video_backoff.record_success()
                self.last_frame_sent_ms = now_ms
                self._stream_frame_count += 1
                if self._stream_frame_count <= 3 or self._stream_frame_count % 10 == 0:
                    elapsed_ms = time.ticks_diff(time.ticks_ms(), self._stream_start_ms)
                    fps = (self._stream_frame_count * 1000.0 / elapsed_ms) if elapsed_ms > 0 else 0.0
                    debug_log("/stream frame=%d bytes=%d encode_ms=%d elapsed_ms=%d fps=%.1f mem_free=%d" % (
                        self._stream_frame_count, len(jpeg), encode_ms, elapsed_ms, fps, gc.mem_free()))
                session.queue(web_server.mjpeg_part(jpeg))
        except (OSError, ValueError, MemoryError) as e:
            if isinstance(e, MemoryError):
                # docs/DEV_HISTORY.md 4-8: img.compress() 내부의 K230 전용
                # 버퍼 풀(가설) 고갈. 일반 OSError/ValueError(TCP
                # 리셋/stall/deadline)는 이 백오프에 넣지 않는다 -- 그런
                # 것들은 네트워크 사정일 뿐 메모리 문제가 아니다.
                self._video_backoff.record_failure()
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
        """JPEG 인코딩 1회 시도 + (Compression Failed/MemoryError 각각)
        1회까지만 재시도 -- 무제한 재시도로 메모리 상황을 악화시키지
        않는다(docs/DEV_HISTORY.md 4-8 섹션 D "근본 원인 조사" 참고).

        MemoryError에 대한 gc.collect() 재시도는 "해결"이 아니라 비용이
        거의 없는(프레임당 최대 1회) 방어적 조치일 뿐이다 -- 발생 위치
        (img.compress(), K230 벤더 C 확장)로 볼 때 일반 Python 힙이
        아니라 이미지 인코더 전용 하드웨어 버퍼 풀 고갈일 가능성이 더
        높다는 가설이 있고(미확인, 외부 자료로 간접 뒷받침만 됨), 그
        경우 gc.collect()는 애초에 효과가 없다. mem_free() 전후
        비교는 VERBOSE_ORCHESTRATOR_LOGS를 켰을 때만 찍히며, 이 가설을
        실기기에서 검증할 최소 계측이다.
        """
        for attempt in range(2):
            img = rig.get_web_frame()
            if FEATURE_WEB_JOINTS and hand_result is not None:
                det, points = hand_result
                ui.draw_landmarks(img, det, points, AI_RGB888P_SIZE,
                                  [WEB_FRAME_WIDTH, WEB_FRAME_HEIGHT])
            mem_before = gc.mem_free()
            try:
                jpeg, encode_ms = video_stream.encode_jpeg(img, quality=WEB_JPEG_QUALITY)
                debug_log("jpeg encode ok mem_free_before=%d mem_free_after=%d" % (
                    mem_before, gc.mem_free()))
                return jpeg, encode_ms
            except OSError as e:
                if attempt != 0 or "Compression Failed" not in str(e):
                    raise
                log("JPEG compression failed once; retrying with a new frame")
                gc.collect()
            except MemoryError:
                debug_log("jpeg encode MemoryError mem_free_before=%d mem_free_after_gc=%d" % (
                    mem_before, gc.mem_free()))
                if attempt != 0:
                    raise
                log("JPEG MemoryError once; retrying once after gc.collect()")
                gc.collect()

    def _route(self, rig, hand_result, session, path, mouse_controller=None):
        if path == "/health":
            body = (
                '{"status":"ok","hand_recognition":%s,"web_joints":%s}'
                % (str(FEATURE_HAND_RECOGNITION).lower(),
                   str(FEATURE_WEB_JOINTS).lower())
            ).encode()
            session.queue(web_server.http_response("200 OK", "application/json", body))
        elif path == "/device-info" and session.method == "GET":
            body = (
                '{"identity":"%s","device":"K230D-Zero","service":"EdgeGlass-AI"}'
                % BOARD_IDENTITY
            ).encode()
            session.queue(web_server.http_response("200 OK", "application/json", body))
        elif path == "/register" and session.method == "POST":
            self._handle_register(session, mouse_controller)
        elif path == "/stream" and FEATURE_WEB_VIDEO:
            if not self._video_backoff.should_attempt():
                log("/stream rejected: web video backing off after repeated MemoryError")
                body = b'{"status":"EDGEGLASS_WEB_VIDEO_BACKOFF"}'
                session.queue(web_server.http_response(
                    "503 Service Unavailable", "application/json", body))
                return
            log("/stream start")
            self.streaming = True
            self._stream_frame_count = 0
            self._stream_start_ms = time.ticks_ms()
            session.queue(web_server.MJPEG_STREAM_HEADER)
        else:
            # 브라우저 쪽 자동 재연결 -- 서버의 TCP 전송 로직(web_server.py)과는
            # 완전히 분리된, 순수 클라이언트 JS다. 서버가 이제 정체된 전송을
            # 5초 안에 포기하므로(docs/DEV_HISTORY.md 6-10), 모든 정체는
            # 결국 이 <img>에 에러 이벤트로 나타난다 -- 그래서 "에러 없이
            # 조용히 멈추는" 경우를 따로 감지할 타이머는 필요 없다. 재연결은
            # 1초부터 지수 백오프(최대 8초)로, 중복 재연결은 retryTimer로
            # 막는다. healthyTimer는 onload(멀티파트 스트림에서 매 프레임마다
            # 확실히 불린다는 보장이 없어 믿지 않음)가 아니라 "에러 없이 N초
            # 지속"으로만 백오프를 리셋한다 -- Wi-Fi가 완전히 끊긴 경우는
            # 재시도마다 금방 또 실패해 백오프가 계속 늘어나고, 일시적
            # 정체였다면 한 번 복구된 뒤 자연히 리셋된다(서버 쪽 복구와는
            # 독립적으로 동작).
            body = (
                b"<!doctype html><html><head><meta charset='utf-8'>"
                b"<title>EdgeGlass-AI</title></head><body>"
                b"<h1>EdgeGlass-AI</h1>"
                b"<img id=\"stream\" src=\"/stream\" width=\"%d\" height=\"%d\">"
                b"<script>"
                b"(function(){"
                b"var img=document.getElementById('stream');"
                b"var retryTimer=null,healthyTimer=null,failures=0;"
                b"var MIN_MS=1000,MAX_MS=8000,HEALTHY_MS=5000;"
                b"function connect(){"
                b"retryTimer=null;"
                b"img.src='/stream?_='+Date.now();"
                b"clearTimeout(healthyTimer);"
                b"healthyTimer=setTimeout(function(){failures=0;},HEALTHY_MS);"
                b"}"
                b"function scheduleRetry(){"
                b"clearTimeout(healthyTimer);"
                b"if(retryTimer!==null)return;"
                b"var delay=Math.min(MAX_MS,MIN_MS*Math.pow(2,failures));"
                b"failures+=1;"
                b"retryTimer=setTimeout(connect,delay);"
                b"}"
                b"img.onerror=function(){img.removeAttribute('src');scheduleRetry();};"
                b"connect();"
                b"})();"
                b"</script>"
                b"</body></html>" % (WEB_FRAME_WIDTH, WEB_FRAME_HEIGHT)
            )
            session.queue(web_server.http_response("200 OK", "text/html; charset=utf-8", body))

    def _handle_register(self, session, mouse_controller):
        """POST /register -- Mac이 보낸 identity+udp_port를 확인하고, 유효하면
        요청의 실제 송신자 IP(session.addr[0])를 UDP 목적지로 등록한다.
        identity는 인증이 아니라 다른 장치와 혼동하지 않기 위한 식별용이다.

        이 핸들러 안에서 생기는 어떤 예외도(잘못된 JSON, 예상 밖의 타입 등)
        절대 밖으로 새어나가서는 안 된다 -- WebState.step()의
        except (OSError, ValueError)는 이걸 못 잡고, 그러면 main()까지
        올라가 카메라/AI/OLED 전체가 함께 죽는다. mouse_controller.transport
        .step()에 이미 쓰인 것과 같은 방어 패턴(실패해도 이 기능만 끈다).
        """
        valid = False
        try:
            payload = json.loads(session.body.decode()) if session.body else {}
            identity = payload.get("identity") if isinstance(payload, dict) else None
            udp_port = payload.get("udp_port") if isinstance(payload, dict) else None
            valid = (
                identity == USER_IDENTITY
                and isinstance(udp_port, int) and not isinstance(udp_port, bool)
                and 0 < udp_port < 65536
            )
            if valid:
                mac_ip = session.addr[0]
                if mouse_controller is not None and hasattr(mouse_controller.transport, "register"):
                    mouse_controller.transport.register(mac_ip, udp_port)
                else:
                    log("/register from %s:%d accepted but no registrable UDP "
                        "transport is active" % (mac_ip, udp_port))
        except Exception as error:
            log("/register handler error (ignored): %r" % (error,))
            valid = False

        if not valid:
            log("/register rejected from %r" % (session.addr,))
            body = ('{"identity":"%s","status":"EDGEGLASS_REJECTED"}' % BOARD_IDENTITY).encode()
            session.queue(web_server.http_response("400 Bad Request", "application/json", body))
            return
        body = ('{"identity":"%s","status":"EDGEGLASS_REGISTERED"}' % BOARD_IDENTITY).encode()
        session.queue(web_server.http_response("200 OK", "application/json", body))


def main(transport_kind=None, enable_web=None, oled=None, oled_ui=None):
    """Run the orchestrator loop.

    ``transport_kind`` ("uart"/"udp") and ``enable_web`` let a thin entry
    point (run_uart.py / run_wifi.py) pin the run profile explicitly,
    without editing config.py or the FEATURE_* constants above. Calling
    main() with no arguments (e.g. running this file directly) keeps the
    previous config.py-driven behavior.

    ``oled``/``oled_ui``: pass these in when the caller already brought the
    OLED up itself (tools/autorun/main.py does, so it can show boot-stage
    screens starting before the SAFE_MODE countdown -- docs/DEV_HISTORY.md
    4-8) instead of this function opening I2C a second time. If not given,
    this function brings the OLED up itself at the same point it always
    has, unchanged, for direct callers (run_uart.py/run_wifi.py).
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
    wifi_networks = []
    fatal_error = None
    stage_timer = boot_stage.BootStageTimer(BOOT_MIN_STAGE_MS)

    try:
        _boot_stage_enter(oled_ui, stage_timer, ("CAMERA", "INITIALIZING"))
        rig.create(
            enable_display=FEATURE_DISPLAY_OSD,
            enable_ai=FEATURE_HAND_RECOGNITION,
            enable_web=FEATURE_WEB_SERVER and FEATURE_WEB_VIDEO,
            ai_size=AI_RGB888P_SIZE,
            web_size=[WEB_FRAME_WIDTH, WEB_FRAME_HEIGHT],
            display_mode=DISPLAY_MODE,
        )
        _boot_stage_exit(stage_timer)

        if FEATURE_HAND_RECOGNITION:
            _boot_stage_enter(oled_ui, stage_timer, ("AI MODELS", "LOADING"))
            hand_det_model = "/sdcard/examples/kmodel/hand_det.kmodel"
            hand_kp_model = "/sdcard/examples/kmodel/handkp_det.kmodel"
            tracker = HandTracker(hand_det_model, hand_kp_model, AI_RGB888P_SIZE)
            gesture_controller = GestureController(AI_RGB888P_SIZE)
            _boot_stage_exit(stage_timer)

        if FEATURE_DISPLAY_OLED and oled is None:
            # Not pre-built by the caller -- bring it up here exactly as
            # before (unchanged path for run_uart.py/run_wifi.py, which
            # never show the earlier boot-stage screens anyway since they
            # skip tools/autorun/main.py's countdown entirely).
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
        elif FEATURE_DISPLAY_OLED and oled is not None and oled_ui is None:
            oled_ui = display_ui.DisplayUI(oled)

        ifconfig = None
        banner_lines = []

        _boot_stage_enter(oled_ui, stage_timer, ("WIFI", "CONNECTING"))
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
        elif oled_ui is not None:
            oled_ui.show_stage(("WIFI", "OFF"))
        _boot_stage_exit(stage_timer)

        _boot_stage_enter(oled_ui, stage_timer, ("MOUSE", "INITIALIZING"))
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
                        udp_use_http_registration=config.MOUSE_UDP_USE_HTTP_REGISTRATION,
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
                elif hasattr(mouse_controller.transport, "register"):
                    # RegisteredUdpTransport -- no scanning here; the Mac
                    # bridge finds this board over TCP (GET /device-info)
                    # and confirms it with POST /register.
                    def _on_mac_registered_http(peer, _log=banner_print):
                        _log("[UDP] Mac registered via HTTP: %s:%d" % (peer[0], peer[1]))
                        _log("[UDP] Mouse control ready")
                    mouse_controller.transport.on_registered = _on_mac_registered_http
                    banner_lines.append(
                        "[UDP] Waiting for Mac to register via HTTP (POST /register)...")
                elif mouse_transport_kind == "udp":
                    banner_lines.append(
                        "[UDP] Fixed target: %s:%s" % (config.MOUSE_UDP_HOST, config.MOUSE_UDP_PORT)
                    )
            elif oled_ui is not None:
                oled_ui.show_stage(("MOUSE", "DISABLED"))
        elif oled_ui is not None:
            oled_ui.show_stage(("MOUSE", "OFF"))
        _boot_stage_exit(stage_timer)

        _boot_stage_enter(oled_ui, stage_timer, ("WEB SERVER", "STARTING"))
        if FEATURE_WEB_SERVER:
            web_state = WebState()
            web_state.start(WEB_PORT)
            if web_state.enabled:
                banner_lines.append("[WEB] Server started")
                if ifconfig:
                    banner_lines.append("[WEB] URL: http://%s:%d/" % (ifconfig[0], WEB_PORT))
            else:
                banner_lines.append(
                    "[WEB] Server failed to start: %s "
                    "(web disabled for this run -- AI/mouse/OLED unaffected)"
                    % web_state.start_error)
                if oled_ui is not None:
                    oled_ui.show_stage(("WEB SERVER", "FAILED"))
        elif oled_ui is not None:
            oled_ui.show_stage(("WEB SERVER", "OFF"))
        _boot_stage_exit(stage_timer)

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

        _boot_stage_enter(oled_ui, stage_timer, ("SYSTEM READY",))
        _boot_stage_exit(stage_timer)

        log_mem("STEP: after all init, before loop")
        frame_count = 0
        last_action = None
        last_fps = None  # 30프레임마다만 갱신, OLED 상태줄에는 그 사이 마지막 값을 보여준다
        loop_start_ms = time.ticks_ms()
        wifi_backoff = failure_backoff.FailureBackoff(
            delays_ms=(3000, 10000, 30000), max_failures=None)
        wifi_was_connected = wlan.isconnected() if wlan is not None else None
        wifi_lost_since_ms = None
        wifi_alert_active = False
        # docs/DEV_HISTORY.md 6-11: sensor.snapshot(chn=CAM_CHN_ID_2)가
        # RuntimeError("sensor(0) snapshot chn(2) failed(3)")로 실패해
        # 전체 스크립트가 죽은 실기기 사례. 연속 실패만 센다(성공하면
        # 바로 0으로 리셋) -- 시간 기반 백오프가 아니라, "카메라가 아예
        # 복구 불가능해졌는지"를 판단하는 카운터다.
        ai_frame_failures = 0
        # True가 되면 다시는 rig.get_ai_frame()을 호출하지 않는다(무한
        # 재시도 방지). 능동 재초기화(MediaManager 재호출 등)는 과거
        # 보드가 물리 전원 재인가 없이는 안 풀리는 hang을 일으킨 전례가
        # 있어(docs/DEV_HISTORY.md) 시도하지 않는다 -- 이번 실행 동안은
        # 포기하고, 마우스(UART)/OLED/웹/Wi-Fi는 계속 살려둔다.
        camera_disabled = False

        while True:
            frame_count += 1
            hand_result = None  # (det, points) — 웹/디스플레이가 같이 쓰는 캐시
            ai_frame_fetch_failed = False

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

            if FEATURE_HAND_RECOGNITION and camera_disabled:
                # 영구 비활성화됨 -- rig.get_ai_frame()을 다시는 호출하지
                # 않는다. OLED의 "CAMERA ERROR" 화면은 비활성화 전환
                # 시점에 한 번만 그렸다(아래 참고) -- 내용이 바뀔 일이
                # 없는 정적 화면을 매 루프 다시 그리면(특히 카메라
                # 타임아웃이 없어져 루프가 훨씬 빨리 도는 지금 상태에서는)
                # OLED I2C 버스를 불필요하게 계속 두드리게 된다. OSD
                # (HDMI/LCD)도 이 블록에서 아예 안 그려 마지막 프레임에
                # 멈춘 채로 남는다 -- 카메라와 같은 Display 자원을
                # 공유해 완전히 분리할 수 없는 부분(이번 작업 범위 밖,
                # 보고서 참고). get_ai_frame()의 ~1000ms 타임아웃이
                # 더 이상 루프 속도를 눌러주지 않으므로, 마우스/웹
                # 응답성은 유지하면서도 CPU를 공회전시키지 않을 정도의
                # 짧은 대기를 둔다.
                time.sleep_ms(20)
            elif FEATURE_HAND_RECOGNITION:
                fetch_start_ms = time.ticks_ms()
                try:
                    ai_frame = rig.get_ai_frame()
                except (RuntimeError, OSError) as error:
                    # 카메라/센서 VI 드라이버 단계 실패 (docs/DEV_HISTORY.md
                    # 6-11) -- AI 추론(tracker.run)에는 아예 들어가지도
                    # 못한 상태. 이 프레임만 "손 없음"으로 처리하고 다음
                    # 루프에서 다시 시도한다 -- 전체를 죽이지 않는다.
                    ai_frame_fetch_failed = True
                    ai_frame_failures += 1
                    fetch_elapsed_ms = time.ticks_diff(time.ticks_ms(), fetch_start_ms)
                    # mem_free가 낮지 않다면(보통 그럴 것으로 예상) 일반
                    # Python 힙 고갈이 아니라는 뜻이다 -- MicroPython
                    # 힙이 부족했다면 이 예외 자체가 RuntimeError가 아니라
                    # MemoryError였을 것이다(간접 증거). 카메라 드라이버
                    # 쪽 버퍼/자원 상태를 직접 조회하는 API는 이 저장소
                    # 안에서 찾지 못했다 -- 지금 남길 수 있는 가장 직접적인
                    # 계측은 이 세 값(실패 연속 횟수/소요 시간/일반 힙
                    # 여유)뿐이다.
                    log("AI frame fetch failed (%d/%d consecutive): %r "
                        "fetch_ms=%d mem_free=%d" % (
                            ai_frame_failures, AI_FRAME_FAILURE_LIMIT, error,
                            fetch_elapsed_ms, gc.mem_free()))
                    det, points, fallback = None, None, None
                else:
                    ai_frame_failures = 0
                    det, points, fallback = tracker.run(ai_frame)

                if FEATURE_DISPLAY_OSD:
                    rig.osd_img.clear()

                if det is None or points is None:
                    action = gesture_controller.no_hand() if gesture_controller else "STOP"
                    if ai_frame_fetch_failed:
                        # 프레임 자체를 못 받아온 경우엔 gesture_controller의
                        # grace-period 유지 동작(예: 손이 잠깐 안 보여도
                        # DRAG를 몇 프레임 더 유지하는 로직)을 신뢰하지
                        # 않는다 -- 카메라가 복구될지 불확실한 상태에서
                        # 의도치 않은 이동/드래그가 계속되는 것을 막기
                        # 위해 무조건 STOP으로 덮어쓴다.
                        action = "STOP"
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
                        _update_oled(oled_ui, wifi_alert_active, None, action, last_fps,
                                     web_state.warning_code() if web_state is not None else None)
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
                        _update_oled(oled_ui, wifi_alert_active, oled_landmarks, action, last_fps,
                                     web_state.warning_code() if web_state is not None else None)

                if FEATURE_DISPLAY_OSD:
                    rig.refresh_osd()

                if ai_frame_fetch_failed and ai_frame_failures >= AI_FRAME_FAILURE_LIMIT:
                    # 더 재시도하지 않고 "카메라/AI만" 이번 실행 동안
                    # 영구 비활성화한다 -- while 루프 자체는 끝내지
                    # 않는다(이전에는 여기서 break -> finally가 마우스
                    # UART/OLED/카메라를 전부 같이 종료시켜, 자체 오류가
                    # 없는 기능까지 끌고 내려가는 문제가 있었음, 2026-10-30
                    # 실기기에서 확인, docs/DEV_HISTORY.md 6-11). 마우스는
                    # 이미 위에서 이번 프레임에 action="STOP"으로 갱신됐지만
                    # (DRAG 중이었다면 MouseController.update()가 내부적으로
                    # DRAG_END를 먼저 보냄), 확실히 하기 위해 한 번 더
                    # 명시적으로 STOP을 보낸다.
                    camera_disabled = True
                    log("AI frame fetch failed %d times in a row (limit %d) -- "
                        "disabling camera/AI for the rest of this run "
                        "(mouse/web/Wi-Fi/OLED keep running)" % (
                            ai_frame_failures, AI_FRAME_FAILURE_LIMIT))
                    if mouse_controller is not None:
                        mouse_controller.update("STOP")
                    if oled_ui is not None:
                        # 정적 화면이라 한 번만 그린다 -- Wi-Fi 경고보다
                        # 우선순위가 높아(_update_oled 참고) 이후
                        # wifi_alert_active가 바뀌어도 이 화면 위에
                        # 다시 그려지지 않는다.
                        oled_ui.show_alert(("CAMERA ERROR", "AI DISABLED"))

            if web_state is not None:
                web_state.step(rig, hand_result, mouse_controller)

            if frame_count % 30 == 0:
                gc.collect()
                elapsed_ms = time.ticks_diff(time.ticks_ms(), loop_start_ms)
                fps = (frame_count * 1000.0 / elapsed_ms) if elapsed_ms > 0 else 0.0
                last_fps = fps
                log_mem("main_loop frame=%d fps=%.1f" % (frame_count, fps))

                if camera_disabled and frame_count % 300 == 0:
                    # 저빈도 heartbeat -- 카메라/AI가 꺼진 뒤에도 메인
                    # 루프(마우스/웹/Wi-Fi)가 계속 살아있다는 걸 USB
                    # 로그로 확인할 수 있게 한다. 300프레임마다 한 번
                    # (frame_count % 30 == 0 블록 안에서 또 10번에 1번)
                    # 이라 매초 단위로 스팸이 되지 않는다.
                    log("heartbeat: main loop alive, camera/AI still "
                        "disabled since frame_count=%d" % frame_count)

                if wlan is not None:
                    # 부팅 시 1회만 연결하던 것과 달리, 런타임 중 끊김은
                    # 지금까지 아무도 감지하지 않고 있었다(docs/DEV_HISTORY.md
                    # 4-8). 기존 30프레임 주기를 재사용 -- 새 타이머를
                    # 따로 만들지 않는다. Wi-Fi는 bind 실패(웹서버)와
                    # 달리 "포기"하지 않고 계속 재시도한다(max_failures=None)
                    # -- 물리적으로 다시 붙을 가능성이 늘 있기 때문.
                    now_ms = time.ticks_ms()
                    wifi_connected = wlan.isconnected()
                    if wifi_connected:
                        if wifi_was_connected is False:
                            banner_print("[Wi-Fi] reconnected")
                        wifi_backoff.record_success()
                        wifi_lost_since_ms = None
                        wifi_alert_active = False
                    else:
                        if wifi_was_connected:
                            wifi_lost_since_ms = now_ms
                            banner_print("[Wi-Fi] connection lost, will retry in background")
                        if wifi_lost_since_ms is not None:
                            wifi_alert_active = (
                                time.ticks_diff(now_ms, wifi_lost_since_ms) > WIFI_LOST_ALERT_MS)
                        if wifi_backoff.should_attempt(now_ms):
                            wifi_backoff.record_failure(now_ms)
                            try:
                                wifi.connect_if_needed(wifi_networks, on_progress=banner_print)
                            except OSError as error:
                                banner_print("[Wi-Fi] reconnect attempt failed: %r" % (error,))
                    wifi_was_connected = wifi_connected

    except KeyboardInterrupt:
        log("stopped by user")
    except BaseException as error:
        fatal_error = error
        sys.print_exception(error)
        raise
    finally:
        # main.py already does this in its own finally block; smart_glass_server.py
        # was missing it, which could leave a DRAG held on the Mac side if this
        # script stops (IDE interrupt, exception, Ctrl-C) while mid-drag.
        if mouse_controller is not None:
            mouse_controller.close()
        if oled is not None:
            if fatal_error is not None and oled_ui is not None:
                # 치명적 크래시: 화면을 꺼지 않고 마지막 정보를 남겨둔다
                # (docs/DEV_HISTORY.md 4-8 섹션 C). 사용자의 의도적 중단
                # (KeyboardInterrupt)이나 정상 종료는 여기 안 들어오므로
                # 기존 poweroff 동작이 그대로 유지된다. 전체 Traceback은
                # 이미 위 sys.print_exception()으로 USB 로그(별도
                # mac/serial_logger.py)에 남고, OLED에는 요약만 둔다.
                oled_ui.show_fatal_error((
                    "FATAL",
                    type(fatal_error).__name__[:16],
                    str(fatal_error)[:16],
                ))
            else:
                oled_device.close_display(oled)
        rig.destroy()
        log("cleanup done")


if __name__ == "__main__":
    main()
