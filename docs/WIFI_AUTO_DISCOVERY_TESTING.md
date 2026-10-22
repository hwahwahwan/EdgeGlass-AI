# Wi-Fi 자동 IP 탐색 — 실기기 검증 준비 문서

이 문서는 `feature/wifi-auto-discovery` 브랜치(별도 worktree:
`/Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI-wifi-dev`)에서 로컬로만
구현/테스트한 내용을 핫스팟을 켤 수 있을 때 실기기로 이어서 검증하기
위한 절차다. **이 문서 작성 시점까지 실제 Wi-Fi/보드 배포는 전혀
진행하지 않았다** — 아래 전부는 다음 세션에서 할 일이다.

## 0. 이 브랜치가 바꾼 것 (요약)

- `firmware/discovery.py` (신규): 보드가 자기 서브넷의 모든 호스트에
  `@HELLO`를 보내고, Mac이 받은 주소로 직접 `@ACK`를 돌려주는 방식으로
  Mac의 IP를 고정값 없이 찾는다. 브로드캐스트를 쓰지 않는다 — 핫스팟이
  보통 작은 서브넷(`/28` 안팎)이라 전수 스캔이 더 안전하다.
- `firmware/transport.py`: `AutoDiscoverUdpTransport` 추가.
  `config.MOUSE_UDP_AUTO_DISCOVER=True`(기본값)일 때 사용되며, 등록되기
  전에는 패킷을 아예 보내지 않는다. `False`로 끄면 기존 고정 IP
  (`MOUSE_UDP_HOST`) 방식으로 완전히 되돌아간다.
- `firmware/config.py`: `MOUSE_UDP_AUTO_DISCOVER`, `MOUSE_UDP_MAX_SCAN_HOSTS`,
  `VERBOSE_ORCHESTRATOR_LOGS` 추가. `MOUSE_UDP_HOST`는 수동 대안으로만 남음.
- `firmware/smart_glass_server.py`: Wi-Fi/WEB/UDP/AI 상태를 깔끔한 배너로
  출력(`[Wi-Fi]`/`[WEB]`/`[UDP]`/`[AI]`, 접두사 없음), STEP:/FPS 등 기존
  디버그 로그는 `config.VERBOSE_ORCHESTRATOR_LOGS=True`일 때만 보이도록
  분리. 메인 루프에 `mouse_controller.transport.step()` 호출 추가(논블로킹).
- `mac/mac_mouse_bridge.py`: `@HELLO`에 실제 송신자 주소로 `@ACK` 응답,
  시작 배너(`[NET]`/`[PERMISSION]`/`[UDP]`/`[DISCOVERY]`/`[MOUSE]`),
  `get_local_ip()`(인터페이스 이름 가정 없음), `check_accessibility_trusted()`,
  파싱 실패 진단(2초 레이트리밋), DRAG_START/DRAG_END/STOP RX 로그
  (MOVE/DRAG는 기존처럼 매 프레임 로그하지 않음).
- `firmware/main.py`는 전혀 수정하지 않았다. UART 경로
  (`firmware/run_uart.py`, `mac_mouse_bridge.py --transport uart`)도
  동작을 바꾸지 않았다(공용 `process_tick`/`handle_line`/`dispatch`는
  그대로이고, `@HELLO` 처리만 UDP 루프에만 추가됨).

