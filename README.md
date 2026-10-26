# EdgeGlass-AI

K230D-Zero가 카메라 영상에서 손을 인식해 `MOVE` / `CLICK` / `DRAG` / `STOP`
제스처를 판별하고, Mac의 실제 마우스를 제어하는 Smart Glass 프로젝트입니다. 손 인식,
제스처 판정, 포인터 smoothing은 모두 K230에서 수행합니다. Mac의
`mac/mac_mouse_bridge.py`는 K230 결과를 macOS CoreGraphics mouse event로 변환합니다.
손 관절 21개는 보드에 연결된 VLT-OL016 OLED에도 실시간으로 표시됩니다
(`firmware/display_ui.py` 등, `docs/DEV_HISTORY.md` 4-3 참고). 보드는 USB
케이블의 UART2로 유선 제어하거나, Wi-Fi(UDP 자동 탐색)로 무선 제어할 수 있고,
전원만 연결해도 자동으로 카메라+AI+OLED+Wi-Fi+웹서버가 켜지는 자동부팅도
지원합니다(`tools/autorun/README.md` 참고).

## 통신 구조

```text
K230
├─ USB CDC → /dev/cu.usbmodem0010000001 → VS Code CanMV / Preview
├─ UART2 → CH342K → /dev/cu.usbmodem58930597043
│                                     └→ mac_mouse_bridge.py → macOS mouse
└─ Wi-Fi(UDP, 자동 탐색) ─────────────────────────┐
                                                   └→ mac_mouse_bridge.py(--transport udp) → macOS mouse
```

`001`과 `043`은 서로 다른 통신 경로이므로 VS Code CanMV/Preview와
`mac/mac_mouse_bridge.py`를 동시에 실행할 수 있습니다. `041`
(`/dev/cu.usbmodem58930597041`)은 현재 mouse transport에 사용하지 않습니다.
UART/Wi-Fi 중 어느 쪽을 쓸지는 보드에서 실행하는 진입점
(`run_uart.py`/`run_wifi.py`/`run_uart_web.py`, 아래 "파일 역할" 참고)으로
고르며, 둘 다 실기기로 검증돼 있습니다.

## 제스처

- `MOVE`: 검지 위치로 커서 이동
- `CLICK`: 엄지와 검지 pinch
- `DRAG`: 주먹(FIST)
- `STOP`: 손이 감지되지 않음

## 최초 1회: Mac 설치

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 평소 실행

실행 방법은 두 가지입니다 — 손 추적만 필요하면 1-A, OLED/웹서버/Wi-Fi까지
전부 쓰려면 1-B를 고릅니다. 전원만 연결해도 자동으로 켜지게 하려면 "자동부팅"
절을 참고합니다.

### 1-A. 손 추적 단독 실행 (`main.py`, 가장 단순한 경로)

1. VS Code에서 CanMV Board를 `/dev/cu.usbmodem0010000001`에 연결합니다.
2. 보드의 실제 프로젝트 파일은 `/sdcard/smart_glass/main.py`입니다 (로컬 `firmware/main.py`를 그대로 올린 것).
3. VS Code CanMV에서 현재 프로젝트의 `firmware/main.py`를 실행합니다.

`main.py`는 손 인식, gesture, Preview/UI와 UART2 mouse transport만 시작합니다
— OLED·웹서버·Wi-Fi는 켜지지 않습니다. VS Code는 `001` 연결을 계속 유지합니다.

### 1-B. 통합 실행 (`smart_glass_server.py` — 카메라+AI+OLED(+웹+Wi-Fi))

손 추적/마우스 제어에 OLED 손 관절 표시, 웹 스트리밍, 무선(Wi-Fi/UDP) 마우스
제어까지 더한 통합 오케스트레이터입니다. 아래 세 진입점 중 하나를 VS Code
CanMV에서 그대로 실행하면 됩니다(모두 `/sdcard/smart_glass/`에 배포돼 있어야
함, "파일 역할" 참고):

| 진입점 | 마우스 전송 | 웹서버 | 용도 |
|---|---|---|---|
| `firmware/run_uart.py` | UART2(케이블) | 꺼짐 | Wi-Fi 없이 케이블로만, 가장 단순 |
| `firmware/run_wifi.py` | UDP(무선, 자동 탐색) | 켜짐 | 무선 마우스 제어 + 웹 영상 |
| `firmware/run_uart_web.py` | UART2(케이블) | 켜짐 | 마우스는 유선, 웹 영상만 추가로 보고 싶을 때 |

