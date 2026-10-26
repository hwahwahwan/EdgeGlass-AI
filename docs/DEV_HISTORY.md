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
| 10-23 | 기존 GMT130(ST7789) LCD를 VLT-OL016 OLED(0.96인치, 128×64, I2C, SSD1306 추정)로 교체하기로 하고, `firmware/`와 완전히 분리된 `display/`에서 독립 개발을 시작했다. 실물이 없어 PC 시뮬레이션·단위 테스트만 완료, 실기기 검증은 하지 못했다. | 미커밋 변경(`display/`); 근거는 본 문서 4-3 |

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

### 4-3. `display/` OLED(VLT-OL016) — 드라이버/핀 선택 근거 (실기기 미검증)

GMT130 ST7789 LCD를 VLT-OL016 OLED(0.96인치, 128×64, I2C, SSD1306 추정)로
교체하기로 하고 `firmware/`와 완전히 분리된 `display/`에서 독립 개발했다.
실물이 없어 아래는 전부 PC 시뮬레이션·단위 테스트 수준이며, 실기기 검증은
하지 못했다(문서 6번 참고).

- **CanMV의 `framebuf`/`machine.I2C` API 호환성**: 캐시된 CanMV K230
  MicroPython 스텁(`machine.pyi`, `framebuf.pyi`)을 조회해, `framebuf.FrameBuffer`에
  `MONO_VLSB`가 있고 `machine.I2C`가 `writeto(addr, buf, stop)`/
  `writevto(addr, nitems, stop)`를 표준 MicroPython과 동일한 시그니처로
  제공함을 확인했다(확인됨 — 스텁 시그니처 대조. 실제 동작은 미확인). 이를
  근거로 MicroPython 공식 SSD1306 드라이버
  (https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/display/ssd1306/ssd1306.py)를
  거의 수정 없이 포팅하기로 했다.
- **공식 K230 CanMV SSD1306 예제 발견**: 캐시된 예제에서
  `examples/03-Machine/i2c_ssd1306.py`를 찾았다 — `fpioa.set_function(11,
  FPIOA.IIC2_SCL)`, `fpioa.set_function(12, FPIOA.IIC2_SDA)`, `I2C(2,
  freq=400*1000)` 패턴(이 공식 예제 자체는 framebuf 드라이버 대신 저수준
  명령을 직접 보낸다). `examples/03-Machine/touch_user.py`도 I2C2에
  `scl=11, sda=12`를 써서 핀 선택을 교차 확인했다. FPIOA/I2C 핀·id 선택은
  이 공식 예제를 그대로 따르고, 그림 그리기는 더 풍부한 micropython-lib의
  framebuf 기반 드라이버를 쓰기로 했다 — 사용자가 요청한 text/line/pixel
  등 다양한 드로잉이 저수준 명령 방식보다 훨씬 적은 코드로 충족되기 때문.
  참고: https://www.kendryte.com/k230_canmv/en/v1.3/api/machine/K230_CanMV_I2C_API_Manual.html ,
  https://www.kendryte.com/k230_canmv/en/main/example/peripheral/fpioa.html
- **드라이버 포팅 범위**: `SSD1306`/`SSD1306_I2C`의 명령 시퀀스·
  `write_cmd`/`write_framebuf`는 upstream과 동일하게 유지하고, CanMV 전용
  코드(FPIOA 핀 설정, I2C 객체 생성)는 드라이버 밖(`display/src/oled_device.py`)으로
  분리했다 — 실기기에서 문제가 생겼을 때 "포팅 버그"와 "이 패널/펌웨어
  고유 문제"를 구분하기 쉽게 하기 위함.
- **`hand_renderer.py`를 순수 Python으로 분리**: 실기기 없이도 좌표 변환·
  정규화·클램핑 로직을 `machine`/`framebuf` 없이 PC에서 모킹 없이 단위
  테스트하기 위해서다. `display_ui.py`도 canvas를 덕 타이핑으로만 요구해,
  실제 SSD1306과 PC용 `VirtualOLED`가 같은 코드 경로를 타도록 했다.
- **기존 코드 참조(읽기 전용)**: `firmware/ui.py`의 `_SKELETON_CONNECTIONS`
  (21관절, palm-arc 없는 20개 연결선)를 확인하고 `hand_renderer.py`에
  동일한 리스트를 복제했다(import 아님). `firmware/`·`mac/`·최상위 문서
  전체를 grep해, 선택한 I2C 핀(GPIO11/12)이 기존 UART2(고정 보드 핀
  44/45)나 보관된 ST7789 LCD 테스트 핀(GPIO14/15/16/17/20/21)과 겹치지
  않음을 확인했다(확인됨).
- **상태 표시줄 레이아웃이 참고 목업과 다른 이유 (해결됨)**: 목업은 하단에
  "MOVE    FPS 8.5    HAND OK"(약 27자) 한 줄을 보여줬지만,
  `framebuf.FrameBuffer.text()`는 고정 8×8 비트맵 폰트만 제공해 128px에
  한 줄 최대 16자다(확인됨 — 스텁/표준 framebuf 동작 기준). 폰트 축소는
  기각했고(크기 조절 API 없음, 커스텀 폰트 렌더러는 범위 밖), 제스처
  라벨 5자 + FPS 4자 + 손인식여부 1자(약 12자)로 압축하는 방식을
  채택해 `_draw_status_bar()`에 구현했다. 코드 레벨(`test_display_ui.py`)로
  상태줄이 픽셀을 켜는 것은 확인했으나, 실제 패널 가독성은 미검증이다.
- **합성 "주먹" landmark가 정규화 후 펼친 손과 뚜렷이 안 구분됨 (부분
  해결/미해결)**: `hand_demo.py`의 주먹 좌표가 `layout_skeleton()`의
  bounding-box 확대·축소 후에도 펼친 손과 크게 달라 보이지 않았다. 원인은
  가설 — 손허리손가락관절(MCP)은 실제 주먹에서도 크게 움직이지 않아
  바운딩 박스가 여전히 넓게 잡히고, 정규화가 전체를 다시 화면 가득
  확대하면서 "손가락이 짧아진" 효과가 시각적으로 희석되는 것으로 추정했으나
  미확인이다. 손가락 끝(TIP) 좌표를 손목 쪽으로 더 당기는 조정으로 부분
  개선(선이 교차·꺾이는 형태로는 구분됨)했지만, 완전히 뭉친 실루엣은
  아니다. 렌더러 자체는 "꺾인 토폴로지도 예외 없이 그려짐"만 단위
  테스트(`test_fist_hand_also_lays_out_without_error`)로 확인했고, 손으로
  만든 합성 좌표의 한계로 판단해 낮은 우선순위로 미해결 상태로 남겼다 —
  시각적 "주먹다움"은 실제 AI 모델 출력으로 재검증이 필요하다.
