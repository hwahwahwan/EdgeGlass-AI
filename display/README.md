# display/ — VLT-OL016 OLED (독립 개발, 기본 bring-up 실기기 검증 완료)

`firmware/`(손 추적/마우스 제어 데모)와 완전히 분리된 독립 모듈이다. 이 폴더의
코드는 `firmware/`를 **읽기 전용으로만** 참고했고, import하거나 수정하지 않았다.
기존 ST7789 LCD 코드는 `archive/st7789_lcd/`에 보관돼 있다(더 이상 유지보수 안 함).

**2026-10-26, 실제 Voltly VLT-OL016을 K230D-Zero에 연결해 `oled_basic_test.py`
기본 bring-up 테스트를 실기기에서 실행하고 육안으로 확인했다** — I2C scan,
주소 인식, 화면 지우기/전체 켜짐/텍스트+도형 출력까지 전부 성공(아래 7절
"실기기 테스트 결과" 참고). 다만 이것은 **독립 bring-up 테스트 수준의 검증**이고,
실제 손 관절 스켈레톤(`DisplayUI`)을 AI 추론 루프에 연결해 보여주는 것까지는
아직 실기기로 검증하지 않았다 — 아래 "알려진 제약" 참고.

## 1. 대상 디스플레이 — 확인된 사양 vs 추정

| 항목 | 값 | 근거 |
|---|---|---|
| 제품명 | Voltly VLT-OL016 | 사용자 제공 |
| 종류 | 0.96인치 White OLED | 사용자 제공 |
| 인터페이스 | 4핀 I2C (GND/VCC/SCL/SDA) | 사용자 제공 |
| 해상도 | 128×64 | 가정값 그대로 `oled_basic_test.py`를 실기기에서 실행해 정상 출력 확인(2026-10-26) — 패널 고유 데이터시트로 치수를 직접 대조한 것은 아님 |
| 컨트롤러 | SSD1306 | `drivers/ssd1306.py`(micropython-lib 포팅, 초기화 시퀀스 무수정)로 실기기에서 화면 출력 확인(2026-10-26) — SSD1306 호환으로 사실상 확인됨 |
| I2C 주소 | 0x3C | 실기기 `i2c.scan()`에서 `0x3C` 하나만 확인됨(2026-10-26) |

컨트롤러가 SSD1306이 아닐 경우, `drivers/ssd1306.py`만 교체하면 되도록
`src/oled_device.py`는 `SSD1306_I2C`를 **딱 한 곳**에서만 import한다(아래
"드라이버 교체" 참고).

## 2. 사용한 드라이버와 공식 자료

- MicroPython 공식 SSD1306 드라이버(이식 원본):
  https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/display/ssd1306/ssd1306.py
- MicroPython SSD1306 사용법: https://docs.micropython.org/en/latest/esp8266/tutorial/ssd1306.html
- K230 CanMV I2C API: https://www.kendryte.com/k230_canmv/en/v1.3/api/machine/K230_CanMV_I2C_API_Manual.html
- K230 FPIOA 공식 예제: https://www.kendryte.com/k230_canmv/en/main/example/peripheral/fpioa.html
- **이 저장소에 캐시된 K230 CanMV 공식 I2C+SSD1306 예제**
  (`examples/03-Machine/i2c_ssd1306.py`, `canmv-k230` MCP 도구로 조회) — 핀
  설정 패턴(`fpioa.set_function(11, FPIOA.IIC2_SCL)` 등)과 I2C 생성 방식을
  이 예제에서 그대로 따랐다. `examples/03-Machine/touch_user.py`도 같은
  GPIO11/12 조합을 I2C2에 쓰고 있어 교차 확인했다.

포팅 결과(자세한 근거는 `DEVELOPMENT.md` 참고): CanMV의 `machine.I2C`가
`writeto(addr, buf)`/`writevto(addr, vector)`를 표준 MicroPython과 동일한
시그니처로 제공하고(`machine.pyi` 캐시 스텁으로 확인), `framebuf.FrameBuffer`도
`MONO_VLSB`를 포함해 동일한 API를 제공해서, **드라이버 로직 자체는 수정 없이
그대로 포팅**했다. CanMV 전용 코드(FPIOA 핀 설정, I2C 객체 생성)는 드라이버
밖(`src/oled_device.py`)으로 분리했다.

