# EdgeGlass-AI Project Status

## 프로젝트 목표

- K230D Zero + CanMV 기반 온디바이스 스마트글래스 에어마우스.
- 카메라 손 랜드마크로 MOVE, CLICK, DRAG, STOP을 판정하고 UART2를 거쳐 Mac 마우스를 제어한다.
- 손의 카메라 내 절대 위치와 PC 커서 위치를 분리하고, 시야 재조정 뒤에도 현재 커서 위치에서 조작을 이어간다.

## 현재 구조

- 보드 실행 경로: `/sdcard/smart_glass/main.py`. 로컬 `main.py`가 Pipeline, 루프, Preview 및 모듈 연결을 담당한다. 실제 SD 파일과 현재 로컬 HEAD의 동기화 여부는 미확인.
- `hand_tracker.py`: 검출, crop, keypoint 추론, 2프레임 bbox fallback. `HandKeypoint.postprocess()`가 640×360 카메라 좌표계의 21개 랜드마크를 만든다.
- `gesture_controller.py`: 검지 tip(landmark 8)의 x/y 두 값만 One Euro 필터로 평활화한 뒤 2D 안정 기준점 바깥의 초과 이동량을 MOVE 커서에 누적한다. 기존 adaptive alpha EMA는 CLICK/FIST anchor에 유지한다. 초기 로컬 설정: `POINTER_MIN_CUTOFF=1.0 Hz`, `POINTER_BETA=0.05`, `POINTER_D_CUTOFF=1.0 Hz`, `POINTER_DEAD_ZONE=5.0 px`, `POINTER_DELTA_GAIN=1.0`. DRAG 설정은 유지했다.
- `mouse_controller.py`: 640×360 커서 좌표를 0..1로 정규화 및 clamp하고 UART2 115200 baud로 `@MOUSE|...` 전송. `mac_mouse_bridge.py`가 macOS 주 화면 크기로 변환하여 CoreGraphics 이벤트를 발생시킨다.
- 통신: CanMV USB CDC `/dev/cu.usbmodem0010000001`, UART2 bridge `/dev/cu.usbmodem58930597043`. 카메라 입력 640×360, Preview는 `display_mode="auto"`.
- `config.py`는 현재 실행 설정을 제공하지 않으며, 모델 경로와 디스플레이 설정은 `main.py`에 있다.

## 현재 구현 상태

- 손 검출, 랜드마크, OPEN 및 MOVE 표시는 실제 보드에서 사용자 확인됨. CLICK/FIST/DRAG는 기존 상태 머신이 있다.
- 최근 커밋 `2c5ee3d`에서 도입한 고정 중립점 대비 속도 적분이 회귀 원인이어서, 이번 로컬 수정에서 MOVE만 프레임 간 delta로 바꿨다. DRAG의 palm EMA 및 제스처 판정 기준은 유지했다.
- 현재 미커밋 사용자 변경: `main.py`의 `sys.path.append(PROJECT_DIR)` → `sys.path.insert(0, PROJECT_DIR)`. 유지할 것.
- raw delta를 올린 실제 보드에서 정지 커서 떨림과 CLICK/DRAG 사용감 저하를 사용자 보고로 확인했다. One Euro + 안정 기준점 버전은 로컬 수정 및 테스트를 완료했으나 실제 보드 파일과 동기화 여부는 이번 분석에서 확인하지 않았다. 보드 업로드는 별도 확인 전 금지.

## 현재 문제

- 이전 고정 중립점 속도 방식의 하단 clamp 원인은 정지 중에도 offset을 적분한 것이다. 이후 raw frame delta 방식은 원시 검지 landmark의 ±3~5 px 노이즈가 2 px 축별 문턱을 넘어 커서 왕복 이동으로 전송되어 실제 보드에서 심한 jitter가 났다. Mac 화면 정규화 변환이 그 움직임을 더 크게 보이게 할 수 있다.
- 현재 One Euro 버전은 정지 노이즈를 로컬에서 크게 줄였지만 실제 보드 사용감은 미검증이다. 빠른 이동 직후 필터가 남은 이동을 반영하는 짧은 tail이 있다. 로컬 40 px step/33 ms 사례에서 첫 프레임 23 px 반응 후 정지 중 추가 11 px 이동했다. 무리한 즉시 reset은 실제 이동량을 버리므로 적용하지 않았다. 보드 평가의 주요 확인 항목이다.
- CLICK/DRAG 체감 악화가 인식 오류인지 커서 흔들림 때문인지는 보드의 action 로그가 없어 미확정. 제스처 판정 입력과 시간 기준은 변경하지 않았다.
- 사용자 추가 실측: Preview 빨간 점이 검지 tip에서 벗어나 엄지 쪽을 따르는 것처럼 보인다. 원인은 thumb/index 배열 인덱스 혼동이 아니라 UI가 mouse용 `info["x/y"]`를 그대로 그리는 연결이다. 예전 `info["x/y"]`는 평활화한 검지 tip이었지만 상대 MOVE에서는 독립된 누적 커서 좌표다. `ui.py`와 `hand_tracker.py` 자체는 이전 안정 Git 버전과 차이가 없다. 실제 보드에 올라간 gesture_controller 버전은 이번 분석에서 읽지 않았으므로 미확인.
- UI의 `X/Y`는 원시 손 좌표가 아니라 계산된 커서 결과다. 로컬 수정은 초기 커서를 640×360 범위의 중앙에 두고, 재획득 시 마지막 커서 위치를 유지한다. 앱을 새로 시작할 때 Mac의 기존 커서 위치를 알 수 없어 최초 MOVE가 중앙으로 맞춰질 수 있다.
- 손 landmark만으로 머리/카메라 이동과 손 이동을 구별할 수 없다. 이번 단계에서는 해결하지 않았다.

