# EdgeGlass-AI 개발 이력 및 문제 해결 기록

조사일: 2026-10-23 (KST)
조사 범위: 모든 로컬 Git 참조(`git log --all`, 28개 고유 커밋), 두 로컬/원격 추적
브랜치(`main`, `presentation`), 커밋 본문·주요 diff, README/배포 문서/작업 추적 문서,
`experiments/`·`logs/`, 현재 작업 트리, Git 전체 객체의 민감정보·불필요 파일 흔적.
하드웨어 구매·선정 및 일반적인 환경 구축 과정은 조사 대상에서 제외했다.

## 판정 기준

- **실기기 검증 완료**: 보드 또는 Mac 종단간 로그/관찰이 문서에 남아 있다.
- **코드·로컬 검증 완료**: 단위 테스트·문법 검사만 확인되었으며 보드 검증은 아니다.
- **임시 우회 적용**: 위험한 경로를 피하거나 범위를 제한해 사용한다.
- **원인 확인, 미해결 / 원인 미확정**: 관측과 추정을 섞지 않는다.

커밋 본문에 "완료"라고 적혀도 위 근거가 없으면 실기기 완료로 분류하지 않았다.
해시의 짧은 표기는 모두 Git에서 해석 가능한 접두사다.

## 1. 프로젝트 개발 연혁

| 시기 | 구현 단계와 결과 | 근거 |
|---|---|---|
| 날짜 미상 (10-21 Wi-Fi/JPEG 기록 이전) | K230D-Zero 내장 Wi-Fi만으로 아이폰 핫스팟의 TCP client/server를 실기기에서 확인했다. TCP 연결성·MicroPython socket API 호환성을 먼저 분리 확인했으며, HTTP·MJPEG는 이 단계에서 시험하지 않았다. | 사용자가 보존한 당시 실험 기록(본 문서 10-4-1); Git 커밋 근거 아님 |
| 10-04 | K230D-Zero/CanMV용 손 검출·랜드마크, 제스처, OSD, Mac Quartz bridge를 처음 모듈로 분리했다. K230 import 경로·의존성, UART2 분리, 제스처 전환/좌표 보정이 이어졌다. | `a8ff735`~`2c5ee3d` |
| 10-06 | MOVE를 상대 이동으로 재설계한 뒤 필터와 안정 기준점을 추가했다. ghost click, FIST/손 유실 진단을 UART2 CSV로 남기기 시작했다. | `fd0a6be`~`cd7f50f` |
| 10-13~14 | 발표 슬라이드·이미지와 20.9 MB 시연 영상을 `presentation` 브랜치에 추가했다. | `fdea673`, `f25017b` |
| 10-21 오전 | 내장 Wi-Fi의 TCP/HTTP/MJPEG 단독 실험으로 OV5647 JPEG 포맷 및 Wi-Fi 연결 문제를 분리 진단했다. | `cefb100` 및 `experiments/wifi_test/WIFI_TEST_REPORT.md` |
| 10-21 오후 | 기존 단독 `main.py`는 보존하고, 3채널 카메라·웹·AI·OSD를 한 루프에 묶은 `smart_glass_server.py`로 모듈화했다. 실기기 단계 검증 중 MediaManager/Display 충돌과 HTTP bind를 해결했다. | `8fd7c89`, `cba31d6`, `791d3f5`, `51ce689` |
| 10-22 | UART와 Wi-Fi UDP 전송을 공통 transport로 분리했다. 실행 프로필의 CanMV import 오류 및 종료 시 DRAG 버튼 고착을 보완했다. | `a7e4565`, `447cb94` |
| 10-23 | 고정 IP 의존을 `@HELLO/@ACK` 자동 탐색으로 대체하고, 집 Wi-Fi 우선/핫스팟 폴백을 넣었다. MicroPython `decode` 호환성 문제를 고쳤다. 현재는 JPEG/제스처 품질 회귀를 진단 중이다. | `7ceda8d`, `25452f0`, `5cb0e66`, `87ff5c7` 및 미커밋 변경 |

### 브랜치와 중복 커밋

- `main`은 `87ff5c7`까지의 기능 이력이다. `presentation`은 `f25017b`에서
  갈라져 발표 영상만 추가했으며 핵심 firmware 변경은 없다.
- `7ceda8d`/`3eaca6e` 및 `25452f0`/`52890ff`는 각각 내용과 시각이 같은
  병렬 커밋 쌍이다. `main`에는 전자 쌍이 도달하고, 후자 쌍은 별도 참조에서만
  보인다. 기능 이력/문제 수를 두 번 세지 않았다.
- `5cb0e66`은 코드 변경 커밋이 아니라 `WORK_TRACKER.md`의 긴 진단 기록이
  커밋 제목에 잘못 들어간 형식 이상 커밋이다. 그 기록의 사실은 아래에 반영했다.

## 2. 단계별 구현 기능

1. **K230/CanMV 기본 경로**: OV5647 카메라, `hand_det.kmodel` +
   `handkp_det.kmodel`, OSD, 손가락·FIST 기반 MOVE/CLICK/DRAG/STOP,
   UART2 `@MOUSE` 프로토콜과 macOS CoreGraphics bridge.
2. **커서 안정화**: 중립점 방식에서 프레임 상대 이동으로 바꾸고, One Euro
   Filter·2D dead zone·기준점 동기화를 추가했다.
3. **관측성**: `@TRACK` CSV, CLICK/전환 로그, Wi-Fi 단독 JPEG/TCP/HTTP/MJPEG
   실험과 런타임 진단 스크립트를 추가했다.
4. **웹 통합**: 단독 `main.py`는 보존하고, `smart_glass_server.py`가 카메라
   채널 0(OSD), 1(RGB565 웹), 2(AI)의 한 프레임 추론 결과를 공유한다.
5. **무선 마우스**: UART/UDP transport 선택, UDP bridge watchdog, Wi-Fi 재사용,
   자동 IP 탐색 및 홈 Wi-Fi→핫스팟 폴백을 구현했다.

## 3. 전체 문제 발생 및 해결 이력

