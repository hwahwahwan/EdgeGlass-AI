# 실행 시점에 정해지는 설정값은 main.py의 원래 위치에 유지합니다.
# 아래 전송 설정은 smart_glass_server.py(신규 통합 오케스트레이터)만 읽는다.
# main.py(손 추적 단독 실행, 보존 대상)는 이 파일을 참조하지 않고 항상
# MouseController의 기본 UART 전송을 그대로 사용한다.

# "uart"(기본, 실기기 검증됨) 또는 "udp"(Wi-Fi, 아직 실기기 미검증).
MOUSE_TRANSPORT = "uart"

# udp 포트. Mac에서 mac_mouse_bridge.py --transport udp 로 띄운 UDP
# 리스너의 포트와 일치해야 한다(기본 9000, 양쪽 기본값이 이미 같다).
MOUSE_UDP_PORT = 9000

# 아래 MOUSE_UDP_USE_HTTP_REGISTRATION이 True면 이 값은 무시된다(신규
# 기본 경로가 우선). MOUSE_UDP_USE_HTTP_REGISTRATION=False로 끈 경우에만
# 쓰이는 옛 방식: True면 Mac IP를 고정값으로 쓰지 않고, 보드 자신의
# 서브넷을 스캔해 @HELLO/@ACK 핸드셰이크로 Mac을 자동으로 찾는다
# (firmware/discovery.py). 핫스팟은 재연결마다 Mac에 새 IP를 주므로 고정
# IP는 금방 틀려진다. False로 끄면 아래 MOUSE_UDP_HOST 고정 주소로 보내는
# 더 예전 방식으로 되돌아간다 — 자동 탐색이 안 되는 환경(서브넷이 너무
# 크거나 실패)의 수동 대안.
MOUSE_UDP_AUTO_DISCOVER = True

# True(기본, 2026-10-27부터): 보드가 자기 서브넷을 스캔하지 않는다. 대신
# Mac 브리지가 TCP 8060으로 보드를 찾아(GET /device-info, EDGEGLASS_BOARD
# 식별) POST /register로 자신의 UDP 포트를 알려주면, 보드는 그 요청의
# 송신자 IP+포트를 목적지로 저장한다(RegisteredUdpTransport). 아래
# MOUSE_UDP_AUTO_DISCOVER/MOUSE_UDP_HOST 기반의 보드측 unicast 스캔
# 방식(AutoDiscoverUdpTransport)보다 이 값이 우선하며, 253-host 가정용
# Wi-Fi에서도 보드측 스캔이 전혀 필요 없다. False로 끄면 아래 옛 방식으로
# 되돌아간다 -- discovery.py/AutoDiscoverUdpTransport 자체는 삭제하지
# 않고 그대로 남겨뒀다(문서/테스트 참고용 겸 수동 대안).
MOUSE_UDP_USE_HTTP_REGISTRATION = True

# 자동 탐색이 서브넷 크기 때문에 실패했을 때(아래 MOUSE_UDP_MAX_SCAN_HOSTS
# 참고 — 가정용 /24처럼 호스트가 64개보다 많은 경우) 자동으로 쓰이는 고정
# 목적지. MOUSE_UDP_AUTO_DISCOVER=False로 직접 끈 경우에도 이 값을 쓴다.
# 집 Wi-Fi(192.168.45.0/24)에서 Mac의 실제 IP로 설정해둔 값이다 — 핫스팟은
# 보통 호스트 수가 적어(/28 등) 자동 탐색이 그대로 작동하므로 이 값을 쓰지
# 않는다. Mac이 집 Wi-Fi에서 다른 IP를 받으면(DHCP 재할당 등) 이 값도
# 함께 갱신해야 한다 — 2026-10-27, Mac이 .62에서 .28로 재할당되어 갱신함
# (DEV_HISTORY.md 참고).
MOUSE_UDP_HOST = "192.168.45.28"

# 자동 탐색이 한 번에 프로브할 수 있는 서브넷 호스트 수의 상한. 이보다 큰
# 서브넷(예: 가정용 라우터의 /24)에서는 자동 탐색을 포기하고 예외를 던진다
# — 이 경우 MOUSE_UDP_AUTO_DISCOVER=False로 바꾸고 MOUSE_UDP_HOST를 직접
# 설정해야 한다.
MOUSE_UDP_MAX_SCAN_HOSTS = 64

# 소프트 리부트 직후 소켓 계층이 NIC를 즉시 인식하지 못하는 레이스를 피하기
# 위한 재시도 횟수/간격(ms). experiments/wifi_test/WIFI_TEST_REPORT.md §0-3,
# §3-E 실측 근거.
MOUSE_UDP_RETRY_ATTEMPTS = 20
MOUSE_UDP_RETRY_DELAY_MS = 500

# STEP:/mem_free/FPS 등 반복 디버깅 로그 on/off. 평소에는 꺼서 Wi-Fi/웹/UDP
# 등록 상태 같은 핵심 정보만 터미널에 남긴다.
VERBOSE_ORCHESTRATOR_LOGS = False