## 결정 사항

- MOVE는 원시 검지 tip의 frame delta를 직접 사용하지 않는다. One Euro는 `time.ticks_ms()/ticks_diff()`의 실제 dt로 alpha를 구하고 x/y 필터만 수행한다. 필터링 좌표가 움직이지 않는 2D 안정 기준점에서 5 px 반경을 넘으면 초과 거리만 커서에 보내며 기준점도 그만큼 이동한다. 따라서 느린 누적 이동은 통과하고 고정 중립점 속도 적분은 없다.
- 파라미터는 MediaPipe 값 복사 없이 CHI 2012의 beta=0 → beta 증가 절차와 640×360 px, 20~33 ms 합성 입력을 사용해 임시 선정했다. 실제 FPS/노이즈 측정 후 보드에서 재튜닝해야 한다.
- 손 랜드마크만으로는 손 전체의 화면 내 translation이 손 움직임인지 머리/카메라 움직임인지 완전히 구별할 수 없다. 시야 재조정 중 포인터 고정을 보장하려면 명시적 clutch/일시정지 또는 별도 카메라 motion 정보가 필요하다. 기존 fist=DRAG와 pinch=CLICK을 새 clutch에 재사용하지 않는다.
- CLICK/FIST/DRAG 판정 시간과 상태 머신은 유지했다. 손 유실, CLICK anchor, FIST/DRAG 및 MOVE 복귀에서 One Euro 상태와 안정 기준점을 현재 손 위치로 재설정한다. CLICK 준비가 처음 켜질 때 불필요한 reset으로 노이즈가 커지는 현상은 로컬 테스트에서 발견해 anchor가 실제 있을 때만 reset하도록 고쳤다.
- 다음 UI 수정 시 Preview 빨간 tracking point는 `points[16]/points[17]`(landmark 8, raw index tip)에 직접 연결하고, `info["x/y"]`는 mouse output으로 유지한다. thumb tip은 landmark 4인 `points[8]/points[9]`. 이 변경은 아직 구현 승인 전이며 이번 분석에서 코드는 수정하지 않았다.

## 테스트 결과

- 로컬 정적 추적: `hand_tracker` → `gesture_controller` → `mouse_controller` → UART2 → Mac bridge 경로 확인. `git diff --check` 통과.
- 로컬 회귀 테스트 11개 통과: ±5 px 랜덤/교차 jitter 1,000프레임, 고정 손 장시간 드리프트, 1 px/frame 느린 이동, 40 px 빠른 이동과 방향 반전, 화면 경계, 짧은/긴 손 유실 후 재획득, CLICK/FIST 후보 anchor, DRAG 종료 좌표 일치. beta=0에서 정지 jitter는 0 px였지만 40 px step 첫 프레임 반응이 1 px; beta=0.05에서 교차 jitter 범위는 x/y 각각 1 px, 첫 프레임 반응 23 px. `git diff --check` 통과.
- 실제 K230D: raw delta의 심한 jitter와 Preview 빨간 점 이탈은 사용자 보고. 이번 분석에서 보드 파일을 읽거나 업로드하지 않았다.

## 다음 작업

1. 로컬 결과를 사용자에게 보고하고 보드 업로드 확인을 기다린다.
2. 확인 후 보드 파일과 로컬 파일을 비교하고 `gesture_controller.py`만 동기화한다. 실제 FPS, 정지 노이즈, 빠른 이동 직후 tail, 반전·재획득·CLICK/DRAG 및 Mac 커서 사용감을 확인한다.
3. 머리 이동 보정은 이번 변경에 포함하지 않는다. 순수 delta 실기 평가 후 별도 결정한다.
4. Preview tracking point와 mouse cursor 좌표를 분리하는 UI 연결 수정안을 사용자에게 보고하고 승인 후 구현한다.

## 주의사항

- 보드의 `/sdcard` 파일을 로컬 HEAD와 같다고 가정하지 않는다. 업로드 전 파일별 차이를 확인한다. SD 삭제·포맷·초기화 금지.
- 원본 `/Users/yonghwan/Desktop/Smart_Glass/smart_glass.py`는 수정하지 않는다.
- 기존 사용자 변경을 덮어쓰지 않는다. AI/gesture 수치나 상태 머신을 증상 완화를 위해 임의 변경하지 않는다.
- 다음 세션 시작 시 이 문서를 먼저 읽고, 실제 코드 및 `git status`/`git diff`와 대조한다. 의미 있는 변경·테스트·문제 발견 시 갱신하고 오래된 세부 기록은 정리한다.
