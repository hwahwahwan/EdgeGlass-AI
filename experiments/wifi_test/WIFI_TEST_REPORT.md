# K230D-Zero 내장 Wi-Fi 통신 검증 보고서

- 작성일: 2026-10-21
- 대상 보드: CanMV K230D Zero - 128M, 펌웨어 `K230D-v1.8-0-gc2d1f5cc994c206d0032aaf6aaf09332f3dc3c4c` (2026-07-03 빌드)
- 연결 인터페이스: CDC 시리얼 포트 `/dev/cu.usbmodem0010000001` (canmv-k230 MCP 경유)
- 네트워크: 아이폰 개인용 핫스팟, SSID `i` (비밀번호는 본 문서 및 로그에 기록하지 않음, `wifi_test/net_config.py`에만 보관)
- 보드 IP `172.20.10.2` / MacBook IP `172.20.10.3` / 게이트웨이 `172.20.10.1`
- 테스트 코드 위치: 로컬 `EdgeGlass-AI/experiments/wifi_test/`(2026-10-21 디렉터리 재정리로 `wifi_test/`에서 이동), 보드 `/sdcard/wifi_test/` (기존 `/sdcard/smart_glass/`, `main.py`, UART2(`/dev/cu.usbmodem58930597043`)는 전혀 수정하지 않음)

> 이 문서는 코드 작성 완료를 "검증 성공"으로 취급하지 않는다. 모든 항목에 실제 하드웨어 실행 결과를 근거로 검증 수준을 표시했다.

---

## 0. 작업 중 발견한 환경적 사실 (사전 지식 없이 실측으로 확인)

1. **MCP 스크립트 실행은 매번 MicroPython 소프트 리부트를 유발한다.** `canmv_run_script`, `canmv_write_and_run_script`, `canmv_execute_file` 호출마다 보드 콘솔에 `MPY: soft reboot`가 출력된다. REPL에 남아있던 변수/상태는 매 호출마다 초기화된다.
2. **Wi-Fi STA 연결 상태는 소프트 리부트와 분리되어 있다.** `network` 모듈은 RT-Smart(기반 RTOS) 레벨에서 관리되며 ("`Network (rt-smart) is always active and cannot be disabled.`" 메시지로 확인), 일단 연결에 성공하면 이후 소프트 리부트가 발생해도 `wlan.isconnected()`가 `True`를 유지하고 IP가 보존된다.
3. **단, 소프트 리부트 직후 소켓 계층이 NIC를 즉시 인식하지 못하는 레이스 컨디션이 존재한다.** `wlan.isconnected()`는 `True`인데도 바로 이어서 `socket.socket()` 또는 `setsockopt()`/`bind()`를 호출하면 `OSError: no available NIC`가 발생한 사례를 실측했다. 수백 ms 지연 후 재시도하면 성공한다.
4. **아이폰 개인용 핫스팟은 "검색 가능" 상태가 아니면 보드에서 보이지 않는다.** 최초 세션에서 `wlan.scan()` 결과에 SSID `i`가 전혀 나타나지 않았고, `wlan.connect("i", ...)`는 15초 타임아웃으로 실패했다(`run connect failed.`). 아이폰에서 설정 > 개인용 핫스팟 화면을 열어둔 뒤에는 동일 SSID로 즉시 연결에 성공했다. 즉 "핫스팟이 켜져 있다"와 "핫스팟이 스캔/연결 가능 상태다"는 다른 조건이다.
5. **저장된 Wi-Fi 자격증명은 없다.** `wlan.connect()`를 인자 없이 호출하면 `OSError('should set ssid or ap')`가 발생하며, 매 소프트 리부트 후 처음 연결할 때는 반드시 SSID/비밀번호를 다시 전달해야 한다(단, 2번 사실 덕분에 이미 연결된 뒤의 재실행에서는 다시 connect()를 호출할 필요가 없다).
6. **stub/example 캐시(`k230_canmv_stubs`, `k230_canmv_examples`)가 실제 보드 펌웨어보다 최신이다.** 캐시된 문서에는 `media.mjpeg.MJPEGEncoder`가 존재한다고 나오지만, 실제 보드(`v1.8-0-gc2d1f5c`)에는 해당 모듈이 없다(§3-C 참고). 즉 "stub에 있다"는 "이 보드에서 동작한다"의 증거가 아니다.
7. **공식 예제(`examples/14-Socket/*.py`, `examples/02-Media/*.py`)는 모두 `libs.Network.connect_network/load_network_config`에 의존하지만, 이 모듈은 보드의 `/sdcard/libs/`에도 examples 캐시 안에도 존재하지 않는다.** 따라서 공식 예제를 그대로 복사해서 돌릴 수는 없고, 본 테스트는 `network.WLAN`을 직접 사용하는 자체 구현으로 대체했다.

---

## 1. 사용한 명령어/API 전체 목록 (A)

