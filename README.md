# EdgeGlass-AI

K230D-Zero가 카메라 영상에서 손을 인식해 `MOVE` / `CLICK` / `DRAG` / `STOP`
제스처를 판별하고, Mac의 실제 마우스를 제어하는 Smart Glass 프로젝트입니다. 손 인식,
제스처 판정, 포인터 smoothing은 모두 K230에서 수행합니다. Mac의
`mac/mac_mouse_bridge.py`는 K230 결과를 macOS CoreGraphics mouse event로 변환합니다.

## 통신 구조

```text
K230
├─ USB CDC → /dev/cu.usbmodem0010000001 → VS Code CanMV / Preview
└─ UART2 → CH342K → /dev/cu.usbmodem58930597043
                                      └→ mac_mouse_bridge.py → macOS mouse
```

`001`과 `043`은 서로 다른 통신 경로이므로 VS Code CanMV/Preview와
`mac/mac_mouse_bridge.py`를 동시에 실행할 수 있습니다. `041`
(`/dev/cu.usbmodem58930597041`)은 현재 mouse transport에 사용하지 않습니다.

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

### 1. K230 실행 및 Preview

1. VS Code에서 CanMV Board를 `/dev/cu.usbmodem0010000001`에 연결합니다.
2. 보드의 실제 프로젝트 파일은 `/sdcard/smart_glass/main.py`입니다 (로컬 `firmware/main.py`를 그대로 올린 것).
3. VS Code CanMV에서 현재 프로젝트의 `firmware/main.py`를 실행합니다.

`main.py`는 손 인식, gesture, Preview/UI와 UART2 mouse transport를 함께 시작합니다.
VS Code는 `001` 연결을 계속 유지합니다.

### 2. Mac mouse bridge 실행

별도의 macOS Terminal을 열고 아래 명령을 그대로 실행합니다.

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
source .venv/bin/activate
python mac/mac_mouse_bridge.py --port /dev/cu.usbmodem58930597043 --baud 115200
```

`043`은 실제 보드에서 K230 UART2 송신 포트로 검증된 경로입니다. 기본 실행에서는
포트를 다시 찾을 필요가 없습니다.

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
  OSD + 웹 MJPEG 스트리밍을 하나의 AI 추론 결과로 공유하는 통합 오케스트레이터.
  기능별 ON/OFF는 파일 상단의 `FEATURE_*` 상수로 제어합니다. **보드 미검증** —
  자세한 내용은 파일 상단 주석과 `experiments/wifi_test/WIFI_TEST_REPORT.md` 참고.
- `firmware/web_server.py`: 논블로킹 HTTP 연결 처리(소켓/accept/요청 파싱).
- `firmware/video_stream.py`: RGB565 프레임을 JPEG으로 인코딩.
- `firmware/config.py`: 어디서도 import되지 않는 placeholder. 실행 설정은
  각 파일(`main.py`, `smart_glass_server.py`) 상단에 둡니다.
- `firmware/smart_glass.py`: 2026-10 첫 커밋 이후 갱신되지 않은 초기 버전으로
  보이며, 현재 다른 파일에서 import되지 않습니다. 실제 사용 여부가 불명확해
  삭제하지 않고 남겨뒀습니다.
- `mac/mac_mouse_bridge.py`: UART2 메시지를 macOS CoreGraphics mouse event로
  변환합니다.
- `experiments/wifi_test/`: Wi-Fi/TCP/HTTP/MJPEG 단독 실기기 테스트 코드와
  `WIFI_TEST_REPORT.md`(진단 과정 전체 기록). 보드 배포 절차는 `tools/DEPLOY.md` 참고.
- `tools/DEPLOY.md`: 보드 배포·검증 절차.
- `tests/`: Mac에서 실행하는 unittest. `firmware/`, `mac/`를 sys.path에
  추가해 flat import로 대상 모듈을 불러옵니다.