## 3. K230D-Zero 핀 연결표 — 실기기 연결 및 통신 확인됨 (2026-10-26)

| OLED 핀 | K230D-Zero 핀 | 신호 | 상태 |
|---|---|---|---|
| GND | GND | - | 실제 배선으로 연결, 정상 동작 |
| VCC | 3V3 | 3.3V | 실제 3V3 핀으로 연결, 정상 동작(5V는 시도하지 않았다) |
| SCL | IO_11 | I2C2 SCL (하드웨어) | 실제 배선으로 연결, `i2c.scan()`에서 장치가 잡혀 통신 확인됨 |
| SDA | IO_12 | I2C2 SDA (하드웨어) | 위와 동일 — 실제 배선·통신 확인됨 |

핀 번호는 `display/display_config.py`의 `PIN_SCL`/`PIN_SDA`/`I2C_ID`에 모여 있다.

**다른 K230 보드 예제를 그대로 복사하지 않았다** — IO11/12는 이 프로젝트가 실제
쓰는 "K230 CanMV" 계열의 **공식** SSD1306 예제에서 가져온 것이며, 별도로
`firmware/`의 기존 UART2(고정 보드 핀 44/45, 코드에서 FPIOA로 재설정하지 않음)
및 보관된 ST7789 LCD 테스트(GPIO14/15/16/17/20/21)와 충돌하지 않음을 프로젝트
전체 grep으로 확인했다.

## 4. 폴더 구조

```text
display/
├── drivers/
│   └── ssd1306.py          # micropython-lib 포팅, machine import 없음
├── src/
│   ├── oled_device.py      # CanMV 전용 bring-up (FPIOA/I2C), machine import는 여기만
│   ├── hand_renderer.py    # 순수 Python: landmark -> 픽셀 좌표/선분
│   └── display_ui.py       # DisplayUI.update(landmarks, gesture, fps) 공개 인터페이스
├── tests/
│   ├── virtual_oled.py     # PC용 가상 128x64 캔버스(+PNG 저장), machine import 없음
│   ├── test_hand_renderer.py
│   ├── test_display_ui.py
│   └── test_oled_device.py
├── examples/
│   ├── oled_basic_test.py  # 보드 전용 (I2C scan + 채우기 + 텍스트)
│   ├── oled_hand_demo.py   # 보드 전용 (합성 손동작 더미 데이터 -> 실제 패널, AI 미연동)
│   ├── hand_demo.py        # PC 전용 (가상 손동작 -> PNG 저장)
│   └── output/             # hand_demo.py가 생성하는 PNG들
├── display_config.py        # 핀/I2C/레이아웃/업데이트 주기 상수 (firmware/config.py와
│                             # 모듈명 충돌을 피하려고 config.py가 아닌 이 이름을 씀)
├── README.md                 (이 파일)
└── DEVELOPMENT.md
```

실제 AI 추론 루프 연동(더미 데이터가 아닌 `firmware/hand_tracker.py`의 실시간 손
관절)은 `display/` 바깥, `firmware/smart_glass_server.py`에 구현한다 — 아래
"실제 AI 루프 연동" 절 참고.

## 5. 보드에서 실행할 테스트 파일

CanMV는 실행 스크립트 자신의 디렉터리를 `sys.path`에 자동으로 넣지 않고,
중첩 패키지 import도 이 프로젝트에서 검증된 적이 없다(`CLAUDE.md` 참고) —
`firmware/`가 `/sdcard/smart_glass/`로 평탄화되는 것과 같은 방식으로,
`display/`도 **보드에는 평탄화해서** 올려야 한다:

```text
display/display_config.py      -> /sdcard/display/display_config.py
display/drivers/ssd1306.py     -> /sdcard/display/ssd1306.py
display/src/oled_device.py     -> /sdcard/display/oled_device.py
display/src/hand_renderer.py   -> /sdcard/display/hand_renderer.py
display/src/display_ui.py      -> /sdcard/display/display_ui.py
display/examples/oled_basic_test.py -> /sdcard/display/oled_basic_test.py
display/examples/oled_hand_demo.py  -> /sdcard/display/oled_hand_demo.py  (더미 데이터, AI 미연동)
```

