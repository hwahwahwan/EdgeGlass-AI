# EdgeGlass-AI 작업 추적 (인수인계용)

작성: 2026-10-21, Claude Code 세션 종료 시점. 다음 에이전트는 이 문서와
`CLAUDE.md`, `tools/DEPLOY.md`만 읽고 바로 이어서 작업할 수 있도록 작성했다.
이전 대화 전체를 읽을 필요는 없다.

**원칙**: 이 문서에 적힌 "성공"은 전부 실제 보드 로그로 확인된 것만
표기했다. 코드 작성 완료나 로컬 문법 검사 통과를 성공으로 쓰지 않았다.

---

## A. 현재 목표

K230D-Zero 한 대에서 다음 네 가지를 **동시에** 실행하는 단일 통합
오케스트레이터(`firmware/smart_glass_server.py`)를 완성하는 것:

1. 손 인식(hand_det + handkp_det kmodel 추론)
2. UART2 `@MOUSE|...` 마우스 제어 (기존 `main.py`와 동일 로직)
3. Wi-Fi 웹 영상(HTTP `/`, `/snapshot`, `/stream` MJPEG)
4. 웹 영상 위 손 관절 오버레이 (`FEATURE_WEB_JOINTS`)

기존 `firmware/main.py`(손 추적+마우스 제어 단독, 웹 없음)는 **보존 대상**이며
수정 대상이 아니다.

---

## B. 현재 구현 상태

### 파일 경로 (전부 `firmware/`에 flat 구조, 보드 배포 시 `/sdcard/smart_glass/`로 평탄화)

| 로컬 파일 | 역할 | 로컬-보드 동기화 상태 |
|---|---|---|
| `firmware/main.py` | 기존 단독 진입점(보존, 미수정) | **일치** |
| `firmware/hand_tracker.py` | 손 검출+키포인트 추론 | **일치**(미수정) |
| `firmware/gesture_controller.py` | 제스처 판정 | **일치**(미수정) |
| `firmware/mouse_controller.py` | UART2 송신 | **일치**(미수정) |
| `firmware/ui.py` | `draw_landmarks()`(공용) + `draw_hand()`(OSD 래퍼) | **일치** |
| `firmware/video_stream.py` | RGB565→JPEG 인코딩 | **일치** |
| `firmware/web_server.py` | 논블로킹 HTTP 서버 | **일치** (`last_err` 진단 포함, G절 참고) |
| `firmware/smart_glass_server.py` | 통합 오케스트레이터(신규) | **일치** (NIC 초기화·JPEG 1회 재시도 포함, G절 참고) |
| `firmware/config.py`, `firmware/smart_glass.py` | 미사용 placeholder / 레거시 의심 | 확인 안 함(두 파일 다 `smart_glass_server.py` 실행에 불필요) |

`git status`(이 문서 작성 시점): `M firmware/smart_glass_server.py`,
`M firmware/web_server.py`, `M tools/DEPLOY.md` — 전부 미커밋. **커밋/푸시하지
않았다.**

### `main.py` vs `smart_glass_server.py` 차이

- `main.py`: `libs.PipeLine.PipeLine` 클래스로 채널 0(디스플레이)+2(AI) 2채널만 연다.
- `smart_glass_server.py`: `PipeLine`을 쓰지 않고 자체 `CameraRig` 클래스로
  채널 0(디스플레이)+1(웹 RGB565)+2(AI) 최대 3채널을 **기능 플래그에 따라
  조건부로** 연다. `PipeLine.py` 파일 자체는 수정하지 않았다.
- 그 외 AI 추론/제스처 판정/UART 송신 로직은 `smart_glass_server.py`가
  `hand_tracker.py`/`gesture_controller.py`/`mouse_controller.py`를 그대로
  재사용하므로 `main.py`와 동일하다.

### `FEATURE_*` 현재 값 (`firmware/smart_glass_server.py` 상단, 로컬=보드 일치)

```python
FEATURE_HAND_RECOGNITION = True
FEATURE_MOUSE_CONTROL = True
FEATURE_DISPLAY_OSD = True
FEATURE_WEB_SERVER = True       # <- 현재 이 값 때문에 마지막 실행이 실패함(아래 E)
FEATURE_WEB_VIDEO = True
FEATURE_WEB_JOINTS = False      # 아직 켜본 적 없음
WEB_PORT = 8060
```

