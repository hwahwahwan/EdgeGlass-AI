# EdgeGlass-AI Project Status

## 프로젝트 목표

- K230D Zero + CanMV 기반 온디바이스 스마트글래스 에어마우스.
- 카메라 손 랜드마크로 MOVE, CLICK, DRAG, STOP을 판정하고 UART2를 거쳐 Mac 마우스를 제어한다.
- 손의 카메라 내 절대 위치와 PC 커서 위치를 분리하고, 시야 재조정 뒤에도 현재 커서 위치에서 조작을 이어간다.

## 현재 구조

- 보드 실행 경로: `/sdcard/smart_glass/main.py`. 로컬 `main.py`가 Pipeline, 루프, Preview 및 모듈 연결을 담당한다. 실제 SD 파일과 현재 로컬 HEAD의 동기화 여부는 미확인.
- `hand_tracker.py`: 검출, crop, keypoint 추론, 2프레임 bbox fallback. `HandKeypoint.postprocess()`가 640×360 카메라 좌표계의 21개 랜드마크를 만든다.
- `gesture_controller.py`: 검지 tip(landmark 8)의 프레임 간 원시 좌표 delta로 MOVE 커서를 계산한다. 기존 적응형 EMA는 제스처 anchor에 유지한다. MOVE 설정: `POINTER_DELTA_GAIN=1.0`, `POINTER_DEAD_ZONE=2`. DRAG 설정: `DRAG_PALM_ALPHA=0.45`, `DRAG_DEAD_ZONE=3`.
- `mouse_controller.py`: 640×360 커서 좌표를 0..1로 정규화 및 clamp하고 UART2 115200 baud로 `@MOUSE|...` 전송. `mac_mouse_bridge.py`가 macOS 주 화면 크기로 변환하여 CoreGraphics 이벤트를 발생시킨다.
- 통신: CanMV USB CDC `/dev/cu.usbmodem0010000001`, UART2 bridge `/dev/cu.usbmodem58930597043`. 카메라 입력 640×360, Preview는 `display_mode="auto"`.
- `config.py`는 현재 실행 설정을 제공하지 않으며, 모델 경로와 디스플레이 설정은 `main.py`에 있다.

## 현재 구현 상태

- 손 검출, 랜드마크, OPEN 및 MOVE 표시는 실제 보드에서 사용자 확인됨. CLICK/FIST/DRAG는 기존 상태 머신이 있다.
- 최근 커밋 `2c5ee3d`에서 도입한 고정 중립점 대비 속도 적분이 회귀 원인이어서, 이번 로컬 수정에서 MOVE만 프레임 간 delta로 바꿨다. DRAG의 palm EMA 및 제스처 판정 기준은 유지했다.
- 현재 미커밋 사용자 변경: `main.py`의 `sys.path.append(PROJECT_DIR)` → `sys.path.insert(0, PROJECT_DIR)`. 유지할 것.
- 사용자가 로컬 MOVE 수정과 테스트를 승인했다. 로컬 `gesture_controller.py` 및 `tests/test_gesture_controller.py` 수정 완료. 보드 업로드는 별도 확인 전 금지.

## 현재 문제

- 실제 보드에서 하단 clamp 및 비자연스러운 MOVE가 재현됐다(사용자 보고). 원인은 고정 중립점과 손의 차이를 정지 중에도 매 프레임 적분한 것. 현재 로컬 delta 수정의 실제 보드 사용감은 미검증이다.
- UI의 `X/Y`는 원시 손 좌표가 아니라 계산된 커서 결과다. 로컬 수정은 초기 커서를 640×360 범위의 중앙에 두고, 재획득 시 마지막 커서 위치를 유지한다. 앱을 새로 시작할 때 Mac의 기존 커서 위치를 알 수 없어 최초 MOVE가 중앙으로 맞춰질 수 있다.
- 손 landmark만으로 머리/카메라 이동과 손 이동을 구별할 수 없다. 이번 단계에서는 해결하지 않았다.

## 결정 사항

- MOVE는 원시 검지 tip의 프레임 간 delta를 1:1 누적한다. 축별 2픽셀 이하 변위는 보류하고 기준점에 누적하므로 느린 의도적 이동은 추후 반영된다. 좌표 EMA를 MOVE에 쓰지 않아 정지 후 잔여 추종을 피한다.
- 손 랜드마크만으로는 손 전체의 화면 내 translation이 손 움직임인지 머리/카메라 움직임인지 완전히 구별할 수 없다. 시야 재조정 중 포인터 고정을 보장하려면 명시적 clutch/일시정지 또는 별도 카메라 motion 정보가 필요하다. 기존 fist=DRAG와 pinch=CLICK을 새 clutch에 재사용하지 않는다.
- CLICK/FIST/DRAG 판정 시간과 상태 머신은 유지했다. CLICK anchor 및 FIST/DRAG 중에는 MOVE 기준점을 재설정하고, DRAG 출력 좌표를 내부 커서와 맞춘다. DRAG 출력은 화면 범위로 clamp해 UI와 UART 출력 좌표를 일치시킨다.

## 테스트 결과

- 로컬 정적 추적: `hand_tracker` → `gesture_controller` → `mouse_controller` → UART2 → Mac bridge 경로 확인. `git diff --check` 통과.
- 로컬 회귀 테스트 6개 통과: 최초 손 절대 위치 무관, 정지 1,000프레임 드리프트 0, 좌/우/상/하 및 반전, 작은 noise와 느린 이동, 짧은/긴 손 유실 뒤 재획득, CLICK anchor 및 DRAG 종료 좌표 일치, 경계 clamp 뒤 즉시 반전. `git diff --check` 통과.
- 실제 K230D: 이전 속도 방식의 회귀는 사용자 재현. 이번 delta 수정은 아직 업로드·실기 테스트하지 않았다.

## 다음 작업

1. 로컬 결과를 사용자에게 보고하고 보드 업로드 확인을 기다린다.
2. 확인 후 보드 파일과 로컬 파일을 비교하고 `gesture_controller.py`만 동기화한다. 실기에서 정지·반전·재획득·CLICK/DRAG 및 Mac 커서 사용감을 확인한다.
3. 머리 이동 보정은 이번 변경에 포함하지 않는다. 순수 delta 실기 평가 후 별도 결정한다.

## 주의사항

- 보드의 `/sdcard` 파일을 로컬 HEAD와 같다고 가정하지 않는다. 업로드 전 파일별 차이를 확인한다. SD 삭제·포맷·초기화 금지.
- 원본 `/Users/yonghwan/Desktop/Smart_Glass/smart_glass.py`는 수정하지 않는다.
- 기존 사용자 변경을 덮어쓰지 않는다. AI/gesture 수치나 상태 머신을 증상 완화를 위해 임의 변경하지 않는다.
- 다음 세션 시작 시 이 문서를 먼저 읽고, 실제 코드 및 `git status`/`git diff`와 대조한다. 의미 있는 변경·테스트·문제 발견 시 갱신하고 오래된 세부 기록은 정리한다.