셋 다 OLED에 손 관절 21개와 하단 상태(MOVE/CLICK/DRAG/STOP, FPS)를 실시간으로
표시합니다. 자세한 시연 순서는 `시연용_README.md` 참고.

### 1-C. 자동부팅 — 전원만 연결해도 자동 실행

`tools/autorun/`의 `boot.py`/`main.py`를 `/sdcard/boot.py`/`/sdcard/main.py`에
배포해두면, USB 데이터선 없이 전원만 연결해도 `run_wifi.py`와 같은 구성
(카메라+AI+OLED+Wi-Fi+UDP 마우스+웹서버)이 몇 초 뒤 자동으로 실행됩니다.
복구 방법(USB로 끼어들어 취소, `/sdcard/SAFE_MODE` 플래그 파일)과 자세한 동작은
`tools/autorun/README.md` 참고.

### 2. Mac mouse bridge 실행

별도의 macOS Terminal을 열고, 1단계에서 고른 실행 방식에 맞는 명령을
실행합니다.

**UART(케이블, `main.py`/`run_uart.py`/`run_uart_web.py`를 실행했다면)**
```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
source .venv/bin/activate
python mac/mac_mouse_bridge.py --port /dev/cu.usbmodem58930597043 --baud 115200
```
`043`은 실제 보드에서 K230 UART2 송신 포트로 검증된 경로입니다. 기본 실행에서는
포트를 다시 찾을 필요가 없습니다.

**UDP(무선, `run_wifi.py`를 실행했거나 자동부팅 중이라면)**
```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
source .venv/bin/activate
python mac/mac_mouse_bridge.py --transport udp --udp-port 9000
```
아이폰 핫스팟처럼 호스트 수가 적은 네트워크에서는 보드가 자동으로 Mac을
찾아 `@HELLO/@ACK`로 등록합니다(`[UDP] Mac registered: ...`가 뜨면 성공).
자세한 내용은 `시연용_README.md`의 "Wi-Fi(UDP) 시연" 참고.

### 3. macOS Accessibility 권한

실제 커서 제어를 위해 `mac/mac_mouse_bridge.py`를 실행하는 Terminal/iTerm/VS Code 등의
앱에 Accessibility 권한이 필요합니다. **System Settings → Privacy & Security →
Accessibility**에서 해당 앱을 켠 뒤 bridge를 다시 실행하세요.

## 문제 해결과 확인