## 1. 지금까지 검증한 것 (로컬, CPython, 루프백 소켓만)

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI-wifi-dev
python3 -m unittest discover -s tests -v
python3 -m compileall -q firmware mac tests
```

- `tests/test_wifi_auto_discovery.py`: `compute_scan_targets()`(서브넷
  계산, 자기 IP 제외, 큰 서브넷 상한 처리), `UdpRegistry`(프로브 전송,
  ACK 등록, 중복 ACK 무시, 주소 변경 시 재등록, 재공지 주기),
  `AutoDiscoverUdpTransport`(미등록 시 무전송, 등록 후 전송, 큰 서브넷
  예외), `create_transport()`의 `udp_auto_discover` 분기, Mac 쪽
  `get_local_ip()`/`check_accessibility_trusted()`/`_reply_to_hello()`/
  파싱 실패 레이트리밋/실제 `run_udp_loop()` 스레드+루프백 소켓 통합
  테스트.
- 기존 `tests/test_wifi_mouse_transport.py`, `test_gesture_controller.py`,
  `test_ui_transport.py` 전부 회귀 없이 통과(70개 전체, 3회 반복).
- 실제 마우스 이벤트는 테스트 내내 `DryRunMouse`만 사용했다(Quartz 호출
  없음).

## 2. 아직 전혀 검증하지 않은 것 (PASS로 보지 말 것)

- 실제 아이폰 핫스팟 환경에서 `@HELLO`/`@ACK` 핸드셰이크가 실제로
  성립하는지. 로컬 테스트는 전부 `127.0.0.1` 루프백이라 실제 Wi-Fi
  지연/패킷 유실/AP 클라이언트 격리 여부는 반영되지 않았다.
- K230D-Zero(MicroPython)에서 `socket.sendto()`를 비연결 소켓으로 14개
  내외 주소에 연속 호출했을 때 실제 동작(지연, 예외 패턴)이 CPython
  테스트와 같은지.
- `smart_glass_server.py`의 배너 출력, `VERBOSE_ORCHESTRATOR_LOGS` 분리,
  `transport.step()` 메인 루프 삽입이 실제 AI 추론 FPS에 미치는 영향.
- 보드가 핫스팟에 먼저 붙는 경우 / Mac 브리지를 먼저 켜는 경우 각각의
  순서별 등록 동작.
- Mac/보드 IP가 실제로 바뀌는 상황(핫스팟 재연결)에서 재등록이 실제로
  일어나는지.

## 3. 실기기 검증 절차 (핫스팟 켤 수 있을 때)

### 3-1. 준비

1. 이 worktree(`EdgeGlass-AI-wifi-dev`)에서 작업한다. 시연용 원본
   (`EdgeGlass-AI`, `main` 브랜치)과 보드 SD카드는 아직 이 브랜치의
   코드를 전혀 모른다 — 아래 3-2에서 처음 배포한다.
2. `firmware/wifi_credentials.py`가 이 worktree에 있는지 확인한다
   (gitignore 대상이라 worktree 생성 시 자동으로 복사되지 않았을 수
   있다). 없으면 기존 `EdgeGlass-AI/firmware/wifi_credentials.py`의
   SSID/PASSWORD를 그대로 옮긴다. **비밀번호를 커밋하거나 보고서/로그에
   적지 않는다.**
3. 아이폰에서 설정 > 개인용 핫스팟 화면을 열어 검색 가능 상태로 둔다.

### 3-2. 보드 배포 (기존 `tools/DEPLOY.md` 절차 그대로 재사용)

변경/신규 파일만 `/sdcard/smart_glass/`에 올린다:

```text
firmware/discovery.py        (신규)
firmware/transport.py        (수정)
firmware/config.py           (수정)
firmware/smart_glass_server.py (수정)
```

`mouse_controller.py`, `wifi.py`, `ui.py`, `web_server.py`,
`video_stream.py`, `hand_tracker.py`, `gesture_controller.py`,
`run_uart.py`, `run_wifi.py`, `main.py`는 이 브랜치에서 건드리지
않았으므로 보드 쪽이 `EdgeGlass-AI`(main)와 이미 동기화돼 있다면 재배포
불필요 — 단, `tools/DEPLOY.md`의 "비교 → 업로드 → 해시 검증" 절차대로
실제로 다른지 먼저 확인할 것. `main.py`는 이번에도 배포 대상이 아니다.

### 3-3. Mac 브리지 실행

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI-wifi-dev
source ../EdgeGlass-AI/.venv/bin/activate   # 또는 이 worktree에 맞는 venv
python mac/mac_mouse_bridge.py --transport udp --udp-port 9000
```

예상 출력(등록 전):
```text
========== EdgeGlass-AI Mac Bridge ==========
[NET] Local IP: <실제 Mac IP>
[PERMISSION] Accessibility: granted (또는 NOT granted/unknown)
[UDP] Listening on 0.0.0.0:9000
[DISCOVERY] Waiting for board...
=============================================
```

### 3-4. 보드 실행 (CanMV IDE)

`/sdcard/smart_glass/run_wifi.py` 실행. 예상 출력:
```text
========== EdgeGlass-AI ==========
[Wi-Fi] Connected
[Wi-Fi] Board IP: <실제 보드 IP>
[UDP] Waiting for Mac registration...
[WEB] Server started
[WEB] URL: http://<실제 보드 IP>:8060/
[AI] Gesture tracking started
==================================
```

### 3-5. 등록 확인

몇 초 안에 양쪽에서 아래가 각각 한 번씩 보여야 한다(Mac 쪽):
```text
[DISCOVERY] Board registered: <실제 보드 IP>
[MOUSE] Ready
```
(보드 쪽은 `[UDP] Waiting for Mac registration...`가 배너 안에 고정으로
남고, 실제 등록 성공 로그는 별도 `[ORCH]` 라인으로 찍히지 않는다 —
Mac 쪽 로그가 등록 성사의 1차 증거다. 필요하면
`config.VERBOSE_ORCHESTRATOR_LOGS=True`로 보드 쪽 STEP 로그도 켜서
`transport.step()`가 매 프레임 호출되는지 확인한다.)