- **PC 가상 렌더러(`VirtualOLED`)의 상태 텍스트가 흰 블록으로만 보이던
  문제 (해결됨)**: 생성된 PNG의 하단 상태 줄(`MOVE`, `8.5` 등)이 글자가
  아니라 속이 찬 흰 사각형으로 렌더링됐다. 원인은 확인됨 —
  `tests/virtual_oled.py`의 `VirtualOLED.text()`가 애초에 "글자당
  `fill_rect`로 속 찬 사각형을 그리는" 플레이스홀더였고, 실제
  `framebuf.FrameBuffer.text()`의 8×8 비트맵 폰트를 흉내 낸 것이 아니었다
  (파일 docstring에도 "NOT a pixel-accurate framebuf reimplementation"으로
  명시돼 있었음). MicroPython 업스트림 GitHub 소스
  (`extmod/font_petme128_8x8.h`, 96글리프·MIT 라이선스·Damien P. George;
  `extmod/modframebuf.c`의 `framebuf_text()`)를 `curl`로 직접 받아, 폰트
  바이트 테이블과 렌더링 알고리즘(컬럼 단위, LSB가 맨 위 픽셀인 비트 순서,
  글자당 8px, 32~127 범위 밖 문자는 127번 글리프로 대체)을 그대로 이식해
  해결했다. **소스 코드 레벨로 검증함** — CanMV의 `framebuf` 모듈이
  upstream 구현을 수정 없이 그대로 포함한다는 전제(근거: `framebuf.pyi`
  스텁 API 표면이 upstream과 동일) 하에서만 실제 패널과 일치하며, CanMV
  자체 C 소스 대조나 실기기 육안 비교는 못했다(실물 없음). 재생성한 PNG
  (`examples/output/*.png`, 128×64 원본 해상도 `*_native_128x64.png`
  포함)에서 `MOVE`/`DRAG`/`CLICK`/`STOP`/`8.5`/`H`/`-` 글자가 육안으로
  읽힌다.
- **손 관절 점이 3×3 사각형이라 너무 크고 서로 뭉쳐 보이던 문제
  (해결됨)**: `display_ui.py`의 `_draw_joint()`가 관절마다 3×3 채워진
  사각형을 그려서, 손가락 끝처럼 관절끼리 가까운 구간에서 사각형끼리
  뭉쳐 보였다. 단일 픽셀은 6배 확대 미리보기에서도 거의 안 보일 것으로
  판단해 처음에 3×3을 택했는데 실제로 과했다. 완전한 1×1 픽셀은
  연결선(1px)과 구분이 안 될 것으로 보고 대신 2×2로 축소했다
  (`fill_rect(x-1, y-1, 2, 2, 1)`, 화면 밖 클램핑은 유지). 재생성한 PNG에서
  21개 관절점이 이전보다 서로 분리돼 보임을 육안으로 확인했다(점 크기
  자체를 검증하는 자동 테스트는 없음). `display/` 단위 테스트 29개, 최상위
  프로젝트 테스트 78개 모두 영향 없이 통과.
- **손 스켈레톤이 화면에 비해 너무 작고 가늘게 보이던 문제 (해결됨)**:
  사용자가 지적한 뒤 원인을 좌표 정규화 수식·확대 비율·테스트용 관절
  데이터 세 가지로 나눠 분리 확인했다. `hand_renderer.layout_skeleton()`의
  정규화 수식(`scale = min(usable_w/span_x, usable_h/span_y)`, 종횡비
  보존 contain 방식)과 `config.SKELETON_MARGIN_PX=2`는 **원인이 아님
  (확인됨)** — 둘 다 의도대로 정확히 동작했고 여백은 무시할 수준이었다.
  실제 원인은 **확인됨** — `examples/hand_demo.py`의 테스트용 합성 관절
  데이터(`_open_hand()`)의 바운딩박스 비율이 70:112≈0.62(세로로 긴
  모양)인데, 스켈레톤 영역은 124:50≈2.48(가로로 넓은 landscape)이라
  `layout_skeleton()`이 종횡비를 지키며 더 작은 배율(세로 기준)에
  맞추다 보니 세로는 100% 채워도 가로는 약 26%만 채워졌던 것 — 알고리즘이
  아니라 입력 테스트 데이터의 모양이 landscape 패널과 안 맞았던 것이
  원인이다. 구조적으로 스켈레톤 영역(2.48:1)과 일반적으로 편 손 모양
  (1.0~1.3:1)의 비율 차이 때문에, 손의 실제 비율을 왜곡하지 않는 한 가로
  폭을 100% 채우는 것은 물리적으로 불가능하다는 점도 확인했다. (기각)
  `layout_skeleton()`에서 x/y축에 다른 배율을 곱해 강제로 채우는 방법 —
  손의 실제 비율을 왜곡해 사용자가 명시한 "실제 손의 비율 유지" 요구에
  위배되므로 채택하지 않음. (채택) `_open_hand()`/`_fist_hand()`의 합성
  좌표를 손가락이 더 옆으로 퍼진(엄지·새끼손가락이 더 바깥으로 뻗은)
  형태로 조정 — 각 손가락 내부 관절 간격·상대 비율은 그대로 두고 "손가락을
  넓게 편" 더 현실적인 포즈를 선택한 것이라 왜곡이 아니다. 결과:
  `_open_hand()` 바운딩박스 비율 0.62→1.23, `_fist_hand()` 0.94→1.31,
  스켈레톤 영역(124×50 usable) 기준 실제 렌더 가로폭이 열린 손
  32px→62px, 주먹 31px→66px로 약 2배 증가(세로는 둘 다 이미 50px로
  최대치였으므로 변화 없음) — `hand_renderer.layout_skeleton()`을 직접
  호출해 전/후 수치를 코드로 재계산해 **검증함**. 재생성한 PNG에서도
  육안으로 확인. 기존에 기록된 "주먹이 펼친 손과 뚜렷이 안 구분됨" 문제는
  이번 수정으로 해결되지 않았고 여전히 미해결로 남아 있다.
- **`DisplayUI`에 `joint_size` 옵션 추가 (2×2 vs 3×3 비교 지원)**:
  사용자가 2×2(기존 기본값)와 3×3 관절 점 버전을 같은 손 데이터로 나란히
  비교하고 싶어해서, `_draw_joint()`에 하드코딩돼 있던 2를
  `DisplayUI.__init__(..., joint_size=2)`의 인스턴스 속성으로 분리했다
  (기본값 2로 기존 동작과 동일하게 유지, 하위 호환). 동시에
  `examples/hand_demo.py`가 생성하는 PNG 시나리오를 26장 → 8장(열린 손
  joint_size=2/3 비교 2개 + 주먹 1개 + 손가락 모으는 동작 중간 프레임
  1개, 각각 확대+원본 해상도)으로 대폭 축소했다 — 사용자가 "PNG 너무
  많이 만들지 말고 2~3장만"이라고 명시적으로 요청했기 때문. `display/`
  단위 테스트 29개 전부 통과(기존 테스트는 `joint_size` 미지정이라 기본값
  2 경로를 계속 검증).
