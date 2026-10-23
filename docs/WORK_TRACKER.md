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

---

## J. 2026-10-21 시연용 Wi-Fi 한 줄 실행 파일

### 로컬 구현 완료

- `experiments/wifi_test/demo_wifi.py`를 추가했다. 이 파일은 Wi-Fi 연결을
  구현하지 않고 기존 `net_config.py`의 `SSID`/`PASSWORD`와 `net.py`의
  `connect(..., timeout_s=60)`만 호출한다.
- CanMV REPL 실행 경로를 보장하기 위해 `/sdcard/wifi_test`를 `sys.path`에
  추가한 뒤 모듈을 import한다.
- 로컬 문법 검사 통과. SHA-256:
  `e5c3ea4ead83787a8d9324fc95ef1e0f6bebbfdb2b022d39b9e535ae8891c29b`.

### 보드 배포·실기기 검증 완료

- 사용자 전원 재인가 후 CDC 포트 `/dev/cu.usbmodem0010000001`에 연결해
  `connected: true, ready: true`를 확인했다.
- `/sdcard/wifi_test/demo_wifi.py`에 배포 후 로컬/보드 SHA-256 및 바이트
  일치 확인 완료:
  `e5c3ea4ead83787a8d9324fc95ef1e0f6bebbfdb2b022d39b9e535ae8891c29b`.
- 전원 재인가 뒤 CanMV에서 정확히 다음 한 줄을 실행했다.
  `exec(open('/sdcard/wifi_test/demo_wifi.py').read())`
- 실제 출력: `CONNECT_OK ('172.20.10.2', '255.255.255.240',
  '172.20.10.1', '172.20.10.1')`. Wi-Fi 연결과 IP 출력 성공을 확인했다.
- `../시연용_README.md`의 Wi-Fi 여러 줄 명령어를 위 한 줄 명령어로 교체했다.

---

## K. 2026-10-23 실기기 안정성 진단 — UDP 자동 탐색 + 웹서버 + AI 동시 실행

### 배경

- 사용자가 홈 Wi-Fi(`SK_WiFiGIGA3A00_2.4G`)로 Wi-Fi + 웹서버 + AI 제스처
  인식 + UDP 자동 탐색(discovery)을 동시에 켜고 실행하자 보드가 멈추거나
  연결이 끊기는 문제를 보고했다. 직전 시도에서 `config.MOUSE_UDP_MAX_SCAN_HOSTS`를
  임시로 300까지 올려 `/24` 전체(253개 주소)를 한 번에 스캔했고,
  `canmv_stop_script` 호출 후 보드가 30초 넘게 무응답 상태가 되어 **물리적
  전원 재인가로 복구**했다(사용자가 직접 수행).
- 재현 테스트는 253개 주소 전체 스캔으로 바로 시작하지 않고, 작은 범위부터
  단계적으로 올리는 방식으로 진행했다. `experiments/runtime_diagnostics/`에
  `smart_glass_server.main()`을 그대로 재사용하되 `config`/`discovery`
  속성만 런타임에 monkey-patch하는 1회성 진단 스크립트 두 개를 작성했다
  (firmware/ 파일은 건드리지 않음, 배포 경로도 `/sdcard/runtime_diagnostics/`로
  분리):
  - `diag_stage4_fixed_udp.py`: `MOUSE_UDP_AUTO_DISCOVER=False`, 고정 IP
    UDP만 사용(탐색 없음).
  - `diag_stage5_small_discovery.py`: `discovery.compute_scan_targets`를
    5개 주소(Mac의 실제 IP 포함)로 monkey-patch한 "진짜" `@HELLO/@ACK`
    탐색 경로.

### K-1. 발견한 버그 — `discovery.py`의 `decode()` 키워드 인자 — 해결/검증 완료

- **증상**: Stage 5(5개 주소 탐색) 실행 중 Mac 브리지가 `[DISCOVERY] Board
  registered: 192.168.45.44`까지는 정상 출력했지만, 그 직후 보드 터미널에
  다음 traceback이 뜨며 메인 루프가 죽었다(단, 보드 자체는 멈추지 않고
  `[ORCH] cleanup done`까지 깔끔하게 출력됨 — 행이 아니라 처리되지 않은
  예외였다):
  ```
  File "/sdcard/smart_glass/discovery.py", line 119, in step
  TypeError: function doesn't take keyword arguments
  ```
- **근거(실기기 REPL로 직접 확인)**: `b"@ACK|ok".decode("utf-8",
  errors="replace")`는 이 보드의 MicroPython 빌드에서
  `TypeError: function doesn't take keyword arguments`를 던지고,
  `b"@ACK|ok".decode("utf-8", "replace")`(같은 인자를 위치 인자로)는
  정상 동작한다. 즉 이 빌드의 `bytes.decode()`는 **키워드 인자를 전혀
  받지 않는다**(위치 인자는 받음). `discovery.py`의 `step()`이
  `data.decode("utf-8", errors="replace")`로 호출하던 것이 원인이었다.
- **수정 위치**: `firmware/discovery.py`의 `UdpRegistry.step()` — 키워드
  `errors="replace"`를 위치 인자 `"replace"`로 변경.