**다음 에이전트가 바로 이어받을 수 있도록, 로컬 파일의 값이 이미 위와 같이
되어 있다.** 다만 `web_server.py`의 미배포 수정(아래 E) 때문에 지금 그대로
보드에 재배포하면 "같은 실패가 재현되는지"부터 확인하는 게 맞다 — F 참고.

---

## C. 실제 보드 테스트 결과 (성공/실패/미검증 구분)

| 항목 | 상태 | 근거 |
|---|---|---|
| 2채널(웹 OFF) 손 추적+마우스 제어+OSD | **성공** | `main.py`로 1차 확인(`DISPLAY: [800, 480]`, `ACTION: MOVE`, `CLICK_TX` UART 송신 로그) + `smart_glass_server.py`(`FEATURE_WEB_SERVER=False`)로 2차 재확인 |
| 2채널 FPS | **성공, 측정값 있음** | `smart_glass_server.py` 270+프레임 동안 `fps=19.9~20.0` 일관 |
| 2채널 메모리 안정성 | **성공, 측정값 있음** | `mem_free` 3874464→3920320바이트로 수렴, 270+프레임 동안 누수 없음 |
| 2채널 깔끔한 종료 | **성공** | `canmv_stop_script` → `[ORCH] cleanup done`까지 정상 |
| UART2 `@MOUSE|CLICK` 등 송신 | **성공(보드 쪽 송신만)** | `CLICK_TX ms=... packet=@MOUSE|CLICK` 로그 다수 확인 |
| Mac `mac_mouse_bridge.py` 실제 수신 | **미검증** | 이번 세션에서 bridge를 띄워 실제 커서 이동을 본 적 없음 |
| 3채널(채널0+1+2) 동시 초기화 | **성공** | `sensor.run() done mem_free=3878144`까지 2회 재현 성공, 행 없음 |
| 3채널 초기화 메모리 영향 | **성공, 측정값 있음** | 채널1 설정 전후 `mem_free` 3880192→3879744 (448바이트만 사용) |
| Wi-Fi 연결(아이폰 핫스팟 `i`) | **성공(마지막 확인 시점 기준)** | `CONNECT_OK ('172.20.10.2', ...)`. 이후 보드 재실행을 여러 번 했지만 Wi-Fi 연결 자체를 다시 체크하지는 않았다 — **다음 에이전트가 재확인 필요** |
| HTTP 서버 포트 8060 bind | **실패(재현됨, 2회)** | 1회차: 핫스팟 꺼진 상태에서 보드 무응답(행). 2회차: 핫스팟 켠 상태에서도 `OSError: HttpServer: bind failed after 20 retries` — 핫스팟 꺼짐이 원인이 아니었음이 반증됨 |
| `/`, `/snapshot`, `/stream` 실제 응답 | **미검증** | bind 단계를 넘어선 적이 없어 도달 못함 |
| `FEATURE_WEB_JOINTS` 관절 오버레이 | **미검증** | 위와 동일한 이유 |
| 웹서버 ON 상태에서 손 인식/UART2 동시 유지 | **미검증** | 위와 동일 |

---

## D. 해결한 버그

### D-1. `sys.path` import 순서 문제 — 해결/검증 완료

- **재현 조건**: `smart_glass_server.py`에서 `import sys`를 `from media.media
  import *` **보다 먼저** 두면, wildcard import가 `sys`라는 이름을 다시
  바인딩해 버려서(이 미디어 모듈 네임스페이스 안에 `sys`라는 이름이 있음)
  이후 `sys.path.insert(...)`가 `AttributeError: 'module' object has no
  attribute 'path'`로 죽는다.
- **발견 경위**: `main.py`는 원래부터 `from media.media import *` 다음에
  `import sys`를 두고 있었다(우연히 회피). 두 파일을 나란히 비교해서 발견.
- **수정 위치**: `firmware/smart_glass_server.py` 상단 — `import sys/gc/time/image`를
  `from media.media import *` **뒤로** 이동.