- **실제 AI 추론 루프 연결 방법 분석 (코드 변경 없는 리서치)**: `display/`를
  실제 `firmware/` 손 추적 결과에 연결하기 전, 연결 지점·형식·성능 영향을
  코드 레벨로 조사했다.
  - `display_ui.py`의 `_draw()`는 매 `update()` 호출마다 인자로 받은
    landmarks로 스켈레톤을 다시 계산해 그리며(캐싱 없음), `gesture` 인자는
    하단 상태 텍스트에만 쓰이고 스켈레톤 렌더링과는 무관함을 확인함
    (확인됨) — "제스처별 고정 손 모양" 로직은 존재하지 않는다.
  - `firmware/hand_tracker.py`의 `HandTracker.run(img)`가 반환하는
    `points`는 (x,y) 튜플 리스트가 아니라 `numpy.int16` flat 배열
    (`[x0,y0,x1,y1,...,x20,y20]`, 길이 42)이고, `firmware/ui.py`/
    `gesture_controller.py` 전체가 `points[i*2]`/`points[i*2+1]`로
    접근함을 확인(확인됨). 좌표 공간 `AI_RGB888P_SIZE=[640,360]`은
    `display/config.py`의 `AI_FRAME_WIDTH/HEIGHT`와 이미 일치하지만,
    `display/hand_renderer.landmarks_bounds()`는 (x,y) 튜플 21개 리스트를
    기대하므로 연결 시
    `[(points[i*2], points[i*2+1]) for i in range(21)]` 형태 변환이
    필요함을 확인.
  - 연결 대상은 `firmware/smart_glass_server.py`(main.py는 CLAUDE.md상
    보존 대상이라 제외)로 특정(확인됨, 코드 레벨) — 초기화부(tracker 생성
    근처, 새 `FEATURE_DISPLAY_OLED` 플래그로 기존 `FEATURE_DISPLAY_OSD`와
    독립적으로 OLED 리소스 생성)와 메인 루프(`tracker.run()` 직후, 손
    있음/없음 두 분기 모두). `action`은 이미 "MOVE"/"CLICK"/"DRAG"/"STOP"
    문자열로 나와 별도 변환이 필요 없음을 확인.
  - **통합 장애 요인 발견(미해결)**: `display/config.py`가 `import
    config`로 임포트되는데, CLAUDE.md의 flat 배포 규칙대로 `display/`를
    `firmware/`와 같은 `/sdcard/smart_glass/`에 평탄화하면 기존
    `firmware/config.py`와 모듈명이 충돌함(확인됨). 다른 display/
    파일명(`ssd1306.py`, `oled_device.py`, `hand_renderer.py`,
    `display_ui.py`)은 충돌 없음. 해결 방법(배포 시 리네임 vs 상수 병합)은
    아직 결정하지 않았다 — 다음 연결 작업의 선결 과제.
  - **성능 영향 분석(가설 위주, 미확정)**: `ssd1306.py`의 `show()`가
    128×64 전체 프레임(1024 byte)을 부분 갱신 없이 `i2c.writevto()` 1회로
    통째로 전송함을 확인(확인됨). `I2C_FREQ=400kHz` 기준 1회 전송 시간은
    가설 — 약 20~25ms로 추정(실측 아님). 기존에 실측된 AI 루프 속도(약
    8~9fps, 프레임당 110~125ms)와 비교하면 `MIN_UPDATE_INTERVAL_MS=100ms`
    스로틀이 루프 속도와 비슷해 실질적으로 거의 매 프레임 실제 갱신이
    발생할 가능성이 높고, 추정 20~25ms는 프레임 예산의 약 15~20%에
    해당함(가설, 미확정). `machine.I2C.writevto()`의 실기기 블로킹
    동작은 이미 미확인으로 기록돼 있고, 현재 `display_ui.update()`의
    try/except는 예외만 구제할 뿐 오래 블로킹되는 경우의 타임아웃/안전장치는
    없음을 확인(확인됨 — 코드에 없음). AI 추론·UART/UDP 마우스 전송·웹
    스트리밍이 전부 단일 스레드를 공유하므로 OLED I2C가 블로킹되면 전체
    루프가 같이 멈출 위험이 있다(가설, 미검증).
- **첫 실기기 배선/부팅 테스트 — I2C 통신과 실제 화면 출력 모두 확인됨
  (해결됨)**: 실제 Voltly VLT-OL016(0.96인치 White I2C OLED, 4핀)을
  K230D-Zero에 연결(GND-GND, VCC-3V3, SCL-IO11, SDA-IO12 — `config.py`의
  후보 핀과 정확히 일치)한 뒤 `display/`를 `/sdcard/display/`에 평탄화
  배포하고 `oled_basic_test.py`를 실행했다. 콘솔 로그:
  `i2c.scan() -> ['0x3c']`, `ready (128x64 @ 0x3C)`, cleared/full-on/
  text+shape 전부 OK, PASSED(2회 재실행 모두 동일). **I2C 핀
  (GPIO11=SCL/GPIO12=SDA, I2C2)과 주소(0x3C)가 실기기에서 확인됨
  (확인됨)** — 기존에 "공식 예제 기반 후보, 실기기 미검증"이었던 항목.
  처음에는 사용자가 "화면에 아무것도 안 뜬 것 같다"고 보고해 원인 미확인
  상태로 기록했었으나, 사용자가 다시 확인한 결과 **오인이었음이 밝혀짐
  (확인됨)** — 실제로는 검정→흰색 전환과 "EdgeGlass OLED"/"OK" 텍스트+
  사각형이 전부 정상 출력됐고, 그 직후 `oled_basic_test.py`의 `finally`
  블록이 `oled_device.close_display(oled)` → `oled.poweroff()`를 호출해
  화면이 꺼지는 것(의도된 동작)을 "안 떴다"로 오인한 것이었다. 추가로
  화면을 흰색으로 켠 채 무한 루프로 유지하는 진단 스크립트
  (`oled.contrast(255); oled.fill(1); oled.show()` 후
  `while True: time.sleep(1)`, 보드에만 임시 작성)를 실행해 사용자가
  "흰색 유지되고 있어 굿"이라고 직접 재확인했다(`canmv_stop_script`로
  정상 종료 — IDE interrupt → soft reboot, 4-1/21의 기존에 알려진 정상
  정지 패턴과 동일). **결론: VLT-OL016의 I2C 통신, 주소, SSD1306 초기화
  시퀀스, 실제 화면 출력(지우기/전체 켜짐/텍스트+도형)까지 전부 실기기
  육안으로 검증 완료** — `archive/st7789_lcd`의 "코드는 PASSED인데 화면엔
  안 나왔던" 사례와 달리, 이번에는 코드 레벨 성공과 시각적 성공이 둘 다
  확인된 첫 사례다. 남은 것: 이번에 검증한 것은 `oled_basic_test.py`의
  기본 bring-up까지이고, `DisplayUI`(21개 손 관절 스켈레톤 렌더링)를
  실기기에서 실행해 본 적은 아직 없으며 실제 AI 추론 루프 연결(4-3 앞
  항목에서 분석만 함)도 아직 구현 전이다.