- **검증 결과**: 로컬 단위 테스트(`tests/test_wifi_auto_discovery.py` 포함
  73개) 전부 통과. 실기기에서 Stage 5를 동일하게 재실행한 결과, 이번에는
  `TypeError` 없이 `[UDP] Mac registered: 192.168.45.62:9000` /
  `[UDP] Mouse control ready`가 정상 출력됐고, Mac 쪽에서 실제 손 제스처로
  발생한 `EVENT MOVE ...` 패킷이 연속으로 수신됐다. **UDP 자동 탐색 +
  웹서버 + AI + 카메라 동시 실행이 실기기에서 크래시 없이 성공한 첫
  사례.**

### K-2. 구조 개선 — UDP 트랜스포트 오류가 웹서버/AI를 중단시키지 않도록 격리

- K-1의 `TypeError`처럼 트랜스포트 계층에서 예상 못한 예외가 나면, 기존
  구조는 `smart_glass_server.main()`의 바깥쪽 `except BaseException`까지
  그대로 올라가 **카메라/AI/웹서버까지 전부 함께 종료**됐다(K-1 재현
  당시에도 이 경로로 죽었지만, 보드 자체는 멈추지 않았다).
- **수정 위치**: `firmware/smart_glass_server.py`
  - 마우스 컨트롤러/트랜스포트 생성부(`FEATURE_MOUSE_CONTROL` 블록)를
    `try/except (OSError, ValueError)`로 감싸, 트랜스포트 설정 실패 시
    `mouse_controller=None`으로 두고 나머지(웹서버/AI)는 그대로 진행하도록
    변경.
  - 메인 루프의 `mouse_controller.transport.step()` 호출을
    `try/except Exception`으로 감싸, 예외 발생 시 로그만 남기고
    `step`을 그 실행 동안 no-op으로 교체해 **루프 자체는 계속 돌도록**
    변경(카메라/AI/웹서버는 영향받지 않음).
- **검증 결과**: 로컬 73개 테스트 통과(회귀 없음). 이번 재현에서는 K-1을
  고쳐서 예외 자체가 발생하지 않았기 때문에, 이 방어 코드가 실제로 걸리는
  경로까지는 실기기에서 트리거되지 않았다 — **즉, 이 구조 개선은 로컬
  구현+단위테스트까지 완료, 실기기에서 "예외가 실제로 발생한 상태에서
  웹서버/AI가 살아남는지"는 아직 실기기로 직접 검증하지 못했다.**

### K-3. 원래 사건(253개 주소 전체 스캔 시 행)의 원인 — 미확정, 추측 수정 안 함

- **확정된 것**: 원래 행이 발생했던 시도에서는 Mac 쪽에 `[DISCOVERY] Board
  registered` 로그가 **한 번도 찍히지 않았다** — 즉 ACK가 한 번도
  처리되지 못했다는 뜻이고, 이는 K-1의 `decode()` 버그가 그 행의 직접
  원인이 **아니라는** 근거다(그 코드 경로까지 도달하지 못했다).
- **아직 모르는 것**: 253개의 서로 다른 목적지로 `sendto()`를 짧은 루프
  안에서 연달아 호출하는 것 자체(ARP 해석 지연, 네트워크 스택 리소스
  고갈 등)가 행의 원인인지, 아니면 다른 요인(메모리, KPU/카메라 버퍼
  경쟁 등)인지는 **이번 세션에서 재현 테스트하지 않았다** — 사용자 지시에
  따라 253개 전체 스캔 재현은 의도적으로 수행하지 않았다.
- **현재 상태로 유지되는 안전장치**: `config.MOUSE_UDP_MAX_SCAN_HOSTS=64`
  (기존 기본값, 이번 세션에서 되돌림/재확인 완료) — 이 값 이하에서는 Stage
  5(5개 주소)로 안전성이 실증됐지만, 64개 전부를 동시에 보내는 경우까지는
  아직 실기기로 확인되지 않았다.
- **다음 단계(아직 실행하지 않음)**: 안전하다고 확인된 소규모(5개) 다음
  단계로, 더 큰 그러나 253보다는 작은 중간 규모(예: 20~30개, 실제 존재하지
  않는 주소 다수 포함)로 한 단계씩 올려가며 행 재현 여부를 관찰하는 것을
  권장. 이번 세션에서는 사용자 지시에 따라 진행하지 않았다.

### K-4. 측정값 (Stage 4, 고정 IP UDP + 웹 + AI, 실기기)

- FPS ~10–13.5, `gc.mem_free()` ~3.1–3.9MB로 안정적으로 유지됨(관찰 구간
  내 메모리 누적 증가 추세 없음).
- Mac 쪽에서 실제 손 제스처로 발생한 `MOVE`/`CLICK`/`DRAG_START`/`DRAG_END`
  패킷을 연속으로 수신 — UDP 마우스 제어(고정 IP 경로)의 첫 실기기 종단간
  검증 성공.

### K-5. 배포·정리 상태

- `firmware/discovery.py`, `firmware/smart_glass_server.py` 수정분을
  `/sdcard/smart_glass/`에 배포, 보드에서 직접 계산한 SHA-256으로 로컬과
  바이트 일치 확인 완료.
