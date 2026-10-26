# K230D-Zero 배포 절차

별도의 배포 스크립트나 CLI는 **존재하지 않는다.** 이 프로젝트에서 보드와의
유일한 전송 경로는 VS Code CanMV 확장이 쓰는 시리얼 프로토콜이며, 지금까지는
이를 그대로 감싼 MCP 도구(`canmv_write_file`, `canmv_read_file`,
`canmv_stop_script`, `canmv_execute_file`, `canmv_run_script`,
`canmv_board_info` 등)로만 접근해 왔다. 로컬에 `mpremote`/`ampy`/`canmv` 같은
독립 CLI는 설치되어 있지 않다(2026-10-21 확인). 아래 절차는 전부 이 MCP
도구들을 손으로 순서대로 호출하는 것을 전제로 한다 — 자동 실행되는 파이프라인이
아니다.

## 1. Mac ↔ K230D-Zero 연결과 포트 역할

| 포트 | 역할 | 주의 |
|---|---|---|
| `/dev/cu.usbmodem0010000001` (CDC) | 보드 제어/배포 전용(VS Code CanMV, MCP 도구가 쓰는 포트) | 배포/실행은 반드시 이 포트로 |
| `/dev/cu.usbmodem58930597043` (UART2, CH342K) | `mouse_controller.py` → `mac/mac_mouse_bridge.py`로 가는 `@MOUSE|...` 전송 전용 | **배포 작업 중 이 포트는 절대 열거나 점유하지 않는다** |

두 포트는 물리적으로 분리되어 있어 CDC로 배포 작업을 하는 동안 UART2 쪽
mouse bridge를 동시에 켜 둬도 서로 간섭하지 않는다(단, 보드가 소프트
리부트되면 그 순간 실행 중이던 어떤 스크립트든 중단된다는 점은 감안해야 한다).

## 2. 배포 전 준비 사항

- CDC로 보드가 연결되어 있는지 확인(`canmv_board_info` → `connected: true,
  ready: true`).
- 보드에서 현재 실행 중인 스크립트가 있는지 확인(`canmv_script_running`).
  실시연 중(마우스 제어 중)인 `main.py`를 함부로 덮어쓰거나 중단하지 않는다 —
  배포 전에는 반드시 사용자에게 확인한다.
- 배포할 로컬 파일들이 `python3 -m py_compile`을 통과하는지, 관련 있다면
  `python3 -m unittest discover -s tests`가 통과하는지 먼저 확인한다(보드
  없이 가능한 범위의 정적 검증).

## 3. 로컬 경로 ↔ SD카드 경로 매핑

**로컬 폴더 구조와 보드 SD카드 구조는 다르다.** 로컬에서 폴더로 묶여 있다고
보드에도 같은 하위 폴더가 생기는 것이 아니다 — 평탄화해서 올린다.

| 로컬 경로 | 보드 경로 | 비고 |
|---|---|---|
| `firmware/*.py` | `/sdcard/smart_glass/<같은 파일명>` | 평탄화(폴더 제거). 정식 프로젝트 경로. |
| `experiments/wifi_test/*.py` | `/sdcard/wifi_test/<같은 파일명>` | **정식 경로와 분리된 실험 전용 경로.** 섞어서 올리지 않는다. `net_config.py`는 Wi-Fi 비밀번호가 있어 커밋도, 별 생각 없이 로그에 남기지도 않는다. |
| `mac/*.py` | (배포 대상 아님) | Mac에서만 실행. 보드에 올리지 않는다. |

예: `firmware/hand_tracker.py`를 고쳤다면 보드의 `/sdcard/smart_glass/hand_tracker.py`에
쓴다. `firmware/smart_glass_server.py`를 처음 배포한다면 `/sdcard/smart_glass/smart_glass_server.py`로
**새 파일로** 올라가며, 기존 `/sdcard/smart_glass/main.py`는 그대로 남는다(둘
다 공존 가능, 실행은 하나씩만).

## 4. 신규 오케스트레이터 배포 대상 (`smart_glass_server.py`를 올릴 때)

`smart_glass_server.py`는 아래 파일들을 **같은 디렉터리에서** import하므로,
처음 배포하거나 이 중 하나라도 바뀌었다면 전부 같이 올려야 한다
(2026-10-26 기준 최신 목록 — OLED/Wi-Fi/UDP 통합 이후):

- `firmware/smart_glass_server.py`
- `firmware/hand_tracker.py`
- `firmware/gesture_controller.py`
- `firmware/mouse_controller.py`
- `firmware/ui.py`
- `firmware/web_server.py`
- `firmware/video_stream.py`
- `firmware/transport.py`, `firmware/wifi.py`, `firmware/wifi_credentials.py`,
  `firmware/discovery.py` (UART/UDP 전송 분리, Wi-Fi 연결, UDP 자동 탐색)