| API / 명령어 | 목적 | 실행 코드 요지 | 입력 | 실행 결과 | 정상 동작 | 주의사항 |
|---|---|---|---|---|---|---|
| `network.WLAN(network.STA_IF)` | STA 인터페이스 핸들 획득 | `wlan = network.WLAN(network.STA_IF)` | - | 정상 반환 | O | `network.WLAN()`(인자 없음)도 동일하게 동작함을 REPL에서 확인 |
| `wlan.active(True)` | 인터페이스 활성화 | `wlan.active(True)` | `True` | `"Network (rt-smart) is always active and cannot be disabled."` 출력, 예외 없음 | O (사실상 no-op) | 비활성화 불가능한 플랫폼. 호출해도 무해하지만 의미 없음 |
| `wlan.isconnected()` | 연결 여부 확인 | `wlan.isconnected()` | - | `True`/`False` | O | |
| `wlan.ifconfig()` | IP 설정 조회 | `wlan.ifconfig()` | - | `('172.20.10.2','255.255.255.240','172.20.10.1','172.20.10.1')` | O | |
| `wlan.connect(ssid, key)` | AP 접속 | `wlan.connect(SSID, PASSWORD)` (값은 `net_config.py`, 커밋 제외) | SSID/PW | 핫스팟이 스캔 불가 상태일 때 `run connect failed.` + 15초 후 타임아웃 / 스캔 가능 상태일 때 `True` 반환 후 수 초 내 연결 | 조건부 O | 저장된 자격증명 없음. SSID 생략 시 `OSError('should set ssid or ap')` |
| `wlan.scan()` | 주변 AP 스캔 | `wlan.scan()` | - | AP 리스트(ssid/bssid/channel/rssi/security/band/hidden 포함) | O | 핫스팟이 비검색 상태면 목록에 안 나타남 |
| `socket.socket(AF_INET, SOCK_STREAM)` | TCP 소켓 생성 | 표준 | - | 정상 | O | 소프트 리부트 직후엔 `OSError: no available NIC` 가능 (재시도 필요) |
| `sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)` | 포트 재사용 | 표준 | - | 정상 | O | |
| `sock.bind(addr)` | 바인드 | `server.bind(("0.0.0.0", PORT))` | - | 정상(재시도 포함) | O | 위와 동일한 NIC 레이스 영향받음 |
| `sock.listen(n)` | 리슨 | `server.listen(5)` | backlog | 정상 | O | |
| `sock.setblocking(False)` | 논블로킹 전환 | 표준 | `False` | 정상 | O | |
| `sock.accept()` | 연결 수락 | `server.accept()` | - | 대기 클라이언트 있으면 `(conn, addr)`, 없으면 논블로킹 모드에서 `OSError: [Errno 11] EAGAIN` | O (논블로킹 전제) | **블로킹 모드로 설정해도 EAGAIN이 발생할 수 있다는 사용자 관찰은, 공식 예제 주석("RT-Smart caps a blocking socket's send timeout at 500 ms")과 함께 보면 이 플랫폼의 "블로킹" 소켓이 OS 레벨에서 완전한 무기한 블로킹을 보장하지 않음을 시사한다. 따라서 accept/recv는 항상 논블로킹 + `select.poll()`/데드라인 루프로 작성해야 한다.** |
| `select.poll()` / `poll.register(sock, select.POLLIN)` / `poll.poll(timeout_ms)` / `poll.unregister(sock)` | 입출력 준비 상태 감지 | 본 테스트의 TCP/HTTP/MJPEG 서버 전부에서 사용 | - | 연결 대기 중 `[]`, 이벤트 발생 시 `[(sock, 1)]` | O | 서버 소켓과 클라이언트 소켓에 각각 별도의 `Poll` 객체를 사용함(한 객체에 여러 소켓 register도 가능하나 본 테스트는 분리) |
| `sock.recv(n)` | 수신 | 표준 | 버퍼 크기 | 데이터 있으면 bytes, 없으면(논블로킹) `OSError errno 11`, 피어 종료 시 `b''` | O | **블로킹 모드에서 `recv()`를 타임아웃/논블로킹 없이 호출하면 상대가 추가 데이터를 보내지 않는 한 영구 대기한다 — 사용자가 겪은 "REPL 무한 대기"의 직접 원인.** 해결: `settimeout()` 또는 논블로킹+poll+데드라인 |
| `sock.send(data)` / `sock.sendall(data)` | 송신 | 표준 | bytes | 전송 바이트 수 반환 | O | 대용량 전송 시 청크 분할 + 백프레셔 처리 필요(공식 예제 패턴 채택) |
| `sock.settimeout(sec)` | 블로킹 타임아웃 설정 | `client.settimeout(5)` | 초 | 예외 없이 설정됨 | O | |
| `sock.setblocking(flag)` | 블로킹/논블로킹 전환 | 표준 | bool | 정상 | O | |
| `sock.getsockname()` | 로컬 바인드 주소 조회 | `s.getsockname()` | - | `AttributeError: 'socket' object has no attribute 'getsockname'` | **미지원** | stub(`socket.pyi`)에도 해당 메서드 없음 — 문서와 실기 모두 미지원 일치 |
| `sock.gettimeout()` | 타임아웃 조회 | `s.gettimeout()` | - | `AttributeError: 'socket' object has no attribute 'gettimeout'` | **미지원** | 위와 동일 |
| `sock.close()` | 소켓 종료 | 표준 | - | 정상 | O | |
| `socket.getaddrinfo(host, port)` | 주소 변환 | 표준 | - | 정상 | O | |
| `media.sensor.Sensor()` / `.reset()` / `.set_framesize()` / `.set_pixformat()` / `.run()` / `.stop()` | 카메라 초기화/해제 | 본 테스트 mjpeg 스크립트 | width/height/alignment, `Sensor.YUV420SP` | 정상 초기화, `sensor(0), mode 0, buffer_num 4` 로그 출력 | O | `alignment=12` 추가해도 본 테스트의 화질 문제는 해결되지 않음(§3 참고) |
| `media.media.MediaManager.init()` / `.deinit()` | 미디어 파이프라인 리소스 할당/해제 | 표준 | - | 정상 | O | `finally` 블록에서 반드시 호출해 리소스 누수 방지 |
| `sensor.snapshot()` | 프레임 캡처 | `img = sensor.snapshot()` | - | `Image` 객체 | O | |
| `sensor.snapshot(dump_frame=True)` | 저수준 video-frame 핸들 캡처 | `sensor.snapshot(dump_frame=True)` | - | `py_video_frame_info` 객체 반환 (Image 아님) | 용도 다름 | `.compress()` 없음 → `AttributeError`. MJPEGEncoder(비디오 프레임 입력 전용) 경로용이며 본 보드엔 MJPEGEncoder 자체가 없어 사용 불가 |
| `img.compress(quality=50)` | JPEG 인코딩 | `jpeg_img = img.compress(quality=50)` | quality | **원본과 분리된 새 `Image` 객체 반환** | O | `ret is img` → `False`. 원본 `img`를 그대로 바이트 추출하면 안 됨 |
| `img.bytearray()` | 원시 바이트 추출 | `jpeg_img.bytearray()` | - | 호출 대상 Image 객체 자신의 버퍼 전체 반환 | O (단, 대상 선택 주의) | 압축 전 `img`에 호출하면 raw YUV 버퍼(FFD8 아님)가 나오고, 압축 후 반환된 `jpeg_img`에 호출해야 실제 JPEG(`FF D8 ... FF D9`)가 나옴 |
| `img.size()` | (의도상) 유효 데이터 크기 | `img.size()` | - | **원본/압축 여부와 무관하게 원시 버퍼 전체 크기(예: 640×480×1.5=460800)를 반환** | **문서 기대와 다름** | 압축 후 실제 JPEG 크기를 얻으려면 `img.size()`가 아니라 `len(jpeg_img)`를 사용해야 한다 — 실기에서만 드러난 차이 |
| `len(img)` | (비압축 Image) | `len(img)` | - | 460800이 아니라 **프레임 높이(480)** 반환 | 문서에 없는 동작 | 비압축 Image의 `__len__`은 byte 길이가 아님에 주의 |
| `len(jpeg_img)` | 압축 JPEG 바이트 수 | `len(jpeg_img)` | - | 실제 JPEG 바이트 수(예: 16225, 23899 등)와 `len(jpeg_img.bytearray())`가 정확히 일치 | O | **MJPEG 스트리밍에서 Content-Length로 사용할 올바른 값** |
| `media.mjpeg.MJPEGEncoder` | (공식 예제 기준) MJPEG 인코더 | `from media.mjpeg import MJPEGEncoder` | - | `ImportError: no module named 'media.mjpeg'` | **미지원 (이 펌웨어)** | 하위 레벨 `_media` 모듈에도 `MJPEGEncoder` 속성 없음(`dir(_media)`로 확인: `['Display','GSDMA','_MediaManager','py_video_frame','py_video_frame_info']`뿐). stub 캐시에는 존재하므로 "문서상 지원 확인"과 "실기 미지원"이 공존하는 사례 |
| `os.exitpoint()` | 협조적 인터럽트 체크포인트(공식 예제 패턴) | 공식 `tcp_server.py`/`http_server.py`에서 사용 | - | (본 테스트 자체 서버에는 미적용, 참고용으로만 확인) | 참고 | 본 테스트는 `time.ticks_ms()` 데드라인 기반으로 대체 구현 |