- **검증 결과**: 수정 후 같은 에러 재현 안 됨. 이후 모든 실행에서 import
  단계는 문제없이 통과함.

### D-2. `MediaManager.init()`과 `Display.init()` 충돌 — 해결/검증 완료

- **재현 조건**: `Display.init()`을 호출한(=`FEATURE_DISPLAY_OSD=True`)
  상태에서 추가로 `MediaManager.init()`을 호출하면 **보드가 완전히
  멈춘다**. `ready: false`가 고착되고, 소프트 리부트나 재연결로 회복되지
  않았으며 **물리적 USB 전원 재인가가 필요했다**(실제로 그렇게 복구함).
- **근거**: `media/media.pyi` stub에 `MediaManager.init`/`deinit`이
  "Deprecated media manager initializer/deinitializer"로 명시돼 있고,
  `libs/PipeLine.py`(보드에 있는, `main.py`가 쓰는 검증된 클래스)는
  `Display.init()`을 쓰면서 `MediaManager.init()`을 전혀 호출하지 않는다.
  반대로 `experiments/wifi_test/mjpeg_stream_test.py`(Display 안 씀)는
  `MediaManager.init()`이 있어야 동작했고 실제로 문제없이 동작했다.
- **수정 위치**: `firmware/smart_glass_server.py`의 `CameraRig.create()` —
  `enable_display`가 True면 `MediaManager.init()`을 호출하지 않도록 조건
  분기. `destroy()`도 대칭으로 수정(Display 쓸 때는 `MediaManager.deinit()`
  호출 안 함).
- **검증 결과**: 수정 후 2채널, 3채널 구성 양쪽 다 이 행이 재현되지 않았다
  (2회 이상 재현 테스트).

---

## E. 남은 문제

### E-1. (현재 최전선) 웹서버 포트 8060 bind 실패 — 원인 미확정

- **증상**: `FEATURE_WEB_SERVER=True`, `FEATURE_WEB_VIDEO=True`일 때
  `rig.create()`(3채널 초기화)까지는 매번 성공하지만, 그 다음
  `WebState.start()` → `web_server.HttpServer.start()`의 `socket.bind()`가
  **20회(10초) 전부 실패**한다.
- **1차 시도(핫스팟 꺼짐)**: 보드가 완전히 무응답 상태가 됨(행). 재연결
  반복 않고 USB 전원 재인가로 복구(사용자가 직접 수행).
- **2차 시도(핫스팟 켬, Wi-Fi `172.20.10.2` 연결 확인된 상태)**: 이번엔
  행이 아니라 **깔끔한 `OSError`**로 종료됨 — `OSError: HttpServer: bind
  failed after 20 retries`. 보드는 즉시 응답 정상 상태로 복귀했다.
- **확정된 것**: "핫스팟이 꺼져 있어서"라는 가설은 **반증됨**(2차 시도는
  핫스팟이 켜져 있었는데도 실패).
- **아직 모르는 것**: `bind()`가 매번 어떤 구체적 `OSError`(errno)를
  던지는지 — 기존 코드가 `except OSError:`로 예외 내용을 버리고 있었다.
  포트가 이전 실행에서 완전히 안 풀렸는지, 3채널 센서 구성이 소켓 계층에
  영향을 주는지, 다른 NIC 레이스 변형인지는 전부 가설일 뿐이다.
- **적용한 조치(로컬에만 있음, 보드 미배포, 미재검증)**: `firmware/web_server.py`의
  `HttpServer.start()`에서 각 시도의 실제 `OSError`를 `last_err`에 저장해
  최종 예외 메시지에 포함하도록 최소 수정(재시도 횟수·대기시간·구조는
  바꾸지 않음). **배포도, 재테스트도 하지 않은 상태로 세션이 끝났다.**

### E-2. USBDBG 연결 문제 및 복구 절차 (참고용, 현재는 발생 안 함)

- 이번 세션 중 `canmv_board_info`/`canmv_script_running` 호출이 간헐적으로
  `USBDBG command 0xA4 response: short read` 또는 `Not connected`를 반환한
  적이 여러 번 있었다. 대부분은 `canmv_connect_board(port="/dev/cu.usbmodem0010000001")`
  재연결 1회로 복구됐다.