- `firmware/config.py` (`MOUSE_TRANSPORT`, `MOUSE_UDP_*`,
  `VERBOSE_ORCHESTRATOR_LOGS` 등 — `smart_glass_server.py`가 실제로
  import해서 쓴다. "미사용 placeholder"가 아니다)
- `firmware/display_config.py`, `firmware/ssd1306.py`,
  `firmware/oled_device.py`, `firmware/hand_renderer.py`,
  `firmware/display_ui.py` (VLT-OL016 OLED, `display/README.md` 참고)

`firmware/main.py`(손 추적 단독 실행)와 `firmware/smart_glass.py`는
`smart_glass_server.py` 실행에 필요하지 않다(단, `main.py`는 보드에서
지우지 않고 그대로 둔다). `firmware/run_uart.py`/`run_wifi.py`/
`run_uart_web.py`는 위 전부를 import해서 쓰는 실행 진입점이므로, 셋 중
무엇을 실행하든 위 파일은 전부 배포돼 있어야 한다.

## 5. `main.py` 실행과 `smart_glass_server.py` 실행의 차이

| | `main.py` | `smart_glass_server.py` |
|---|---|---|
| 검증 상태 | 실기기에서 반복 검증됨 | **실기기에서 반복 검증 완료**(카메라+AI+OLED+UART/UDP 마우스+웹서버 전체 조합, `docs/DEV_HISTORY.md` 4-3) |
| 카메라 채널 | 0(디스플레이)+2(AI) 2채널 | 0(디스플레이)+1(웹 RGB565)+2(AI) 최대 3채널 — **실기기 검증 완료** |
| 기능 | 손 추적+마우스 제어+디스플레이 OSD | 위 전부 + OLED 손 관절 표시, UART/Wi-Fi(UDP) 마우스 전송 선택, 웹 MJPEG 스트리밍, `FEATURE_*` 상수로 개별 on/off |
| 동시 실행 | - | `main.py`와 동시에 실행하지 않는다(같은 카메라/UART2 리소스를 쓰므로 충돌) |

처음 보드에서 돌릴 때는 `FEATURE_WEB_SERVER = False`, `FEATURE_WEB_VIDEO = False`로
시작해서 `main.py`와 동일한 2채널 구성으로 먼저 손 추적/마우스 제어 동작이
`main.py`와 같은지 확인한 다음, 웹 기능을 하나씩 켜는 것을 권장한다(아래
11번 참고) — 다만 이 단계별 순서 자체는 이미 여러 차례 실기기로 끝까지
검증됐으므로, "될지 안 될지 모르는 미검증 구성"이 아니라 "디버깅이 필요할
때 되돌아갈 수 있는 순서"로 이해하면 된다.

## 6. AI 모델 등 필수 자산

- `/sdcard/examples/kmodel/hand_det.kmodel`
- `/sdcard/examples/kmodel/handkp_det.kmodel`

둘 다 `firmware/` 배포 대상이 아니라 CanMV 펌웨어의 examples 자산으로,
**이미 SD카드에 있다고 가정**하고 `main.py`/`smart_glass_server.py`가 참조만
한다. 배포 전에 `canmv_stat_file` 등으로 두 경로가 실제로 존재하는지 한 번
확인하는 것을 권장한다 — 펌웨어 버전이 바뀌었거나 SD카드가 교체됐다면
없을 수 있다(이번 세션에서 직접 확인하지는 않았다).

## 7. 검증된 배포 절차: 비교 → 변경 파일 업로드 → 해시 검증 → 실행 테스트

로컬 `firmware/`가 코드의 단일 원본이다. 보드에서 코드를 직접 고치거나,
로컬에 이미 있는 코드를 REPL에서 다시 타이핑해 재구성하지 않는다. 배포
후보 파일마다 아래 네 단계를 순서대로 따른다.

1. **비교(어떤 파일을 올릴지 결정)**: `canmv_read_file(path)`로 보드의
   현재 내용을 읽고, 로컬 `shasum -a 256 firmware/<파일>` 해시와 비교해
   실제로 다른 파일만 골라낸다. 내용이 같으면 올리지 않고 건너뛴다(불필요한
   재배포 방지).
   - 보드 쪽 내용이 로컬에 없는 변경으로 보이면 **곧바로 로컬 내용으로
     덮어쓰지 않는다** — 보드에서만 이루어진 수정이 유실될 수 있으므로,
     차이를 먼저 확인하고 애매하면 사용자에게 확인한다.