---

## 2. 성공한 기능 (B) — 실제 하드웨어 검증

### 2-1. Wi-Fi STA 연결
- 환경: iPhone 개인용 핫스팟(설정 화면 열어 검색 가능 상태), SSID `i`
- 절차: `network.WLAN(network.STA_IF)` → `wlan.connect(SSID, PASSWORD)` → `isconnected()` 폴링
- 실제 출력: `isconnected: True`, `ifconfig: ('172.20.10.2', '255.255.255.240', '172.20.10.1', '172.20.10.1')`
- 판단 근거: 보드에서 직접 획득한 IP가 MacBook과 같은 서브넷(172.20.10.0/28)이고 이후 모든 TCP/HTTP 테스트가 이 IP로 실제 왕복 성공
- 검증 수준: **실제 하드웨어 검증 성공**

### 2-2. TCP 양방향 통신 (select.poll 기반)
- 서버: `wifi_test/tcp_echo_server.py`, 포트 8090, 논블로킹 + `select.poll()`, 최대 3개 연결까지 처리 후 자동 종료, 전체 60초 타임아웃
- 클라이언트: MacBook에서 Python `socket`으로 3회 연속 연결/송신/수신
- 실제 출력(MacBook):
  ```
  conn#0 sent=b'Hello K230D #0\n' reply=b'ECHO:Hello K230D #0\n'
  conn#1 sent=b'Hello K230D #1\n' reply=b'ECHO:Hello K230D #1\n'
  conn#2 sent=b'Hello K230D #2\n' reply=b'ECHO:Hello K230D #2\n'
  ```
