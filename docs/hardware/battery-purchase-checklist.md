# EdgeGlass-AI 배터리 구매 전 체크리스트

확인일: 2026-10-26  
대상: K230D-Zero + DFR1026 + 1S 보호 Li-Po, 짧은 시연용

## 주문 결론

**현재 제시된 세 제품만으로는 안전한 완성 조립을 시작할 수 없다.** 특히 `Molex 53047-0210`은 배터리 플러그와 물리적으로 맞을 수 있으나, 공개 부품 정격이 1 A라 이 프로젝트의 보수 설계 배터리 전류 1.18 A 및 셀의 1.8 A 조건을 만족한다고 확정할 수 없다. PCB용 헤더를 전선에 공중 납땜하는 방식도 제조사 용도가 아니다.

따라서 이 문서는 다음 세 등급으로 분류한다.

| 등급 | 뜻 | 현재 품목 |
| --- | --- | --- |
| 구매 가능 | 사양·용도가 확인되어 지금 주문해도 됨 | SZH-EK026, 1.5 kΩ 저항, 절연·고정 소모품 |
| 조건부 구매 | 수령품 또는 판매자 문서 확인 후에만 다음 단계 진행 | DTP103450, USB-A 출력 하네스 |
| 구매 보류 | 설계 조건에 맞지 않거나 필요한 정보가 없음 | 53047-0210을 배터리 하네스로 쓰는 구성 |

이 상태에서는 “배송 후 바로 완성 조립”이라고 약속할 수 없다. A 등급으로 올리려면 DTP103450 공급처가 **출고 리드 AWG, 커넥터 품번, 커넥터를 포함한 연속 1.8 A 정격**을 문서로 제공하거나, 처음부터 2 A 이상 정격 커넥터·리드가 달린 보호 Li-Po 팩으로 바꿔야 한다.

## 제시된 세 제품 검증