- **단, 1차 bind 행 사건 때는 재연결로도 복구되지 않아 물리적 USB 전원
  재인가가 필요했다.** 재연결을 반복해도 안 풀리면 사용자에게 전원
  재인가를 요청할 것 — 무리하게 반복 재연결하지 말 것(사용자가 명시적으로
  지시한 원칙).
- 전원 재인가 후에는 `canmv_board_info` → `ready: true` 확인, 그다음
  REPL 응답(`canmv_run_script("print(1)")`) 확인 순서로 복구를 검증했다.

### E-3. Wi-Fi 연결 — 코드가 아니라 환경 특성

- `net.py`의 `connect()`는 **1회만 `wlan.connect()`를 호출하고 최대 60초까지
  패시브 대기**하도록 이미 고쳐져 있다(세부 내용은
  `experiments/wifi_test/WIFI_TEST_REPORT.md` 참고). 짧은 대기(30~45초)로는
  실패하고 60초까지 기다려야 성공한 사례가 있었다 — **연결이 느릴 뿐
  정상적으로 되는 경우가 많으니, 반복 재호출로 "고치려" 하지 말 것.**
- 아이폰 핫스팟은 설정 앱에서 "개인용 핫스팟" 화면을 열어 검색 가능
  상태로 유지해야 보드가 스캔으로 찾을 수 있었던 사례가 과거에 있었다.

---

## F. 다음 작업 순서 (바로 실행 가능한 체크리스트)

**0단계 — 시작 전 확인 (코드 수정 없이 상태만 확인)**

- [ ] `canmv_board_info` → `connected: true, ready: true` 확인. 아니면
      사용자에게 USB 재연결 요청(무리하게 반복 재연결하지 말 것).
- [ ] `canmv_script_running` → 보드에 실행 중인 프로세스가 있으면 **임의로
      중단하지 말고** 사용자에게 먼저 보고.
- [ ] Wi-Fi 재확인: `network.WLAN(network.STA_IF).isconnected()`를
      `canmv_run_script`로 조회. 끊겨 있으면 `experiments/wifi_test/net_config.py`
      + `net.py`의 `connect(SSID, PASSWORD, timeout_s=60)`로 **1회만**
      재연결(반복 호출 금지).

**1단계 — `web_server.py` 미배포 수정 배포**

- 실행: 로컬 `firmware/web_server.py`(이미 `last_err` 로깅 추가됨)를
  `canmv_write_file("/sdcard/smart_glass/web_server.py", ...)`로 배포.
- 검증: `canmv_read_file`로 재다운로드 → 로컬과 SHA-256 비교(`tools/DEPLOY.md`
  §7~8 절차 그대로). **다르면 실행하지 말 것.**
- 예상 결과: 배포 성공, 해시 일치.
- 성공 판정: `shasum -a 256`이 로컬/보드 동일.

**2단계 — 웹서버 ON 재시도, 이번엔 실제 에러 내용 확인**

- 실행: `canmv_stop_script()` → `canmv_execute_file("/sdcard/smart_glass/smart_glass_server.py")`
  → `canmv_terminal_output()`.
- 예상 결과(가설): 또 `HttpServer: bind failed after 20 retries, last_err=OSError(...)`
  형태로 실패하되, 이번엔 괄호 안에 **구체적인 errno/메시지**가 보일 것.
- 성공 판정:
  - **성공 시나리오**: `web server listening on port 8060`이 뜨고
    메인 루프(`EdgeGlass-AI orchestrator START`)까지 도달 → 3단계로.
  - **실패 시나리오**: 여전히 bind 실패, 단 `last_err` 내용을 확보 →
    그 errno를 근거로 원인 분류(예: `EADDRINUSE`면 포트 점유 문제,
    다른 코드면 또 다른 가설 필요) → `tools/DEPLOY.md`에 기록 후 사용자에게
    보고.
- 실패 시 확인할 로그: `canmv_terminal_output()`의 `Traceback`/`OSError` 전체,
  그리고 그 직전 `log_mem()` 출력들(메모리 부족 가능성 배제용).
- 다음 단계로 넘어갈 조건: `web server listening on port %d` 로그가 실제로
  찍혀야 함.