- 실제 출력(보드 로그):
  ```
  [TCP] listening on port 8090
  [TCP] client connected: ('172.20.10.3', 55968)
  [TCP] received: b'Hello K230D #0\n'
  [TCP] sent reply: b'ECHO:Hello K230D #0\n'
  ... (총 3회 반복) ...
  [TCP] server closed, handled=3
  ```
- 검증 항목 충족: bind/listen/accept, POLLIN 기반 연결·수신 감지, Mac→보드 송신, 보드→Mac 송신, 연결 종료, 반복 연결(3회), 전체/개별 타임아웃 설계
- 검증 수준: **실제 하드웨어 검증 성공**

### 2-3. HTTP 웹서버
- 서버: `wifi_test/http_server_test.py`, 포트 8070, 동적 HTML(요청 횟수/클라이언트 주소/uptime 표시), 최대 4회 요청 후 자동 종료
- 테스트: MacBook `curl`로 3회 연속 GET + Chrome 브라우저로 1회 접속(총 4회, 한도 소진)
- 실제 출력(curl, 3회 모두 동일 패턴):
  ```
  HTTP/1.1 200 OK
  Content-Type: text/html; charset=utf-8
  Content-Length: 222
  Connection: close
  ...
  <h1>EdgeGlass-AI wifi_test HTTP server</h1><p>request #0</p>...
  ```
- 브라우저 확인: `get_page_text` 결과 `request #3`, `client: 172.20.10.3:54203`가 정상 표시됨(HTML 렌더링 성공)
- 보드 로그: 4건의 `client connected` → `response sent` → 마지막에 `server closed, served=4`로 리소스 정리 확인
- 검증 항목 충족: GET 수신, 정상 응답, 브라우저 렌더링, 반복 요청(새로고침과 동일한 신규 연결 4회), 연결 종료/정리
- 검증 수준: **실제 하드웨어 검증 성공**

### 2-4. 카메라 JPEG 인코딩 (API 단위)
- `Sensor()` → `snapshot()` → `img.compress(quality=50)` → `len(jpeg_img)`/`jpeg_img.bytearray()` 경로로 유효한 JPEG(시작 `FF D8`, 끝 `FF D9`) 생성 확인
- 검증 수준: **실제 하드웨어 검증 성공** (인코딩 메커니즘 자체에 한함, 화질은 2-5 참고)

### 2-5. MJPEG HTTP 스트리밍 (전송 계층)
- 서버: `wifi_test/mjpeg_stream_test.py`, 포트 8060, `multipart/x-mixed-replace; boundary=frame`
- MacBook 소켓 클라이언트로 `/stream`에서 프레임 5개를 직접 파싱해 검증:
  ```
  frame 0 len=23690 magic=ffd8 tail=ffd9
  frame 1 len=23620 magic=ffd8 tail=ffd9
  frame 2 len=23469 magic=ffd8 tail=ffd9
  frame 3 len=23506 magic=ffd8 tail=ffd9
  frame 4 len=23630 magic=ffd8 tail=ffd9
  ```
- 별도 실행에서 브라우저가 8초간 77프레임을 수신(약 9.6 fps, 640×480, quality=50)하고 `<img>` 태그에 실제 이미지를 렌더링함(깨진 HTTP/빈 이미지가 아님)
- 검증 수준: **부분 검증** — HTTP/MJPEG 전송 프로토콜 자체(바운더리, Content-Length, 연속 프레임 전달, 비정상 종료 처리)는 성공이나, 아래 2-6의 화질 문제로 "실사용 가능한 영상 스트리밍"까지는 검증되지 않음

### 2-6. 비정상 종료 처리
- MacBook 클라이언트가 스트림 중간에 소켓을 강제 종료하자 보드에서 `OSError(104,)`(ECONNRESET)가 발생했고, `try/except OSError`로 포착되어 서버가 크래시 없이 다음 연결 대기로 복귀함을 확인
- 검증 수준: **실제 하드웨어 검증 성공**

---

## 3. 실패/미지원 기능 (C)

### 3-A. `media.mjpeg.MJPEGEncoder` — ImportError (재현됨)
- 오류: `ImportError: no module named 'media.mjpeg'`
- 발생 조건: `from media.mjpeg import MJPEGEncoder`를 이 보드(`v1.8-0-gc2d1f5c`)에서 직접 실행
- 조사: stub 캐시(`media/mjpeg.pyi`)와 공식 예제(`examples/02-Media/mjpeg_web_server.py`, `ai_mjpeg_web_server.py`)에는 해당 클래스가 문서화되어 있으나, 실제 펌웨어의 `_media` 네이티브 모듈에는 `MJPEGEncoder` 속성이 전혀 없음(`dir(_media)` 결과에 부재)
- 해결 시도: 대안으로 `image.Image.compress()`를 사용해 JPEG 인코딩 자체는 성공시킴(§2-4, 2-5)
- 최종 상태: **미해결** — `MJPEGEncoder`를 쓰려면 펌웨어 업데이트가 필요할 것으로 추정되나 본 세션에서 펌웨어를 변경하지 않았으므로 확인하지 않음
- 대체 구현: `Sensor.snapshot()` + `Image.compress()` + HTTP multipart (본 보고서 §2-5)

