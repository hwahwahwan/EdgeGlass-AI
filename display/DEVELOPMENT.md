# display/ 개발 기록

실기기(VLT-OL016) 없이 진행한 독립 개발 세션의 구현 과정·발견한 문제·해결
방법·테스트 결과를 기록한다. 실기기 검증 항목은 README.md와 명확히 구분해서
표시한다(이 문서의 어떤 항목도 실기기로 확인되지 않았다).

## 1. 리서치 — 드라이버/API 조사

### 1-1. CanMV가 `framebuf`/표준 I2C API를 지원하는지

- **확인한 방법**: 이 저장소에 캐시된 CanMV K230 MicroPython 스텁
  (`machine.pyi`, `framebuf.pyi`)을 `canmv-k230` MCP 도구로 조회.
- **확인된 사실**:
  - `framebuf.pyi`에 `FrameBuffer` 클래스와 `MONO_VLSB` 상수가 존재 —
    micropython-lib SSD1306 드라이버가 요구하는 바로 그 조합.
  - `machine.pyi`의 `I2C` 클래스가 `writeto(addr, buf, stop=True)`와
    `writevto(addr, nitems, stop=True)`를 표준 MicroPython과 동일한
    시그니처로 제공.
  - `machine.pyi`의 `FPIOA` 클래스에 `IIC0_SCL`~`IIC4_SDA`(5개 I2C
    컨트롤러) 함수 상수가 있음.
- **결론**: SSD1306 드라이버를 거의 수정 없이 포팅할 수 있다고 판단 —
  아래 1-2에서 실제로 그렇게 됨.

### 1-2. 공식 K230 CanMV SSD1306 예제 확인

- **확인한 방법**: `canmv_examples_search("I2C")`로 캐시된 예제 검색.
- **발견**: `examples/03-Machine/i2c_ssd1306.py`가 **이미 존재** —
  `fpioa.set_function(11, FPIOA.IIC2_SCL)`, `fpioa.set_function(12,
  FPIOA.IIC2_SDA)`, `I2C(2, freq=400*1000)` 패턴을 그대로 씀. 다만 이
  공식 예제 자체는 SSD1306 명령 바이트를 직접 만들어 보내는 저수준
  구현이고, framebuf 기반 드라이버는 쓰지 않았다.
- **선택**: FPIOA/I2C 생성 패턴(핀, 함수 상수, I2C id)은 이 공식 예제를
  그대로 따르고, 그림 그리기 API는 더 풍부한 micropython-lib의
  framebuf 기반 드라이버를 포팅해서 쓰기로 함 — 이유: 사용자가 요청한
  `text`/`line`/`pixel` 등 다양한 드로잉 기능이 저수준 명령 방식보다
  framebuf 기반 쪽이 훨씬 적은 코드로 충족됨.
- **참고**: `examples/03-Machine/touch_user.py`도 I2C2에 `scl=11,
  sda=12`를 쓰고 있어 핀 선택을 다시 한번 교차 확인.

## 2. 설계 결정

### 2-1. 드라이버 포팅 범위

- **조사한 방법**: micropython-lib 공식 ssd1306.py의 구조를 CanMV
  스텁과 한 줄씩 대조.
- **선택한 방법**: `SSD1306`/`SSD1306_I2C` 클래스 로직은 **그대로 포팅**
  (명령 바이트 시퀀스, `write_cmd`/`write_framebuf` 전부 동일).
- **선택 이유**: 위 1-1에서 확인했듯 CanMV의 `framebuf.FrameBuffer`와
  `machine.I2C.writeto/writevto`가 upstream이 기대하는 API와 시그니처가
  일치해서, 수정할 이유 자체가 없었다.
- **CanMV 전용 코드는 분리**: FPIOA 핀 설정과 `I2C(id, freq=...)` 객체
  생성은 드라이버 파일이 아니라 `src/oled_device.py`에 뒀다 — 이유:
  드라이버를 upstream과 최대한 가깝게 유지해 나중에 실기기에서 문제가
  생겼을 때 "포팅 중 생긴 버그"와 "이 패널/펌웨어 고유의 문제"를
  구분하기 쉽게 하기 위함.