**3단계 — `/`, `/snapshot`, `/stream` 순서대로 확인 (2단계 성공 시에만)**

- Mac에서 `curl http://172.20.10.2:8060/`, `curl -o snap.jpg
  http://172.20.10.2:8060/snapshot`, 그리고 `/stream`은 MJPEG 멀티파트
  파서(세션 중 `experiments/wifi_test/mjpeg_stream_test.py`에서 쓴 방식
  참고)로 프레임 2~3개를 실제로 받아 JPEG 매직바이트(`FFD8...FFD9`)를
  확인.
- 이 단계에서도 보드 터미널 로그(`/snapshot bytes=... encode_ms=...`,
  `/stream frame=... fps=...`)를 같이 기록할 것 — §C의 "JPEG 인코딩 시간",
  "HTTP 응답 시간" 항목을 이 로그로 채운다.
- 성공 판정: 세 엔드포인트 모두 실제 바이트 응답 확인.
- 다음 단계 조건: `/stream`이 최소 몇 프레임이라도 안정적으로 나와야 함.

**4단계 — 손 인식/UART2 동시 유지 확인 (3단계 성공 시에만)**

- 손을 카메라 앞에서 움직이며 보드 로그의 `ACTION: MOVE/CLICK`과
  `/stream frame=...`이 번갈아/동시에 찍히는지 확인. 가능하면
  `mac/mac_mouse_bridge.py`도 띄워 Mac 커서가 실제로 움직이는지까지 확인
  (이번 세션에서 한 번도 확인 못한 부분).
- 성공 판정: 웹 스트리밍 중에도 `ACTION:` 로그가 끊기지 않고, FPS가
  2채널 때(~20)보다 과도하게 떨어지지 않음.

**5단계 — `FEATURE_WEB_JOINTS=True` (4단계 성공 시에만)**

- 로컬에서 플래그만 바꾸고 1단계와 같은 배포 절차(해시 검증 포함)를 거쳐
  재실행. 웹 영상에 관절 점/선이 올바른 위치에 그려지는지 눈으로 확인
  (RGB565 640×480과 AI 640×360 간 좌표 변환이 맞는지).

**모든 단계 공통 — 실패 시**

- 보드가 무응답이면 재연결을 반복하지 말고, 마지막 성공 로그와 함께
  사용자에게 USB 재인가를 요청한다.
- 어떤 설정이 마지막으로 검증됐는지는 항상 `firmware/smart_glass_server.py`
  상단 `FEATURE_*` 값과 이 문서 B절을 기준으로 삼는다.

---

## 인수인계 시 주의할 사항 (요약)

- `firmware/web_server.py`의 진단 수정은 배포·해시 검증 완료됐다(G절).
- `firmware/smart_glass_server.py`는 로컬=보드 일치,
  `FEATURE_WEB_SERVER=True`, `FEATURE_WEB_VIDEO=True`,
  `FEATURE_WEB_JOINTS=False` 상태다. 다음 시작점은 G절의 Wi-Fi 재연결 후
  `/snapshot`·`/stream` 재검증이다.
- Wi-Fi 비밀번호는 `experiments/wifi_test/net_config.py`에 있고
  `.gitignore`로 제외되어 있다. 로그나 문서에 평문으로 남기지 말 것.
- `main.py`, `hand_tracker.py`, `gesture_controller.py`, `mouse_controller.py`는
  이번 세션에서 전혀 수정하지 않았다 — 문제가 생기면 이 파일들이 원인일
  가능성부터 배제하고 시작해도 된다.
- Git 커밋/푸시는 이번 세션에서 하지 않았다. 모든 변경은 워킹 트리에만 있다.

---

## G. 2026-10-21 Codex 재개 작업 — HTTP bind 해결, 엔드포인트 부분 검증

### 로컬 구현 완료

- `firmware/web_server.py`의 `last_err` 진단 코드를 확인했다.
- 진단 로그로 bind 20회 실패의 실제 원인이
  `OSError('no available NIC')`임을 확보했다.