- `config.py`의 `MOUSE_UDP_MAX_SCAN_HOSTS`는 테스트 중 300으로 올렸던 것을
  64로 되돌리고 보드에서 해시로 재확인했다(로컬 값은 처음부터 변경되지
  않았음).
- `experiments/runtime_diagnostics/`(로컬)와 `/sdcard/runtime_diagnostics/`
  (보드)의 두 진단 스크립트는 **삭제하지 않고 유지**했다 — K-3의 253개
  스캔 행 원인이 아직 확정되지 않아, 추후 중간 규모 재현 테스트를 이
  스크립트들로 이어서 진행할 수 있도록 남겨둔 것이다. Mac 쪽 임시 dry-run
  브리지 프로세스(`--dry-run`, PID 파일 `/tmp/diag_bridge5.pid`)는 작업
  종료 시 중지했다.
- Git 커밋/푸시는 수행하지 않았다(지시 사항).

---

## L. 2026-10-23 Wi-Fi 시연 실행 문제 — README 경로 재현 및 수정

### 배경

사용자가 `시연용_README.md`를 보고 직접 `run_wifi.py`를 실행했을 때 Wi-Fi
연결이 반복 실패했다고 보고했다(`run connect failed.` 반복, 웹서버 접속
안 됨). K절 진단 때 썼던 `experiments/runtime_diagnostics/` 몬키패치
스크립트가 아니라, 사용자가 실제로 쓰는 `firmware/run_wifi.py` 그 자체로
재현·수정했다.

### L-1. `wifi.connect_if_needed()`가 드라이버 거부를 무시하던 문제 — 해결/검증 완료

- **근거(실기기 REPL로 직접 확인)**: `wlan.connect(ssid, password)`가 이
  보드에서 **`False`를 반환**하는 경우(드라이버가 그 네트워크를 즉시
  거부 — 비밀번호 오류, 보안 모드 비호환 등)가 있는데, 기존
  `connect_if_needed()`는 이 반환값을 전혀 확인하지 않고 그냥
  `isconnected()`를 최대 `timeout_s`(기본 30초)까지 기다렸다 — 드라이버가
  이미 "안 된다"고 답한 뒤에도 쓸모없이 수십 초를 더 낭비하고, 사용자에게는
  아무 이유도 보여주지 않은 채 조용히 다음 네트워크로 넘어갔다.
- **수정 위치**: `firmware/wifi.py`의 `connect_if_needed()` — `wlan.connect()`
  반환값이 `False`면 바로 다음 후보로 넘어가도록 하고, 추가로
  `on_progress(message)` 콜백을 받아 "어느 네트워크를 시도 중인지/왜
  실패했는지"를 그때그때 보고하도록 변경. `smart_glass_server.py`가 이
  콜백을 `banner_print`에 연결해 `[Wi-Fi] connecting to ...`/`rejected by
  the Wi-Fi driver ...`/`timed out ...`/`connected to ...` 형태로
  콘솔에 바로 보이게 했다.
- **검증 결과**: 로컬 단위 테스트 3개 추가(`test_driver_rejection_*`,
  `test_on_progress_reports_each_attempt_and_outcome`) 포함 76개 전부
  통과. 실기기에서 `run_wifi.py`를 재실행했을 때 이 메시지들이 실제로
  그대로 출력됨을 확인했다.

### L-2. 집 Wi-Fi 연결 자체는 간헐적으로 실패함 — 원인 미확정, 재현만 확인

- **확정된 것**: 같은 `wifi_credentials.py`(수정 없음)로 연속 3회
  `run_wifi.py`를 실행한 결과 **2회 성공, 1회 실패**했다(실패 시
  `[Wi-Fi] 'SK_WiFiGIGA3A00_2.4G' rejected by the Wi-Fi driver ...` →
  핫스팟 후보도 거부 → `OSError` 발생, 보드 자체는 멈추지 않고 깔끔하게
  `cleanup done`까지 진행됨). 즉 비밀번호 자체는 맞을 가능성이 높다
  (완전히 틀렸다면 매번 실패해야 하는데 그렇지 않았다).
- **아직 모르는 것**: 왜 간헐적으로 거부되는지는 확인하지 못했다. 짧은
  시간 안에 반복적으로 연결을 시도한 것(이번 진단 포함) 자체가 공유기의
  일시적인 재인증 제한을 유발했을 가능성을 의심하고 있으나, 이는 가장
  그럴듯한 가설일 뿐 증명하지는 못했다. 신호 강도(-68dBm, 보통 수준)나
  보드 Wi-Fi 드라이버의 특성일 수도 있다.
- **사용자에게 안내한 완화책**: 실패해도 보드가 멈추지 않고 어느
  네트워크가 왜 실패했는지 콘솔에 바로 나오므로(L-1), 실패 시 그냥 한 번
  더 실행하면 대부분 된다 — 추측성 "원인 수정"은 하지 않았다.

### L-3. UDP 자동 탐색이 집 Wi-Fi(`/24`)에서 구조적으로 불가능 — 수동 고정 IP로 자동 전환하도록 수정