### 3-B. MJPEG 스트림 화질 문제 — 미해결
- 증상: 브라우저에 표시된 이미지가 좌우로 동일 내용이 중복되어 보이고(가로 방향 압축/스트라이드 불일치로 추정), 상단은 녹색/마젠타 색조로 왜곡되어 있으며, 하단 1/3 지점에 컬러 노이즈 띠가 나타남
- 시도한 조치: `sensor.set_framesize(..., alignment=12)` 추가 → **증상 변화 없음**(동일한 중복/왜곡 패턴 재현)
- 시도했으나 채택하지 않은 경로: `snapshot(dump_frame=True)` → `py_video_frame_info` 객체 반환, `.compress()` 속성 없어 `AttributeError` 발생, MJPEGEncoder 전용 경로로 판단되어 포기
- 조사한 원인(미확정): 기존 `hand_tracker.py`/`main.py`는 `Sensor()`를 직접 쓰지 않고 `libs/PipeLine.py`의 `PipeLine` 추상화를 통해 카메라를 초기화한다. 이 프로젝트의 카메라 프레임이 정상적으로 보이는 것은 해당 PipeLine 경로이고, 본 테스트처럼 `Sensor()`를 직접 생성해 `YUV420SP`로 스냅샷→JPEG 압축하는 경로는 검증되지 않은 조합일 가능성이 있다. RGB565 포맷 사용, `PipeLine` 경유, 또는 공식 프레임 크기(1920×1080 네이티브 대비 정렬 배수)로 맞추는 시도를 추가로 해야 원인을 좁힐 수 있으나 본 세션에서는 수행하지 않았다.
- 최종 상태: **해결됨 (2026-10-21 후속 조사, §8 참고)** — 원인은 `Image.compress()`가 YUV420SP(NV12) 입력을 올바르게 해석하지 못하는 것으로 확정되었고, RGB565로 전환해 해결했다. 네트워크 없이 SD카드 직접 저장 방식으로 재현/해결을 모두 확인했으므로 전송 계층 문제가 아니었음이 명확하다.

### 3-C. `socket.getsockname()` / `socket.gettimeout()` — AttributeError (재확인)
- 오류: `AttributeError: 'socket' object has no attribute 'getsockname'` / `'gettimeout'`
- 조사: `socket.pyi` stub에도 두 메서드가 정의되어 있지 않아 문서와 실기가 일치함(이 펌웨어의 MicroPython socket 구현 범위 밖)
- 대체 방법: 로컬 바인드 주소가 필요하면 `wlan.ifconfig()[0]`과 직접 지정한 포트 번호를 조합해서 사용. 타임아웃 값을 다시 읽어야 한다면 호출부에서 별도 변수로 기억해 둔다.
- 최종 상태: **미지원으로 확정**, 대체 가능

### 3-D. EAGAIN / 블로킹 수신 문제 — 원인 규명 및 해결
- 사용자가 이전에 겪은 "`setblocking(True)` 이후에도 `accept()`에서 간헐적 EAGAIN", "`conn.recv(1024)`가 멈춤" 현상의 원인을 공식 예제 코드의 주석으로 확인함: *"RT-Smart caps a blocking socket's send timeout at 500 ms"* — 즉 이 플랫폼(RT-Smart 기반)의 "블로킹" 소켓은 표준 POSIX처럼 무기한 블로킹을 보장하지 않는다.
- 해결: 모든 accept/recv를 **논블로킹 + `select.poll()` + `time.ticks_ms()` 데드라인** 조합으로 작성(본 보고서의 세 서버 모두 이 패턴 적용) → EAGAIN은 정상적인 "아직 준비 안 됨" 신호로 처리하고 재시도, 무한정 블로킹 대신 명시적 타임아웃으로 종료
- 최종 상태: **해결됨** (회피 패턴 확립, 근본 원인은 RT-Smart 소켓 구현의 설계 특성으로 추정)

### 3-E. 소프트 리부트 직후 "no available NIC" — 완화됨
- 오류: `OSError: no available NIC` (소켓 생성/`setsockopt`/`bind` 단계에서 발생)
- 발생 조건: MCP로 스크립트를 실행할 때마다 발생하는 소프트 리부트 직후, Wi-Fi 링크 자체는 연결돼 있어도(`isconnected()=True`) 소켓 계층이 아직 네트워크 인터페이스를 등록하지 못한 짧은 시간 창
- 해결: 소켓 생성 전 `wlan.isconnected()`를 폴링하고, 소켓 생성~bind까지를 최대 20회(500ms 간격) 재시도하는 루프로 감쌈 → 이후 테스트에서 재발하지 않음
- 최종 상태: **완화/회피됨**, 근본 수정(펌웨어 패치) 아님

---

## 4. 검증 수준 요약 (D)

