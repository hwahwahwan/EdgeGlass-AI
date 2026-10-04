# EdgeGlass-AI

K230D-Zero가 카메라 영상에서 손을 인식해 `MOVE` / `CLICK` / `DRAG` / `STOP`
제스처를 판별하고, Mac의 실제 마우스를 제어하는 Smart Glass 프로젝트입니다. 손 인식,
제스처 판정, 포인터 smoothing은 모두 K230에서 수행합니다. Mac의
`mac_mouse_bridge.py`는 K230 결과를 macOS CoreGraphics mouse event로 변환합니다.

## 통신 구조

```text
K230
├─ USB CDC → /dev/cu.usbmodem0010000001 → VS Code CanMV / Preview
└─ UART2 → CH342K → /dev/cu.usbmodem58930597043
                                      └→ mac_mouse_bridge.py → macOS mouse
```

`001`과 `043`은 서로 다른 통신 경로이므로 VS Code CanMV/Preview와
`mac_mouse_bridge.py`를 동시에 실행할 수 있습니다. `041`
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
2. 보드의 실제 프로젝트 파일은 `/sdcard/smart_glass/main.py`입니다.
3. VS Code CanMV에서 현재 프로젝트의 `main.py`를 실행합니다.

`main.py`는 손 인식, gesture, Preview/UI와 UART2 mouse transport를 함께 시작합니다.
VS Code는 `001` 연결을 계속 유지합니다.

### 2. Mac mouse bridge 실행

별도의 macOS Terminal을 열고 아래 명령을 그대로 실행합니다.

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
source .venv/bin/activate
python mac_mouse_bridge.py --port /dev/cu.usbmodem58930597043 --baud 115200
```

`043`은 실제 보드에서 K230 UART2 송신 포트로 검증된 경로입니다. 기본 실행에서는
포트를 다시 찾을 필요가 없습니다.

### 3. macOS Accessibility 권한

실제 커서 제어를 위해 `mac_mouse_bridge.py`를 실행하는 Terminal/iTerm/VS Code 등의
앱에 Accessibility 권한이 필요합니다. **System Settings → Privacy & Security →
Accessibility**에서 해당 앱을 켠 뒤 bridge를 다시 실행하세요.

## 문제 해결과 확인

연결 상태가 달라졌거나 장치를 점검해야 할 때만 후보 포트를 확인합니다.

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
source .venv/bin/activate
python mac_mouse_bridge.py --list
```

OS mouse event 없이 bridge의 메시지 파싱과 MOVE/CLICK/DRAG/STOP dispatch를 확인하려면:

```bash
python mac_mouse_bridge.py --self-test
```

`001`은 VS Code CanMV 전용입니다. bridge에 `001`을 지정하지 마세요. Bridge가
`043`을 열 수 없다면 다른 프로그램이 해당 UART2 포트를 점유하고 있는지, USB 케이블과
CH342K 장치가 연결되어 있는지 확인하세요.

## 종료

K230 `main.py` 또는 Mac bridge 터미널에서 `Ctrl-C`를 누르면 종료합니다. K230과
bridge는 종료 시 드래그 중이었다면 mouse-up을 보내 버튼이 눌린 상태로 남지 않게 합니다.

## 파일 역할

- `main.py`: K230에서 카메라, AI, UI 및 모듈을 실행합니다.
- `hand_tracker.py`: 손 검출과 키포인트 추론을 담당합니다.
- `gesture_controller.py`: 제스처 판정과 포인터 smoothing을 담당합니다.
- `mouse_controller.py`: 계산된 action/좌표를 UART2 `@MOUSE|...` 메시지로 전송합니다.
- `mac_mouse_bridge.py`: UART2 메시지를 macOS CoreGraphics mouse event로 변환합니다.