- **`str.ljust()`가 이 보드의 MicroPython 빌드에 없어 스켈레톤 렌더링이
  매 프레임 실패하던 문제 (해결됨)**: `DisplayUI`(21개 손 관절
  스켈레톤)를 실기기에서 처음 실행해보려고 새 보드 전용 테스트
  `examples/oled_hand_demo.py`(합성 손 좌표로 실제 패널에서 `DisplayUI`를
  구동 — `oled_basic_test.py`와 달리 스켈레톤 렌더링 경로까지 실제로
  실행하는 첫 보드 테스트)를 작성해 배포·실행하자, 콘솔에 매 프레임
  `[OLED] update() draw failed: AttributeError("'str' object has no
  attribute 'ljust'",)`가 출력되고 화면에 스켈레톤이 전혀 그려지지
  않았다(`DisplayUI.update()`의 기존 try/except가 예외를 삼켜 보드 자체가
  멈추지는 않았음). 원인은 확인됨 — `display_ui.py`의
  `_draw_status_bar()`가 `label = (gesture or "")[:5].ljust(5)`로 상태
  텍스트를 패딩했는데, PC의 CPython에는 `str.ljust()`가 있어 단위 테스트
  29개는 전부 통과했지만 이 K230D-Zero CanMV MicroPython 빌드
  (v1.8-0-gc2d1f5c)의 str 타입에는 `ljust()`/`rjust()`가 구현돼 있지
  않다 — PC 테스트가 실기기 MicroPython API 서브셋 차이를 못 잡아낸
  사례로, `bytes.decode(errors=...)` 키워드 인자 버그(10-4-2, K-1)와
  같은 종류. (채택) `.ljust(5)` 호출을 제거하고
  `label = (gesture or "")[:5]; label = label + " " * (5 - len(label))`로
  수동 패딩하는 코드로 교체 — 슬라이싱과 문자열 `+`/`*`는 CPython/
  MicroPython 양쪽에서 동일하게 지원된다. `display/` 전체에서
  `.ljust`/`.rjust`/`.format(`/f-string 사용을 재검색해 다른 곳에는 이
  패턴이 없음을 확인(확인됨). 검증 결과: PC 단위 테스트 29개 재실행 전부
  통과(회귀 없음), 보드의 `/sdcard/display/display_ui.py`에도 재배포 후
  `oled_hand_demo.py`를 다시 실행한 결과 `AttributeError` 없이 그리기가
  성공하는 것을 콘솔 로그로 확인함(에러 로그가 더 이상 찍히지 않음).
- **`display/config.py` 모듈명 충돌을 `display_config.py`로 리네임해 해결
  (해결됨)**: `display/config.py`와 `firmware/config.py`가 둘 다
  `config.py`라서, 평탄화해서 같은 디렉터리(`/sdcard/smart_glass/`)에
  배포하면 하나가 다른 하나를 가린다는 문제를 이전 턴에 발견만 하고
  해결은 미뤄뒀었다. 원인은 확인됨 — 두 독립 모듈이 각자 개발되며
  우연히 같은 파일명을 씀. (채택) `display/config.py`를
  `display/display_config.py`로 리네임(로컬 소스 자체 변경, 배포 시
  별도 변환 없이 그대로 평탄화 복사). `src/oled_device.py`,
  `src/display_ui.py`의 `import config`를
  `import display_config as config`로 바꿔 코드 내부의 `config.XXX`
  참조는 그대로 유지(변경 범위 최소화). `tests/test_display_ui.py`의
  테스트 내부 `import config` 2곳도 동일하게 변경. 검증 결과: PC 단위
  테스트 29개와 `examples/hand_demo.py` PC 데모 재실행 전부 정상 동작,
  보드에 `/sdcard/smart_glass/display_config.py`로 배포한 뒤 아래 통합
  테스트에서 `firmware/config.py`와 충돌 없이 둘 다 정상 import됨을
  실기기로 확인.
- **실제 AI 추론 루프(`firmware/smart_glass_server.py`)와 OLED 연동 —
  첫 실기기 통합 성공 (해결됨)**: 이전 턴들은 연결 지점 분석(연구)과
  더미 데이터 bring-up 테스트까지만 했고, 실제 `hand_tracker.py` 결과를
  OLED에 연결하는 구현·배포·실행은 이번에 처음 했다. 구현(`main.py`는
  건드리지 않음): 새 `FEATURE_DISPLAY_OLED` 플래그를 기존
  `FEATURE_DISPLAY_OSD`와 독립된 별개 물리 디스플레이로 추가;
  `oled_device`/`display_ui`를 try/except ImportError로 가드 임포트(미배포
  시에도 오케스트레이터 전체가 죽지 않도록); 메인 루프에서
  `tracker.run()`의 flat `points` 배열(`[x0,y0,x1,y1,...,x20,y20]`)을
  `[(points[i*2], points[i*2+1]) for i in range(21)]`로 변환해 매 프레임
  `DisplayUI.update()`에 전달, 손이 없을 때는 `landmarks=None`을 명시적
  전달(`_draw()`가 매번 `canvas.fill(0)`을 먼저 호출하므로 이전 프레임
  스켈레톤이 안 남음을 보장); 제스처 `action`은 하단 상태 텍스트에만
  전달(스켈레톤은 항상 실제 landmarks로만 그려짐, 더미 고정 포즈 없음 —
  이전 턴에 코드 레벨로 이미 확인된 설계 그대로); 30프레임마다만
  갱신되는 fps를 `last_fps`에 캐싱해 매 프레임 전달; `finally`에
  `oled_device.close_display(oled)` 추가. OLED는 기존
  `MIN_UPDATE_INTERVAL_MS=100ms` 내부 스로틀을 그대로 쓰고 매 프레임
  강제 갱신하지 않음(이전 턴에 분석한 I2C 성능 영향 완화를 위해 추가
  조정 없이 기존 안전장치에 의존). 배포 전 보드의 기존
  `smart_glass_server.py`가 로컬 git HEAD와 바이트 단위로 완전히 일치함을
  먼저 확인(27493바이트 동일, 보드 자체 수정 없었음 확인)한 뒤 덮어썼고,
  배포 후 전 파일 바이트 크기를 로컬과 대조해 일치 확인. **검증 결과:
  실기기 통합 테스트 성공(확인됨)** — `run_uart.py`(Wi-Fi 없이 UART만,
  카메라+AI+OSD+OLED 경로)로 실행해 `[OLED] i2c.scan() -> ['0x3c']`,
  `[OLED] ready (128x64 @ 0x3C)`, `[OLED] display ready`가 출력되고 실제
  손 움직임에 따라 `[ORCH] ACTION: MOVE`/`STOP`과 `CLICK_DECISION`/
  `CLICK_TX` 로그가 실시간으로 바뀌는 것을 확인했으며, **사용자가 OLED
  패널에서 실제 손 움직임을 따라가는 스켈레톤과 하단 상태 텍스트 변화를
  직접 육안으로 확인하고 "잘됨"이라고 확인함**. 카메라+AI 추론+제스처
  판정+UART 마우스 전송+OLED가 동시에 크래시 없이 동작.