### 3-6. MOVE·CLICK·DRAG·STOP 확인

보드 앞에서 손을 움직여 Mac 커서가 따라가는지, 핀치로 CLICK, 주먹으로
DRAG가 되는지 확인한다. Mac 터미널에 `CLICK_RX`/`DRAG_START_RX`/
`DRAG_END_RX`가 찍히는지 확인한다(MOVE/DRAG 연속 프레임은 로그하지
않으므로 안 보이는 게 정상).

### 3-7. 웹 브라우저 접속

`[WEB] URL: ...`에 찍힌 실제 주소로 접속해 `/`, `/snapshot`, `/stream`을
확인한다(기존 시연 절차와 동일, IP만 매 세션 다를 수 있음).

### 3-8. IP 변경·재연결 테스트

1. Mac 또는 보드 쪽 Wi-Fi를 끄고 다시 켜 새 IP를 받게 한다.
2. 몇 초 안에 Mac 쪽에 새로운 `[DISCOVERY] Board registered: <새 IP>`가
   다시 뜨는지 확인한다(코드상 보드는 등록 이후에도 주기적으로
   재공지하므로 자동으로 재등록되어야 한다 — `discovery.py`의
   `reannounce_interval_ms` 참고).
3. 재등록 전까지 마우스 명령이 전송되지 않는지(엉뚱한 주소로 새지
   않는지) 확인한다.

## 4. 문제 발생 시 되돌리는 법

### 4-1. 이 worktree만 되돌리기 (가장 흔한 경우)

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI-wifi-dev
git checkout -- firmware/config.py   # 특정 파일만 되돌릴 때
# 또는 이 브랜치 전체를 포기하려면(커밋 안 된 변경은 날아감 — 먼저 확인):
git status
```

### 4-2. 보드를 즉시 기존 시연용으로 되돌리기

보드에 이 브랜치 파일을 아직 올리지 않았다면 할 일이 없다(가장 안전한
상태). 이미 올렸다면:

```text
canmv_execute_file("/sdcard/smart_glass/main.py")
```
으로 바로 기존 검증된 UART 단독 경로로 돌아간다(main.py는 건드리지
않았으므로 항상 그대로 있다). `run_uart.py`도 이 브랜치의 변경과
무관하게 동작한다(UART 경로 자체를 바꾸지 않았음).

보드의 `/sdcard/smart_glass/transport.py`/`config.py`/
`smart_glass_server.py`를 이전 상태로 되돌려야 한다면, `main` 브랜치의
`EdgeGlass-AI/firmware/`에 있는 파일을 그대로 다시 올린다(해시 검증
포함, `tools/DEPLOY.md` 절차).

### 4-3. Mac 브리지를 기존 방식으로 되돌리기

```bash
cd /Users/yonghwan/Desktop/Smart_Glass/EdgeGlass-AI   # main 브랜치, 원래 worktree
python mac/mac_mouse_bridge.py --transport uart --port /dev/cu.usbmodem58930597043
```
`EdgeGlass-AI`(main)는 이 브랜치의 어떤 변경도 받지 않았으므로 그냥 그
디렉터리에서 실행하면 된다.

## 5. 참고: 이 브랜치의 설계 결정 메모

- 브로드캐스트(`SO_BROADCAST`)를 쓰지 않고 전수 스캔을 선택한 이유:
  이 보드/펌웨어에서 `SO_BROADCAST`가 실제로 동작하는지 검증된 적이
  없고, 아이폰 핫스팟이 클라이언트 간 브로드캐스트를 막을 수도 있다
  (AP 격리). 핫스팟 서브넷은 보통 `/28`(14개 호스트) 정도로 작아서,
  전수 스캔이 더 단순하고 검증된 소켓 기능(`sendto`/`recvfrom`)만으로
  충분하다. `MOUSE_UDP_MAX_SCAN_HOSTS`(기본 64)를 넘는 큰 네트워크에서는
  자동 탐색을 포기하고 예외를 던지며, 그 경우
  `MOUSE_UDP_AUTO_DISCOVER=False` + 수동 `MOUSE_UDP_HOST`가 대안이다.
- 등록 후에도 계속 재공지(재스캔)하는 이유: 등록된 피어로만 하트비트를
  보내는 방식은 Mac IP가 바뀌면 영원히 그 사실을 알 수 없다. 전체
  서브넷을 계속(느리게) 재스캔하면 어느 주소로 바뀌든 다음 ACK로
  자연스럽게 재등록된다. 대신 보드 쪽에 별도의 "연결 끊김" 타임아웃/상태
  머신은 두지 않았다(최소 구현 우선) — DRAG 안전장치는 이미 Mac 쪽
  `DragWatchdog`이 담당한다.