- **증상**: 집 Wi-Fi(192.168.45.0/24, 호스트 253개)는
  `config.MOUSE_UDP_MAX_SCAN_HOSTS`(64) 상한을 넘어서, 자동 탐색이
  `ValueError`를 던지고 그대로 마우스 제어가 꺼진 채 끝났다(웹서버/AI는
  K-2 방어 코드 덕분에 계속 동작 — 실기기에서 처음 확인).
- **사용자 결정**: 집 Wi-Fi에서는 수동 고정 IP(`MOUSE_UDP_HOST`)를 쓰기로
  결정함(핫스팟처럼 작은 서브넷에서는 기존 자동 탐색을 그대로 유지).
- **수정 위치**: `firmware/transport.py`의 `create_transport()` — 자동
  탐색이 서브넷 크기 때문에 실패(`ValueError`)하면, `udp_host`가 설정돼
  있으면 예외를 던지는 대신 고정 IP `UdpTransport`로 자동 전환하도록
  변경(설정돼 있지 않으면 기존처럼 예외). `config.py`의 `MOUSE_UDP_HOST`
  기본값을 핫스팟 예시 주소(`172.20.10.3`)에서 집 Wi-Fi에서 확인한 Mac의
  실제 IP(`192.168.45.62`)로 갱신.
- **검증 결과**: 로컬 단위 테스트 2개 추가
  (`test_falls_back_to_fixed_host_when_subnet_too_large_for_scan`,
  `test_raises_when_subnet_too_large_and_no_fixed_host_configured`) 포함
  78개 전부 통과. 실기기에서 `run_wifi.py` 재실행 시 `[UDP] Fixed target:
  192.168.45.62:9000`이 출력되고, Mac dry-run 브리지에 실제 손 제스처로
  발생한 `EVENT MOVE`/`EVENT CLICK`이 연속 수신됨을 확인 — **집 Wi-Fi에서
  Wi-Fi 연결+웹서버+AI+UDP 마우스 제어가 README 그대로의 실행 경로로
  종단간 성공한 첫 사례.**

### L-4. 배포·정리 상태

- `firmware/wifi.py`, `firmware/smart_glass_server.py`,
  `firmware/transport.py`, `firmware/config.py` 수정분을
  `/sdcard/smart_glass/`에 배포, 보드에서 직접 계산한 SHA-256으로 로컬과
  바이트 일치 확인 완료.
- 진단 중 포트 9000을 점유하고 있던, `--dry-run` 없이 떠 있던 Mac
  브리지 프로세스(PID 53826, 약 26분째 실행 중)를 발견해 중지했다 —
  사용자가 이전에 직접 실행해 둔 것일 수 있어 투명하게 보고함.
- `시연용_README.md`를 이번에 확인된 실제 동작(집 Wi-Fi 우선 시도,
  `[Wi-Fi]`/`[UDP]` 콘솔 메시지, 서브넷 크기별 UDP 목적지 결정 방식, 집
  Wi-Fi 간헐적 실패 시 재실행 안내)에 맞춰 갱신했다.
- Git 커밋/푸시는 수행하지 않았다(지시 사항).

---

## M. 2026-10-23 Wi-Fi 마우스 제어 품질 회귀 조사 — 사용자 요청으로 작업 일시 중단

### 배경

사용자가 "Wi-Fi 시연에서 마우스 제어 품질이 기존 UART 버전보다 심각하게
나빠졌다"고 보고했다(커서 거의 안 움직임/순간이동, MOVE·STOP 반복,
의도하지 않은 CLICK·DRAG, JPEG 압축 실패 반복). **새 알고리즘을 만들지
말고 기존에 정상 동작하던 제스처 구현을 기준으로 회귀 원인을 찾아
복구하라**는 명시적 지시였다. 조사·수정 도중 사용자가 외출을 위해
**작업을 안전하게 중단해 달라고 요청**해서, 아래 상태로 멈췄다. **추가
코드 수정·테스트는 하지 않았다.**

### M-1. 코드 비교 결과 — 제스처 알고리즘 자체는 회귀 없음 (확인 완료)

- `firmware/main.py`(UART, 기존 정상 경로)와 `firmware/smart_glass_server.py`
  (Wi-Fi)를 직접 읽고 비교했다. 둘 다 `hand_tracker.py`/`gesture_controller.py`
  /`mouse_controller.py`를 **완전히 동일한 모듈 그대로** 쓴다 — 복제되거나
  바뀐 부분이 전혀 없다. 즉 **새 알고리즘이 추가되거나 기존 알고리즘이
  변형된 사실은 없다.**
- 두 파일의 유일한 실질적 차이는 카메라 채널 구성(Wi-Fi 쪽만 웹용 채널1을
  추가로 엶)과, 웹 스트리밍/HTTP 처리가 같은 메인 루프에서 함께 실행된다는
  점이다.

### M-2. 실기기 측정 — 카메라 채널 수는 회귀 원인이 아님 (확인 완료)

`experiments/runtime_diagnostics/diag_frame_timing.py`(신규, 로컬+SD 배포
완료)와 `diag_pipeline_baseline.py`(신규, 로컬+SD 배포 완료)로 AI 루프의
프레임 간격(dt)을 직접 측정했다 — 둘 다 `main.py`/`smart_glass_server.py`가
실제 쓰는 클래스(`libs.PipeLine`/`CameraRig`)를 그대로 재사용하고,
제스처 로직은 전혀 호출하지 않는다(프레임 타이밍만 측정).