- **OLED 모듈을 `display/`에서 `firmware/`로 이동 — 단일 원본 통합**:
  LED 조사가 끝난 뒤 사용자가 실제 통합·배포·실행을 요청하면서, display/
  테스트 폴더의 모듈을 실제 firmware/ 구조로 옮겨 정리해달라고 명시적으로
  요청함. `display/display_config.py`, `display/drivers/ssd1306.py`,
  `display/src/oled_device.py`, `display/src/hand_renderer.py`,
  `display/src/display_ui.py` 5개 파일을 각각 `firmware/display_config.py`,
  `firmware/ssd1306.py`, `firmware/oled_device.py`,
  `firmware/hand_renderer.py`, `firmware/display_ui.py`로 물리적으로
  이동(복사 아님, 중복 보관 안 함) — 선택 이유: CLAUDE.md의 "로컬
  firmware/가 보드에 배포되는 코드의 단일 원본" 원칙과, 이 모듈들이 이미
  `smart_glass_server.py`에서 쓰여 보드에 배포되는 상태라는 점에서 원본이
  display/에 남아있는 게 "로컬 구조=보드 배포 구조" 원칙에 어긋났기
  때문. 복사가 아니라 이동을 택한 이유는 두 벌을 유지보수하며 생기는
  동기화 드리프트 위험을 피하기 위함. `display/`는 이제 PC 전용 테스트
  하네스(`tests/`, `examples/`)만 남고, 그 테스트들은 firmware/의 모듈을
  직접 import하도록 sys.path 설정을 변경. 영향받은 빈 디렉터리
  (`display/src/`, `display/drivers/`)와 `__pycache__` 캐시는 정리해
  삭제. **검증 결과**: PC 단위 테스트 29개, `examples/hand_demo.py` PC
  데모, 최상위 프로젝트 테스트 78개 전부 재실행해 영향 없음 확인(회귀
  없음). 보드 배포본(`/sdcard/smart_glass/`)도 전부 로컬과 바이트 단위
  크기 일치 확인하며 재배포. 보드의 구버전 `/sdcard/display/` 디렉터리
  (이동 전 잔재)는 삭제하고, `oled_basic_test.py`/`oled_hand_demo.py`는
  새 경로(`/sdcard/smart_glass/`)로 재배포. `display/README.md`의 폴더
  구조·배포 경로 설명도 새 구조에 맞춰 갱신.
- **UART 마우스 + Wi-Fi 웹서버 동시 실행용 새 진입점
  `firmware/run_uart_web.py` 추가**: 사용자가 "카메라+AI+OLED+UART
  마우스"와 "+ Wi-Fi 웹서버"를 각각 별도 단계로 전력 측정하고 싶어했는데,
  기존 `run_uart.py`(UART, 웹 끔)와 `run_wifi.py`(UDP 마우스+웹)로는
  "UART 마우스 유지 + 웹서버 켜기" 조합이 없었음. (채택)
  `smart_glass_server.main(transport_kind="uart", enable_web=True)`를
  고정하는 새 얇은 진입점 파일을 기존 run_uart.py/run_wifi.py와 동일한
  패턴으로 추가 — `smart_glass_server.py` 자체는 수정하지 않음(이미
  transport_kind와 enable_web이 독립적으로 동작하도록 설계돼 있었고,
  `transport.wifi_is_needed()`가 `web_server_enabled`만으로도 True를
  반환하는 로직을 코드로 확인함). 선택 이유: 기존에 검증된 두 진입점은
  그대로 보존하고 새 조합만 얇게 추가하는 게 "이미 성공한 기능을
  재구현하지 않는다"는 재사용 원칙에 맞기 때문. 검증 결과: 로컬 AST 문법
  검사 통과. 보드 배포 후 1단계(카메라+AI+OLED+UART, `run_uart.py`
  재실행)에서 `[OLED] display ready`까지 정상 확인(전력 측정 1단계
  진행 중, 사용자 측정 대기). 2단계(`run_uart_web.py`)는 아직 실행 전.
- **카메라+AI+OLED+UART+Wi-Fi+웹서버 전체 조합 첫 성공 (확인됨)**: 사용자가
  전원만으로 자동 부팅되게 설정해달라고 요청. 과거(`tools/DEPLOY.md`
  2026-10-21 기록)에 이 조합 계열에서 `HttpServer: bind failed after 20
  retries`나 `MediaManager.init()` 오설정으로 인한 완전 먹통 등 실패
  사례가 있었고, OLED가 추가된 이번 전체 조합은 이번 세션에 한 번도 끝까지
  같이 실행해 본 적이 없었다. 그래서 자동 부팅을 설정하기 전에 먼저 USB로
  수동 실행해 이 조합이 실제로 안정적으로 도는지 검증하기로 함(전원 테스트
  전 안전장치). `run_uart_web.py`를 USB REPL로 수동 실행한 결과, 카메라
  (채널0 OSD+채널1 웹+채널2 AI)+AI 추론+OLED+UART2 마우스+Wi-Fi+웹서버가
  전부 동시에 크래시 없이 정상 동작함을 확인: `[OLED] i2c.scan() ->
  ['0x3c']`/`ready`/`display ready`; 집 Wi-Fi(`SK_WiFiGIGA3A00_2.4G`)는
  거부됨("rejected by the Wi-Fi driver", 비밀번호 또는 보안 모드 문제로
  추정, 미확인)되었으나 핫스팟(`i`)으로 자동 폴백 성공 — 기존 "집 Wi-Fi
  우선, 실패 시 핫스팟 폴백" 로직이 실제로 작동함을 재확인; `[WEB] Server
  started`, `URL: http://172.20.10.3:8060/`로 웹서버 정상 bind(과거
  기록된 bind 실패 재발 없음); `[AI] Gesture tracking started` 후
  `[ORCH] ACTION: STOP/MOVE` 전환과 `CLICK_DECISION`/`CLICK_TX` UART
  패킷 송신이 지속적으로 정상 발생, 수 분 관찰 동안 멈추거나 재부팅되지
  않고 안정적으로 유지됨. **결론**: 이 전체 조합이 이번에 처음으로
  실기기에서 끝까지 안정적으로 동작함이 검증됐다 — OLED 추가 이후, 그리고
  과거 bind 실패/MediaManager 행 사례 이후 처음으로 이 조합 전체가 성공한
  사례. 이로써 자동 부팅 기본값으로 설정하기 전 안전 확인이 완료됨.