| # | 시기/관련 커밋 | 기능·증상 | 원인과 시도 | 최종 조치·주요 파일 | 검증과 현재 상태 |
|---|---|---|---|---|---|
| 1 | 10-04 `0ad2585` | CanMV에서 K230 모듈 import/누락 의존성 오류 | 커밋 diff는 `hand_tracker.py`, `main.py`의 import만 고친 것을 보인다. 당시 상세 오류 로그는 없다. | import 경로·의존성 보완. | **기록 부족**: 코드 변경은 확인되나 실기기 재현/검증 근거가 없다. |
| 2 | 10-04 `402a454` | Preview용 USB CDC와 mouse bridge가 같은 포트를 쓰면 충돌할 위험 | mouse 전송을 UART2 CH342K 전용으로 분리했다. | `mouse_controller.py`, `mac_mouse_bridge.py`, README. | README는 `/dev/cu.usbmodem58930597043`을 검증된 UART2로 기록. **실기기 검증 완료**(후속 WORK_TRACKER의 UART 송신 근거). |
| 3 | 10-04 `859929`, `2c5ee3d` | 제스처 전환에서 커서가 튀고, 이동 범위/DRAG 떨림이 불량 | 상태 전환 때 기준 좌표가 동기화되지 않은 것으로 코드 수정에서 확인된다. | `gesture_controller.py`의 기준점·범위·DRAG 보정. | 회귀 테스트는 존재하나 당시 보드 관찰 상세는 부족. **코드·로컬 검증 완료, 실기기 근거 일부 부족**. |
| 4 | 10-06 `fd0a6be` | 중립점 속도 누적 방식에서 손을 멈춰도 화면 끝까지 드리프트 | 프레임 간 상대 이동으로 변경했지만 랜드마크 미세 진동이 그대로 이동에 반영됐다. | 상대 이동으로 전환, 전환/재획득 테스트 추가. | 커밋이 실제 K230 떨림 잔존을 명시. **원인 확인, 미해결(당시)**. |
| 5 | 10-06 `8d8cb3f` | 상대 이동 후 커서 떨림과 빠른 이동 뒤 잔여 이동 | landmark noise가 상대 delta에 반영됨. | One Euro Filter, 2D 안정 기준점, 정지 보정. | 카메라 흔들림 모사 회귀 테스트. 후속 UART 경로가 반복 실기기 검증됐지만 수치 기록은 제한적. **실기기 사용 가능으로 확인, 정량 품질 근거 부족**. |
| 6 | 10-06 `a68dfa5`, `36c72cf` | FIST/손 유실 뒤 ghost click, fingertip pointer 불일치, CLICK 원인 파악 곤란 | pinch 후보 상태가 남고 진단 정보가 없었다. | 후보 초기화, 실제 fingertip 표시, `@TRACK` CSV와 수신 예외 격리. | 전환·전송 테스트 및 추적 CSV 4개(총 4,952행)가 남아 있다. **코드·진단 완료; ghost click의 완전한 실기기 종결 근거는 부족**. |
| 7 | 10-21 `cefb100` | `YUV420SP + Image.compress()` JPEG가 색 왜곡·좌우 중복 | 네트워크 없이 `jpeg_format_test.py`로 재현해 포맷 조합이 원인임을 분리했다. | 웹 캡처를 RGB565로 전환하고 mirror/flip 설정. | USB/SD 및 Wi-Fi `/snapshot`에서 정상 색·방향 확인. **실기기 검증 완료**. |
| 8 | 10-21 `cefb100` | Wi-Fi 연결이 자주 실패하거나 40초 이상 걸림 | `wlan.connect()` 반복 호출이 handshake를 중단시킨다고 실기기에서 확인. | connect는 한 번만 호출하고 최대 60초 passive wait. | 실제 IP 출력·연결 성공. 핫스팟 환경은 여전히 느리고 불안정. **해결(연결 방식), 환경 불안정은 미해결**. |
| 9 | 10-21 `cefb100` | 아이폰 핫스팟에서 MJPEG가 약 640 B/s, 18 KB 프레임에 29초, 3~4프레임 뒤 timeout | HTTP/TCP와 JPEG 포맷은 분리해 정상임을 확인했지만, 핫스팟/일반 2.4 GHz 중 원인을 분리하지 못했다. | 별도 구현 수정 없이 안정적 AP에서 재시험을 남김. | snapshot은 성공; 연속 MJPEG는 미검증/실패. **원인 미확정, 미해결**. |
| 10 | 10-21 `8fd7c89`~`cba31d6` | 새 오케스트레이터에서 `sys.path`가 `AttributeError`로 죽음 | `from media.media import *`가 `sys` 이름을 덮어씀. `main.py`와 비교해 확인. | wildcard import 뒤에 `import sys`를 둠. `smart_glass_server.py`. | 동일 오류 재발 없이 이후 실행 통과. **실기기 검증 완료**. |
| 11 | 10-21 `cba31d6` | `Display.init()` 뒤 `MediaManager.init()` 시 보드 complete hang, 물리 전원 재인가 필요 | CanMV stub의 deprecated 표기와 검증된 `PipeLine` 경로 비교로 충돌 확인. | display 사용 시 `MediaManager.init/deinit`을 호출하지 않음. | 2·3채널에서 재발 없음. **실기기 검증 완료**. |
| 12 | 10-21 `cba31d6`, `791d3f5` | HTTP 8060 bind 실패/초기 무응답, 이후 `bind failed after 20 retries` | WLAN/NIC 초기화 누락과 오류 내용 소실을 발견. Wi-Fi 꺼짐만이 원인은 아님도 재현. | Wi-Fi/NIC 초기화, bind 원인 로깅·재시도, JPEG 1회 재시도. | `/` 200, 640×480 snapshot, MJPEG, AI+UART 동시 동작을 커밋이 실기기로 기록. **실기기 검증 완료**; 핫스팟 처리량 문제는 별개로 남음. |
| 13 | 10-21 `51ce689` | 시연 시 CanMV REPL에서 Wi-Fi 연결 절차가 길고 오류 가능 | 이미 검증된 `net.py`를 재사용. | 한 줄 `demo_wifi.py`. | 전원 재인가 뒤 IP 출력, 전체 시연 절차 재검증. **실기기 검증 완료**. |
| 14 | 10-22 `a7e4565`, `447cb94` | Wi-Fi 마우스 기능 추가 뒤 `run_uart.py`/`run_wifi.py`가 `ImportError: no module named smart_glass_server`; 중단 중 DRAG button이 남음 | CanMV가 실행 스크립트 디렉터리를 `sys.path`에 자동 추가하지 않음; orchestrator finally에 close 누락. | 실행 진입점에서 `PROJECT_DIR` 삽입, `mouse_controller.close()`, UDP watchdog/keep-alive. | 45개 테스트, `run_uart.py`의 카메라·AI·제스처·UART 실기기 확인. Wi-Fi 종단간은 당시 미검증. **UART 완료; Wi-Fi는 후속 #17에서 완료**. |
| 15 | 10-23 `7ceda8d` | 고정 Mac IP가 핫스팟 재연결 때 깨짐 | 브로드캐스트는 AP 격리 등으로 검증되지 않아 채택하지 않았다. | 서브넷 `@HELLO/@ACK`, 등록/재등록, 64-host 상한·고정 IP fallback. `discovery.py`, `transport.py`, bridge. | 70개 로컬 테스트만. 이 커밋 자체는 **코드·로컬 검증 완료**. |
| 16 | 10-23 `25452f0` | 집 Wi-Fi 우선·핫스팟 폴백 필요 | 단일 SSID 설계. | SSID 목록 순차 시도, 연결 SSID 반환. `wifi.py`, server, tests. | 73개 테스트. 커밋 시점 실기기 미검증이나 #18에서 홈 Wi-Fi 동작 관찰. **실기기 검증 완료(성공 경로); 실패→폴백 전환은 미검증**. |
| 17 | 10-23 미커밋 기록 `5cb0e66` | 자동 탐색 ACK 뒤 `TypeError: function doesn't take keyword arguments`, 메인 루프 종료 | 이 MicroPython의 `bytes.decode`가 keyword argument를 받지 않음을 REPL로 확인. | `errors="replace"`를 위치 인자로 변경. `firmware/discovery.py`. | 73개 테스트, 5-host 탐색에서 Mac 등록·MOVE 수신, AI+웹+카메라 동시 실행. **실기기 검증 완료**. |
| 18 | 10-23 `87ff5c7` 및 직전 진단 | Wi-Fi 연결 실패가 다음 네트워크로 안 넘어가거나 UDP 오류가 전체 AI/웹을 종료 | `wlan.connect()` 반환값 미점검, transport 예외가 최상위까지 전파. | 반환값/다음 후보 처리, 집 Wi-Fi 큰 scan 시 고정 IP fallback, transport 예외 격리. | 웹 접속·AI 제스처 확인. 예외 격리 분기는 의도적으로 실기기 trigger하지 않았다. **연결/고정 UDP는 실기기 완료; 예외 격리는 코드·로컬 검증 완료**. |
| 19 | 10-23 미커밋 `WORK_TRACKER` M절 | `/24` 253개 UDP 목적지 scan 중 보드 30초 이상 무응답, 물리 전원 재인가 | ACK까지 도달하지 않아 #17 decode 버그가 직접 원인이 아님. ARP/네트워크 스택, 메모리, KPU 경쟁은 가설일 뿐이다. | 상한을 64로 되돌리고 5-host 단계만 검증; 20~30 host 단계 테스트를 보류. | 5-host는 성공, 64/253 host는 미검증. **임시 우회 적용, 원인 미확정**. |
| 20 | 10-23 현재 미커밋, 실측 갱신 10-23 | Wi-Fi 시연에서 JPEG 압축 실패 반복 뒤 MOVE/STOP 반복, 순간이동, 오CLICK/오DRAG | 최초 가설(synchronous `img.compress()`가 단일 AI loop에 불규칙 지연)은 **실측으로 기각**: `video_stream.encode_jpeg`와 `web_server.ClientSession.queue/pump_send`를 런타임 monkey-patch로 직접 계측(`diag_stream_breakdown.py`, `diag_combined_regression.py`, firmware 파일은 미수정)한 결과 — JPEG 인코딩(CPU)은 n=286, avg=47.1ms/p95=50ms/max=51ms로 작고 일정함. 반면 네트워크 전송(`queue()`~전송 완료)은 n=288, avg=177.5ms/p95=876ms/**max=2558ms**로 훨씬 크고 변동이 큼 — 핫스팟 MJPEG 지연(#9)이 JPEG CPU 비용보다 지배적인 지연 원인이라는 **확인된** 근거. 단 `pump_send()`가 논블로킹이라 이 네트워크 지연 자체가 AI loop를 직접 멈추지는 않는 것으로 보여(스트리밍 중 main_loop fps 8.2~9.1 유지), "JPEG 실패 직후 CLICK" 상관관계가 처음 가정보다 약한 인과관계일 가능성 — **미확정, 계속 조사 필요**. JPEG 압축 실패율도 실측 328회 중 42회(~12.8%)로, 로그에 실패만 매번 찍혀 보였던 것(성공은 10프레임마다만 로그)보다 낮음. | 미사용 `frame_interval_ms`를 실제 연결해 MJPEG JPEG 인코딩을 최소 200 ms 간격으로 throttling. `firmware/smart_glass_server.py`. | AST parse, 78 tests, SD hash 일치. 실기기 실측(위 JPEG/네트워크 분리 계측) 완료, 실제 브라우저 `/stream` + 실제 손동작 동시 진행 107.5초간 비정상 종료 없음(유일한 종료는 의도적 `stop_script`, "IDE interrupt"로 구분됨 — 단 이것으로 종료 문제 해결을 단정하지 않음, #21 참고). **원인 가설이 JPEG CPU→네트워크 지연으로 갱신됨; 인과관계(JPEG 실패→오CLICK)와 실제 체감 품질은 여전히 미확정**. 같은 조건의 2차 세션(303.9초, dry-run 해제한 실제 Mac 커서 제어 + 후반 실제 `/stream` 클라이언트)도 비정상 종료 없이 동일 경향(CPU 작고 일정/네트워크 변동 큼) 재확인; 사용자가 실제 커서로 테스트 후 "마우스는 좀 안정화 된 것 같다"고 평가(주관적, 정량 항목별 확인은 아님) — **이것으로 회귀 해결을 단정하지 않음**. |
| 21 | 10-21 이후 문서 기록, 10-23 재현 | 보드 제어 중 USBDBG `short read`/`Not connected`가 간헐 발생했고, 일부 hang 뒤에는 CDC 제어 채널도 복구되지 않음 | `WORK_TRACKER` E-2는 이 오류가 여러 번 발생했다고 기록한다. 대부분은 CDC 재연결 1회로 복구했으나, MediaManager 충돌 및 대규모 UDP scan 사건 뒤에는 물리 전원 재인가가 필요했다. 10-23 실제 Wi-Fi 스트리밍+UDP 마우스 제어 동시 실행 중 사용자가 "연결해제"를 1회 관찰; 재연결로 보드는 즉시 정상 응답(`ready: true`)했으나 끊기기 직전 로그는 재연결의 soft reboot로 소실돼 **그 1회의 정확한 원인은 미확인**(CDC/USBDBG 글리치인지, CanMV IDE 자체의 연결 표시인지 구분 못함). | CDC `/dev/cu.usbmodem0010000001`로 보드 상태(`connected`, `ready`)를 확인하고 재연결은 한 번만 시도; 계속 실패하면 전원 재인가 후 상태·REPL 응답을 확인. | **임시 복구 절차 실기기 확인**(10-23 재현 사례도 1회 재연결로 즉시 복구). USBDBG 오류의 근본 원인과 "초기 IDE 목록 미표시" 사건의 직접 연관은 기록상 확인 불가. |
| 22 | 날짜 미상, 10-21 이전의 사용자 보존 실험 기록 | K230D TCP server의 최초 `accept()`가 `EAGAIN (Errno 11)`로 실패했고, ping timeout 때문에 네트워크 자체가 실패한 것처럼 보일 수 있었음 | `setblocking(True)`만으로는 해결되지 않았다. 소켓을 새로 만들고 `SO_REUSEADDR`→`bind()`→`listen(5)` 순으로 다시 설정한 뒤 Mac TCP 연결과 `accept()`가 성공했으나, 어느 한 변경이 결정적이었는지는 기록만으로 분리 불가. | TCP server 재생성·재설정. `select`/`poll` 사용 가능성도 확인. | **TCP client/server 실기기 검증 완료**. HTTP 응답·MJPEG는 이 단계에서 미검증이며, ping timeout은 TCP 실패와 동치로 판정하지 않음. |
| 23 | 10-23 실기기 보고 | 손이 카메라에 가까워지면(촬영 범위/FOV 한계로 추정) 손 관절(keypoint)이 일그러져 제스처 오작동 발생 | 가설 — 사용자가 카메라 렌즈/FOV 하드웨어 제약으로 추정. 근거리에서 광각 렌즈 왜곡이 커지는 일반적 특성과 방향은 맞으나, 실측·원인 분리는 하지 않음. | 조치 없음 — Wi-Fi/네트워크 지연 조사(#20)와 무관한 별개 이슈로 범위 밖으로 둠. 제스처 알고리즘(`gesture_controller.py` 등) 수정 금지 지시에 따라 임계값 조정 등 어떤 변경도 시도하지 않음. | **미해결**. 하드웨어 제약인지, 소프트웨어(ROI/크롭 로직)로 완화 가능한지 분리 검증되지 않음. |
| 24 | 10-23 `experiments/lcd_test/` 미커밋 | GMT130-V1.0(ST7789 240x240) SPI LCD 단독 테스트 — (a) 이전엔 LCD 미연결 상태에서 `machine.SPI_LCD()` 생성자만 호출해도 보드가 즉시 소프트 리부트(2회 확인); (b) 실제 7핀 배선·전원 연결 후 재시도하자 생성자 크래시는 처음으로 발생하지 않고 `color_test`/`text_test`까지 예외 없이 "PASSED"로 끝났으나, 패널에는 **실제로 아무 색도 표시되지 않음**(사용자 시각 확인). | (a) 미연결 상태 크래시: 확인됨 — CanMV v1.8의 `SPI_LCD(spi, dc, cs, rst)` 생성자가 패널 부재 시 그대로 크래시(원인 자체는 미분석, 재현만 확인). (b) "코드는 성공, 화면은 무출력": SPI가 쓰기 전용이라 소프트웨어로 LCD 도달 여부를 검증할 수 없음 — 가설 2개를 세워 각각 테스트함. | - (실패) `BLK_ACTIVE_LOW`를 True→False로 전환 후 재실행 — 화면 변화 없음. 백라이트는 VCC/GND 연결만으로 이미 켜져 있었던 것으로 확인돼, 백라이트 극성은 원인이 아니라는 근거. <br>- (실패) 공식 예제(`examples/03-Machine/spi_lcd_show.py`)와 비교해 RST 핀의 FPIOA 레벨 pull-up(`fpioa.set_function(pin, func, pu=1)`) 누락을 발견, `_make_pin()`에 `fpioa_pu` 파라미터를 추가해 RES(IO20)에 동일하게 적용 — 재실행에도 화면 변화 없음. <br>- (실패) 사용자가 제조사 페이지/CanMV 공식 SPI_LCD API/동일 LCD의 SPI Mode 3 흑백화면 해결 사례(블로그) 3건을 조사해 제공 — 기존 코드가 이미 Mode 3(polarity=1, phase=1)였음을 확인하고, 신규 스크립트 `lcd_mode_test.py`(단색 채우기만 하는 최소 테스트, `lcd_test.py`는 그대로 보존)로 SPI 속도를 20MHz→1MHz로 낮춰 Mode 3 재시도 — 화면 변화 없음(사용자 확인: "안보여어"). <br>- (결과 대기) 같은 1MHz에서 Mode 0(polarity=0, phase=0)으로 전환해 재실행 — 코드는 PASSED, **사용자 시각 확인은 아직 받지 못함**(점심 시간으로 중단, 복귀 후 확인 예정). | (미해결) — 소프트웨어 레벨 가설 중 백라이트 극성, RST pull-up, SPI 속도(20MHz→1MHz, Mode 3) 전부 기각됨(화면 변화 없음). 남은 유력 가설(미확인)은 여전히 점퍼선 접촉 불량(SCK/SDA/RES/DC 중 하나 이상) 또는 GMT130-V1.0에 `SPI_LCD`의 기본 ST7789 초기화 시퀀스가 맞지 않을 가능성(가설, 미검증) — Mode 0 결과를 봐야 더 좁혀짐. | (a)는 **실기기 재현 확인(크래시 자체)**; (b)의 "코드 PASSED"는 실기기로 반복 확인됐으나 **"실제 화면 출력 성공"은 지금까지 4회 시도(기본 설정 2회+1MHz Mode3 1회+1MHz Mode0 1회) 모두 미확인/실패로 확정**(코드 실행 성공과 시각적 성공을 동일시하지 않음). |

## 4. 주요 기술적 의사결정과 변경 이유

- **기존 `main.py` 보존**: 검증된 2채널 UART 경로를 rollback 기준으로 남기고,
  웹 통합은 별도 `smart_glass_server.py`에 넣었다. 손 추적·제스처·mouse
  controller는 복제하지 않고 공유한다.
- **flat 배포 유지**: 로컬은 `firmware/`, `mac/`, `experiments/`로 정리하되,
  보드에는 `firmware/*.py`를 `/sdcard/smart_glass/`로 평탄화한다. CanMV의
  package/import 제약과 기존 경로 호환성 때문이다.
- **RGB565 웹 인코딩**: 실기기 재현된 YUV420SP JPEG 손상을 피한 결정이다.
- **단계별 기능 플래그**: 2채널 AI→웹 server→3채널 영상→관절 overlay 순으로
  리소스 문제를 분리한다.
- **UART와 UDP를 interface로 분리**: 검증된 UART의 기본 동작을 유지하면서
  Wi-Fi 경로만 선택 가능하게 했다.
- **broadcast 대신 `@HELLO/@ACK`**: broadcast/AP 격리의 미검증 가정 대신,
  실제 수신 주소로 응답하는 등록 방식을 택했다. 단, 과도한 scan은 상한으로
  제한한다.

### 4-1. USB CDC와 CH342K UART2의 역할 분리 (2차 검증 보완)

확인된 포트 역할은 다음과 같다. 이 구분은 장비 선정의 설명이 아니라, 실제
배포·실행 중 포트 충돌을 피하기 위한 운영 사실이다.

| 경로 | 확인된 역할 | 확인된 사용/복구 방식 |
|---|---|---|
| `/dev/cu.usbmodem0010000001` | K230 USB CDC. VS Code CanMV/보드 연결 도구의 제어·배포·실행·Preview 경로. | `canmv_board_info`에서 `connected: true`, `ready: true`를 먼저 확인한다. USBDBG `short read` 또는 `Not connected` 시 재연결 1회가 대부분 복구했으며, 계속 실패하면 물리 전원 재인가가 기록된 방법이다. |
| `/dev/cu.usbmodem58930597043` | CH342K UART2. K230 `@MOUSE|...`를 Mac bridge가 수신하는 mouse-data 경로. | Mac bridge 전용으로 열며, CDC 배포 중에는 점유하지 않는다. `001`과 물리적으로 분리되어 동시 사용 가능하다. |
| `/dev/cu.usbmodem58930597041` | mouse transport에는 사용하지 않는 후보 포트. | README가 명시적으로 비사용으로 분류한다. |

`run_uart.py`/`run_wifi.py`의 `ImportError`는 USB 포트 미표시 문제가 아니라,
CanMV 실행 환경이 실행 파일의 디렉터리를 `sys.path`에 자동 등록하지 않은 문제였다
(문제 #14). `PROJECT_DIR` 삽입 뒤 CDC를 통한 배포·실행 및 UART2 송신이 실기기로
확인됐다.

반면, **프로젝트 초기 시점에 CanMV IDE가 `001...` 포트를 표시하지 않았거나
연결하지 못했다는 개별 사건은 Git 로그, README, `PROJECT_STATUS.md`,
`WORK_TRACKER.md`, 배포 문서에서 찾지 못했다.** 그 사건의 케이블·권한·드라이버·IDE
원인이나 해결 방법은 이 문서에 추정으로 쓰지 않는다.

### 4-2. `@HELLO/@ACK`와 broadcast의 정확한 차이 (2차 검증 보완)

- 구현은 **broadcast datagram을 보내지 않는다.** `compute_scan_targets()`가 보드의
  IP/netmask에서 같은 subnet의 개별 host 주소 목록을 만들고, 최대 64 host일 때만
  각 주소에 unicast `@HELLO|<id>` UDP datagram을 보낸다. 자신의 IP, network 및
  broadcast 주소는 대상에서 제외된다.
- Mac bridge는 `recvfrom()`으로 받은 `@HELLO`의 **송신자 주소·포트**로 unicast
  `@ACK|<id>`를 돌려보낸다. 보드는 ACK를 실제로 보낸 소켓 주소를 peer로 저장한다.
  즉 broadcast 응답을 수집하는 방식도, Mac의 사전 고정 IP를 신뢰하는 방식도 아니다.
- 등록 전에는 mouse event를 UDP로 보내지 않으며, 등록 뒤에도 재공지하여 IP 변경 시
  재등록할 수 있다. 단, 실제 IP 변경 후 재등록은 로컬 루프백 테스트가 아닌 5-host
  실기기 등록만 확인됐고, 재연결 시나리오 전체는 아직 미검증이다.
- `/24`처럼 상한보다 큰 subnet은 전수 unicast scan을 하지 않고 자동 탐색을 포기한다.
  현재 집 Wi-Fi에서는 설정된 고정 IP로 fallback한다. 이 결정은 broadcast가 실패했다고
  실증해서가 아니라, broadcast/AP 격리의 동작을 이 프로젝트에서 검증하지 않았고,
  253-address unicast burst가 보드 무응답과 함께 관측됐기 때문이다.
- **dev-history-recorder 스킬을 기존 섹션 체계에 매핑**: 전역 개발 기록 스킬이
  기본으로 쓰는 "개발 목표/리서치 및 설계 결정/문제 및 해결" 3섹션 템플릿 대신,
  이 문서의 기존 섹션 체계(3번=문제 이력, 4번=의사결정, 6번=남은 문제)에 의미
  매핑해서 쓰도록 했다. 문서를 표준 템플릿으로 재구성하면 기존 22건의 문제
  이력과 서술을 잃거나 중복시킬 위험이 있고, 스킬 자체를 특정 프로젝트 구조에
  종속시키지 않는 것이 범용성에 맞기 때문이다.

## 5. 실패했던 접근 방식과 교훈

- `wlan.connect()` 반복 호출은 연결을 빠르게 만들지 않고 handshake를 깨뜨렸다.
  한 번 호출 후 충분히 기다려야 한다.
- Display 경로에 deprecated MediaManager 초기화를 함께 넣으면 치명적 hang이
  발생했다. 공식/검증된 `PipeLine`의 lifecycle을 기준으로 비교해야 한다.
- JPEG 포맷 문제와 핫스팟 처리량 문제를 처음부터 하나의 문제로 취급하면 안 된다.
  USB/네트워크 없는 재현으로 포맷 원인을 분리한 방식이 유효했다.
- 모든 `/24` 대상에 짧은 시간 sendto하는 탐색은 안전성이 증명되지 않았다.
  작은 범위에서 단계적으로 올리고, 보드 무응답 재현을 무리하게 반복하지 않는다.
- 웹 인코딩을 제스처와 같은 single-thread loop에서 매 프레임 수행하면 제스처의
  wall-clock 확인창(90/180 ms)에 간섭할 수 있다. 현재 throttling은 가설 기반
  완화책이므로 시연 기준 재검증이 필요하다.

### 5-1. 초기 마우스 안정화의 변경 순서와 검증 한계 (2차 검증 보완)

이 항목은 커밋 diff와 커밋 본문에서 직접 확인되는 범위만 정리한다.

1. `fd0a6be`는 고정 중립점의 속도 누적을 프레임 간 **상대 이동량**으로 바꿨다.
   직접 기록된 증상은 손을 멈춰도 커서가 화면 끝까지 이동하는 drift였다. 방향 반전,
   느린 이동, 손 재획득, CLICK/DRAG 전환 테스트를 추가했으나, 실제 K230에서는
   landmark 미세 변화 때문에 정지 jitter가 남았다고 같은 커밋이 명시한다.
2. `8d8cb3f`는 그 잔여 jitter에 One Euro Filter, 2D 안정 기준점(dead zone 성격의
   미세 흔들림 억제), 필터된 상대 이동, 빠른 이동 뒤 잔여 이동 보정을 적용했다.
   카메라 흔들림 모사 테스트는 보강됐지만, 이 변경만의 실기기 수치나 before/after
   영상은 남아 있지 않다.
3. `a68dfa5`는 FIST 및 손 유실 시 남아 있던 pinch 후보를 초기화하여 ghost click을
   막고, Preview 포인터를 실제 index fingertip으로 고쳤다. FIST bbox/ROI/keypoint,
   CLICK 판정, UART 송신, Mac 수신 로그를 추가했다. `36c72cf`는 이를 `@TRACK` CSV로
   분리했다. 현재 추적 CSV는 존재하지만, "오인식이 완전히 사라졌다"는 실기기
   종결 기록은 없다.
4. FIST는 DRAG보다 우선하고, 일정 유지 시간 뒤 DRAG가 되며 순간 손실에는 grace
   window를 둔다. CLICK은 pinch 비율과 유지 시간, re-arm 조건을 사용한다. 이는
   초기 코드와 후속 수정에서 확인되는 **적용 사항**이며, 현재 Wi-Fi 경로의
   오CLICK/오DRAG 문제(#20)가 해소됐다는 뜻은 아니다.

## 6. 현재 남아 있는 문제

1. **JPEG/제스처 품질 회귀** — 원인 가설이 "JPEG CPU 인코딩"에서 "핫스팟
   네트워크 전송 지연"으로 갱신됐다(encode_ms avg 47ms vs network_send_ms
   max 2558ms, 실측). 200 ms MJPEG throttle은 적용·배포됐고 107.5초 실제
   스트리밍+실손동작 중 비정상 종료는 없었으나, 실제 체감 품질(순간이동/
   오CLICK/오DRAG 재현 여부)과 JPEG 실패↔오CLICK의 인과관계는 여전히
   미확정이다. `시연용_README.md`의 실제 시연 기준으로 UART/Wi-Fi, 웹
   ON/OFF를 비교해야 한다.
2. **대규모 UDP 자동 탐색 hang** — 253 host 사건의 원인은 미확정이며 64 host도
   실기기 전수 검증되지 않았다. 20~30 host부터 단계 검증이 필요하다.
3. **핫스팟 MJPEG 처리량 변동** — 10-23 실측으로 network_send_ms가 CPU 인코딩
   대비 훨씬 크고 변동이 큼(p95 876ms, max 2558ms)을 **직접 계측으로 확인**
   했다. 다만 이것이 pump_send()의 논블로킹 특성 때문에 AI loop 자체를
   멈추는지, 전용(비핫스팟) AP에서는 어떻게 다른지는 아직 비교 측정하지
   못했다.
4. **Wi-Fi 실패 뒤 홈→핫스팟 실제 폴백** — 성공 연결은 확인됐지만 timeout 후
   다음 SSID로 넘어가는 실기기 시나리오는 확인되지 않았다.
5. **transport 예외 격리** — 코드와 테스트는 통과했으나, 의도적으로 UDP 예외를
   발생시킨 상태에서 AI/웹이 살아남는 실기기 검증은 없다.

## 7. 앞으로의 개선 과제

- 시연 기준의 테스트 표를 만들고, 각 항목에 보드 로그·영상·날짜를 연결한다.
- `diag_frame_timing.py`로 200 ms throttle 전후의 p50/p95 및 180/350 ms 초과
  프레임 수를 수집한 뒤, 실제 손동작으로 CLICK/DRAG 오작동을 판정한다.
- `diag_stream_breakdown.py`/`diag_combined_regression.py`(10-23 신규, JPEG
  인코딩·네트워크 전송 분리 계측)를 전용(비핫스팟) AP에서도 같은 방식으로
  재측정해, 핫스팟 특유의 네트워크 지연인지 일반화되는지 확인한다.
- Wi-Fi 자동 탐색 목적지 수를 작게부터 올리고, 메모리/FPS/ARP 지연을 같은
  세션에서 기록한다.
- 전용 공유기 환경에서 MJPEG 처리량과 UDP 지연을 별도로 재측정한다.
- CanMV runtime 호환성(`decode` keyword 등)을 작은 smoke test로 유지하고,
  network/transport 오류를 AI loop와 계속 격리한다.

## 8. 보안 및 불필요 파일 커밋 점검

### 민감정보

로컬에서 접근 가능한 모든 ref의 텍스트 blob에 대해 `password`, `secret`, `token`,
`api key`, private-key header 등의 문자열을 경로와 함께 점검했다. 실제 값은 이
문서에 기록하지 않았다.

- **확인 결과**: 추적 이력에서 `.env`, `wifi_credentials.py`, `net_config.py`,
  private key, API key, token 파일은 발견되지 않았다. password 매치는
  `wifi.py`/`net.py`의 변수명·테스트와 `.gitignore` 규칙뿐이었다.
- `.gitignore`는 현재 `firmware/wifi_credentials.py`,
  `experiments/wifi_test/net_config.py`, `logs/tracking_*.csv`, JPEG 진단 이미지,
  cache/venv를 제외한다. 현재 두 credential 파일도 ignored 상태다.
- **권장 조치**: SSID·비밀번호를 README, `WORK_TRACKER`, 커밋 본문, 진단 로그에
  넣지 말고, 배포 전 `git diff --cached` 및 secret scanner를 실행한다. 과거
  secret 유출 증거는 없으므로 history rewrite/rotation을 권고할 근거는 없다.
- **검사 한계**: 이 검사는 현재 clone의 `git rev-list --all` 도달 객체와 사람이
  읽을 수 있는 텍스트 패턴을 대상으로 했다. encrypted/압축 binary 내부, 고엔트로피
  문자열의 의미 판별, 삭제되어 현재 clone에 없는 원격 객체, GitHub 외부 서비스의
  secret은 검증하지 못한다. 따라서 "민감정보가 절대 없다"가 아니라 **이 범위에서
  값 형태의 유출을 발견하지 못했다**는 결론이다.

### 불필요하거나 큰 이력 객체

- 초기 import 관련 두 커밋(`0ad2585`, `402a454`, `859929`)에는 `.pyc` binary가
  커밋됐고 `2626362`에서 제거됐다. 현재 `.gitignore`가 막지만 **과거 Git
  history에는 남아 있다**. 노출 민감정보는 아니나 clone 용량·diff 가독성을
  해친다.
- `logs/tracking_*.csv` 네 개(4,952행)가 추적 중이다. 해당 로그는 이후
  ignore됐지만 기존 history/current index에는 남아 있으며, 자세한 손 추적
  좌표·시간 데이터가 들어갈 수 있다. 외부 공개 필요가 없다면 향후 새 로그는
  artifact 저장소로 분리하고, 필요 시 별도 승인 아래 history 정리 여부를
  검토한다. 이 조사에서는 변경하지 않았다.
- `videos/edgeglass-demo.mp4`(20,892,535 bytes)와 이미지 5개(각 약 1.2~1.9 MB)가
  Git에 들어 있다. 발표 자산으로 의도된 `presentation` 브랜치 변경이지만,
  저장소 비대화 요인이다. 향후 Git LFS 또는 release asset을 고려한다.
- 현재 untracked 진단 스크립트 3개와 수정된 `WORK_TRACKER.md`/
  `smart_glass_server.py`는 진행 중 조사 자료다. 이 보고서는 이들을 수정하지
  않았으며, 자동으로 커밋 대상이라고 판단하지 않는다.

## 9. 관련 커밋 참고 자료

- 핵심 시작: `a8ff735`; 안정화: `fd0a6be`, `8d8cb3f`, `a68dfa5`.
- Wi-Fi/JPEG: `cefb100`; 모듈화: `8fd7c89`, `cba31d6`, `791d3f5`.
- transport/실행 프로필: `a7e4565`, `447cb94`.
- 자동 탐색/폴백: `7ceda8d`, `25452f0`; 최신 안정화: `87ff5c7`.
- 미커밋 진단 근거: `docs/WORK_TRACKER.md`의 K, M 절과
  `experiments/runtime_diagnostics/`.

## 10. 코드 diff 기반 상세 개발 과정 복원

이 절은 커밋 메시지를 요약한 것이 아니라 각 커밋과 부모의 diff, 변경 전후 함수
구현을 읽어 복원한 것이다. **[diff 사실]**은 소스 변경으로 직접 확인되는 내용,
**[기술적 해석]**은 그 변경이 증상에 작용하는 방식의 설명이며, 해석만으로
실기기 해결을 확정하지 않는다. 발표 자산만 추가한 `fdea673`/`f25017b`, 문서만
추가한 `eeac3fd`/`54d6189`, cache 제거 `2626362`는 기능 오류를 고친 코드가
없어 이 절의 문제 흐름에서는 제외하되 조사 대상 커밋에는 포함했다.

### 10-1. 초기 K230 실행·UART 경로: import와 전송 포트 분리

**최초 구현 (`a8ff735`)**

- **[diff 사실]** 최초 `main.py`는 `HandTracker`, `GestureController`,
  `MouseController`, `draw_hand`를 직접 조합했다. 손이 없으면
  `gesture_controller.no_hand()`을, 있으면 `is_fist(points)`와
  `gesture_controller.update(points, fist_now)`를 호출해 action/좌표를 만들고
  `mouse_controller.update()`에 넘긴다. 초기 `MouseController`는 생성자에서
  `machine.UART(UART.UART2, 115200, ...)`를 직접 열고 `@MOUSE|...` 한 줄을
  UART에 썼다.
- **[diff 사실]** 초기 제스처에는 pinch on/off ratio, CLICK 90 ms 유지,
  재무장 120 ms, FIST→DRAG 180 ms 유지, FIST release 220 ms, hand-loss
  grace라는 상태값이 이미 있었다. 따라서 이후 안정화는 MOVE의 좌표 산출과
  상태 전환 중 좌표 처리의 보강이지, CLICK/FIST를 새로 도입한 작업은 아니다.

**CanMV import 오류 (`0ad2585`)**

- **증상/기존 동작**: 커밋은 K230 module import 및 의존성 오류를 고쳤다고
  말하며, 실제 diff는 `main.py`가 `/sdcard/smart_glass`를 `sys.path`에 넣은
  뒤 flat import하도록 바꾼 것을 보인다. `hand_tracker.py`의 import도 한 줄
  수정됐다. 원래 어떤 module name 또는 누락 의존성이 오류였는지의 console
  traceback은 보존되지 않았다.
- **수정 원리**: 보드에 평탄화해 배포한 모듈의 directory를 import search path에
  명시하면 `from hand_tracker import HandTracker` 같은 flat import가 실행
  위치와 독립적으로 해석된다.
- **검증**: 이 커밋 자체의 실기기 실행 log는 없다. 후속 `447cb94`에서 같은
  CanMV path 제약이 실제 `ImportError`로 재현되고 해결됐으므로, 원리는 일관되나
  `0ad2585`만으로 초기 오류가 끝났다고 단정하지 않는다.

**CDC와 UART2의 분리 (`402a454`)**

- **[diff 사실]** `mouse_controller.py`의 UART 인스턴스는 UART2를 계속 쓰되,
  README와 Mac bridge의 기본 포트를 `58930597043`으로 바꿨다. 따라서 보드
  제어/CanMV Preview의 USB CDC `001...`를 Mac mouse bridge가 열지 않도록
  역할을 분리했다.
- **기술적 원리**: CDC 제어 channel을 잡은 IDE와 mouse byte stream을 읽는
  bridge가 같은 serial endpoint를 경쟁하면 양쪽 프로토콜이 깨질 수 있다.
  별도 CH342K UART2 endpoint를 mouse data 전용으로 쓰면 실행·배포와 mouse
  수신이 동시에 가능하다.
- **검증/한계**: 후속 문서에는 `043` UART 송신과 bridge 경로가 검증됐다고
  남아 있다. 다만 "초기에 CDC 포트가 IDE에 전혀 표시되지 않았다"는 사건은
  source history에 없으므로 이 수정의 증상으로 소급해 연결하지 않는다.

### 10-2. 커서 튐과 DRAG 좌표: 절대 fingertip 좌표를 상태별 anchor로 바꾸다

**문제의 출발점 (`859929b`)**

- **기존 동작**: `update()`는 매 프레임 `smooth_point(index_tip)`의 결과
  `move_x/move_y`를 MOVE·CLICK·FIST candidate·DRAG 모두의 반환 좌표로 썼다.
  손 모양 전환에 따라 검지 landmark가 크게 움직이면 action은 유지돼도 mouse
  좌표가 새 fingertip 위치로 바뀔 수 있는 구조였다.
- **[diff 사실] 수정**: `cursor_x/y`, `click_anchor_x/y`, `fist_anchor_x/y`,
  `drag_start_palm_x/y`, `drag_start_cursor_x/y`를 추가했다. `result()`가
  마지막 출력 cursor를 기억하고, pinch가 처음 시작될 때 `click_anchor`, FIST
  candidate가 처음 시작될 때 `fist_anchor`를 현재 cursor로 고정한다.
- **[diff 사실] DRAG 변경**: DRAG 확정 뒤에는 index tip이 아니라 wrist·index
  MCP·middle MCP·pinky MCP 평균인 `palm_x/y`의 변화량을 시작 cursor에 더한다.
  `drag_x = drag_start_cursor_x + (palm_x - drag_start_palm_x)` 방식이다.
- **기술적 해석**: pinch/FIST의 손가락 접힘은 index tip 좌표를 급변시켜도 palm은
  상대적으로 안정적이다. 시작 cursor를 anchor로 고정하면 action 전환 직후의
  순간이동을 막고, palm delta만 DRAG 이동량으로 사용하면 제스처 모양 변화와
  drag movement를 분리한다. `clear_cursor_locks()`를 hand-loss 및 DRAG 종료에
  호출한 것은 오래된 anchor가 다음 gesture에 재사용되는 것을 막는다.
- **검증**: 테스트는 존재하지만 이 커밋의 보드 전후 좌표 trace는 없다. 따라서
  코드상 튐 경로는 제거됐어도 당시 실제 cursor jump가 완전히 해소됐다는 직접
  실기기 근거는 부족하다.

**DRAG의 추가 보정 (`2c5ee3d`)**

- **[diff 사실]** 이후 `GestureController(pointer_size)`에 velocity pointer
  상태, `DRAG_PALM_ALPHA=0.45`, `DRAG_DEAD_ZONE=3` 및
  `drag_relative_point()`가 추가됐다. 이 함수는 palm을 EMA로 필터한 후 시작
  palm과의 delta가 3 pixel 이하이면 0으로 만든다.
- **수정 전후 차이**: 앞 단계는 raw palm delta를 바로 더했지만, 이 단계는
  `filtered_palm = previous*(1-alpha)+raw*alpha`를 거친 delta만 더한다.
  동시에 FIST/CLICK transition에서는 `hold_pointer_control()`로 일반 pointer
  이동을 중립화한다.
- **기술적 해석**: palm landmark도 프레임 noise가 있으므로 small delta를
  dead zone에서 제거하고 EMA로 완화하면 DRAG 중 버튼은 눌린 채 미세 이동이
  누적되는 현상을 줄인다. 이는 noise 억제이지, detection이 잘못된 palm을
  복구하는 방법은 아니다.
- **검증**: 커밋에는 DRAG 떨림 보정과 이동 범위 확장이 기록됐지만 독립적인
  실기기 trace는 없다.

### 10-3. MOVE 드리프트·떨림: 중립점 속도 방식의 폐기와 One Euro Filter

**1차 변경과 남은 문제 (`fd0a6be`)**

- **기존 동작**: diff의 삭제 주석은 이전 pointer가 “neutral point로부터의
  deflection을 velocity로 바꾸는” 방식임을 보인다. 손을 카메라 가장자리에
  계속 두면 offset이 계속 남아 cursor가 계속 같은 방향으로 누적 이동한다.
- **[diff 사실] 1차 수정**: 이 커밋은 그 방식에서 프레임 간 relative movement로
  전환하고 방향 반전·느린 이동·손 재획득·CLICK/DRAG 전환 테스트를 추가했다.
  커밋 본문은 이 뒤 K230에서 landmark의 작은 변화가 매 relative delta에 들어가
  정지 떨림이 남았다고 명시한다.
- **판정**: 화면 끝 drift라는 최초 증상에는 목표를 맞춘 변경이지만, 같은
  commit이 최종 안정화가 아니라고 기록한다. **원인 확인 후 1차 수정, 미완료**다.

**2차 안정화 (`8d8cb3f`)**

- **[diff 사실]** `OneEuroFilter`를 MOVE 좌표 path에 넣고, 2D stable anchor와
  filtered relative movement, 빠른 이동 뒤 잔여 movement 보정을 추가했다.
  검지 raw point는 adaptive EMA/One Euro 계열 temporal filter를 거쳐 cursor
  delta의 입력이 된다.
- **수정 원리**: One Euro Filter는 움직임이 느릴 때 cutoff를 낮춰 noise를 더
  제거하고, 빠를 때 cutoff를 높여 의도된 이동에 대한 지연을 낮추는 방식이다.
  stable anchor/dead-zone은 작은 좌표 차이를 0으로 취급한다. 따라서 단순
  moving average보다 정지 안정성과 반응성의 trade-off를 상황별로 조정한다.
- **검증**: 카메라 shake를 모사한 regression test는 추가됐지만, filter parameter가
  실제 보드에서 어떤 jitter/FPS 수치 개선을 냈는지는 기록되지 않았다. 후속 UART
  시연 경로가 동작했다는 사실과 이 세부 tuning의 정량 검증은 구분해야 한다.

**FIST/CLICK/손 유실의 상태 보강 (`a68dfa5`, `36c72cf`, `cd7f50f`)**

- **기존 동작과 증상**: FIST 또는 true hand loss 뒤에도 `pinch_since` 후보가
  남으면 손이 다시 열릴 때 이전 후보의 시간과 결합해 의도하지 않은 CLICK으로
  이어질 수 있었다. UI의 빨간 pointer도 실제 index tip이 아닌 다른 기준을
  표시해 tracking 문제의 관찰을 어렵게 했다.
- **[diff 사실] 수정**: FIST/손 유실 경로에서 pinch 후보를 reset하고, preview를
  index fingertip로 바꾸며, bbox·ROI·keypoint·fist·click 결정을 log한다.
  `36c72cf`는 mouse event와 별도 `@TRACK` record를 UART로 보내고 Mac bridge가
  CSV에 기록하게 했다. CSV write 실패는 mouse dispatch를 중단시키지 않도록
  예외 처리한다.
- **기술적 원리**: transient gesture state를 reset하면 서로 다른 hand episode의
  timing state가 이어지지 않는다. event와 raw tracking context를 분리하면
  "FIST 판단 오류", "keypoint 흔들림", "mouse 수신/dispatch" 중 어디가
  원인인지 나중에 같은 timestamp 기준으로 나눠 볼 수 있다.
- **검증/한계**: tracking CSV 4개가 남아 있고 전송·state regression test가
  추가됐다. 그러나 모든 ghost CLICK/FIST 오인식이 실기기에서 사라졌다는
  종결 log는 없으며, 현재 Wi-Fi 회귀(#20)도 이 상태 machine이 완전히 면역임을
  뜻하지 않는다.

### 10-4. Wi-Fi 단독 실험: 연결 재시도와 JPEG format을 분리 진단

#### 10-4-1. 초기 K230D-Zero 내장 Wi-Fi/TCP 실험 (날짜 미상, 사용자 보존 기록)

> **근거 구분**: 이 항목은 Git commit, source diff 또는 후속 `WORK_TRACKER`에서
> 역추적한 사실이 아니다. 사용자가 보존한 당시 실험 기록을 이력 보완을 위해
> 제공한 것이며, 정확한 날짜는 기록되지 않아 만들지 않았다. 아래 IP와 결과도
> 그 기록의 당시 환경값이다.

**실험 환경과 범위**

- 보드는 `k230d_canmv_bpi_zero`, firmware는 `v1.8-0-gc2d1f5c` (build
  2026-07-03), OS는 RT-Smart였다. 별도 ESP32나 firmware 수정 없이 CanMV
  MicroPython에서 내장 Wi-Fi를 사용했다.
- 아이폰 hotspot에서 K230D는 `172.20.10.2`, Mac은 `172.20.10.3`, gateway는
  `172.20.10.1`, netmask는 `255.255.255.240`이었다. `wlan.isconnected()`는
  `True`, `wlan.ifconfig()`는 정상 IP 정보를 반환했다.
- 이 단계의 목적은 **TCP socket의 양방향 연결성과 server accept** 확인이었다.
  browser HTTP response, JPEG encode, MJPEG stream은 이때 구현·검증하지
  않았다. 뒤의 `cefb100` 및 이후 문서의 HTTP/MJPEG 성공·실패를 이 결과에
  소급하지 않는다.

**연결성에서 실제 관찰한 차이**

- Mac→K230D ICMP ping은 timeout이었다. 그러나 K230D→Mac `socket.connect()`는
  성공했고, Mac→K230D TCP port check도 `nc -vz -G 5`에서 최초 실패 뒤 성공했다.
- K230D TCP server는 `bind()`→`listen(5)`→`accept()`에 도달했다. port 확인용
  `nc`가 연결 직후 종료했으므로 `conn.recv(1024)`는 `b''`를 반환했고, 이것은
  application payload가 없다는 EOF이지 TCP accept 실패의 증거가 아니다.
  같은 연결에서 `conn.send()`는 70 bytes 반환을 기록했다.
- **해석**: 이 환경에서 ping timeout만으로 Wi-Fi 또는 TCP가 실패했다고 결론
  내릴 수 없다. ICMP reachability와 TCP listener/client path는 별도로
  관측해야 한다. 다만 최초 Mac TCP 실패가 hotspot의 지연, listener 준비 전
  접속, 또는 다른 조건 중 무엇 때문인지는 기록만으로 판별되지 않는다.

**`EAGAIN` 실패와 재설정 시도**

- 최초 `server.accept()`는 `EAGAIN (Errno 11)`을 반환했다. `setblocking(True)`를
  적용했지만 그 조치만으로는 해결되지 않았다.
- 이후 socket을 새로 생성하고 `SO_REUSEADDR`를 설정한 뒤 `bind()` 및
  `listen(5)`을 다시 적용했을 때 Mac TCP connect와 board `accept()`가
  성공했다.
- **확정 가능한 결론**은 “재생성·재설정 뒤 성공했다”까지다. 기존 socket의
  상태, listener 준비 순서, `SO_REUSEADDR`, bind/listen 재호출 중 어느 하나가
  결정적으로 `EAGAIN`을 해소했는지는 당시 통제 비교가 없으므로 **원인 미확정**이다.
  따라서 후속 `web_server.py`의 bind retry/`SO_REUSEADDR`가 이 초기 사건을
  완전히 해결한 것으로 기술하지 않는다.

**MicroPython socket API 호환성**

| API | 당시 관찰 결과 | 문서상 판정 |
|---|---|---|
| `getsockname()` | 미지원 | 이 firmware에서 API 의존 금지 또는 별도 호환 처리 필요 |
| `gettimeout()` | 미지원 | timeout 값을 read-back하는 CPython식 진단은 사용 불가 |
| `settimeout()` | 호출 가능 | 실제 timeout expiry/exception 동작은 당시 미검증 |
| `select`, `poll` | 지원 확인 | 후속 non-blocking HTTP server의 event polling 설계와 연결 가능한 capability이나, 초기 TCP test만으로 HTTP server 전체가 검증된 것은 아님 |

**후속 구현과의 연결**

- `cefb100`의 Wi-Fi test suite는 이 초기 TCP 사실을 대체하지 않고, 그 위에서
  HTTP server·JPEG·MJPEG를 별도 검사한 단계다. 특히 TCP client/server success와
  MJPEG의 낮은 처리량/timeout은 서로 모순이 아니라 서로 다른 계층의 관찰이다.
- 이후 `web_server.py`가 `select.poll()`과 non-blocking client session을 쓰고,
  `HttpServer.start()`가 `SO_REUSEADDR`/bind retry를 쓰는 것은 초기 실험에서
  확인한 제한과 양립한다. 단, 해당 코드를 이 초기 기록에서 직접 파생했다고
  증명할 Git diff 또는 설계 메모는 없으므로 **기술적 연속성**으로만 기록한다.

**JPEG 색상·기하 손상 (`cefb100`)**

- **기존 동작/증상**: Wi-Fi 실험의 `mjpeg_stream_test.py`는 camera channel의
  `YUV420SP` image에 `Image.compress()`를 적용했다. `jpeg_format_test.py`로
  network 없이도 JPEG의 색 왜곡·좌우 중복이 재현됐으므로, 전송 socket 자체가
  직접 원인이라는 가설은 배제됐다.
- **[diff 사실] 수정**: 웹 image format을 `RGB565`로 바꾸고 mirror/flip을
  설정했다. video stream test에는 snapshot/health 및 encode/send timing log도
  추가됐다.
- **기술적 원리**: 이 보드 firmware에서 해당 compressor가 기대하는 pixel layout과
  YUV420SP buffer layout이 맞지 않는 반면 RGB565 경로는 정상 JPEG bitstream을
  만든 것으로 관찰됐다. mirror/flip은 JPEG encoder의 문제가 아니라 sensor
  coordinate 방향을 preview와 맞추기 위한 설정이다.
- **검증**: USB/SD 및 Wi-Fi `/snapshot`에서 정상 색·방향을 관찰했다. 이는
  format bug 해결 근거지만, continuous MJPEG 처리량 문제의 해결 근거는 아니다.

**Wi-Fi association 실패처럼 보인 문제 (`cefb100`, 후속 `a7e4565`)**

- **기존 동작**: 초기 `net.py`의 reconnect 방식은 `wlan.connect()`를 다시
  부를 수 있었다. 보드에서는 association이 40초 이상 걸릴 수 있는데, 진행
  중 connect를 반복하면 handshake가 끊긴다는 관찰이 남아 있다.
- **[diff 사실] 수정**: `connect()`는 한 번 호출하고 `isconnected()`를 최대
  timeout까지 passive polling하도록 바뀌었다. `a7e4565`의 `wifi.py`
  `connect_if_needed()`는 이 코드를 production path로 옮겨, 이미 연결된
  WLAN은 건드리지 않고 재사용한다.
- **기술적 원리**: STA association은 비동기이므로 새 connect 요청이 이전
  request를 취소하면 retry 횟수를 늘려도 성공 확률이 오히려 내려간다. 한 번의
  request와 deadline polling은 driver state machine이 완료할 시간을 보장한다.
- **검증/한계**: 실제 IP 출력 성공은 기록됐지만, 핫스팟의 association 시간
  변동과 MJPEG 처리량 변동은 남았다. 따라서 코드 수정은 연결 API 사용법을
  바로잡은 것이며 network 품질을 보장한 것은 아니다.

**시연용 연결 진입점 (`51ce689`)**

- **[diff 사실]** `demo_wifi.py`는 새로운 network algorithm을 만들지 않고,
  이미 검증 대상으로 삼은 `net.py`와 gitignore된 `net_config.py`를 import해
  한 줄 실행에서 `connect(SSID, PASSWORD, timeout_s=60)`를 호출한다.
- **변경 이유와 검증**: 이는 재연결 bug의 새 수정이 아니라, 연결을 수동 REPL
  여러 줄로 입력할 때의 절차 오류를 줄이는 wrapper다. 전원 재인가 후 Wi-Fi
  연결과 IP 출력은 실제로 확인됐지만, 모든 hotspot 상태에서의 재연결 안정성을
  보장하는 테스트는 아니다.

**soft reboot 직후 NIC race (`a7e4565`, `cba31d6`)**

- **[diff 사실]** `UdpTransport._connect()`는 UDP socket/connect가
  `OSError('no available NIC')`를 내면 500 ms 간격으로 최대 20회 retry한다.
  web path는 `network.WLAN(network.STA_IF)`, `active(True)`, `isconnected()`
  확인 뒤 bind한다.
- **기술적 원리**: Wi-Fi link의 `isconnected()`가 true여도 MicroPython socket
  layer에 NIC가 등록되기 전 짧은 구간이 있을 수 있다. WLAN handle을 만들고
  socket creation을 늦추거나 retry하면 이 두 상태가 맞춰질 수 있다.
- **검증**: 이 race의 관찰과 retry 필요성은 실기기 report에 있으나, 모든 reboot
  timing에서 재현/해결됐다는 exhaustive 검증은 없다.

### 10-5. main.py를 보존한 웹 모듈화와 CanMV hang 분석

**구조 변경 (`8fd7c89`)**

- **[diff 사실]** 기존 root 파일을 `firmware/`, `mac/`, `experiments/`로
  이동하고, 보드에서는 여전히 flat import하도록 배포 mapping을 유지했다.
  새 `CameraRig`는 channel 0(YUV420SP display), 1(RGB565 web), 2(RGBP888 AI)를
  feature flag에 따라 열며, 새 `WebState`가 한 AI inference의 `hand_result`를
  OSD와 JPEG overlay에 공유한다. 기존 `firmware/main.py`는 rename 후 내용이
  보존됐다.
- **변경 이유**: 웹 기능 때문에 tracker/gesture를 복제하면 UART와 Wi-Fi가
  서로 다른 recognition logic으로 갈라질 위험이 있다. 공유된 module과
  single orchestrator는 이 회귀를 줄이지만, JPEG encode와 AI가 같은 loop에서
  경쟁하는 새 성능 위험을 만든다.
- **검증**: 이 커밋은 py_compile·17 unittest만 통과했고 보드 배포는 하지
  않았다. 이 단계의 "모듈화 완료"는 코드 구조에만 해당한다.

**`sys` shadowing과 MediaManager hang (`cba31d6`)**

- **증상/기존 동작**: `smart_glass_server.py`가 `from media.media import *`
  전에 `import sys`하면 wildcard import가 `sys` name을 덮어 이후
  `sys.path.insert`가 `AttributeError`로 실패했다. 또 Display 사용 경로가
  `Display.init()` 후 무조건 `MediaManager.init()` 및 destroy 때 무조건
  `MediaManager.deinit()`을 호출했다.
- **[diff 사실] 수정**: import 순서를 `from media.media import *` 뒤
  `import sys`로 바꾸고, `CameraRig.create()`에서 display가 활성화된 경우
  MediaManager init을 skip, `destroy()`에서도 display path에는 deinit을
  호출하지 않게 했다. `CameraRig` 단계별 log/memory log도 추가했다.
- **기술적 원리**: Python wildcard import는 현재 module namespace에 동명
  name을 bind할 수 있어 import ordering이 실제 semantics를 바꾼다. CanMV의
  Display path는 media subsystem을 이미 초기화하는 것으로 보이며, deprecated
  initializer를 다시 호출하면 lifecycle 이중 초기화가 될 수 있다.
- **검증**: 2/3 channel에서 MediaManager hang 재발이 없고 2-channel 270+ frame,
  약 20 FPS, memory 안정 log가 있다. 다만 "이중 초기화"는 코드 비교와 관찰로
  지지되는 기술적 해석이며 vendor 내부 원인을 source로 증명한 것은 아니다.

**HTTP bind와 JPEG retry (`cba31d6`, `791d3f5`)**

- **[diff 사실]** server 시작 전 WLAN을 활성화·확인하고, `HttpServer.start()`은
  `SO_REUSEADDR` socket/bind를 retry한다. 실패한 bind의 마지막 exception을
  `last_err`로 보존하도록 바꿨다. `WebState._capture_web_jpeg()`는
  `Compression Failed`일 때 새 frame을 한 번 받아 재시도하고 `gc.collect()`를
  호출한다. 이후 `FEATURE_WEB_JOINTS=True`로 overlay를 실제 켰다.
- **변경 전후 핵심 차이**: 이전에는 bind failure의 errno가 버려져 같은 20회
  실패의 원인을 분류할 수 없었고, JPEG error는 해당 request path를 바로
  종료시켰다. 이후에는 NIC readiness와 마지막 error를 노출하고, 일시적인
  compression failure에는 1회만 recovery한다.
- **검증/한계**: `/` 200, snapshot, MJPEG, AI/UART 동시 동작과 overlay는
  실기기 기록이 있다. 그러나 retry가 모든 JPEG failure를 해결한다는 근거는
  없으며, 후속 #20에서 repeated compression failure와 gesture 문제의 상관이
  다시 관찰됐다.

### 10-6. UART→UDP 전환: protocol은 유지하고 transport failure를 격리

**공통 transport와 watchdog (`a7e4565`)**

- **[diff 사실]** `MouseController`는 UART 인스턴스를 소유하던 구조에서
  `transport.write()`/`transport.close()`만 호출하는 구조로 바뀌었다.
  `UartTransport`는 기존 UART2 구현을 감싸고, `UdpTransport`는 동일한
  `@MOUSE` text를 UDP datagram으로 쓴다. 즉 gesture classifier와 normalized
  coordinate protocol은 바뀌지 않았다.
- **[diff 사실] DRAG 안전성**: controller는 DRAG 중 마지막 normalized point를
  기억해 hand-loss grace에서도 DRAG keep-alive를 보낸다. Mac bridge의
  `DragWatchdog`는 1초 동안 어느 packet도 안 오면 mouse-up을 강제한다.
- **기술적 원리**: UDP는 delivery/connection close를 보장하지 않으므로
  `DRAG_END` 유실만으로 OS mouse button이 계속 눌리는 상태를 만들 수 있다.
  지속 packet은 정상 drag의 proof-of-life, timeout mouse-up은 link failure의
  fail-safe가 된다.
- **검증**: 39개 자동 test는 transport interface, watchdog 및 message parsing을
  검증한다. 이 커밋 자체는 Wi-Fi 실기기 미검증으로 표시됐으며, 후속 고정 IP
  path에서 MOVE/CLICK/DRAG packet 수신이 확인될 때까지 UDP 종단간 완료로
  취급하면 안 된다.

**실기기 entry point와 종료 누락 (`447cb94`)**

- **증상**: `run_uart.py`/`run_wifi.py`가 직접 실행되면
  `ImportError: no module named smart_glass_server`가 났고, server의 finally는
  `mouse_controller.close()`를 호출하지 않아 실행 중단 시 DRAG_END를 보장하지
  못했다.
- **[diff 사실] 수정**: 두 entry point가 import 전에 `PROJECT_DIR`을 sys.path에
  넣고 `smart_glass_server.main(transport_kind, enable_web)`을 명시적으로
  호출한다. main finally가 `mouse_controller.close()`를 호출해 transport의
  DRAG_END/STOP cleanup을 실행한다.
- **검증**: 45 tests, deployment hash 확인, 실제 `run_uart.py`에서 sensor,
  AI, MOVE/STOP/DRAG, CLICK UART 송신과 clean cleanup이 확인됐다. Wi-Fi profile은
  이 커밋만으로는 종단간 검증되지 않았다.

### 10-7. 고정 IP의 한계와 unicast 자동 탐색의 진화

**고정 IP UDP의 문제와 최초 설계 (`7ceda8d`)**

- **기존 동작**: UDP transport는 config의 `MOUSE_UDP_HOST`에 connected UDP
  socket을 만들었다. 핫스팟 재연결로 Mac IP가 바뀌면 UDP send는 성공처럼
  보이지만 수신자가 없어 mouse가 조용히 멈출 수 있다.
- **[diff 사실] 수정**: `AutoDiscoverUdpTransport`/`UdpRegistry`가 생성됐다.
  보드는 subnet의 각 candidate host에 `@HELLO|id`를 `sendto()`하고, bridge는
  `recvfrom()` sender address로 `@ACK|id`를 답한다. registry는 ACK의 `addr`를
  peer로 저장하고 등록 전 event transmission을 막으며, 이후 재공지한다.
- **폐기/제한한 접근**: UDP broadcast는 구현하지 않았다. diff와 설계 문서는
  AP isolation 및 hotpot에서 broadcast가 검증되지 않은 점을 이유로 든다.
  64 host보다 큰 subnet에서는 candidate list를 만들지 않아 무차별 scan도
  피한다. 이는 broadcast가 실제로 실패했다는 증거가 아니라 미검증 의존을
  피한 설계 선택이다.
- **검증**: 70 local tests는 loopback ACK, peer registration/re-registration,
  max-host 분기와 bridge handler를 검증했다. 이 커밋 시점의 실제 Wi-Fi proof는
  없었다.

**다중 SSID와 fallback (`25452f0`)**

- **[diff 사실]** `connect_if_needed(ssid, password)`의 단일 인자가 network
  candidate 목록으로 바뀌었다. 빈 SSID는 건너뛰고, 각 candidate마다 connect
  한 번+passive wait를 하며 connect exception/timeout이면 다음 candidate로
  진행한다. 반환값에 실제 연결 SSID를 추가했다.
- **기술적 원리**: 연결 재시도 logic을 web과 UDP가 공유하므로 홈 Wi-Fi 실패가
  전체 feature initialization을 즉시 끝내지 않고 hotspot candidate로 이어질 수
  있다.
- **검증**: fake WLAN 73 tests는 home success, timeout/failure 후 fallback,
  빈 목록을 검사했다. 실제 보드에서 home success는 확인됐지만 실패 후 hotspot
  전환 전체는 아직 미검증이다.

**실기기 discovery compatibility와 error containment (`5cb0e66`, `87ff5c7`)**

- **증상**: 5-host test에서 Mac은 board registration을 출력한 뒤, K230은
  `data.decode("utf-8", errors="replace")`에서 keyword argument를 받지 않는
  MicroPython `TypeError`로 main loop가 종료했다.
- **[diff 사실] 수정**: `UdpRegistry.step()`은 동일 인자를 positional form
  `data.decode("utf-8", "replace")`로 바꿨다. Wi-Fi helper는
  `wlan.connect()`의 반환/driver rejection을 확인해 다음 candidate를 계속
  시도하고, `create_transport()`은 큰 subnet의 auto-discovery `ValueError`에서
  configured fixed host가 있으면 `UdpTransport`로 fallback한다. server는
  mouse transport 생성과 `transport.step()`을 try/except로 감싸 transport
  error가 camera/AI/web outer loop로 전파되지 않게 한다.
- **기술적 원리**: CPython-compatible source라도 MicroPython builtin signature가
  좁으면 keyword call이 실패할 수 있다. transport 계층의 optional network
  failure를 AI loop와 격리하면 mouse 기능을 잃어도 image/recognition까지 함께
  종료하지 않는다.
- **검증/한계**: positional decode는 REPL 및 5-host 실기기에서 Mac 등록·MOVE
  수신으로 확인됐다. 고정-IP UDP는 web/AI와 함께 MOVE/CLICK/DRAG end-to-end
  수신, 약 10–13.5 FPS, free memory 약 3.1–3.9 MB가 기록됐다. 반면 intentional
  transport exception 상태에서 AI/web이 계속 사는 branch는 실기기로 trigger하지
  않았고, home→hotspot fallback도 미검증이다.

### 10-8. 253-host hang 및 현재 JPEG/gesture 회귀: 해결로 선언하지 않은 항목

**대규모 unicast scan hang (`5cb0e66`의 WORK_TRACKER 기록)**

- **관찰 사실**: test 중 max scan hosts를 300으로 올려 `/24`의 253 destination에
  짧은 burst로 `sendto()`한 뒤 보드가 30초 이상 무응답이어서 물리 전원 재인가가
  필요했다. 그 사건에는 Mac `Board registered` log가 없었으므로, ACK decode
  TypeError가 직접 원인이라는 설명은 성립하지 않는다.
- **적용한 안전 조치**: source default는 64로 유지하고, 5-host만 monkey-patch한
  Stage 5로 실제 `@HELLO/@ACK`를 검증했다. 집 Wi-Fi처럼 큰 subnet은 fixed IP
  fallback을 택했다.
- **미확정 원인**: ARP resolution burst, network stack resource, memory,
  KPU/camera 경쟁은 가능한 설명일 뿐 diff나 재현 시험으로 판별되지 않았다.
  따라서 64-host도 안전하다고 실기기 증명된 것은 아니다.

**웹 JPEG와 gesture 품질 회귀 (현재 미커밋 diff)**

- **[diff 사실] 비교 결과**: `main.py`와 server는 동일한 `hand_tracker.py`,
  `gesture_controller.py`, `mouse_controller.py`를 import한다. web server path만
  CameraRig channel 1 및 `WebState.step()`의 JPEG capture/encode를 같은 main
  loop에 추가한다. 2-channel timing diagnostic은 약 91–94 ms/frame으로
  기록됐고 click confirm window 90 ms에 가깝다.
- **[diff 사실] 현재 수정**: 이전에는 `frame_interval_ms=0`이어서 streaming
  client가 있으면 loop마다 `_capture_web_jpeg()`→`img.compress()`를 실행했다.
  미커밋 변경은 `WEB_STREAM_MIN_INTERVAL_MS=200`을 만들고, 마지막 frame 이후
  아직 200 ms가 안 됐으면 `stream_wait_frame`에서 return해 encode 자체를
  건너뛴다.
- **기술적 해석**: JPEG encode/retry의 불규칙 비용이 AI frame 사이에 들어가면
  gesture의 wall-clock threshold를 넘기거나 frame cadence를 흔들 수 있다.
  encode frequency를 5 FPS 이하로 제한하면 AI가 uninterrupted frame을 더
  받게 되는 것이 기대 효과다. 이는 filter threshold를 바꿔 증상을 숨기는
  수정이 아니다.
- **검증/한계**: AST parse·78 tests·SD hash 일치는 code/deployment 근거일 뿐,
  JPEG failure 빈도, frame latency distribution, 실제 cursor 순간이동/오CLICK/
  오DRAG 개선은 아직 측정하거나 시연 기준으로 검증하지 않았다. 원인은 **유력한
  상관관계**일 뿐 확정이 아니다.

### 10-9. 커밋별 분석 범위와 복원 불가 항목

- 분석한 고유 커밋은 28개다. 그중 코드/설정/테스트/진단 변경이 있는 21개를
  위 문제 표와 상세 흐름에 연결했다. 동일 patch를 다른 parent에 얹은
  `7ceda8d`/`3eaca6e`, `25452f0`/`52890ff`는 각각 한 번만 기술했다.
- `5cb0e66`은 code diff보다 `WORK_TRACKER`의 진단 text가 제목/본문으로
  들어간 비정상 형식의 commit이다. 해당 text가 직접 진단 근거이므로 코드
  commit처럼 과장하지 않고 기록 근거로만 사용했다.
- 최초 IDE CDC 미표시 사건의 exact error, `0ad2585`의 원래 missing module,
  `859929b`/`2c5ee3d`의 실기기 before/after cursor trace, One Euro parameter별
  측정, Wi-Fi fallback과 IP-change re-registration, transport exception
  containment의 실기기 시험은 자료가 부족해 복원하지 못했다.