- **2채널(웹 없음, `CameraRig`)**: n=99, avg=94.2ms(10.6fps), p50=99,
  p95=107, max=116, 90ms 초과=90/99, 180ms 초과=0, 350ms 초과=0.
- **`main.py`가 실제 쓰는 `libs.PipeLine`(UART 경로 그대로)**: n=99,
  avg=91.3ms(11.0fps), p50=98, p95=109, max=119, 90ms 초과=85/99, 180ms
  초과=0, 350ms 초과=0.

두 결과가 통계적으로 동일하다 — **카메라 채널 수(2채널 vs 3채널) 자체는
회귀 원인이 아니다.** 또한 이 결과는 흥미로운 별도 사실도 보여준다: 웹이
전혀 없는 상태에서도 평균 프레임 간격(~91~94ms)이 이미
`gesture_controller.py`의 `click_confirm_ms=90ms`에 아주 가깝다 — 즉
UART 경로도 원래부터 이 임계값에 여유가 거의 없는 상태로 동작해 왔다는
뜻이다(이 자체가 버그라기보다는, 안정적인 베이스라인 위에서는 문제없이
동작해 온 것으로 보인다).

### M-3. 실제 웹 스트리밍 중(3채널+클라이언트 접속) 정량 측정 — 미완료

`diag_frame_timing.py`에 `MODE="3ch_web_streaming"`을 만들어 Mac에서
`curl .../stream`으로 실제 클라이언트를 붙이고 같은 방식으로 재현하려
했으나, 다음 이유로 **깨끗한 수치를 확보하지 못한 채 중단**했다:

- 집 Wi-Fi 연결이 간헐적으로 거부됨(L-2에서 이미 확인된 별개 문제, 이
  작업에서 새로 발견한 것 아님) — 여러 번 재시도 필요.
- `canmv_execute_file` 호출마다 보드가 자체적으로 soft reboot를 하는데,
  Wi-Fi 연결을 별도 호출로 먼저 해두면 그 soft reboot가 소켓 계층을
  리셋해 "no available NIC" 재현 — 진단 스크립트 안에서 Wi-Fi 연결까지
  같은 실행 안에서 하도록 고쳐서 해결함.
- 이후에도 보드가 Wi-Fi+웹+카메라로 몇십 초 넘게 바쁘게 돌면 **MCP 도구의
  시리얼 연결 자체가 끊기는 현상**이 여러 번 재현됐다(재연결하면 바로
  `ready: true`로 복구 — **보드가 실제로 멈춘 것은 아니었다**, 매번
  `print()` 테스트로 확인함). 반복되는 재연결 비용 때문에 정량적
  `over180ms`/`over350ms` 수치는 끝내 받지 못했다.
- **대신 확보한 근거**: 이번 세션 앞부분에서 실제 `run_wifi.py`로 실행한
  진짜 운영 로그에, `JPEG compression failed once; retrying with a new
  frame`가 여러 번 연달아 찍힌 직후 `CLICK_DECISION`(의도하지 않은
  CLICK으로 추정)이 바로 뒤따르는 패턴이 3번 관찰됐다 — 정량적 분포는
  아니지만, 실제 운영 중 발생한 직접적인 상관관계 증거다.

### M-4. 결론 (현재까지의 근거 기준) 및 적용한 수정

- M-1·M-2로 "새 알고리즘 문제"와 "채널 수 문제"는 배제됨.
- M-3의 상관관계 증거(확정적 정량 수치는 아님)를 근거로, **웹 스트리밍
  JPEG 인코딩(`img.compress()`)이 AI 추론과 같은 단일 루프에서 동기적으로
  실행되면서 만드는 불규칙하고 큰 프레임 지연**을 현재까지 가장 유력한
  원인으로 보고, **그 메커니즘만** 최소 범위로 수정했다. 제스처 판정
  임계값이나 필터(`click_confirm_ms`, `fist_confirm_ms`, OneEuroFilter
  등)는 전혀 건드리지 않았다 — "필터를 세게 걸어 증상을 숨기는" 방식이
  아니다.
- **수정 위치**: `firmware/smart_glass_server.py`의 `WebState` —
  이미 선언돼 있었지만 한 번도 실제로 쓰인 적 없던
  `self.frame_interval_ms`(항상 0으로 방치되어 매 루프 인코딩됨)를 실제로
  작동시켰다. 새 상수 `WEB_STREAM_MIN_INTERVAL_MS = 200`을 추가하고,
  `step()`의 `"stream_wait_frame"` 분기에서 이 간격이 지나지 않았으면
  JPEG 인코딩 자체를 건너뛰도록 가드를 추가했다(세션 상태는 그대로 유지,
  다음 루프에서 다시 확인). `gesture_controller.py`/`mouse_controller.py`
  /`hand_tracker.py`는 **한 줄도 수정하지 않았다.**