| 품목 | 확인 결과 | 판정 |
| --- | --- | --- |
| [DTP103450 3.7 V 1,800 mAh](https://www.devicemart.co.kr/goods/view?no=12710302) | 7,150원(VAT 포함), KC 인증, 3.7 V/1,800 mAh. 같은 모델의 다른 판매 페이지는 `Molex 51021-0200`, 1.25 mm 2핀, 500 mm 리드를 표기하지만, 이 판매 페이지 자체는 출고 커넥터 품번·AWG를 공개하지 않는다. | 조건부 구매 |
| [SZH-EK026](https://www.devicemart.co.kr/goods/view?no=1278836) | 770원(VAT 포함), Micro-USB 5 V 입력, TP4056, BAT+/BAT−, 기본 1 A이고 RPROG 변경 가능. | 구매 가능 |
| [Molex 53047-0210](https://regoelec.edenstore.co.kr/shop/item.php?ca_id=101010&it_id=1569296884) | 1.25 mm 2회로 PicoBlade 수직 THT PCB 헤더. 51021-0200과 맞지만 공개 정격 1 A이며 PCB 장착품이다. | 구매 보류 |

### 커넥터 전류 검증

Molex의 최신 PicoBlade 시스템 자료는 2회로·26 AWG에서 2.5 A라는 **열상승 참고값**을 제시하지만, 이는 30°C 온도 상승 한계, 모든 회로 통전, PCB 패턴 조건에서의 참고값이다. 별도의 제품 시리즈 사양은 53047-0210을 1 A로 표시한다. DTP103450의 실제 출고 리드 AWG·단자·PCB 패턴 조건은 공개되지 않았다. 그러므로 참고값을 적용하여 1.18 A 또는 1.8 A를 보증할 수 없다.

- [Molex PicoBlade 51021 제품 사양](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/productspecificationpdf/510/51021/510211006-PS-000.pdf)
- [Molex PicoBlade 시스템 데이터시트](https://www.content.molex.com/dxresources/e24c/e24ca95a-11dc-46d6-be7b-592110a37b66.pdf)
- [Molex 53047 시리즈 공식 페이지](https://www.molex.com/en-us/products/series-chart/53047)

## 구매 목록

### 1. 지금 주문 가능한 공통 부품

| 품목 | 모델·수량 | 판매처·링크 | VAT 포함 가격 | 필요한 이유 |
| --- | --- | --- | ---: | --- |
| 충전 모듈 | SZH-EK026 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/view?no=1278836) | 770원 | 1셀 Li-Po를 DFR1026과 분리해 충전한다. |
| RPROG 저항 | 1.5 kΩ, 0603, AR03BTC1501 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=00030001&code=0024&display_style=lattice_a&iframe=&popup=&setMode=mobile&sort=review) | 170원 | 수령 모듈의 `122`가 0603임을 확인한 경우에만 0.78 A로 변경한다. |
| 열수축튜브 | 2 mm 적색 1 m ×1, 12 mm 흑색 1 m ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?code=0315&iframe=&page=27&popup=&setMode=mobile) | 800원 | 각 납땜부와 하네스 인장완화 절연. |
| 절연 테이프 | Kapton 10 mm, BB781 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=0017&code=0315) | 2,300원 | 배터리·기판과 금속부 사이 절연. |
| 케이블타이 | T6833, 100 mm ×2.5 mm ×1봉 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=0016&code=0315&display_style=lattice_b&iframe=&page=31&popup=&sort=review) | 1,400원 | 케이블 인장완화와 케이스 고정. |
| 출력 하네스 | Adafruit USB-A Jack Breakout Cable 30 cm, ada-4449 ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=00110002&code=0118) | 3,600원 | DFR1026 출력에 USB-A 암 단자를 만든다. 정격 미공개라 실제 부하 시험 조건이다. |
| USB 케이블 | Coms ID534 USB-A→USB-C 3 A ×1 | [디바이스마트](https://www.devicemart.co.kr/goods/brand?category_code=00110002&code=0315&display_style=lattice_b&iframe=&page=3&popup=&sort=popular_sales) | 6,000원 | K230D-Zero USB-C 입력에 5 V를 공급한다. |
| 전선 | 22 AWG 적색·흑색 연선, 각 0.5 m 이상 ×1식 | 국내 전자부품 판매처에서 소량 구매 | 가격 미확정 | DFR1026 출력부와 기판 간 배선. 소량 판매처·가격을 확인할 수 없어 구매 확정 가격에는 넣지 않는다. |
| 케이스 | 내부 최소 70×45×15 mm, 비전도성 난연 케이스 ×1 | 현물 치수 대조 후 구매 | 가격 미확정 | 배터리를 압박·마찰·피부 접촉으로부터 보호한다. |

디바이스마트의 위 가격 확정 품목은 부가세 포함 **15,040원**(770+170+800+2,300+1,400+3,600+6,000)이고, 기본 묶음배송 2,700원을 더하면 **17,740원**이다. 이것은 배터리, 전선, 케이스를 제외한 금액이다.

### 2. 전원부 조건부 품목

| 품목 | 수량 | 가격 | 주문 조건 |
| --- | ---: | ---: | --- |
| DTP103450 보호 Li-Po | 1 | 7,150원(VAT 포함) | 판매자에게 출고 리드 AWG와 커넥터를 포함한 1.8 A 연속 방전 허용 여부를 서면으로 확인한 뒤 주문한다. |
| 배터리용 하네스 2개 | 방전용 1, 충전용 1 | 미확정 | 배터리의 실제 커넥터·전류 정격 확인 후에만 선택한다. 배터리는 DFR1026와 TP4056 중 한 하네스에만 연결할 수 있어야 한다. |
| Micro-USB 충전 케이블 | 1 | 미확정 | SZH-EK026 충전 입력용. 5 V USB 전원과 함께 필요하다. |

**모든 부품을 신규 구매하는 최종 총액은 확정할 수 없다.** 안전 조건을 만족하는 배터리 하네스와 케이스·전선의 실제 판매품이 아직 확정되지 않았기 때문이다. 확인된 부품만 합산하면 배터리까지 24,890원(17,740+7,150)으로 이미 2만원을 넘고, 전선·케이스·충전 케이블은 추가다. 따라서 예산보다 전기적 안전성을 우선해야 한다.

이미 보유한 DFR1026, USB 전력계, USB 전원 어댑터, Micro-USB 케이블, USB-A→USB-C 3 A 케이블, 22 AWG 전선, 절연재, 케이스, 납땜 공구를 모두 제외할 수 있는 경우에만, 배터리·충전모듈·저항의 소계와 배송비는 **10,790원**이다. 단, 이 금액은 배터리 하네스가 확정되지 않았으므로 주문 확정 총액이 아니다.

## 반드시 새로 준비할 공구·소모품

보유 여부를 확인할 수 없으므로 아래는 모두 준비물이다. 보유하면 구매 목록에서 제외할 수 있다.

- 온도조절 납땜인두와 미세 팁, 60/40 또는 무연 납, 플럭스, 납제거 심지
- ESD 핀셋, 확대경 또는 현미경, 와이어 스트리퍼, 절단기
- 멀티미터(전압·저항·도통 측정), 이미 보유한 USB 전력계
- 5 V USB 전원 어댑터와 Micro-USB 충전 케이블
- 22 AWG 적·흑 연선, 열수축튜브, 캡톤테이프, 케이블타이, 비전도성 케이스
- 배터리를 후두부 밴드/뒤쪽 케이스에 고정할 벨크로 또는 스트랩

DFR1026은 `KEY` 패드로 출력을 제어하므로 별도 전원 스위치는 필수가 아니다. `KEY`와 출력 GND 사이에는 유지형 스위치가 아니라 순간누름(normal-open) 버튼만 사용한다.

## 주문·수령 게이트

1. **주문 전:** DTP103450 판매자에게 리드 AWG, 장착 커넥터 품번, 커넥터 포함 1.8 A 연속 방전 허용 여부를 문의한다. 답이 없으면 배터리·헤더 구성은 구매 보류다.
2. **수령 직후:** 배터리 팩 표기, 보호회로, 커넥터 피치·품번, 리드 굵기, 팽창·피복 손상을 확인한다. 커넥터 극성은 멀티미터로 확인 전까지 표시하지 않는다.
3. **충전기 수령 후:** `122` RPROG 저항의 실제 패키지가 0603인지 확인한다. 다르면 AR03BTC1501을 납땜하지 않는다.
4. **출력 하네스 수령 후:** USB-A 암 브레이크아웃의 적색/흑색 리드를 도통 측정해 VBUS/GND로 확인한다. 색상만으로 판단하지 않는다.
5. 위 항목 중 하나라도 불일치하면 조립을 중지하고 해당 부품을 바꾼다.

## 근거

- [DTP103450 셀 사양서](https://biakom.com/pdf/DTP103450-1800mah-En-1.0V.doc.pdf): 1C=1.8 A 충·방전, 4.2 V 충전, 3.0 V 방전 종료, 38.5 g 미만.
- [DTP103450 KC 자료](https://m.eleparts.co.kr/data/goods_attach/202007/good-pdf-5980400-1.pdf): DTP103450 보호회로 사진·인증 대상.
- [동일 모델의 커넥터 표기 판매 페이지](https://www.devicemart.co.kr/goods/view?no=15285794): Molex 51021-0200, 1.25 mm 2핀 표기.
- [SZH-EK026 사양·RPROG 설정표](https://www.devicemart.co.kr/goods/view_contents?no=1278836&setMode=pc&zoom=1)
- [TP4056 데이터시트](https://evelta.com/content/datasheets/482-TP4056.pdf)
