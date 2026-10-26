# 자동 부팅 (`/sdcard/boot.py` + `/sdcard/main.py`)

USB 데이터 연결 없이 **전원만 공급해도** K230D-Zero가 카메라+AI+OLED+Wi-Fi+UDP
마우스+웹서버(`firmware/run_wifi.py`와 동일한 구성,
`smart_glass_server.main(transport_kind="udp", enable_web=True)`)를 자동으로
실행하게 하는 두 파일이다.

**2026-10-26 UART에서 UDP로 전환**: 처음엔 UART(`run_uart_web.py`와 동일
구성)로 만들었으나, UART2는 CH342K 케이블을 Mac에 물리적으로 꽂아야만
Mac 쪽 `mac_mouse_bridge.py`가 받을 수 있어 "전원만으로 무선 동작"이라는
목표와 모순됐다(`docs/DEV_HISTORY.md` 4-3 참고). UDP 자동 탐색
(`@HELLO/@ACK`)으로 바꿔 Mac 브리지가 같은 Wi-Fi/핫스팟에서 보드를 무선으로
찾도록 변경했고, 실기기에서 `[UDP] Mac registered: ...`/`Mouse control
ready`까지 확인했다. **`firmware/run_uart.py`는 전혀 수정하지 않았다** —
케이블로 직접 제어하고 싶을 때는 그대로 쓸 수 있다.

## 이 폴더와 보드 경로의 관계

이 폴더(`tools/autorun/`)는 **로컬 원본 보관용**이다. 보드에 올릴 때는
`CLAUDE.md`의 "로컬 구조와 보드 SD카드 구조가 다른 것은 의도된 것" 원칙대로
아래처럼 평탄화해서 올린다 — `firmware/` → `/sdcard/smart_glass/`와 같은
원칙이지만 대상 경로가 다르다:

| 로컬 | 보드 | 역할 |
|---|---|---|
| `tools/autorun/boot.py` | `/sdcard/boot.py` | MicroPython 표준: 전원이 들어올 때마다 가장 먼저 실행됨 |
| `tools/autorun/main.py` | `/sdcard/main.py` | boot.py 다음에 자동 실행됨 — 실제 지연·안전모드 판단·앱 실행 로직 |

**`firmware/main.py`(손 추적 단독 실행, `/sdcard/smart_glass/main.py`에
배포됨)와는 완전히 다른 파일이다.** `/sdcard/main.py`는 보드 루트의 특수
부팅 파일이고, `/sdcard/smart_glass/main.py`는 이 프로젝트의 수동 실행용
스크립트 중 하나일 뿐이다 — 혼동하지 않는다.

## 복구 방법 (둘 중 하나)

1. **USB로 끼어들기**: 전원이 들어온 뒤 `/sdcard/main.py`가 8초 카운트다운을
   출력하는 동안 USB로 연결해 인터럽트(CanMV IDE의 Stop 버튼, 터미널의
   Ctrl-C, 또는 MCP의 `canmv_stop_script`)를 보내면 그 자리에서 REPL로
   멈추고 아래쪽 실행 코드는 전혀 실행되지 않는다 — 기존처럼 수동으로
   `firmware/run_uart.py` 등을 실행하면 된다.
2. **`/sdcard/SAFE_MODE` 플래그 파일**: 이 파일이 있으면 카운트다운 자체를
   건너뛰고 곧바로 REPL로 남는다. USB 타이밍을 맞출 필요 없이, 다음 번
   부팅 전에 이 파일만 만들어 두면 된다.

**이 두 가지로도 막을 수 없는 것**: `tools/DEPLOY.md`에 기록된 것처럼
`MediaManager.init()` 오설정 같은 **진짜 하드웨어/펌웨어 레벨 행(hang)**은
파이썬 예외가 아니라서 위 두 방법으로도 못 막는다 — 이 경우는 물리적으로
전원을 다시 뽑았다 꽂는 것 외에 방법이 없다. 반면 Wi-Fi 연결 실패, kmodel
누락 같은 **일반 파이썬 예외**는 이미 안전하다 — MicroPython이 트레이스백만
찍고 REPL로 돌아갈 뿐 재부팅 루프에 빠지지 않는다.

## 배포

```text
tools/autorun/boot.py -> /sdcard/boot.py
tools/autorun/main.py -> /sdcard/main.py
```

다른 `firmware/*.py` 파일들이 이미 `/sdcard/smart_glass/`에 배포돼 있어야
한다(이 두 파일은 그것들을 그대로 가져다 쓴다, 새로 복제하지 않는다).
