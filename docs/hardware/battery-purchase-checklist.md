# EdgeGlass-AI 배터리 구매 체크리스트

확인일: 2026-10-26  
기준: 대학교 발표 시제품. 전체 기능 동시 실행에서 **실측한 5 V/약 0.43 A**를 기준으로 몇 분간 정상 시연하는 것을 목표로 한다.

## 확정 구매 판단

**`DFR1026 + DTP103450 + SZH-EK026` 구성을 주문한다.** DFR1026은 시연 중 5 V 승압 출력만 담당하고, 배터리는 분리하여 SZH-EK026으로 충전한다.

K230D-Zero의 5 V/2 A는 권장 입력 사양이며 실제 소비전류 2 A가 아니다. 실측 부하 2.15 W를 낮은 배터리 전압 3.0 V와 보수적 승압 효율 85%로 환산하면 배터리 전류는 약 **0.84 A**다. 이전 문서의 5 V/0.6 A 및 1.18 A는 실측이 아닌 여유 가정이므로 구매 탈락 기준으로 쓰지 않는다.

## 커넥터 확정

동일 DTP103450 판매 페이지에는 Molex PicoBlade `51021-0200` 1.25 mm 2핀 리셉터클이 표기되어 있다. 여기에 **Molex `53047-0210` ×2**를 쓴다. 하나는 DFR1026용, 하나는 TP4056용이다. 배터리를 둘 중 하나에만 꽂아 시연과 충전을 전환한다.

`53047-0210` 공개 정격은 1 A이며 실측 부하 기반 약 0.84 A는 이 범위 안이다. PCB 헤더 핀에는 전선을 길게 매달지 않고, DFR1026/TP4056 패드에 최대한 짧게 납땜한 뒤 열수축튜브·캡톤테이프·케이스로 움직임을 막는다. 시연 중 커넥터가 따뜻해지거나 접촉이 느슨하면 즉시 전원을 끈다.

극성은 수령 후 멀티미터로 확인한다. 확인한 양극·음극을 각각 DFR1026 `BAT`/GND 및 TP4056 `BAT+`/`BAT−`에 연결한다.

## 지금 주문할 부품

| 품목 | 모델·수량 | 구매 링크 | VAT 포함 가격 | 용도 |
| --- | --- | --- | ---: | --- |
| 보호 Li-Po | DTP103450 3.7 V 1,800 mAh ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/view?no=12710302) | 7,150원 | 시연용 단일 셀 배터리. 보호회로 포함. |
| 충전 모듈 | SZH-EK026 TP4056 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/view?no=1278836) | 770원 | Micro-USB 분리 충전기. |
| 배터리 짝커넥터 | Molex 53047-0210 ×2 | [레고전자](https://regoelec.edenstore.co.kr/shop/item.php?ca_id=101010&it_id=1569296884) | 결제 전 확인 | DFR1026용 1개, TP4056용 1개. |
| 충전 설정 저항 | 1.5 kΩ 0603, AR03BTC1501 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=00030001&code=0024&display_style=lattice_a&iframe=&popup=&setMode=mobile&sort=review) | 170원 | TP4056을 약 0.78 A로 설정. |
| K230 전원 케이블 | USB-A→USB-C 1 m, MO-CB-055 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=00110002&code=0878&iframe=&popup=&sort=low_price) | 1,210원 | USB-A 끝을 잘라 DFR1026 출력에 납땜하고 USB-C 끝을 K230에 연결. |
| 충전 케이블 | Micro USB 5P Cable 1 m ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/view?no=32695) | 770원 | SZH-EK026 충전 입력. |
| 배터리 하네스선 | 26 AWG 적색·흑색 연선, 각 10 cm 이상 ×1식 | 전자부품점 소량 판매품 | 판매처별 확인 | 53047-0210과 DFR1026/TP4056을 각각 짧게 연결. |
| 열수축튜브 | 2 mm 적색·12 mm 흑색, 각 1 m ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?code=0315&iframe=&page=27&popup=&setMode=mobile) | 800원 | 커넥터·케이블 납땜부 절연. |
| 절연 테이프 | Kapton 10 mm, BB781 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=0017&code=0315) | 2,300원 | 기판·배터리와 금속 프레임 사이 절연. |
| 케이블타이 | T6833 ×1봉 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=0016&code=0315&display_style=lattice_b&iframe=&page=31&popup=&sort=review) | 1,400원 | 케이블 인장완화·후두부 케이스 고정. |

디바이스마트 표기 가격은 **14,570원**이고 기본 배송비 2,700원을 더하면 **17,270원**이다. 53047-0210 두 개와 26 AWG 짧은 전선의 판매가·배송비만 결제 전 더한다. 보유 DFR1026와 USB 전력계는 제외했다.

### 없으면 함께 준비할 것

- 온도조절 납땜인두와 미세 팁, 납, 플럭스, 핀셋, 납제거 심지
- 멀티미터, 와이어 스트리퍼/절단기, 확대경
- 배터리·두 기판을 넣는 비전도성 케이스 또는 후두부 스트랩 파우치

배터리는 안경 다리에 붙이지 않고 후두부 케이스/스트랩에 넣는다.

## 수령 후 점검

1. 배터리 피복·보호회로에 팽창·손상·냄새가 없는지 확인한다.
2. 플러그가 1.25 mm 2핀이고 53047-0210에 정상 체결되는지 확인한다.
3. 멀티미터로 배터리 플러그 양극·음극을 확인해 표시한다.
4. SZH-EK026의 Micro-USB, `BAT+`, `BAT−`, `122` 저항을 확인한다.
5. `122`가 0603일 때만 1.5 kΩ 0603으로 바꾼다. 다르면 같은 크기의 1.5 kΩ 저항을 준비한다.
6. 잘라낸 USB-A→USB-C 케이블의 적색(VBUS)·흑색(GND)을 멀티미터로 확인한다.

## 근거

- [DFRobot DFR1026 공식 사양](https://www.dfrobot.com/product-2632.html)
- [DTP103450 사양서](https://biakom.com/pdf/DTP103450-1800mah-En-1.0V.doc.pdf)
- [동일 DTP103450의 51021-0200 표기](https://www.devicemart.co.kr/goods/view?no=15285794)
- [Molex PicoBlade 시스템 사양](https://www.content.molex.com/dxresources/e24c/e24ca95a-11dc-46d6-be7b-592110a37b66.pdf)
- [SZH-EK026 충전전류 설정표](https://www.devicemart.co.kr/goods/view_contents?no=1278836&setMode=pc&zoom=1)