| 기능 | 검증 수준 |
|---|---|
| Wi-Fi STA 연결(`network.WLAN`) | 실제 하드웨어 검증 성공 |
| `wlan.scan()` | 실제 하드웨어 검증 성공 |
| TCP 서버(bind/listen/accept/poll) | 실제 하드웨어 검증 성공 |
| TCP 양방향 송수신(Mac↔보드) | 실제 하드웨어 검증 성공 |
| TCP 반복 연결(3회) | 실제 하드웨어 검증 성공 |
| HTTP GET 응답 | 실제 하드웨어 검증 성공 |
| HTTP 브라우저 렌더링 | 실제 하드웨어 검증 성공 |
| HTTP 반복 요청/정리 | 실제 하드웨어 검증 성공 |
| `socket.settimeout()` | 실제 하드웨어 검증 성공 |
| `socket.getsockname()`/`gettimeout()` | 실제 하드웨어 검증 실패(미지원 확정) |
| 카메라 JPEG 인코딩(`compress()`) | 실제 하드웨어 검증 성공 |
| MJPEG HTTP 전송(프로토콜) | 실제 하드웨어 검증 성공 |
| MJPEG 영상 화질(실사용 가능 여부) | 실제 하드웨어 검증 성공 — RGB565 전환으로 해결, §8 참고 (Wi-Fi 경유 재검증은 보류) |
| `media.mjpeg.MJPEGEncoder` | 실제 하드웨어 검증 실패(모듈 자체 없음) — 문서상 지원 확인되었으나 실기 불일치 |
| 손 추적 AI 추론 + Wi-Fi 동시 실행 | 미검증 (본 세션에서 main.py와 wifi_test를 동시 실행하지 않음) |
| 마우스 제어 수준 지연시간 | 미검증 (RTT 수치 측정 안 함) |

---

## 5. 재현 가능한 테스트 절차 (E)

### 5-0. 공통 준비
1. iPhone에서 **설정 > 개인용 핫스팟** 화면을 열어 검색 가능 상태로 유지(백그라운드로 보내면 보드가 재연결에 실패할 수 있음).
2. VS Code CanMV 확장 또는 canmv-k230 MCP로 보드에 연결: 포트는 반드시 CDC `/dev/cu.usbmodem0010000001`을 사용하고, UART2(`/dev/cu.usbmodem58930597043`, 마우스 제어용)는 사용하지 않는다.
3. `wifi_test/net_config.py`에 실제 SSID/비밀번호가 들어있는지 확인(값은 본 문서에 기록하지 않음). 보드 쪽에도 `/sdcard/wifi_test/net_config.py`로 동일 파일이 있어야 한다.

### 5-1. TCP 테스트
1. 보드에서 실행: `canmv_execute_file("/sdcard/wifi_test/tcp_echo_server.py")` (또는 CanMV IDE에서 동일 파일 실행)
2. 보드 콘솔에 `[TCP] listening on port 8090`이 뜰 때까지 대기(최대 몇 초, NIC 레이스로 재시도 로그가 몇 줄 나올 수 있음 — 정상)
3. MacBook에서:
   ```bash
   python3 -I -c "
   import socket, time
   for i in range(3):
       s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
       s.settimeout(8)
       s.connect(('172.20.10.2', 8090))
       msg = ('Hello K230D #%d\n' % i).encode()
       s.sendall(msg)
       print(s.recv(1024))
       s.close()
       time.sleep(1)
   "
   ```
4. 기대 출력: `ECHO:Hello K230D #0`, `#1`, `#2`가 순서대로 수신됨. 보드 콘솔에는 `server closed, handled=3`이 출력되고 자동 종료됨.
5. 실패 시 복구: 보드 콘솔에 `OSError: no available NIC`가 반복되면 몇 초 기다렸다가 다시 `canmv_execute_file`로 재실행. `Connection refused`가 뜨면 보드 쪽 리스닝 로그가 실제로 떴는지 먼저 확인.

### 5-2. HTTP 테스트
1. 보드에서 실행: `canmv_execute_file("/sdcard/wifi_test/http_server_test.py")`
2. `[HTTP] listening on port 8070` 확인 후 MacBook에서:
   ```bash
   curl -i http://172.20.10.2:8070/
   ```
   또는 브라우저로 `http://172.20.10.2:8070/` 접속(최대 4회 요청까지만 응답, 5번째부터는 서버가 이미 종료되어 연결 거부됨 — 재테스트하려면 서버를 다시 실행).
3. 기대 출력: HTML 본문에 `EdgeGlass-AI wifi_test HTTP server`, `request #N`, 클라이언트 주소가 표시됨.

### 5-3. MJPEG 스트리밍 테스트
1. 보드에서 실행: `canmv_execute_file("/sdcard/wifi_test/mjpeg_stream_test.py")` — 카메라 초기화 로그(`find sensor ov5647_csi2...`) 및 `[MJPEG] camera ready, first JPEG size=...bytes` 확인
2. `[MJPEG] listening on port 8060` 확인 후 브라우저로 `http://172.20.10.2:8060/` 접속 → `<img src="/stream">`가 라이브 이미지를 표시함(단, §3-B의 화질 문제가 현재도 재현됨을 감안할 것)
3. 소켓 레벨 검증이 필요하면 MacBook에서 raw multipart 파서 스크립트로 `/stream`에 접속해 각 파트의 `FF D8`/`FF D9` 매직 바이트를 확인한다(본 보고서 §2-5 코드 참고).
4. 서버는 최대 2개 클라이언트(또는 60초) 후 자동 종료되며 `sensor.stop()`/`MediaManager.deinit()`으로 카메라 리소스를 해제한다.
5. 실패 시 복구: `AttributeError: ... has no attribute 'compress'`가 뜨면 `capture_jpeg()`에서 `dump_frame=True`를 쓰고 있지 않은지 확인(이 옵션은 compress()와 호환되지 않음).

