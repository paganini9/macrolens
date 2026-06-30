---
id: causal-0007
type: causal
indicators: [WTI, BRENT, CPI]
sectors: [에너지/화학, 자동차]
market: [US, KR]
direction: 유가 상승 → 헤드라인 인플레↑ → 긴축압력·실질소득 위축
confidence: med
lead_lag: leading
lag_window: "1~3개월(물가 전이), 3~6개월(소비)"
lag_method: "에너지가 CPI 바스켓에 직접 반영되는 경로 기반 일반 메커니즘(정성)"
sources:
  - title: "Consumer Price Index (BLS)"
    url: "https://www.bls.gov/cpi/"
  - title: "Oil price and inflation (Investopedia)"
    url: "https://www.investopedia.com/articles/economics/08/oil-prices-inflation.asp"
---
## 인과 명제
유가(WTI·Brent) 상승은 에너지가 직접 포함된 **헤드라인 CPI**를 끌어올려 통화긴축 압력을 강화하고, 휘발유·운송비 상승으로 가계 실질소득을 위축시켜 **자동차** 등 내구재 수요에 부담을 준다. 에너지/화학 일부 업종에는 직접 수혜이나 거시 전이로는 위험요인이다.

## 메커니즘
유가↑ → 헤드라인 인플레↑ → (연준 매파 압력↑ → 금리·할인율↑) + (가처분소득↓ → 내구재·자동차 수요↓). 2차 효과로 운송·물류 원가 전반 상승.

## 시차(리드/래그)
- 물가 전이는 **1~3개월 선행**, 소비 위축은 **3~6개월** 시차.
- 한계: 코어(에너지·식품 제외) 인플레에는 직접 반영 안 됨 → 연준 반응은 코어 추세에 더 의존.

## 반례 / 한계
- 공급 충격(지정학)發 유가 상승은 일시적일 수 있어 연준이 '룩스루(look-through)'하기도 한다.
- 산유국·에너지 수출 비중이 큰 경제에서는 교역조건 개선으로 효과가 달라진다.