연결 상태가 달라졌거나 장치를 점검해야 할 때만 후보 포트를 확인합니다.

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
source .venv/bin/activate
python mac/mac_mouse_bridge.py --list
```

OS mouse event 없이 bridge의 메시지 파싱과 MOVE/CLICK/DRAG/STOP dispatch를 확인하려면:

```bash
python mac/mac_mouse_bridge.py --self-test
```

`001`은 VS Code CanMV 전용입니다. bridge에 `001`을 지정하지 마세요. Bridge가
`043`을 열 수 없다면 다른 프로그램이 해당 UART2 포트를 점유하고 있는지, USB 케이블과
CH342K 장치가 연결되어 있는지 확인하세요.

## 종료

K230 `main.py` 또는 Mac bridge 터미널에서 `Ctrl-C`를 누르면 종료합니다. K230과
bridge는 종료 시 드래그 중이었다면 mouse-up을 보내 버튼이 눌린 상태로 남지 않게 합니다.

## 파일 역할

보드(MicroPython)에서 실행되는 코드는 `firmware/`에, Mac 전용 코드는 `mac/`에
있습니다. 둘 다 로컬 디렉터리 구분일 뿐 보드에는 영향이 없습니다 — 배포 시
`firmware/*.py`는 평탄화되어 보드의 `/sdcard/smart_glass/*.py`에 그대로
올라가고, 보드에서는 지금까지와 똑같이 flat import(`from hand_tracker import
HandTracker`)로 동작합니다. 자세한 로컬→보드 경로 매핑은 `tools/DEPLOY.md` 참고.

- `firmware/main.py`: K230에서 카메라, AI, UI 및 모듈을 실행하는 기존 단독
  진입점(손 추적 전용).
- `firmware/hand_tracker.py`: 손 검출과 키포인트 추론을 담당합니다.
- `firmware/gesture_controller.py`: 제스처 판정과 포인터 smoothing을 담당합니다.
- `firmware/mouse_controller.py`: 계산된 action/좌표를 UART2 `@MOUSE|...`
  메시지로 전송합니다.
- `firmware/ui.py`: 손 관절/박스 드로잉(`draw_landmarks`)과 디스플레이 OSD
  래퍼(`draw_hand`).
- `firmware/smart_glass_server.py`: 손 추적(main.py와 동일 로직) + 디스플레이
  OSD + OLED 손 관절 표시 + 웹 MJPEG 스트리밍을 하나의 AI 추론 결과로 공유하는
  통합 오케스트레이터. 기능별 ON/OFF는 파일 상단의 `FEATURE_*` 상수로
  제어합니다. **손 추적+마우스 제어(UART/UDP 둘 다)+디스플레이 OSD+OLED+
  웹서버까지 전부 실기기 검증 완료**(2026-10-26, `docs/DEV_HISTORY.md` 4-3).
  `run_uart.py`/`run_wifi.py`/`run_uart_web.py` 중 하나로 실행 프로필(마우스
  전송 방식, 웹서버 on/off)을 고릅니다.
- `firmware/run_uart.py` / `run_wifi.py` / `run_uart_web.py`: `smart_glass_server.main()`을
  각각 다른 인자(`transport_kind`, `enable_web`)로 호출하는 얇은 진입점 —
  위 "평소 실행" 1-B 표 참고.
- `firmware/transport.py`: UART2(`UartTransport`)와 Wi-Fi UDP(`UdpTransport`/
  자동 탐색하는 `AutoDiscoverUdpTransport`) 전송 구현.
- `firmware/wifi.py`: 집 Wi-Fi를 먼저 시도하고 실패하면 핫스팟으로 넘어가는
  연결 로직.
- `firmware/discovery.py`: UDP `@HELLO/@ACK` 핸드셰이크로 보드가 서브넷에서
  Mac을 자동으로 찾는 로직.
- `firmware/display_config.py`, `ssd1306.py`, `oled_device.py`,
  `hand_renderer.py`, `display_ui.py`: VLT-OL016 OLED에 손 관절 21개와 하단
  상태 텍스트를 그리는 모듈들(원래 `display/`에서 독립 개발된 뒤 실기기
  연동 시 `firmware/`로 통합됨, `docs/DEV_HISTORY.md` 4-3 참고). PC 전용
  테스트는 `display/tests/`·`display/examples/`에 남아 있습니다(아래
  "display/" 참고).
- `firmware/web_server.py`: 논블로킹 HTTP 연결 처리(소켓/accept/요청 파싱).
- `firmware/video_stream.py`: RGB565 프레임을 JPEG으로 인코딩.
- `firmware/config.py`: `smart_glass_server.py`가 실제로 import해서 쓰는
  설정 모듈 — UART/UDP 마우스 전송 방식 기본값(`MOUSE_TRANSPORT`), UDP
  포트/자동 탐색 여부(`MOUSE_UDP_*`), 로그 상세도(`VERBOSE_ORCHESTRATOR_LOGS`)
  등. `main.py`(손 추적 단독)는 이 파일을 참조하지 않습니다.
- `firmware/smart_glass.py`: 2026-10 첫 커밋 이후 갱신되지 않은 초기 버전으로
  보이며, 현재 다른 파일에서 import되지 않습니다. 실제 사용 여부가 불명확해
  삭제하지 않고 남겨뒀습니다.
- `mac/mac_mouse_bridge.py`: UART2 또는 UDP 메시지를 macOS CoreGraphics
  mouse event로 변환합니다(`--transport uart`/`udp`).
- `experiments/wifi_test/`: Wi-Fi/TCP/HTTP/MJPEG 단독 실기기 테스트 코드와
  `WIFI_TEST_REPORT.md`(진단 과정 전체 기록). 보드 배포 절차는 `tools/DEPLOY.md` 참고.
- `tools/DEPLOY.md`: 보드 배포·검증 절차.
- `tools/autorun/`: 전원만 연결해도 자동 실행되게 하는 `boot.py`/`main.py`
  (`/sdcard/boot.py`/`/sdcard/main.py`에 배포) — 자세한 내용과 복구 방법은
  `tools/autorun/README.md` 참고.
- `display/`: OLED 기능의 PC 전용 테스트 하네스(단위 테스트, 가상 화면 PNG
  데모) — 실제 구현은 위 `firmware/display_*`/`oled_device.py`/`ssd1306.py`/
  `hand_renderer.py`에 있고 `display/`는 그걸 하드웨어 없이 테스트합니다.
  자세한 내용은 `display/README.md` 참고.
- `tests/`: Mac에서 실행하는 unittest. `firmware/`, `mac/`를 sys.path에
  추가해 flat import로 대상 모듈을 불러옵니다.