---

## 6. EdgeGlass-AI 적용 가능성 평가 (F)

- **UART 제스처 명령 → Wi-Fi 대체**: 현재 데이터로는 권장하지 않는다. 왕복 지연시간(RTT)을 수치로 측정하지 않았고(미검증), iPhone 개인용 핫스팟은 "검색 가능 상태"를 유지해야 보드가 재연결할 수 있는 등 유선 UART보다 연결 안정성이 떨어지는 요소가 실측으로 확인됐다. 실시간 마우스 제어처럼 지연에 민감한 경로를 핫스팟 기반 Wi-Fi로 옮기는 것은 추가 지연시간 측정과 더 안정적인 AP(개인용 핫스팟이 아닌 고정 공유기) 환경에서의 재검증 없이는 위험하다.
- **마우스 제어 지연시간 요구사항 충족 여부**: 미검증. 본 세션은 기능 동작 여부만 확인했고 ms 단위 RTT를 측정하지 않았다.
- **카메라 영상 스트리밍 가능성**: 전송 메커니즘(HTTP MJPEG multipart)은 가능함을 입증했으나, 색상/기하 왜곡 문제가 미해결이라 현재 상태로는 "가능하다"고 단정할 수 없다. 공식 `MJPEGEncoder` 경로가 이 펌웨어에 없다는 것도 확정됐으므로, 향후에는 ① 펌웨어 업데이트로 `MJPEGEncoder` 확보, ② 기존 `libs/PipeLine.py` 경유 카메라 초기화와의 통합, ③ RGB565 등 다른 pixformat 조합 중 하나를 추가로 검증해야 한다.
- **AI 추론과 네트워크 통신 동시 처리 가능성**: 미검증. 본 세션에서 `main.py`(손 추적 AI 파이프라인)를 wifi_test 스크립트와 동시에 실행하지 않았다. 메모리/CPU 경합 여부는 알 수 없다.
- **ESP32 추가 없이 내장 Wi-Fi만으로 구현 가능한지**: 기본적인 TCP/HTTP 통신은 내장 Wi-Fi만으로 가능함을 실측으로 확인했다. 다만 (a) 핫스팟 재발견성 문제, (b) 소프트 리부트 직후 NIC 레이스, (c) MJPEG 화질 미해결 등 운영 안정성 측면의 과제가 남아 있어, "가능하다"는 결론은 TCP/HTTP 기본 기능에 한정되며 카메라 스트리밍을 포함한 전체 대체 가능성은 아직 입증되지 않았다.

---

## 7. 기존 EdgeGlass-AI 기능 보존 확인

- `/sdcard/smart_glass/`, `/sdcard/gesture_controller.py`(루트), 로컬 `main.py`/`hand_tracker.py`/`gesture_controller.py`/`mouse_controller.py`/`ui.py`/`smart_glass.py` 등 기존 파일은 이번 세션에서 전혀 읽기 외의 접근(수정/삭제/덮어쓰기)을 하지 않았다.
- UART2(`/dev/cu.usbmodem58930597043`)는 세션 내내 사용하지 않았다.
- 모든 테스트 코드는 로컬 `EdgeGlass-AI/experiments/wifi_test/`(당시 `wifi_test/`)와 보드 `/sdcard/wifi_test/`에만 생성했다.
- MCP 도구가 기본적으로 사용하는 스크래치 경로 `/sdcard/mcp_script.py`는 테스트 종료 후 삭제해 보드를 깨끗한 상태로 되돌렸다.

---

## 8. 2026-10-21 후속 조사 — MJPEG 색상/기하 왜곡 원인 확정 (네트워크 미사용, USB 직결)

### 8-0. 조사 배경 및 참고자료에 대한 메모
이 조사는 "Claude Cloud가 CanMV v1.8 소스를 분석해 `Sensor.YUV420SP`로 만든 NV12 이미지가 `Image.compress()`에서 잘못 해석된다는 가설을 제시했다"는 사용자 설명과, 그 근거로 언급된 보고서(`research/k230d-web-preview-streaming/MJPEG_DISTORTION_ANALYSIS.md`, 커밋 `e3bd33c`)를 확인하라는 요청에서 시작했다.

**사실 확인 결과: 해당 커밋과 파일은 이 저장소의 로컬/원격 어떤 브랜치에도 존재하지 않는다**(`git fetch --all` 후 `git log --all`로 확인, 저장소 전체 파일 검색으로도 미발견). "기존 Wi-Fi 작업 브랜치"도 존재하지 않으며, 실제로는 `main` 브랜치에 `wifi_test/`가 미커밋 상태로 있을 뿐이다. 따라서 이 보고서의 구체적 내용(어떤 방식으로 분석했는지, 다른 근거가 있는지)은 **검증할 수 없었고, 본 절의 결론은 이 미확인 보고서를 근거로 삼지 않았다.** 다만 "YUV420SP가 compress()에서 잘못 해석된다"는 가설 자체는 §3-B(이전 세션)에서 이미 관찰한 왜곡 패턴과 일치하는 합리적인 가설이었으므로, 아래와 같이 보드에서 직접 재검증했다.

### 8-1. 기존 미리보기(정상) 경로 vs 웹 MJPEG(왜곡) 경로 비교
보드의 `/sdcard/libs/PipeLine.py`(EdgeGlass-AI의 `main.py`가 실제로 사용하는 카메라 초기화 모듈)를 직접 읽어 확인한 결과:

- **채널 0 (`CAM_CHN_ID_0`)**: `YUV420SP`로 설정되지만 `Display.bind_layer()`로 **하드웨어 비디오 출력에 직접 바인딩**된다. `Image.compress()`나 소프트웨어 JPEG 인코딩을 전혀 거치지 않는다 — 이것이 CanMV IDE/HDMI 미리보기가 항상 정상으로 보이는 이유다.
- **채널 2 (`CAM_CHN_ID_2`)**: `RGBP888`(RGB888 평면 포맷)로 설정되고 `to_numpy_ref()`를 통해 AI 추론 입력으로만 사용된다. 이 경로도 JPEG 인코딩을 거치지 않는다.
- **결론: 이 프로젝트 안에는 "YUV420SP → `Image.compress()`"를 실제로 사용하는 기존 코드가 전혀 없었다.** wifi_test의 MJPEG 스트리밍 스크립트가 이 조합을 시도한 최초의 코드였고, 기존 미리보기가 정상인 것은 애초에 다른 코드 경로(하드웨어 VO 직결)를 타기 때문이지 YUV420SP→JPEG 변환이 검증된 적이 있어서가 아니다.

### 8-2. JPEG 자체 문제 vs 웹 전송 문제 분리 진단
핫스팟이 꺼져 있어 네트워크를 전혀 사용하지 않고, **SD카드에 JPEG을 직접 저장한 뒤 USB(`canmv_download_file_to_host`)로 받아 확인**하는 방식으로 네트워크 변수를 완전히 제거했다.

테스트 스크립트: `wifi_test/jpeg_format_test.py` (보드에서 `Sensor()` 직접 초기화 → `snapshot()` → `compress(quality=50)` → 파일로 저장, HTTP/소켓 코드 전혀 없음)

| 케이스 | 실행 결과(보드 로그) | 시각 확인 |
|---|---|---|
| YUV420SP, flip 없음 | `YUV420SP OK bytes=44433 magic=(255,216) tail=(255,217)` (JPEG 컨테이너 자체는 유효) | **이전 웹 스트리밍에서 본 것과 동일한 좌우 중복 + 녹색/마젠타 색상 왜곡 + 하단 노이즈 띠가 그대로 재현됨** |
| RGB565, flip 없음 | `RGB565 OK bytes=19925 magic=(255,216) tail=(255,217)` | 색상/기하 모두 정상, 다만 영상이 180도 뒤집혀 있음(카메라 장착 방향, 별개 이슈) |
| RGB565, `set_hmirror(True)` + `set_vflip(True)` | `RGB565 OK bytes=24207 magic=(255,216) tail=(255,217)` | **완전히 정상 — 색상, 좌우 중복 없음, 방향도 올바름** |

**진단 결론**: 왜곡은 100% 인코딩 단계(`Sensor.YUV420SP` + `Image.compress()` 조합)에서 발생하며, 네트워크/HTTP/소켓 전송과는 무관하다. 이는 이전 세션(§3-B)에서 "전송은 정상, 화질만 문제"라고 적었던 추정을 보드 실측으로 확정한 것이다. 사용자가 전달한 가설("YUV420SP/NV12가 compress()에서 잘못 해석된다")은 **독립적으로 재현한 실험으로 사실로 확인되었다** — 다만 그 가설의 출처였다는 보고서 자체는 끝내 찾지 못했다(§8-0).

### 8-3. 적용한 수정 (기존 웹서버 구조 재사용, 최소 변경)
`wifi_test/mjpeg_stream_test.py`에서 카메라 초기화 부분만 수정했고, HTTP/소켓/폴링 로직은 전혀 건드리지 않았다:

```python
sensor.set_hmirror(True)
sensor.set_vflip(True)
sensor.set_framesize(width=FRAME_WIDTH, height=FRAME_HEIGHT)
sensor.set_pixformat(Sensor.RGB565)   # 기존 Sensor.YUV420SP에서 변경
```

`alignment=12` 파라미터는 이번 조사로 원인이 아님이 밝혀져 제거했다(YUV420SP 왜곡은 alignment와 무관하게 재현되었고, RGB565는 alignment 없이도 정상이었다).

### 8-4. 남은 작업 (실제 보드 Wi-Fi 실행 필요)
이번 조사는 사용자 지시에 따라 **핫스팟을 켜지 않고 USB/SD카드 경로로만** 진행했다. 다음 사항은 핫스팟을 다시 켠 뒤 실제로 확인해야 한다:
1. 수정된 `mjpeg_stream_test.py`(RGB565 + flip)를 Wi-Fi 환경에서 재실행해 브라우저 `<img src="/stream">`에 정상 영상이 뜨는지 확인
2. RGB565가 YUV420SP보다 프레임당 바이트 수가 커질 수 있어(색 서브샘플링 없음) 실제 스트리밍 프레임레이트에 미치는 영향을 측정
3. `hmirror`/`vflip` 값이 모든 장착 상태에서 보편적으로 맞는지, 혹은 카메라 개체별로 다를 수 있는지 추가 확인

**현재 코드는 준비 완료 상태이며, 핫스팟을 켜주시면 바로 네트워크 재검증을 진행할 수 있다.**