- **검증 상태**: 로컬 문법 검사(`ast.parse`) 통과, 기존 단위 테스트 78개
  전부 통과(이 파일은 테스트가 직접 import하지 않으므로 회귀 확인용).
  SD카드에 배포 후 보드에서 직접 SHA-256 계산해 로컬과 일치 확인함
  (`d97bab32fb87571ffcd2780fe390a3e249e421d9f8a41b26c61e49c857a219ab`).
  **이 수정이 실제로 dt spike를 줄이는지에 대한 정량적 실기기 재확인은
  하지 못했다**(M-3과 같은 이유로 중단). **실제 손동작으로 커서
  품질·오클릭·오드래그가 개선됐는지는 전혀 검증하지 못했다** — 자동화할
  수 없는 항목이며, 사용자의 직접 실기기 확인이 필요하다.

### M-5. 안전 중단 처리 (사용자 요청)

- 중단 시점에 보드에서 실행 중인 스크립트 없음(`canmv_script_running` →
  `running: false`), 보드 응답 정상(`ready: true`) 확인함.
- Mac 쪽에 남아 있는 백그라운드 프로세스(curl, mac_mouse_bridge 등) 없음
  확인함(`ps aux` 결과 없음) — 정리할 것이 없었다.
- 작성 중이던 `experiments/runtime_diagnostics/diag_verbose_run_wifi.py`는
  **로컬 파일로만 존재**하며, SD카드에 배포하거나 실행한 적 없다(배포 전
  상태에서 중단 요청을 받음). 그대로 보존했다 — 삭제하지 않음.
- 기존에 적용·배포·검증까지 끝난 수정(`firmware/smart_glass_server.py`의
  `WEB_STREAM_MIN_INTERVAL_MS` 추가분, L절의 `wifi.py`/`transport.py`/
  `config.py` 수정분 등)은 전혀 되돌리지 않았다 — 로컬과 SD카드 모두
  그대로 유지.
- Git 커밋/푸시는 하지 않았다(지시 사항, 이번에도 동일).

### M-6. 복귀 후 재개 지점 (다음 작업 순서)

1. **먼저**: `canmv_board_info`로 보드 상태 재확인(전원 재인가 여부와
   무관하게 매 세션 시작 시 하던 대로).
2. `diag_frame_timing.py`의 `MODE="3ch_web_streaming"`을 **같은 방식으로
   한 번 더** 시도해 `WEB_STREAM_MIN_INTERVAL_MS=200` 적용 전/후
   `over90ms`/`over180ms`/`over350ms` 수치를 정량적으로 비교한다 — 이번에는
   Wi-Fi 연결이 간헐적으로 거부되는 문제(L-2)를 먼저 감안하고, 도구 연결이
   끊기면 재연결 1회로 복구만 확인하고 더 재시도하지 않는다(이번 세션에서
   확립한 패턴).
3. 정량 수치가 실제로 개선됐다면(또는 이미 충분한 근거로 판단되면),
   **실제 손동작으로 README 기준 시연 테스트**(UART/Wi-Fi 양쪽, 웹
   스트리밍 켜고 끈 상태 비교)를 사용자에게 요청하거나 함께 진행한다 —
   이 항목은 자동화할 수 없으므로 반드시 사용자 확인이 필요하다.
4. 필요하면 `WEB_STREAM_MIN_INTERVAL_MS` 값(현재 200ms, 임의로 정한
   합리적 기본값)을 실측 결과에 맞춰 조정한다.
5. 작업 4(이 작업 지시의 "4. 테스트 기준" 섹션)에서 요청한 **영구 규칙을
   `CLAUDE.md`에 반영하는 작업은 아직 하지 않았다** — "모든 기능 변경은
   개발용 테스트와 실제 시연 테스트를 구분하고, 최종 완료 판정은
   `시연용_README.md`의 실제 실행 경로를 기준으로 하며, 실기기 검증이
   불가능한 항목은 미검증으로 명시한다"는 원칙을 재개 시 추가해야 한다.
6. `experiments/runtime_diagnostics/`(로컬)와 `/sdcard/runtime_diagnostics/`
   (보드)의 진단 스크립트들은 아직 삭제하지 않았다 — 이번 조사가 완전히
   끝나고 사용자가 실제 품질 개선을 확인한 뒤에 정리 여부를 다시 판단한다.
- Git 커밋/푸시는 재개 후에도 사용자가 별도로 요청하지 않는 한 하지 않는다.

---

## N. 2026-10-23 M절 재개 — JPEG CPU vs 네트워크 전송 분리 계측 + 실제 손동작 검증 + 서버 종료 원인 동시 추적

### 배경

M절에서 중단한 조사를 재개했다. 이번에는 "성능 회귀 검증"과 "서버 종료
원인 추적"을 분리하지 말고 한 번의 실기기 세션에서 동시에 수행하라는
사용자 지시에 따라, 신규 통합 진단 스크립트
`experiments/runtime_diagnostics/diag_stream_breakdown.py`와
`diag_combined_regression.py`를 작성했다(기존 진단 스크립트는 모두 보존).
두 스크립트 모두 `firmware/` 파일을 전혀 수정하지 않고,
`video_stream.encode_jpeg`와 `web_server.ClientSession.queue`/`pump_send`/
`close`/`__init__`을 **런타임에만** monkey-patch해서 계측한다 —
실제 `smart_glass_server.main(transport_kind="udp", enable_web=True)`
(= `run_wifi.py`가 호출하는 것과 동일한 진입점)을 그대로 실행하므로
기존 Wi-Fi 자동 연결·UDP 자동 탐색·제스처 로직은 전혀 바뀌지 않았다.