### 2-2. `hand_renderer.py`를 왜 완전히 순수 Python으로 분리했는가

- **선택 이유**: 실기기가 없는 상태에서 "코드가 돌아간다"와 "실제로
  맞게 그려진다"를 구분해야 한다는 작업 지시를 따르려면, 좌표 변환·정규화·
  클램핑 로직 자체를 `machine`/`framebuf` 없이도 PC에서 직접, 모킹 없이
  단위 테스트할 수 있어야 했다. `display_ui.py`도 같은 이유로 "canvas"를
  오리 타이핑(duck typing)으로만 요구해, 실제 SSD1306과 PC용
  `VirtualOLED`가 동일한 코드 경로를 타게 했다.

### 2-3. 기존 프로젝트 참조 여부

- `firmware/ui.py`의 `_SKELETON_CONNECTIONS`(21개 관절, 20개 연결선)를
  **읽기 전용으로 확인**하고 `hand_renderer.py`에 동일한 리스트를
  복제했다(import는 하지 않음 — `firmware/`는 참고 전용, 이번 작업에서
  수정하지 않는다는 지시에 따름). `firmware/ui.py`의 `draw_landmarks()`가
  `points[i*2]`/`points[i*2+1]` 형태의 평탄 배열(21개 관절 × 2)을 쓰는
  것도 확인했지만, `hand_renderer.layout_skeleton()`은 더 범용적인
  `[(x, y), ...]` 리스트를 입력으로 받도록 설계했다 — 호출부(나중에
  실제 통합 시)에서 변환 한 줄만 추가하면 된다.
- `firmware/smart_glass_server.py`의 `AI_RGB888P_SIZE = [640, 360]`을
  `config.AI_FRAME_WIDTH/HEIGHT`에 참고용으로만 적어뒀다 —
  `hand_renderer.py`의 레이아웃 계산 자체는 이 값에 의존하지 않는다
  (landmark들의 실제 bounding box만 사용).
- `firmware/`, `mac/`, 최상위 문서(`README.md`/`CLAUDE.md`/`AGENTS.md`
  등)를 프로젝트 전체 grep으로 확인해, `display/`가 쓰려는 FPIOA
  핀(11/12)과 겹치는 곳이 없음을 확인했다(기존 UART2는 고정 보드
  핀 44/45, 보관된 ST7789 LCD 테스트는 14/15/16/17/20/21).

### 2-4. 참고 목업 이미지와 실제 128×64 해상도의 차이 (해결됨)

- **증상**: 사용자가 제공한 디자인 목업은 하단에 "MOVE    FPS 8.5
  HAND OK" 형태의 한 줄 텍스트를 보여줬다.
- **원인**: 확인됨 — `framebuf.FrameBuffer.text()`는 고정 8×8 비트맵
  폰트만 제공한다(캔버스 폭 128px ÷ 8px = 한 줄 최대 16글자). 목업
  문구는 공백 포함 약 27자로, 실제 폰트로는 한 줄에 들어가지 않는다.
- **시도한 해결 방법**:
  - (검토 후 기각) 폰트를 줄여서 더 작게 — framebuf 기본 폰트는 크기
    조절 API가 없다(별도 커스텀 폰트 렌더러가 필요해 이번 범위를
    벗어남).
  - (채택) 표시 내용을 압축: 제스처 라벨 5자(`MOVE `/`CLICK`/`DRAG `/
    `STOP `) + FPS 4자(`8.5`를 `" 8.5"`처럼 고정폭으로) + 손 인식 여부
    1자(`H`/`-`) = 총 약 12자, 16자 한도 안에 여유 있게 들어감.
- **최종 해결**: `src/display_ui.py`의 `_draw_status_bar()`가 위 압축된
  레이아웃을 그린다. 손 관절 스켈레톤이 화면 대부분(상단 54px)을 쓰고,
  하단 10px에 구분선 + 압축된 상태 텍스트 한 줄만 쓰는 구조는 목업의
  레이아웃 의도(스켈레톤이 메인, 텍스트는 보조)를 그대로 따랐다.