2. **변경 파일 업로드**: 1번에서 다르다고 확인된 파일만
   `canmv_write_file(path, content)`로 로컬 파일 내용을 그대로 전달해 쓴다.
3. **해시 검증**: `canmv_read_file(path)`로 방금 쓴 내용을 다시 읽어 로컬과
   바이트 단위(또는 SHA-256, 아래 8번)로 비교한다. `canmv_write_file`의
   `success: true` 응답은 "오류 없이 썼다"는 뜻일 뿐 "내용이 맞다"는
   보장이 아니므로 재다운로드 비교를 생략하지 않는다. 다르면 다음 단계로
   넘어가지 않는다.
4. **실행 테스트**: `canmv_stop_script()`로 기존 실행 중단(없어도 안전하게
   호출 가능) → `canmv_execute_file(path)`로 해시 검증을 통과한 파일만
   실행 → `canmv_terminal_output()`으로 실행 로그 확인(아래 9번). 조용히
   아무 로그도 없거나 `Traceback`이 보이면 실행 실패로 간주하고 정상
   동작으로 보고하지 않는다.

이 네 단계는 이번 세션에서 `experiments/wifi_test/` 코드를 여러 번
배포하면서 실제로 검증됐다.

## 8. 배포 후 일치 검증

```bash
shasum -a 256 firmware/<파일>
```
로 로컬 해시를 구하고, `canmv_read_file`로 받은 내용을 로컬에 같은 내용으로
저장한 뒤 다시 `shasum -a 256`으로 비교한다(또는 `diff`로 바이트 비교). **둘이
다르면 절대 실행하지 않는다.** `canmv_write_file`의 응답이 `success: true`인
것은 "오류 없이 썼다"는 뜻이지 "내용이 맞다"는 보장이 아니므로, 재다운로드
비교를 생략하지 않는다.

## 9. 실행 및 정상 동작 확인

`canmv_execute_file` 직후 `canmv_terminal_output`으로 시작 로그를 확인한다.
`main.py` 계열은 `WLAN isconnected=...`, 카메라 초기화 로그
(`find sensor ov5647_csi2...`) 등이 뜨는지 확인한다. 조용히 아무 로그도 없거나
`Traceback`이 보이면 실행이 실패한 것이므로 **정상 동작으로 보고하지 않는다.**

## 10. 실패 시 복구

- `firmware/main.py`는 이번 작업에서 전혀 수정하지 않았다. `smart_glass_server.py`
  배포/실행이 실패해도 `/sdcard/smart_glass/main.py`는 그대로 남아 있으므로,
  `canmv_execute_file("/sdcard/smart_glass/main.py")`로 바로 기존 동작으로
  되돌릴 수 있다.
- SD카드 삭제·포맷·초기화, 펌웨어 교체는 사전 승인 없이 하지 않는다.
- 보드 소프트 리부트 직후 소켓 생성이 `OSError: no available NIC`로 실패할
  수 있다(Wi-Fi 링크 자체는 살아있어도 소켓 계층이 아직 준비 안 된 레이스
  컨디션, §13 참고) — 수백 ms 재시도로 완화 가능함을 실측했다(`experiments/wifi_test/mjpeg_stream_test.py`
  의 bind 재시도 루프 참고).

## 11. 기능별 ON/OFF 단계별 테스트 순서 (`smart_glass_server.py`)

`FEATURE_*` 상수(파일 상단)를 아래 순서로 켜 가며 확인할 것을 권장한다 — 한
번에 다 켜고 뭐가 문제인지 못 찾는 상황을 피하기 위함이다.

1. `FEATURE_HAND_RECOGNITION=True`, `FEATURE_MOUSE_CONTROL=True`,
   `FEATURE_DISPLAY_OSD=True`, `FEATURE_WEB_SERVER=False`, `FEATURE_WEB_VIDEO=False`
   → `main.py`와 동일한 2채널 구성. 손 추적/마우스 제어/OSD가 `main.py`와
   똑같이 동작하는지만 먼저 확인.
2. 위 상태에서 `FEATURE_WEB_SERVER=True`, `FEATURE_WEB_VIDEO=False`만 추가
   → HTTP 서버는 뜨되 `/snapshot`, `/stream`은 응답하지 않는 상태. 포트가
   정상적으로 bind되는지, 손 추적 FPS에 영향이 있는지 확인(3채널 센서 구성
   없이, 서버 루프 자체의 오버헤드만 분리해서 보기 위함).