- **전원 재인가 자동 실행 테스트 — MCP 연결 자체의 관찰자 효과 발견, 원인
  미확정(진행 중)**: `/sdcard/boot.py`/`/sdcard/main.py`(`tools/autorun/`)를
  배포한 뒤 사용자가 USB선을 완전히 뽑았다 다시 꽂아 전원 재인가 테스트를
  했으나 "스크립트가 실행 안 되는 것 같다"고 보고함. Claude가
  `canmv_connect_board`로 재연결해 로그를 본 결과 `File "<stdin>", line
  14, in <module>` / `Exception: IDE interrupt` 트레이스백이 나타났다.
  `<stdin>` 소스라는 점과 `line 14`가 `/sdcard/main.py`의 카운트다운 루프
  (`time.sleep(1)`) 위치와 일치한다는 정황 근거로, boot.py/main.py 자체는
  실행되고 있었는데 Claude의 디버그 연결이 그 순간 보드에 인터럽트를 걸어
  멈췄을 가능성이 있다고 봤다(가설, 완전히 확정 아님) — MCP 디버그 연결
  행위 자체가 이미 자동 실행 중인 흐름을 끊는 "관찰자 효과"가 있을 수
  있다는 방법론적 제약을 발견. 이에 따라 "전원 재인가 직후 Claude가 바로
  연결하지 않고, 사용자가 먼저 OLED/웹서버를 직접 확인한 뒤 보고" 하는
  절차로 바꾸기로 함. **그런데 사용자가 이 방식대로(Claude 연결 없이) USB선을
  뽑았다 몇 초 뒤 다시 꽂아 재시도했을 때도 "똑같은 것 같다"(여전히 실행
  안 되는 것처럼 보임)고 보고함** — 이로써 "Claude의 연결이 유일한 원인"
  이라는 가설은 약화됐으나, 사용자가 정확히 무엇을(OLED 화면/웹 URL
  중 무엇을, 몇 초나 기다린 뒤) 확인했는지는 아직 구체적으로 확인하지
  못했다(미확인) — 다음 단계로 Claude가 연결해 실제 로그를 직접 볼 예정,
  아직 원인 미확정.
  **후속 확인**: Claude가 재연결해 로그를 본 결과 `>>> [BOOT] launching
  in 4...`까지 카운트다운이 실제로 출력된 뒤 또 `Exception: IDE
  interrupt`로 끊기는 패턴이 재현됐다(두 번 연속, 거의 같은 지점). 이
  시점엔 사용자도 Claude도 직접 개입하지 않았는데도 매번 비슷한 지점에서
  끊긴다는 점에서, **Mac에서 실행 중인 VS Code CanMV 확장이 보드가 USB로
  다시 나타나는 것을 감지하면 자동으로 재연결하며 REPL을 가로채는 것**이
  유력한 원인으로 떠올랐다(가설, 확장 자체의 동작을 직접 들여다보지는
  못해 완전히 확정은 아님). 이게 맞다면 같은 Mac에 USB로 물려 있는 한
  "순수 전원만" 자동 실행 테스트가 근본적으로 성립하기 어려우며, 다음
  검증 방법으로 이 Mac이 아닌 별도 전원(충전기/보조배터리)으로 전원을
  공급해 CanMV 확장이 아예 보드를 못 보는 상태에서 재확인할 것을
  제안함(아직 그 방식으로 재시도하지 않음).
- **자동부팅에서 Mac UDP 마우스 제어가 안 되는 원인 — 전송 방식 불일치
  (확인됨, 코드 수정 없는 순수 분석)**: Wi-Fi 웹서버는 자동부팅에서 정상
  동작하는데 Mac의 UDP 디스커버리 브리지(`mac_mouse_bridge.py`)가
  "DISCOVERY: Waiting for board..."에서 멈춰 있다는 보고를 받고 코드만
  대조해 분석함(수정·배포·재부팅 전혀 안 함). `/sdcard/main.py`(자동부팅)는
  `smart_glass_server.main(transport_kind="uart", enable_web=True)`를
  직접 호출 — `firmware/run_uart_web.py`와 동일 프로필이라 마우스 전송은
  무조건 UART(코드 확인됨, `smart_glass_server.py:432`). `transport.py:
  196-197`의 `create_transport()`는 `kind == "uart"`일 때 `UartTransport()`
  만 반환하며 UDP 소켓이나 `discovery.py`의 `@HELLO/@ACK` 자동 탐색은
  `kind == "udp"` 분기에만 있어 전혀 실행되지 않음 — 보드가 UDP 패킷을
  1개도 안 보내는 상태(확인됨). 포트 설정 자체는 양쪽 다 9000으로 일치
  (`config.py MOUSE_UDP_PORT`, `mac_mouse_bridge.py DEFAULT_UDP_PORT`)하지만
  무관함. **결론**: IP/포트 문제가 아니라 전송 채널 자체가 다른 것이
  원인(UART2 물리 케이블 vs UDP 무선) — 자동부팅을 UART 그대로 쓰려면
  Mac도 UART로 맞춰야 하지만 그러면 케이블이 필요해 "전원만으로 무선
  동작" 목표와 모순되고, 자동부팅을 UDP로 바꾸면(`run_wifi.py`와 동일
  조합 가능) `config.py` 자체 주석에 이미 "udp는 아직 실기기 미검증"이라고
  적혀 있어 별도 검증이 필요함 — 둘 다 제안만 하고 적용은 하지 않았다.