- **검증 결과**: `tests/test_display_ui.py`로 상태 줄이 실제로 픽셀을
  켜는지 확인(코드 레벨). 실제 패널에서 글자가 읽히는지는 **미검증**
  (실기기 없음).

### 2-5. 합성 "주먹" landmark가 정규화 후 fist처럼 안 보이던 문제 (부분 해결)

- **증상**: `examples/hand_demo.py`의 초기 주먹 좌표로 PNG를 만들었더니
  `layout_skeleton()`의 bounding-box 확대·축소를 거친 뒤에도 펼친
  손과 큰 차이 없이 보임.
- **원인**: 가설 — MCP(손허리손가락관절)는 실제 주먹에서도 크게
  움직이지 않아 바운딩 박스가 여전히 넓게 잡히고, 정규화가 전체를
  다시 화면 가득 확대하면서 "손가락이 짧아진" 효과가 시각적으로
  희석됨.
- **시도한 해결 방법**:
  - (부분 성공) 손가락 끝(TIP) 좌표를 손목 쪽으로 더 가깝게 당김 —
    여전히 완전한 "뭉친 주먹" 실루엣은 아니지만 펼친 손과는 선이
    교차·꺾이는 형태로 구분됨.
- **최종 해결**: (미해결, 낮은 우선순위) — 이건 렌더러 버그가 아니라
  **손으로 만든 합성 좌표의 한계**다. 렌더러 자체는 `test_hand_renderer.py`의
  `test_fist_hand_also_lays_out_without_error`로 "꺾인 토폴로지도 예외 없이
  그려짐"만 검증했고, 시각적 "주먹다움"은 실제 AI 모델 출력으로
  재검증이 필요하다는 점을 README.md에 명시했다.
- **검증 결과**: 크래시 없음(코드 레벨 확인), 시각적 완성도는 미검증.

### 2-6. PC 가상 렌더러(VirtualOLED)의 상태 텍스트가 흰 블록으로만 보이던 문제 (해결됨)

- **증상**: `examples/output/`의 PNG에서 하단 상태 줄이 `MOVE`, `8.5` 같은
  글자가 아니라 속이 채워진 흰 사각형들로 렌더링됨.
- **원인**: 확인됨 — `tests/virtual_oled.py`의 `VirtualOLED.text()`가 애초에
  "글자당 속이 찬 사각형을 그린다"는 플레이스홀더 구현이었음(공백이 아닌
  문자는 전부 `fill_rect`). 실제 `framebuf.FrameBuffer.text()`가 쓰는
  비트맵 폰트를 흉내 낸 것이 아니었다 — 파일 상단 docstring에도 "NOT a
  pixel-accurate framebuf reimplementation"이라고 명시돼 있었다.
- **시도한 해결 방법**:
  - (채택) MicroPython 업스트림 GitHub 소스에서
    `extmod/font_petme128_8x8.h`(8×8 비트맵 폰트 테이블, 96글리프, MIT
    라이선스)와 `extmod/modframebuf.c`의 `framebuf_text()` 함수(정확한
    렌더링 알고리즘)를 `curl`로 직접 받아, 폰트 바이트 테이블과 렌더링
    알고리즘(컬럼 단위·LSB가 맨 위 픽셀인 비트 순서, 글자당 8px 폭,
    32~127 범위 밖 문자는 127번 글리프로 대체)을 `VirtualOLED.text()`에
    그대로 이식.
- **최종 해결**: `tests/virtual_oled.py`에 `FONT_8X8` 바이트 테이블과
  `framebuf_text()`와 동일한 픽셀 단위 알고리즘을 포팅. 출처(GitHub URL,
  MIT 라이선스, Damien P. George)를 코드 주석으로 명시.