사용자 Mac을 아이폰 핫스팟('i', 172.20.10.0/28)에 연결해 보드와 같은
네트워크로 맞췄다(이전에는 Mac이 다른 네트워크에 있어 실제 `/stream`
클라이언트 테스트가 불가능했다).

### N-1. 성능 측정 결과 — JPEG CPU 인코딩 vs 네트워크 전송 시간 분리 (실측 완료)

두 번의 독립된 실기기 세션(둘 다 `WEB_STREAM_MIN_INTERVAL_MS=200`,
배포된 수정 그대로)에서 측정했다:

| 세션 | 지속시간 | 클라이언트 | jpeg_encode_ms (CPU) | jpeg 실패율 | network_send_ms | 처리량 |
|---|---|---|---|---|---|---|
| 1차 (dry-run 브리지, 실손동작 포함) | 107.5초 | `/stream` 1개 연결 지속 | n=286, avg=47.1, p50=47, p95=50, max=51 | 42/328 (12.8%) | n=288, avg=177.5, p50=99, **p95=876, max=2558** | ~144.9 KB/s |
| 2차 (실제 마우스 제어 브리지, 후반 `/stream` 연결) | 303.9초 | `/stream` 1개 연결(후반부) | n=593, avg=45.0, p50=45, p95=48, max=51 | 135/728 (18.5%) | n=594, avg=89.6, p50=43, **p95=141, max=1704** | ~182.0 KB/s |

- **확인됨**: JPEG 인코딩(CPU, `img.compress()`) 비용은 두 세션 모두
  **작고 매우 일정함**(45~47ms 평균, 최대 51ms). M절에서 가정했던
  "JPEG 인코딩이 AI loop에 불규칙 지연을 준다"는 최초 가설은 **이 실측으로
  기각된다** — CPU 비용 자체는 변동이 거의 없다.
- **확인됨**: 네트워크 전송 시간(`queue()` 호출~전송 완료)은 CPU 인코딩보다
  훨씬 크고 변동이 크다(p95가 CPU 대비 15~18배, max가 30~50배). **아이폰
  핫스팟의 MJPEG 전송 지연이 JPEG CPU 인코딩보다 지배적인 지연 원인이라는
  직접 측정 증거**다 — 과거 문제 #9("640 B/s")와 같은 방향이지만, 이번
  측정한 실제 처리량(~145~182 KB/s)은 #9보다 훨씬 높다. **#9의 수치가
  이번 조건에 일반화되지는 않는다** — 다른 시점/환경 조건이었을 수 있다.
- **확인됨**: JPEG 압축 1차 시도 실패율은 12.8%~18.5%로, 로그에서
  시각적으로 "거의 매번 실패"처럼 보였던 것(성공 로그는 10프레임마다만
  찍혀서 실패 로그만 눈에 띔)보다 실제로는 낮다.
- **미확정**: `pump_send()`가 논블로킹이라는 코드 근거는 있지만, 네트워크
  전송 지연(p95~876ms, max~2558ms)이 AI loop의 프레임 간격에 실제로 전혀
  영향을 주지 않는지는 이번에 프레임 단위 dt를 따로 기록하지 않아 **직접
  확인하지 못했다** — `main_loop fps`(30프레임 평균)는 두 세션 모두 비정상
  저하 없이 유지됐지만, 이는 거친 평균이라 개별 프레임의 큰 지연을
  가릴 수 있다.

### N-2. 서버 종료 원인 조사 (동시 수행)

- **확인됨**: 두 세션(107.5초, 303.9초) 모두 **유일한 종료는 의도적
  `canmv_stop_script`였다** — 로그에 `Exception: IDE interrupt`가 명확히
  찍히고 `[ORCH] cleanup done`까지 정상 진행됐다. 두 세션 중 어느 쪽도
  JPEG 실패, 네트워크 지연, 메모리 저하로 인한 **설명되지 않는 종료는
  없었다**.
- **중요 — 단정하지 않음**: 이 두 세션 사이, 별도의 짧은 시도에서 사용자가
  "연결해제"를 1회 관찰했다. 이때 내(에이전트)가 상태 확인을 위해
  `canmv_connect_board`로 재연결을 시도했는데, 이 재연결 자체가 보드에
  soft reboot를 유발해 **끊기기 직전의 로그가 전부 소실**됐다. 재연결 후
  보드는 즉시 `ready: true`로 정상 응답했다(물리 전원 재인가 불필요).
  → 이 1회 사건은 `docs/DEV_HISTORY.md` 문제 #21(USBDBG 간헐적 연결 끊김,
  대부분 재연결 1회로 복구)과 같은 패턴으로 보이지만, **그 순간의 정확한
  원인(USBDBG 글리치 / CanMV IDE 자체 표시 / 다른 원인)은 확인할 방법이
  없다.** "107.5초/303.9초 무사고"가 **서버 종료 문제가 해결됐다는 뜻은
  아니다** — 사용자가 명시적으로 이렇게 단정하지 말라고 지시했다.

