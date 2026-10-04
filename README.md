# EdgeGlass-AI

K230D-Zero가 카메라 영상에서 손을 인식하고 `MOVE` / `CLICK` / `DRAG` / `STOP`
제스처를 판별하는 Smart Glass 프로젝트입니다. 제스처와 포인터 좌표는 K230에서
계산한 뒤 USB Serial로 Mac에 전송하며, Mac의 `mac_mouse_bridge.py`가 이를 받아
실제 macOS 마우스 이벤트를 발생시킵니다.

## 구성

- `main.py`: K230에서 카메라, AI 추론, UI 및 각 모듈을 실행합니다.
- `hand_tracker.py`: 손 검출과 키포인트 추론을 담당합니다.
- `gesture_controller.py`: MOVE / CLICK / DRAG / STOP 판정과 포인터 smoothing을 담당합니다.
- `mouse_controller.py`: 이미 계산된 action과 좌표를 `@MOUSE|...` USB Serial 메시지로 전송합니다.
- `mac_mouse_bridge.py`: Mac에서 serial 메시지를 CoreGraphics mouse event로 변환합니다.

## Mac 초기 설정

프로젝트 폴더에서 한 번만 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 이후 실행할 때

새 터미널을 열 때마다 가상환경을 활성화합니다.

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI
source .venv/bin/activate
```

### K230 serial 포트 확인

```bash
python mac_mouse_bridge.py --list
```

표시된 `/dev/cu.usbmodem*` 포트 중 실제 CanMV 출력이 나오는 포트를 선택합니다.
포트 번호는 Mac과 USB 연결 상태마다 달라질 수 있으므로 하드코딩하지 말고 항상
`--list`로 확인한 뒤 사용하세요. VS Code CanMV extension이 같은 endpoint를 열고
있으면 bridge가 접근할 수 없으므로, 해당 포트에서는 IDE 연결을 끊어야 합니다.

### Mac mouse bridge 실행

예를 들어 확인한 포트가 아래와 같다면 다음을 실행합니다.

```bash
python mac_mouse_bridge.py --port /dev/cu.usbmodem00100000001
```

K230에서는 기존처럼 `main.py`를 실행합니다. K230의 `main.py`는 AI·제스처·UI와
serial 메시지 출력을 담당하고, Mac의 `mac_mouse_bridge.py`는 메시지를 받아 실제
커서 이동, 클릭, 드래그 및 mouse-up만 담당합니다.

## macOS Accessibility 권한

실제 마우스 제어를 위해 bridge를 실행하는 터미널 앱(또는 해당 Python 실행 앱)에
Accessibility 권한이 필요합니다. **System Settings → Privacy & Security →
Accessibility**에서 사용 중인 Terminal/iTerm/VS Code 등을 켜고, 권한 변경 뒤
bridge를 다시 실행하세요.

## 종료

K230 `main.py` 또는 Mac bridge 터미널에서 `Ctrl-C`를 누르면 종료합니다. Bridge는
종료 시 드래그 중이었다면 mouse-up을 보내 버튼이 눌린 상태로 남지 않게 합니다.