- **검증 결과**: **소스 코드 레벨로 검증함** — upstream MicroPython이
  실제로 쓰는 폰트 바이트와 렌더링 알고리즘을 그대로 가져왔으므로, CanMV의
  `framebuf` 모듈이 이 upstream 코드를 수정 없이 그대로 포함한다는 전제
  하에서는 실제 패널과 일치한다. 다만 **CanMV 자체 C 소스를 직접 대조하지는
  못했고 실기기에서 눈으로 비교하지도 못했다**(실물 없음) — 이 전제의
  근거는 `framebuf.pyi` 스텁의 메서드/상수 표면이 upstream과 동일하다는
  점뿐이다(2-1 참고). 재생성한 PNG(`examples/output/*.png`,
  `*_native_128x64.png`)에서 `MOVE`/`DRAG`/`CLICK`/`STOP`/`8.5`/`H`/`-`
  글자가 육안으로 읽힘.

### 2-7. 손 관절 점이 3×3 사각형이라 너무 크고 서로 뭉쳐 보이던 문제 (해결됨)

- **증상**: `src/display_ui.py`의 `_draw_joint()`가 관절마다 3×3 채워진
  사각형을 그려서, 특히 손가락 끝처럼 관절끼리 가까운 구간에서 사각형들이
  서로 붙어 뭉쳐 보임. 연결선(`canvas.line()`)은 원래부터 굵기 조절 없는
  1px 선이라 이 문제와 무관했음.
- **원인**: 확인됨 — 애초에 단일 픽셀은 128×64 해상도의 6배 확대
  미리보기에서도 거의 안 보일 거라 판단해 3×3을 선택했는데, 실제로
  만들어보니 과했음.
- **시도한 해결 방법**: (채택) `fill_rect` 크기를 3×3 → 2×2로 축소. 완전한
  단일 픽셀(1×1)은 연결선과 구분이 안 될 것으로 판단해 선택하지 않음.
- **최종 해결**: `_draw_joint()`가 `fill_rect(x-1, y-1, 2, 2, 1)`로 2×2
  점을 그림 (화면 밖으로 안 나가게 클램핑은 그대로 유지).
- **검증 결과**: 재생성한 PNG에서 21개 관절점이 3×3 때보다 서로 분리돼
  보임(코드 레벨 테스트는 `test_hand_renderer.py`/`test_display_ui.py`
  그대로 29개 전부 통과, 점 크기 자체를 픽셀 단위로 검증하는 테스트는
  없음 — 육안 확인으로만 검증).

### 2-8. 손 스켈레톤이 화면에 비해 너무 작고 가늘게 보이던 문제 (해결됨)

- **증상**: 재생성한 PNG에서 손 스켈레톤이 128×64(스켈레톤 영역 128×54) 중
  세로는 거의 꽉 채우지만 가로 폭은 좁게만 쓰여, 화면 전체에 비해 작고
  가늘어 보임.
- **원인 분석**: 좌표 정규화 수식·확대 비율·테스트용 관절 데이터 세 후보
  중 하나씩 분리 확인함.
  - `hand_renderer.layout_skeleton()`의 정규화 수식 자체는 **원인이
    아님(확인됨)** — `scale = min(usable_w/span_x, usable_h/span_y)`로
    종횡비를 왜곡하지 않고 더 긴 축을 영역에 꽉 채우는 "contain" 방식의
    표준적인 비율 보존 확대이며, 의도대로 동작한다.
  - `SKELETON_MARGIN_PX=2`(여백)는 **원인이 아님(확인됨)** — 2px는
    128px/54px 기준으로 무시할 수준이며, 여백을 0으로 둬도 개선 폭은
    미미하다.
  - **실제 원인은 테스트용 관절 데이터(`examples/hand_demo.py`의
    `_open_hand()`)의 가로:세로 비율이었다(확인됨)**. 기존 손가락을 거의
    수직으로 편 좌표는 바운딩박스 비율이 `70:112 ≈ 0.62`(세로가 훨씬 긴
    모양)였는데, 스켈레톤 영역은 `124:50 ≈ 2.48`로 가로가 훨씬 넓은
    landscape다. `layout_skeleton()`이 종횡비를 지키며 두 축 중 더 작은
    배율(세로 기준)에 맞추다 보니, 세로는 50/50(100%)까지 채워도 가로는
    `32/124 ≈ 26%`만 채워진 것 — 수식이 아니라 입력 데이터의 모양이
    landscape 패널과 안 맞았던 것이 원인이다.