3. `FEATURE_WEB_VIDEO=True` 추가(3채널 센서 구성 진입점) → 여기서 처음으로
   채널 0+1+2 동시 구성이 시도된다. 가장 실패 가능성이 높은 단계이므로 카메라
   초기화 로그를 자세히 본다.
4. `FEATURE_WEB_JOINTS=True` 추가 → 웹 영상에 관절이 올바른 위치/스케일로
   그려지는지 확인(RGB565 640×480과 AI RGB888P 640×360 간 좌표 변환).

## 12. Wi-Fi가 필요한 테스트 vs USB만 필요한 테스트

| 필요 연결 | 항목 |
|---|---|
| USB(CDC)만 | 파일 배포/검증/실행, 손 추적, 마우스 제어, 디스플레이 OSD, 위 11번의 1~2단계 |
| Wi-Fi(아이폰 핫스팟 등) 추가 필요 | `/snapshot`, `/stream` 실제 응답 확인(11번의 3~4단계), `experiments/wifi_test/`의 TCP/HTTP/MJPEG 테스트 전체 |

손 추적/마우스 제어 자체는 Wi-Fi 없이도 전부 검증 가능하다.

## 13. 남은 실기기 검증 항목 (관측 vs 추정 구분)

`experiments/wifi_test/WIFI_TEST_REPORT.md`에서 **실제로 관측된 사실**:

- `Sensor.YUV420SP` + `Image.compress()`는 색상 왜곡+좌우 중복을 일으킴(재현
  확인됨). `Sensor.RGB565` + `Image.compress()` + `set_hmirror`/`set_vflip`은
  정상 JPEG을 만듦(로컬 USB와 실제 Wi-Fi `/snapshot` 양쪽에서 확인됨).
  **이 사실이 재발하지 않도록, 웹 영상 경로에 `Sensor.YUV420SP`를 다시 쓰지
  않는다.**
- 같은 아이폰 핫스팟, 같은 두 기기 사이에서 `/snapshot` 응답 속도가
  요청마다 0.4초~21.5초로 50배 이상 요동쳤고, `/stream` 연속 전송은 3번
  모두 프레임 3~4개 전후로 15초 타임아웃(`OSError(110)`)에 걸렸다. HTTP
  헤더/소켓 처리 자체는 TTFB 83ms~1.25s로 항상 빨랐다.

위 관측에 대한 **추정(미확정) 원인**: 아이폰 개인용 핫스팟의 무선 처리량
자체가 불안정한 것으로 보인다("최대 호환성" 토글, Tailscale 등은 근거를
가지고 배제했다 — 자세한 배제 과정은 WIFI_TEST_REPORT.md 참고). 다른
네트워크(전용 공유기 등)에서 같은 측정을 해 본 적은 없다 — 이것이
핫스팟 고유의 문제인지, 이 정도 거리/환경의 일반적인 2.4GHz 혼잡 문제인지는
구분되지 않았다.

## 14. 2026-10-21~22 HTTP bind 실패, `MediaManager`/`Display` 충돌, UART `ImportError` — 해결 경위

이 자리에는 원래 2026-10-21~22에 걸친 단계별 디버깅 세션 기록(1단계/2단계
웹서버 켜기, HTTP bind 실패 원인 추적, UART `ImportError` 수정 등)이 그대로
남아 있었다. 그 내용은 전부 `docs/DEV_HISTORY.md`의 문제 이력 표(섹션 3,
#10~#12, #14)로 흡수·정리됐으므로 이 문서에서는 중복 보관하지 않는다
(2026-10-26 문서 정리). 요점만 남기면:

- `MediaManager.init()`을 `Display.init()`과 같이 호출하면 보드가 완전히
  멈춘다 — `Display.init()`을 쓰는 경로에서는 `MediaManager.init()`을
  호출하지 않는다(DEV_HISTORY #11).
- `from media.media import *`는 `import sys`보다 먼저 두면 `sys` 이름을
  덮어쓴다 — wildcard import 뒤에 `import sys`를 둔다(DEV_HISTORY #10).
- HTTP 포트 bind 실패는 핫스팟 꺼짐이 아니라 WLAN/NIC 핸들 초기화 누락이
  원인이었다 — 웹서버 시작 전 WLAN 핸들을 생성·유지하도록 수정해 해결
  완료(DEV_HISTORY #12).
- `run_uart.py`/`run_wifi.py`의 `ImportError`는 `sys.path`에
  `/sdcard/smart_glass`를 넣지 않아서였다 — `PROJECT_DIR` 삽입 패턴을
  두 파일에도 추가해 해결 완료(DEV_HISTORY #14).

세부 로그, 실측 수치, 재현 절차가 필요하면 `docs/DEV_HISTORY.md`의 해당
번호를 참고한다.
