# 실행 시점에 정해지는 설정값은 main.py의 원래 위치에 유지합니다.
# 아래 전송 설정은 smart_glass_server.py(신규 통합 오케스트레이터)만 읽는다.
# main.py(손 추적 단독 실행, 보존 대상)는 이 파일을 참조하지 않고 항상
# MouseController의 기본 UART 전송을 그대로 사용한다.

# "uart"(기본, 실기기 검증됨) 또는 "udp"(Wi-Fi, 아직 실기기 미검증).
MOUSE_TRANSPORT = "uart"

# udp 전송일 때만 사용. Mac에서 mac_mouse_bridge.py --transport udp 로 띄운
# UDP 리스너의 주소/포트와 일치해야 한다.
MOUSE_UDP_HOST = "172.20.10.3"
MOUSE_UDP_PORT = 9000

# 소프트 리부트 직후 소켓 계층이 NIC를 즉시 인식하지 못하는 레이스를 피하기
# 위한 재시도 횟수/간격(ms). experiments/wifi_test/WIFI_TEST_REPORT.md §0-3,
# §3-E 실측 근거.
MOUSE_UDP_RETRY_ATTEMPTS = 20
MOUSE_UDP_RETRY_DELAY_MS = 500