- 분리 진단에서 soft reboot 직후 `network.WLAN(network.STA_IF)` 핸들을
  생성하고 `active(True)`를 호출하면 동일 포트 8060 bind가 성공함을
  확인했다. 이를 근거로 `firmware/smart_glass_server.py`가 웹서버 시작 전에
  WLAN 핸들을 생성·유지하고 연결 상태/IP를 확인하도록 최소 수정했다.
  자격증명이나 자동 재연결 로직은 정식 firmware에 추가하지 않았다.
- 통합 실행 중 JPEG 압축은 첫 요청에서 간헐적으로
  `OSError('Compression Failed!')`가 발생하고 다음 요청에서는 정상 JPEG가
  생성되는 것이 관측됐다. 이 실측에 근거해 해당 오류에 한해서만 새
  프레임으로 1회 재시도하도록 최소 복구를 추가했다.
- 로컬 CPython 문법 검사와 `git diff --check` 통과.

### 보드 배포 완료

- `firmware/web_server.py` 배포 후 로컬/보드 SHA-256 및 바이트 일치:
  `28a94021360545d93f70a1fcfe23f822af1c7b77f8fe8152cf3ca7f5722c0f24`.
- `firmware/smart_glass_server.py` 최종본 배포 후 로컬/보드 SHA-256 및
  바이트 일치:
  `e3c3cbde2cf8597a8006ed1342910e4eb275d0515f032b587523440f1ca8be86`.
- `firmware/main.py`는 수정하거나 배포하지 않았다.

### 실기기 검증 완료

- Wi-Fi 연결/IP `172.20.10.2` 확인 후 통합 프로그램 실행.
- `WLAN ready ifconfig=...`, `web server listening on port 8060`,
  `EdgeGlass-AI orchestrator START`까지 확인해 HTTP bind 문제 해결.
- 웹서버와 AI/UART2 동시 실행 중 `ACTION: MOVE/STOP`, `CLICK_TX`, 메인 루프
  로그가 계속 출력됐다. 웹 ON 상태 FPS는 실행 구간에 따라 약 10~20 FPS였고
  `mem_free`는 약 3.92MB로 유지됐다.
- `/`: 실제 Mac curl로 HTTP 200, HTML 168바이트 확인.
- `/snapshot`: 첫 요청은 `Compression Failed!`로 실패했으나 다음 요청은
  HTTP 200, 29,794바이트, 640x480 JPEG, 매직바이트 `FFD8...FFD9` 확인.

### 실패 및 원인 확인

- 최초 bind 실패 원인은 포트 점유가 아니라 MicroPython socket 계층에
  등록된 NIC 핸들이 없었던 것이다. WLAN 핸들 생성 후 해결됐다.
- 수정 전 `/stream`은 HTTP 200 MJPEG 헤더 뒤 첫 프레임 압축이
  `Compression Failed!`로 끝나 프레임 0개였다. 이를 위해 1회 재시도 코드를
  추가·배포했다.
- 최종 재배포 뒤 Wi-Fi 링크가 끊겼고, 검증된 `net.connect(..., timeout_s=60)`
  단일 재연결 시도도 `wifi connect timeout after 60s`로 실패했다. 추가
  connect 반복은 하지 않았다. 보드는 마지막 확인 시 REPL로 복귀한 유휴
  상태이며 전원 재인가는 필요하지 않다.

### 미검증·보류

- JPEG 1회 재시도 수정 후 `/snapshot` 재검증.
- JPEG 1회 재시도 수정 후 `/stream`에서 실제 MJPEG 2~3프레임 및 각 JPEG
  매직바이트 검증.
- 스트리밍 중 손 관절/AI 추론/UART2 마우스 제어 장시간 동시 동작.
- `FEATURE_WEB_JOINTS=True` 웹 관절 오버레이(아직 False 유지).
- Mac bridge 실제 커서 이동.

### 다음 작업

1. 핫스팟을 검색 가능한 상태로 만든 뒤 `/sdcard/wifi_test/net.py`의
   `connect()`를 1회만 호출하고 최대 60초 기다려 IP를 재확인한다.
2. 이미 배포·해시 검증된 `smart_glass_server.py`를 실행한다.
3. `/snapshot`을 재확인한 다음 `/stream`에서 최소 2~3개 MJPEG 프레임과
   `FFD8...FFD9`를 검증한다.