- **시도한 해결 방법**: (기각) `layout_skeleton()`에서 x/y 축을 다른
  배율로 늘리는 방식 — 손의 실제 비율을 왜곡하게 되어 사용자가 명시적으로
  요구한 "실제 손의 비율 유지"에 위배되므로 채택하지 않음. (채택)
  `_open_hand()`/`_fist_hand()`의 합성 좌표 자체를 더 옆으로 퍼진(손가락이
  바깥쪽으로 더 벌어지고, 엄지·새끼손가락이 더 옆으로 뻗은) 형태로 조정 —
  각 손가락 내부의 관절 간격·상대 비율은 그대로 두고, "손가락을 넓게 편"
  더 현실적인 포즈를 선택한 것이므로 왜곡이 아니다.
- **최종 해결**: `_open_hand()`의 바운딩박스 비율을 `0.62`에서 `1.23`으로,
  `_fist_hand()`를 `0.94`에서 `1.31`로 조정. 스켈레톤 영역(124×50 usable)
  기준 렌더 가로폭이 열린 손은 32px→62px, 주먹은 31px→66px로 약 2배
  커짐(세로는 두 경우 다 이미 50px로 최대치였으므로 변화 없음).
- **검증 결과**: 코드로 `hand_renderer.layout_skeleton()`의 실제 출력
  폭을 재계산해 수치로 확인함(위 32px→62px 등). 재생성한 PNG
  (`examples/output/01_open_hand_move_joint2*.png` 등)에서 손이 화면 가로
  방향으로 눈에 띄게 커짐을 육안으로도 확인. 다만 스켈레톤 영역의 landscape
  비율(2.48:1)과 일반적인 손 모양(펼쳐도 1.0~1.3:1 정도)의 구조적 차이
  때문에, 종횡비를 왜곡하지 않는 한 가로를 100% 채우는 것은 물리적으로
  불가능하다 — 이번 조정은 "가능한 범위에서 최대화"이지 "완전히 꽉 채움"은
  아니다.

### 2-9. `DisplayUI`에 `joint_size` 옵션 추가 (2×2 vs 3×3 비교 지원)

- **배경**: 사용자가 2×2(현재 기본값)와 3×3 관절 점 버전을 같은 손 데이터로
  나란히 비교해 보고 싶어함.
- **선택한 방법**: `_draw_joint()`에 하드코딩돼 있던 `2`를
  `DisplayUI.__init__(self, canvas, min_interval_ms=None, joint_size=2)`의
  인스턴스 속성으로 빼서, 같은 그리기 로직으로 점 크기만 바꿀 수 있게 함.
  기본값 2로 기존 동작과 100% 동일하게 유지.
- **검증 결과**: `examples/hand_demo.py`가 같은 열린 손 좌표를
  `joint_size=2`/`joint_size=3` 두 벌로 각각 렌더링해
  `01_open_hand_move_joint2*.png`/`01_open_hand_move_joint3*.png`로 저장.
  `display/` 단위 테스트 29개 그대로 통과(기존 테스트는 `joint_size`를
  지정하지 않으므로 기본값 2 경로를 계속 검증함).

## 3. 테스트 결과

### 3-1. 단위 테스트 (PC, 실기기 불필요)

```text
cd display && python3 -m unittest discover -s tests -v
```

29개 테스트 전부 통과 (`test_hand_renderer.py` 11개, `test_display_ui.py` 10개,
`test_oled_device.py` 8개). 주요 커버리지:

- `hand_renderer`: 빈/손상된 landmark 입력, 21개 전부 유효한 입력,
  화면 밖 극단 좌표의 클램핑, 종횡비 보존, 모든 landmark가 같은 점인
  퇴화 케이스, `firmware/ui.py`와 연결 리스트 동일성(고정 회귀 테스트).
