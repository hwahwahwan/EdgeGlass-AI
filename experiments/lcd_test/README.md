# GMT130-V1.0 (ST7789) LCD 단독 테스트

`firmware/`(손 추적/마우스 제어 데모)와 완전히 분리된 독립 모듈이다. 이 디렉터리의
코드는 기존 데모의 UART2, 카메라, Wi-Fi 경로를 전혀 사용하지 않는다.

## 1. 배선표 (7핀)

| LCD 핀 | K230D-Zero 핀 | 신호 | 검증 상태 |
|---|---|---|---|
| GND | GND | - | 안전, 변경 없음 |
| VCC | 3V3 | 3.3V | **3.3V만 사용. 5V 금지.** GMT130-V1.0 자체의 공식 데이터시트는 찾지 못했다. 동일 계열 7핀 240x240 ST7789 모듈 다수가 "3.3V 전용, 보드에 레귤레이터 없음"으로 판매되고 있어 이를 근거로 3.3V를 권장하지만, 이 모듈 고유의 전압 스펙은 미확인이다. |
| SCK | IO_15 | SPI1 CLK (하드웨어) | **실기기 확인됨.** `FPIOA.help(15)` 결과 `can be function: GPIO15/OSPI_CLK/RESV/QSPI0_CLK/RESV`, 현재 상태는 기본 GPIO(미점유). 공식 CanMV 예제(`examples/03-Machine/spi_lcd_show.py`)와 동일한 핀. |
| SDA | IO_16 | SPI1 MOSI (하드웨어) | **실기기 확인됨.** `can be function: GPIO16/OSPI_D0/QSPI1_CS4/QSPI0_D0/RESV`, 미점유. 공식 예제와 동일 핀. |
| RES | IO_20 | GPIO (리셋) | **실기기 확인됨.** 미점유, UART2(TXD=핀44/RXD=핀45, 실기기 조회로 확인)와 충돌 없음. |
| DC | IO_21 | GPIO (명령/데이터 선택) | **실기기 확인됨.** 미점유, UART2와 충돌 없음. |
| BLK | IO_17 | GPIO (백라이트) | 핀 자체는 미점유로 실기기 확인됨. **극성(active-high/low)은 미확인** — 인터넷 자료도 상충된다. `lcd_test.py`는 기본으로 HIGH=on을 시도한다. |

CS(칩 셀렉트) 핀은 이 7핀 모듈에 없다. 그러나 CanMV v1.8의 `machine.SPI_LCD` 생성자는
CS용 `Pin` 객체를 요구하며, `cs=None`으로 호출하면 **실제 보드가 소프트 리부트(크래시)
되는 것을 이번 작업에서 두 번 직접 확인했다.** 따라서 코드에서는 LCD에 물리적으로
연결하지 않는 여분의 GPIO(IO_14, 미점유 확인됨)를 더미 CS `Pin` 객체로만 생성자에
전달한다 — **배선표에는 영향 없음**, 소프트웨어 내부에서만 쓰는 자리 표시자다.

## 2. 필요한 점퍼선

7개 (GND, VCC, SCK, SDA, RES, DC, BLK). 추가 부품이나 추가 납땜은 필요하지 않다 —
7핀 헤더가 이미 납땜되어 있고 점퍼선도 보유 중이라고 했으므로 별도 구매 불필요.
CS용 더미 핀(IO_14)은 코드에서만 쓰이며 물리적으로 연결하지 않는다.

## 3. CanMV v1.8 펌웨어 호환성 (실기기로 직접 확인)

실제 보드(펌웨어 `CanMV v1.8-0-gc2d1f5c`, K230D-Zero 128M)에 연결해 확인한 결과:

- `machine.FPIOA`, `machine.Pin`, `machine.SPI` 모두 존재하고 정상 동작.
- `machine.SoftSPI`는 이 펌웨어에 **없다** (캐시된 스텁에서도 검색되지 않음). 대신
  `machine.SPI`(하드웨어 SPI) + `machine.SPI_LCD`를 쓴다.
- `machine.SPI_LCD`라는 **공식 네이티브 ST7789 드라이버 클래스가 이미 펌웨어에
  내장**되어 있다 (`SPI_LCD.TYPE_ST7789` 상수 존재). 별도의 MicroPython ST7789
  드라이버 라이브러리를 작성/포팅할 필요가 없다 — `lcd.init()` 호출만으로 ST7789
  초기화 시퀀스가 자동 수행된다 (`examples/03-Machine/spi_lcd_show.py` 참고). 색이
  반전되거나 틀어지면 `examples/03-Machine/spi_lcd_show_custom_screen.py`처럼
  `lcd.command(...)`로 수동 초기화 시퀀스를 보낼 수도 있다(이번 작업에서는 사용 안 함).