4. 스트리밍이 성공한 경우에만 AI/UART2 동시 동작과
   `FEATURE_WEB_JOINTS=True` 단계로 진행한다.

---

## H. 2026-10-21 MJPEG 스트림 완료 및 웹 관절 오버레이 재개

### 보드 배포 완료

- `firmware/smart_glass_server.py`의 JPEG 1회 재시도 구현과
  `FEATURE_WEB_JOINTS=True` 설정은 보드 `/sdcard/smart_glass/` 사본과
  SHA-256/바이트 일치 확인 완료:
  `7062630e670d49754d8f2c6aa7cd15d46194af1cf00e2d62112a7b0c8e71562b`.
- `firmware/web_server.py`는 기존 배포본과 계속 일치:
  `28a94021360545d93f70a1fcfe23f822af1c7b77f8fe8152cf3ca7f5722c0f24`.

### 실기기 검증 완료

- Wi-Fi 재연결 1회 성공, 보드 IP `172.20.10.2` 확인.
- `/stream`(관절 OFF 당시): Mac curl이 15초 동안 810,200바이트를 수신했고,
  MJPEG boundary 66개, JPEG SOI `FFD8` 66개, EOI `FFD9` 66개를 확인했다.
  curl의 종료 코드 28은 15초 의도적 최대 시간 만료이며 스트림 오류가 아니다.
- 첫 JPEG 압축 실패가 발생했을 때 `JPEG compression failed once; retrying
  with a new frame` 로그 뒤 프레임 1이 정상 전송됐다. 이후에도 재시도 후
  프레임 전송이 계속됐으므로 1회 재시도 복구가 실제 동작함을 확인했다.
- 같은 스트리밍 구간에 `ACTION: MOVE/CLICK/STOP` 및 `CLICK_TX`가 함께
  출력됐다. 웹 ON 메인 루프는 약 9~12 FPS, 스트림은 약 4~5 FPS였고,
  메인 루프 경계에서 `mem_free`는 약 3.90~3.92MB로 회복됐다.
- 관절 ON 설정으로 재실행 후, `/stream` 로그에서 210프레임 이상(약 4.9~5.7
  FPS), `ACTION: MOVE/DRAG/STOP`, `CLICK_TX` 동시 동작을 확인했다.
- **사용자 직접 검증 완료**: 브라우저에서 웹 스트리밍과 손 관절 오버레이가
  정상 표시되는 것을 확인했다. 현재 지연은 정상 사용에 지장이 없는 수준이다.

### 현재 정상 동작 코드 유지

- 현재 `FEATURE_WEB_JOINTS=True`인 통합 오케스트레이터와 배포된 파일을
  유지한다. 정상 동작 중인 손 인식, UART2 마우스 제어, HTTP/MJPEG 경로는
  추가 변경하지 않는다.

### 추후 개선 항목

- FPS 향상 및 스트리밍 지연 최적화. 현재 성능은 사용 가능하므로 기능 회귀를
  유발할 수 있는 성능 변경은 별도 작업으로 보류한다.

### 미검증·보류

- 마지막 단독 snapshot 시도 직후 USBDBG `short read`가 발생했다. 보드가
  완전히 무응답인지 아직 확정하지 않았으며, 규칙에 따라 반복 재연결은 하지
  않았다.
- Mac bridge의 실제 커서 이동.

### 다음 작업

1. 현 정상 동작 구성을 유지한다.
2. 필요 시 별도 작업으로 FPS 및 스트리밍 지연 최적화를 수행한다.
3. 필요 시 Mac bridge의 실제 커서 이동을 별도 검증한다.

---

## I. 2026-10-21 교수님 시연 문서 갱신

- 로컬 문서 `../시연용_README.md`를 전원 재인가부터 종료까지의 시연 절차로
  갱신했다. Wi-Fi는 `net.py`를 단독 실행하지 않고 CanMV REPL에서
  `connect(SSID, PASSWORD, timeout_s=60)`를 한 번 호출하는 검증된 방식임을
  명시했다.
- 통합 실행 파일은 `firmware/smart_glass_server.py`이며, `README.md`와 실행
  코드·보드 파일은 변경하지 않았다.