- **자동부팅을 UART에서 UDP로 전환 (적용 완료, 실기기 검증 진행 중)**:
  사용자가 위 분석을 바탕으로 자동부팅의 마우스 전송 방식을 UDP로
  바꿔달라고 요청, 기존 `run_wifi.py`를 재사용하고 `run_uart.py`는 건드리지
  말라고 지시함. 변경 전 먼저 OLED가 통합된 지금 코드로
  `firmware/run_wifi.py`(`transport_kind="udp", enable_web=True`)를 USB
  REPL로 수동 실행해 검증(이 조합을 OLED 통합 이후 이번 세션에 실행한 적이
  없었음) — `[UDP] Waiting for Mac registration...` → `[UDP] Mac
  registered: 172.20.10.2:9000` → `[UDP] Mouse control ready`까지 정상
  동작 확인(확인됨, 실기기 로그) — Mac이 보고했던 바로 그 IP로 정확히
  등록됨. 이어서 `tools/autorun/main.py`의
  `smart_glass_server.main(transport_kind="uart", enable_web=True)`를
  `transport_kind="udp", enable_web=True`로 변경(`run_wifi.py`와 동일
  프로필), docstring에 전환 이유(UART는 Mac에 케이블이 필요해 "전원만으로
  무선 동작" 목표와 모순)를 명시. `firmware/run_uart.py`는 전혀 수정하지
  않음(확인됨 — 보드에서 재다운로드해 `transport_kind="uart",
  enable_web=False`로 기존과 동일함을 재확인). `canmv_save_main_py`로
  `/sdcard/main.py`에 재배포 후 재다운로드해 `transport_kind="udp"`로
  반영됐음을 확인. `tools/autorun/README.md`에도 전환 이유와 날짜를 기록.
  실제 전원 재인가(물리 파워사이클)로 자동부팅+마우스 조작까지 검증하는
  것은 아직 진행 중 — 직전에 발견한 "Claude의 MCP 연결 자체가 보드의
  자동 실행을 끊는 관찰자 효과" 가설 때문에, 이번엔 Claude가 연결하지
  않고 사용자가 직접(OLED 화면, Mac 브리지의 Board registered 로그, 실제
  커서 이동) 확인한 뒤 보고하는 절차로 진행 중 — 아직 결과 보고받지 못함.
- **자동부팅(UDP) 최종 전원 재인가 테스트 — 성공 확인 (2026-10-26)**:
  위 절차대로 Claude가 연결하지 않은 상태에서 사용자가 직접 전원을
  재인가해 테스트한 결과, OLED 화면 출력·Mac 브리지의 보드 등록·실제 손
  움직임에 따른 Mac 커서 이동까지 전부 정상 동작함을 확인(확인됨, 사용자
  직접 확인). 이로써 "자동부팅을 UDP로 전환"과 "MCP 연결의 관찰자 효과를
  피해 사용자가 직접 확인" 두 가지 모두 유효한 해결책으로 검증됨 — 관찰자
  효과 가설 자체의 근본 원인(VS Code CanMV 확장의 자동 재연결 여부)은
  여전히 미확정이지만, 이를 회피하는 절차만으로 실사용 목표(전원만 연결)는
  달성됨.
- **문서 점검 및 최신화 (2026-10-26)**: 위 전원 재인가 성공을 계기로
  `README.md`와 `../시연용_README.md`(저장소 상위 디렉토리)를 현재 구현과
  대조 검토함. `README.md`에서 두 가지 사실 오류를 확인해 수정: (1)
  `firmware/config.py`를 "어디서도 import되지 않는 placeholder"라고
  설명했으나 실제로는 `smart_glass_server.py`가 `MOUSE_TRANSPORT`,
  `MOUSE_UDP_*`, `VERBOSE_ORCHESTRATOR_LOGS`를 import해 사용 중임을
  코드로 확인(확인됨). (2) `smart_glass_server.py`의 웹서버를 "소켓 bind
  단계에서 막혀 미완료"라고 설명했으나 이번 세션 중 실기기에서 이미 전체
  조합(카메라+AI+OLED+Wi-Fi+UDP+웹) 검증이 끝난 상태라 outdated였음(수정).
  누락돼 있던 `run_uart.py`/`run_wifi.py`/`run_uart_web.py`,
  `transport.py`/`wifi.py`/`discovery.py`, OLED 5개 모듈,
  `tools/autorun/` 항목도 "파일 역할" 표에 추가. `../시연용_README.md`는
  자동부팅(A)/UART(B)/Wi-Fi(C) 세 경로를 모두 반영하도록 재구성(A 섹션
  신규 작성 포함)하고, "집 Wi-Fi 연결 성공률" 설명에 이번 세션 관찰(집
  Wi-Fi가 매번 거부되고 핫스팟으로 전환됨, 원인 미확인)을 2026-10-23
  기존 기록에 덧붙임 — 기존 수치(연속 3회 중 2회 성공)는 삭제하지 않고
  날짜별로 구분해 병기.

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
6. **`display/` OLED — bring-up부터 실제 AI 루프 연동까지 실기기 검증
   완료** — I2C 핀(GPIO11=SCL/GPIO12=SDA, I2C2), 주소(0x3C), SSD1306
   초기화, 화면 출력, 그리고 `firmware/smart_glass_server.py`를 통한 실제
   `hand_tracker.py` 손 관절 스켈레톤 실시간 표시까지 전부 실기기
   육안으로 검증됐다(본 문서 4-3). PC 가상 렌더러의 폰트 렌더링은
   **소스 코드 레벨로는 해결**(upstream MicroPython 폰트/알고리즘
   포팅)됐고, 남은 것은 실제 패널에서의 글자 모양 육안 비교뿐이다.
7. **카메라 센서 구동 시 보드 LED 점등 — 원인 미확정, "카메라 전원" 가설은
   약화됨** — `smart_glass_server.py`(카메라 포함 전체 통합)를 처음
   실행하자 보드 LED가 켜짐(사용자 보고: 눈이 아플 정도로 밝음). 최초
   가설은 "OV5647 카메라 모듈 전원 인가 시 하드웨어 내장 LED가 자동
   점등"이었으나, **사용자가 "카메라는 전부터 계속 썼는데 이번에 처음
   켜졌다"고 반증 정보를 제공해 이 가설은 약화됨.** 코드 기준 재조사
   결과(이번에도 LED를 끄거나 펌웨어를 수정하지 않음, 순수 조사만):
   - 확인됨 — `git diff firmware/smart_glass_server.py`로 대조한 결과,
     카메라/Display 초기화 코드(`CameraRig.create()` 전체)는 이번 턴에
     1바이트도 바뀌지 않았다. 수정분은 전부 새로 추가된 OLED 코드뿐이다.
   - 확인됨 — 이 diff에서 GPIO/전원 레벨 하드웨어를 새로 건드리는 코드는
     `oled_device.open_display()` 내부의 `FPIOA().set_function(11,
     FPIOA.IIC2_SCL)` / `set_function(12, FPIOA.IIC2_SDA)` /
     `I2C(2, freq=400000)` 세 줄이 유일 — GPIO11/12에 FPIOA 함수를
     할당하는 코드가 이 프로젝트에서 이번 세션에 처음 실행됐다.
   - 확인됨 — 캐시된 CanMV 공식 예제 492개를 검색했으나 보드 LED나 카메라
     LED를 설명하는 예제/문서를 찾지 못함. 유일한 관련 예제
     (`examples/27-Gesture-controlled-light/led_control.py`)는 GPIO42/43에
     사용자가 직접 배선한 외부 LED를 PWM으로 제어하는 별개 참고 프로젝트.
   - 미확인 — GPIO11/12가 보드 자체에서 LED와 물리적으로 연결돼 있는지는
     소프트웨어 grep으로 답할 수 없음. 실제 보드의 `FPIOA.help(11)`/
     `FPIOA.help(12)` 조회나 공식 핀맵 문서로만 확인 가능한데, 실시간
     테스트 중단이 필요해 사용자 승인을 받고 조회할 예정 — 아직 실행 전.
   - (이전 턴 가설, **이번 턴 실기기 분리 테스트로 반증·기각됨** — 아래 참고)
     카메라 전원보다는 GPIO11/12 FPIOA 설정이 더 유력하다고 봤던 가설.

   **단계별 분리 테스트 (사용자 제안, 실기기로 직접 확인) — OLED는 원인에서
   배제됨(확인됨)**: 펌웨어를 수정하지 않고 별도 진단 스크립트
   (`display/examples/led_stage_test.py` → `/sdcard/smart_glass/
   led_stage_test.py`)를 만들어 `STAGE` 상수만 바꿔가며 한 단계씩
   실행하고, 매 단계 사용자가 직접 LED를 육안 확인한 뒤에만 다음 단계로
   진행했다:
   1. 카메라(Sensor)+OSD(Display.init)만, OLED 코드 0줄 — **LED 안 켜짐**
   2. + `FPIOA.set_function(11/12, IIC2_SCL/SDA)`(I2C 객체 없음) — **안 켜짐**
   3. + `I2C(2, freq=400000)` 객체 생성(scan 전) — **안 켜짐**
   4. + `i2c.scan()`(`['0x3c']` 정상 감지) — **안 켜짐**
   5. + `SSD1306_I2C(...)` 생성(초기화 명령 전송 + fill(0)+show() 포함) — **안 켜짐**
   6. + 화면 전체를 흰색으로(fill(1)+show()) — **안 켜짐**

   즉 OLED 관련 코드 경로(GPIO11/12 FPIOA, I2C2 통신, SSD1306 초기화,
   실제 화면 출력)를 전부 실행해도 LED는 켜지지 않았다 — **이전에 "GPIO11/12가
   더 유력하다"고 했던 가설은 이번 분리 테스트로 반증되어 기각됨.** OLED는
   LED 점등 원인에서 사실상 배제됨.

   **새로운 용의선(가설, 미검증)**: 위 진단에는 없었지만 실제로 LED가
   켜졌던 `run_uart.py`(smart_glass_server.py 전체 통합) 실행에만 있던
   요소들 — `HandTracker` 생성(hand_det.kmodel/handkp_det.kmodel을 NPU에
   로드), 실제 AI 추론 루프(`tracker.run()` 반복 NPU 추론), 카메라
   채널2(AI용)에서 반복적으로 `sensor.snapshot()`하는 루프, UART 마우스
   컨트롤러. 다음 단계로 "OLED 없이 카메라+OSD+AI 추론(HandTracker, 반복
   루프)만" 조합을 테스트할 예정(사용자 승인받음, 다음 턴에 진행). 당장은
   테이프로 물리적으로 가리는 방법을 안내함(미해결).

   **후속 테스트(AI/NPU 추론) — 확인됨, 추가로 배제됨**: 별도 진단
   스크립트(`display/examples/ai_stage_test.py`)로 카메라+OSD만 깐 상태에서
   (1) `HandTracker` 생성(hand_det.kmodel/handkp_det.kmodel을 NPU에 로드)과
   (2) 실제 NPU 추론 20~30회 반복(`tracker.run()`, 손 인식 성공 확인)까지
   사용자가 매 단계 직접 확인했으나 **LED 안 켜짐**. AI/NPU 추론 경로도
   원인에서 배제됨. (참고: 3단계 추론 도중 USBDBG 연결이 한 번 끊기며
   `IDE interrupt` 없이 조용히 소프트 리부트된 사건이 있었으나, 그 순간도
   LED는 꺼져 있었다고 사용자가 확인함 — 이 리부트 자체와 LED는 무관.)

   **후속 테스트(UART2) — 확인됨, 마지막 용의선도 배제됨**: 별도 진단
   스크립트(`display/examples/uart_stage_test.py`)로 카메라+OSD만 깐
   상태에서 (1) `MouseController(AI_RGB888P_SIZE)` 생성(`UART(UART.UART2,
   115200, 8N1)` 오픈, FPIOA 핀 할당 없음, 고정 보드 핀)과 (2) 실제
   `mouse_controller.update()` 호출로 MOVE/CLICK/STOP `@MOUSE` 프로토콜
   라인을 UART2로 전송하는 것까지 전부 **LED 안 켜짐**. 이로써 OLED(6단계
   전부)·AI/NPU 추론(모델 로드+실제 추론)·UART2(생성+실제 전송) —
   `run_uart.py`를 구성하는 모든 개별 요소가 분리 테스트로 LED와 무관함이
   확인됨.

   **최종 재현 시도 — 확인됨**: 사용자 지시대로 추가 추측 테스트를 만들지
   않고, LED가 실제로 켜졌던 원본 `run_uart.py`(smart_glass_server.py 전체
   통합, FEATURE_DISPLAY_OLED=True 포함)를 코드 변경 없이 그대로
   재실행했다. `[OLED] display ready`, 메인 루프의 `[ORCH] ACTION:
   MOVE/STOP` 반복까지 정상 확인했으나, **이번에는 LED가 켜지지 않음**
   (사용자 확인: "안켜지네 버그였나봐").

   **최종 결론(확인됨)**: OLED, AI/NPU 추론, UART2를 포함한 전체 코드
   경로를 개별적으로도, 원본 그대로도 재현 시도했으나 LED가 다시 켜지지
   않았다 — 이 프로젝트의 어떤 코드 경로도 LED 점등과 결정론적으로
   연결되지 않음이 실기기 재현 시도로 확인됐다. 최초 1회 관찰된 LED
   점등은 이 레포지토리의 코드가 아니라, 그 순간의 **일시적 하드웨어/전원
   글리치(원인 미상)였을 가능성이 가장 높다** — 재현 불가로 더 이상
   특정할 근거가 없다. 조사는 이것으로 종결하되, 재발 시 이번에 만든 세
   진단 스크립트(`led_stage_test.py`, `ai_stage_test.py`,
   `uart_stage_test.py`, 전부 `display/examples/`에 보존됨)로 다시 재현
   테스트할 수 있다.

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