### N-3. 실제 손동작 검증 (사용자 직접 수행)

- 1차 세션: dry-run 브리지(실제 OS 이벤트 없음)로, 사용자가 실제로 손을
  움직여 MOVE/CLICK/DRAG_START/DRAG/DRAG_END/STOP 패킷이 전부 정상
  수신됨을 확인(터미널 로그 기준). CLICK_DECISION의 pinch_ratio/
  pinch_confirm_ms 값은 모두 합리적인 범위(0.06~0.38, 95~156ms)였다.
- 2차 세션: `--dry-run` 해제한 실제 브리지로 전환, 사용자가 **실제 Mac
  커서로 직접 테스트**했다. 사용자 피드백(원문 그대로): "마우스는 좀
  안정화 된 것 같다" — **200ms throttle 적용 후 체감 품질이 개선된
  것으로 보인다는 긍정적 신호**다. 단, 정량적인 "순간이동/오클릭/오드래그
  재현 여부"를 항목별로 하나씩 확인받지는 않았으므로, **완전한 품질
  검증으로 선언하지 않는다**.
- 사용자가 별도로 보고한 문제: "카메라가 찍는 범위가 짧아서 손 관절이
  일그러지면서 오작동이 있다" — 사용자 본인이 **하드웨어(카메라 FOV/렌즈)
  제약으로 추정**했고, 이번 Wi-Fi/네트워크 지연 조사와는 무관한 **별개
  이슈**로 범위에서 제외했다. 제스처 알고리즘은 수정하지 않았으므로 이
  현상에 대해 아무 조치도 취하지 않았다.

### N-4. 검증된 사실 vs 미해결 가설 (요약)

**검증된 사실**:
1. JPEG CPU 인코딩 비용은 작고 일정하다(45~51ms).
2. 네트워크 전송 지연이 CPU 인코딩보다 훨씬 크고 변동이 크다(최대
   1.7~2.6초) — 핫스팟 네트워크가 JPEG CPU보다 지배적인 지연 원인이라는
   직접 측정 근거.
3. `WEB_STREAM_MIN_INTERVAL_MS=200` 적용 상태에서 두 번의 장시간(107.5초,
   303.9초) 실기기 세션 모두 의도치 않은 종료가 없었다.
4. 실제 손동작 MOVE/CLICK/DRAG/STOP 패킷이 정상적으로 Mac에 도착했고,
   사용자가 주관적으로 "안정화된 것 같다"고 평가했다.

**미해결/가설**:
1. 네트워크 전송 지연(최대 2.6초)이 AI loop의 개별 프레임 dt에 실제로
   영향을 주는지 — 프레임 단위로 직접 대조하지 못했다(가설: 비영향,
   `pump_send()`의 논블로킹 구조 근거는 있으나 미확인).
2. "JPEG 실패 직후 CLICK" 인과관계 — M절에서는 유력해 보였으나, 이번
   실측으로 JPEG CPU 비용 자체가 작다는 게 확인되면서 인과관계가
   처음 가정보다 약할 가능성(가설, 미확인).
3. 이전 "연결해제" 1회 사건의 정확한 원인 — 미확인, 로그 소실.
4. 핫스팟 처리량(이번 145~182 KB/s)이 과거 문제 #9(640 B/s)와 왜 이렇게
   다른지 — 환경/조건 차이로 추정되나 미확인. 전용(비핫스팟) AP에서
   재측정 필요.
5. 카메라 FOV로 인한 손 관절 왜곡 — 사용자 추정대로 하드웨어 제약일
   가능성이 높으나, 이번 조사에서 직접 검증하지 않았고 범위 밖으로
   남겨둠.

### N-5. 배포·정리 상태

- 코드 변경 없음(firmware/ 파일 전부 M절 이후 그대로, 이번 세션은 순수
  진단/계측). `firmware/smart_glass_server.py`의 `WEB_STREAM_MIN_INTERVAL_MS`
  수정은 M절 그대로 유지(되돌리거나 덮어쓰지 않음).
- 신규 진단 파일 `experiments/runtime_diagnostics/diag_stream_breakdown.py`,
  `diag_combined_regression.py`를 로컬에 추가(SD카드에도 배포해 실행함).
  기존 진단 파일(`diag_stage4_fixed_udp.py`, `diag_stage5_small_discovery.py`,
  `diag_frame_timing.py`, `diag_pipeline_baseline.py`, `diag_verbose_run_wifi.py`)은
  모두 그대로 보존(삭제 없음) — 원인 조사가 완전히 끝나지 않았다.
- Mac 쪽 임시 브리지 프로세스(dry-run, 실제 브리지 둘 다)는 테스트 종료
  시점에 정리했다. 남은 백그라운드 프로세스 없음 확인.
- `docs/DEV_HISTORY.md` 문제 #20·#21, "6. 현재 남아 있는 문제" 1·3번,
  "7. 앞으로의 개선 과제"를 이번 실측 결과로 갱신했다(기존 기록 삭제 없이
  보강).
- Git 커밋/푸시는 하지 않았다(지시 사항).