이 `/sdcard/display/` 경로는 **`display/`를 독립적으로 테스트할 때만** 쓴다.
실제 AI 루프에 연동할 때는 `firmware/`와 같은 `/sdcard/smart_glass/`에
합쳐서 배포한다 — 아래 "실제 AI 루프 연동" 절 참고.

(로컬 폴더 이름이 보드 경로와 같아야 한다고 가정하지 않는다 — `firmware/`와
동일한 원칙.) 평탄화 후 CanMV IDE에서 `oled_basic_test.py`를 직접 실행한다.
이 파일은 I2C scan → 전체 채우기(검정→흰색) → 텍스트/사각형 순으로 진행하며,
각 단계를 콘솔에 출력한다. **실기기로 한 번도 실행해 보지 못했다** — ST7789
LCD 때와 달리 `oled_device.open_display()`는 패널이 없거나 잘못 연결돼도
크래시 대신 `None`을 반환하도록 설계했지만(`src/oled_device.py` 참고), 이
설계 자체도 실기기로 증명되지는 않았다.

## 6. PC에서 가상 화면을 확인하는 방법

실제 보드/패널 없이 다음을 실행할 수 있다(Python 3, `requirements.txt`의
`Pillow` 필요):

```bash
cd EdgeGlass-AI
source .venv/bin/activate   # 또는 python3 -m venv .venv && pip install -r requirements.txt
cd display
python3 examples/hand_demo.py
```

`display/examples/output/`에 PNG 13장이 저장된다(픽셀이 잘 보이도록 6배
확대, 128×64 원본 비율 유지) — 펼친 손(MOVE), 주먹(DRAG), 손가락을 접는
애니메이션 4프레임, MOVE/CLICK/DRAG/STOP 4종, 손 인식 실패, 화면 경계 밖
극단적 좌표 1장, 연속 업데이트 스로틀링 결과 1장을 포함한다. 콘솔에도
스로틀링 결과와 예외 처리(캔버스 없음/예외 발생)가 안전하게 처리됐는지
출력한다.

단위 테스트(29개, 하드웨어·모킹 불필요 — `hand_renderer`/`display_ui`는 순수
Python이고, `oled_device`는 fake `machine`/`framebuf`로 검증):

```bash
cd display
python3 -m unittest discover -s tests -v
```

## 7. 실제 OLED 연결 후 실행 순서 — 실기기 테스트 결과 (2026-10-26)

1. 4핀(GND/VCC/SCL/SDA)을 위 배선표대로 연결한다 — 전원 올리기 전 한 번 더
   확인(특히 VCC는 3.3V만). **완료.**
2. `display/` 전체를 위 "보드에서 실행할 테스트 파일" 절차대로
   `/sdcard/display/`에 평탄화해서 올린다. **완료.**
3. `oled_basic_test.py`를 CanMV IDE에서 실행한다. **완료, 2회 재실행 모두
   동일하게 성공.**
4. 콘솔의 `[OLED] i2c.scan() -> [...]` 로그를 먼저 확인한다 — **`['0x3c']`
   로 확인됨**, `config.OLED_I2C_ADDR`(0x3C)와 추가 수정 없이 바로 일치했다.
5. 화면에 검정→흰색 전환, 이어서 "EdgeGlass OLED"/"OK" 텍스트와 사각형
   테두리가 보이면 기본 bring-up 성공이다. **사용자가 육안으로 확인함** —
   흰 화면 전환과 텍스트 출력을 확인했고, 이후 `close_display()`가
   `poweroff()`를 호출해 화면이 꺼지는 것도 의도된 동작임을 확인했다(테스트
   종료 직후 "화면이 바로 꺼졌다"는 관찰은 이 때문). 추가로 흰 화면을
   계속 켜 두는 진단 스크립트(`oled_fullon_hold.py`, 무한 루프로 유지,
   `[CanMV] stop` 버튼으로 종료)로 화면이 꺼지지 않고 유지되는 것도
   별도로 확인했다.