- `display_ui`: 스로틀링(바로 재호출 시 미갱신, 간격 경과 후 갱신,
  `force=True`로 우회), canvas가 `None`일 때 안전한 no-op, canvas
  메서드가 예외를 던져도 `update()` 밖으로 전파되지 않음(섹션 9 요구사항).
- `oled_device`: `machine` 모듈이 아예 없을 때(플레인 CPython에서 실제로
  `ImportError`가 나는 경로 — 모킹 없이 진짜 조건), fake `machine`으로
  주소 발견/미발견/스캔 실패/FPIOA 에러 각각 `None`을 반환하고 예외를
  던지지 않는지.

### 3-2. PC 가상 화면 데모

```text
cd display && python3 examples/hand_demo.py
```

2-8 이후로는 PNG 수를 의도적으로 최소화해, 열린 손(`joint_size=2`/`3` 비교
2장) · 주먹(1장) · 손가락 모으는 동작 중간 프레임(1장) 총 4개 시나리오만
렌더링한다. 시나리오마다 6배 확대 PNG(`<name>.png`)와 실제 128×64 원본
해상도 PNG(`<name>_native_128x64.png`)를 함께 저장 — 총 8장을
`display/examples/output/`에 생성. 콘솔에 스로틀링 결과
(`now_ms=[0,10,20,30,150,160,300]` → `drew=[True, False, False, False,
True, False, True]`, 기대값과 일치)와 에러 처리(canvas 없음/예외 발생
모두 안전하게 처리됨) 확인 로그 출력(이 둘은 PNG를 생성하지 않는
콘솔 전용 점검). 확대/원본 해상도 둘 다 직접 육안 확인한 결과: 스켈레톤이
2-8의 수정 이후 화면 가로 방향으로도 눈에 띄게 커졌고, 하단에 상태 줄이
구분되는 레이아웃이 목업과 같은 방향임을 확인(상세 텍스트
내용은 위 2-4 참고), 상태 텍스트가 실제 글자(`MOVE`/`DRAG`/`CLICK`/
`STOP`/`8.5`/`H`/`-`)로 128×64 원본 해상도에서도 읽힘(2-6), 관절점이
2×2로 줄어 서로 분리돼 보임(2-7).

### 3-3. 보드 테스트 (이 문서 작성 시점 기준 — 이후 2026-10-26에 완료됨)

이 문서의 위 내용은 전부 VLT-OL016 실물이 없던 **독립 개발 세션 기준**으로
작성됐다. 당시엔 `examples/oled_basic_test.py`를 작성만 했고 한 번도
실행하지 못했다.

**이후 실제 보드 테스트는 완료됐다** — 2026-10-26, 실제 VLT-OL016을
K230D-Zero에 연결해 bring-up부터 `DisplayUI`를 실제 AI 추론 루프에 연결하는
것까지 전부 실기기로 확인됐다(`README.md` 7절 "실제 OLED 연결 후 실행 순서",
`docs/DEV_HISTORY.md` 4-3). 아래 "남은 질문"은 그 결과로 대부분 해소됐다.

## 4. 남은 질문 (작성 당시 기준) 및 실제 결과

1. `i2c.scan()`에서 실제로 주소가 잡히는가 — **해결**: `0x3C` 하나로 잡힘,
   `config.OLED_I2C_ADDR`와 추가 수정 없이 일치(`README.md` 1절).
2. 주소가 잡히는데 화면이 안 나오면 초기화 시퀀스 불일치 가능성 —
   **해당 없음**: 기본 `firmware/ssd1306.py` 초기화 시퀀스 그대로 화면
   출력까지 정상 확인됨(`README.md` 7절), 분리 진단이 필요하지 않았다.
3. `machine.I2C.writevto()`가 upstream이 기대하는 단일 START/STOP 다중
   버퍼 전송으로 동작하는지 — **간접 확인됨, 저수준 프로토콜 자체는
   미확인**: 화면이 정상 출력되는 것으로 보아 실질적으로는 문제없이
   동작하지만, 버스 레벨(logic analyzer 등)로 START/STOP 경계를 직접
   확인한 적은 없다(`README.md` 8절 "알려진 제약" 참고).