- **중요(실기기로만 발견 가능했던 사실):** LCD가 물리적으로 연결되지 않은 상태에서
  `SPI_LCD(spi, dc, cs, rst)` 생성자를 호출하면 보드가 즉시 소프트 리부트됐다. `cs=None`
  뿐 아니라 더미 `Pin` 객체를 넘겨도 동일하게 발생했다. 재부팅 후 `/sdcard/smart_glass/`
  의 기존 데모 파일들은 전부 그대로 남아 있어 SD카드 손상은 없었지만, **이 때문에
  "LCD를 연결하지 않은 채 보드에서 코드만 미리 돌려 검증"하는 것이 불가능하다.** 이
  스크립트는 반드시 7핀 배선과 전원 연결을 마친 뒤에만 실행해야 한다.

## 4. 실행 방법

1. 위 배선표대로 GMT130-V1.0을 K230D-Zero에 연결한다 (전원을 올리기 전 배선을 한 번
   더 확인).
2. CanMV IDE 또는 이 리포지토리의 보드 연결 도구로 `lcd_test.py`를
   `/sdcard/lcd_test/lcd_test.py`에 업로드한다 (`/sdcard/smart_glass/`와 분리된
   경로 — 기존 데모와 섞지 않는다).
3. CanMV IDE에서 `lcd_test.py`를 직접 실행한다.
4. 화면에 빨강 → 초록 → 파랑 → 검정 → 흰색이 1초 간격으로 순서대로 표시되고, 이어서
   검정 배경에 초록색 "EdgeGlass LCD OK" 텍스트와 노란색 사각형 테두리가 표시되면
   성공이다.
5. 화면이 계속 꺼져 있으면(초기화 자체는 오류 없이 끝났다면) `lcd_test.py`의
   `BLK_ACTIVE_LOW = False`를 `True`로 바꿔 다시 실행한다.

## 5. 테스트 성공 여부 (이번 작업 기준)

- **실기기에서 실제로 화면에 색이 출력되는 것은 이번 세션에서 검증하지 못했다.**
  LCD가 아직 물리적으로 연결되지 않았기 때문이다. 코드 작성 완료를 실기기 검증
  성공으로 취급하지 않는다.
- 실기기로 확인된 것: 보드 연결, 펌웨어 버전, FPIOA 핀 가용성(15/16/17/20/21/14 모두
  현재 미점유), UART2의 실제 핀 번호(44/45)와 위 배선의 비충돌, `machine.SPI_LCD`
  클래스의 존재, `SPI_LCD(cs=...)` 가 `None`이든 더미 Pin이든 LCD 미연결 상태에서는
  보드를 크래시시킨다는 점.
- 확인되지 않은 것: GMT130-V1.0의 정확한 VCC 허용 범위, BLK 극성, 실제 화면 출력
  성공 여부, `lcd.init()`의 기본 ST7789 초기화 시퀀스가 이 특정 패널의 gamma/MADCTL
  설정과 맞는지(틀어지면 `spi_lcd_show_custom_screen.py`식 커스텀 시퀀스 필요).

## 6. 향후 통합 방향 (이번 단계에서는 구현하지 않음)

화면 출력이 실기기에서 확인되면, `smart_glass_server.py`의 OSD 패턴과 마찬가지로
LCD에 아래 정보를 그릴 수 있다 — 지금은 구조 설계만 남겨두고 구현/통합은 하지 않는다.

- Wi-Fi 연결 상태, IP 주소 (`wifi.py`가 이미 들고 있는 값을 읽기만 하면 됨)
- 손 제스처 인식 상태, MOVE/CLICK/DRAG/STOP (`gesture_controller.py`의 현재 상태를
  읽기만 하면 됨)

통합 시에도 `FEATURE_*` 플래그로 LCD 리소스 생성 자체를 건너뛸 수 있게 하고,
`lcd_test.py`의 `init_display()`/`color_test()`와 동일한 패턴(명시적 핀 상수, 예외
처리, `deinit()`)을 재사용하는 것을 권장한다.