6. 실패하면(scan에 주소가 잡히는데도 화면이 안 나오는 경우) `drivers/ssd1306.py`의
   초기화 시퀀스가 이 패널과 안 맞을 가능성이 있다 — 이번에는 이 경우에
   해당하지 않았다.
7. 기본 bring-up이 확인됐으므로, 다음 단계는 `src/display_ui.py`의
   `DisplayUI`를 `oled_device.open_display()`가 반환한 객체로 생성해 실제
   손동작 데이터로 테스트하는 것이다(아직 수행하지 않음 — `docs/DEV_HISTORY.md`
   4-3의 연결 지점 분석 참고).

## 8. 알려진 제약 및 미검증 사항

- VLT-OL016의 I2C 통신·주소(0x3C)·기본 SSD1306 초기화 시퀀스는 **실기기로
  확인됨**(2026-10-26, `oled_basic_test.py`). 다만 `machine.I2C.writevto()`가
  upstream 드라이버가 기대하는 대로 정확히 한 번의 START/STOP 안에서 여러
  버퍼를 보내는지(API가 예외 없이 동작한다는 것과 프로토콜이 정확한지는
  별개)와, IO11(SCL)/IO12(SDA)가 다른 용도와 완전히 충돌 없는 전용 핀인지
  `FPIOA.help()`로 직접 조회한 적은 없다 — 지금까지는 코드 동작과 화면
  출력으로 간접 확인한 것이다.
- `oled_device.open_display()`가 "패널 없음"을 크래시 없이 처리한다는 설계는
  코드 레벨 테스트(fake `machine`)로만 확인했고, 실제 I2C 버스 에러 상황에서도
  똑같이 안전할지는 실기기 확인이 필요하다.
- `DisplayUI`(손 관절 스켈레톤 UI)는 아직 실기기에서 실행해 보지 않았다 —
  이번에 검증한 것은 `oled_basic_test.py`의 기본 bring-up(지우기/전체 켜짐/
  고정 텍스트)뿐이다.
- 상태 표시줄 레이아웃은 `framebuf.FrameBuffer.text()`의 고정 8×8 비트맵
  폰트(128px ÷ 8px = 한 줄 최대 16글자) 제약에 맞춰 설계값을 줄였다 — 참고
  목업 이미지의 "MOVE    FPS 8.5    HAND OK"(약 27자)는 실제 해상도에서
  그대로 들어가지 않는다(`DEVELOPMENT.md` 참고).
- `hand_demo.py`의 합성 "주먹" landmark 좌표는 손으로 만든 근사치이며, 실제
  AI 모델 출력과 다르게 생겼을 수 있다.
- `tests/virtual_oled.py`의 PC 가상 화면 폰트는 MicroPython 업스트림 소스
  (`font_petme128_8x8.h` + `modframebuf.c`의 `framebuf_text()`)에서 바이트
  테이블과 렌더링 알고리즘을 그대로 가져와 **소스 코드 레벨로는** 실제
  `framebuf.FrameBuffer.text()`와 일치하도록 포팅했다. 다만 CanMV 자체 C
  소스를 직접 대조하거나 실제 패널에서 눈으로 비교하지는 못했다 — CanMV의
  `framebuf` 모듈이 upstream 구현을 그대로 쓴다는 전제는 `framebuf.pyi`
  스텁의 API 표면이 동일하다는 점에만 근거한다(`DEVELOPMENT.md` 2-6 참고).
- 스켈레톤 영역(128×54)은 landscape(가로:세로 ≈ 2.5:1)인데 손을 펼친
  모양은 보통 1:1~1.3:1 정도라, `layout_skeleton()`이 손의 실제 비율을
  왜곡하지 않고 맞추는 한 가로 폭을 100% 채우는 것은 구조적으로 불가능하다
  — `examples/hand_demo.py`의 테스트 좌표를 옆으로 더 퍼진 모양으로 조정해
  가로 사용 비율을 약 26%→50% 수준으로 올렸지만(`DEVELOPMENT.md` 2-8), 이는
  "가능한 범위의 최대화"이지 "화면 전체를 꽉 채움"은 아니다. 실제 AI 모델이
  주는 손 모양에 따라 체감 크기는 달라질 수 있다.
