---
id: causal-0003
type: causal
indicators: [DXY, USDKRW]
sectors: [반도체, 자동차]
market: [KR]
direction: 강달러 → 한국 수출주 (양면적)
confidence: med
lead_lag: leading
lag_window: "1~2개월"
lag_estimated_on: 2022-12-31
lag_method: "2022 국면 관찰(환율 단가효과 vs 수요둔화 상쇄). ※개발 단계 최근 6개월 ECOS/yfinance 교차상관 재추정 필요"
period_examples: [2022-H2, 2014-2015]
sources:
  - title: "South Korean Won — Historical Data"
    url: "https://tradingeconomics.com/south-korea/currency"
  - title: "2022 stock market decline"
    url: "https://en.wikipedia.org/wiki/2022_stock_market_decline"
---
## 인과 명제
강달러(DXY 상승, 원/달러 상승)는 원화 환산 단가 개선으로 한국 수출 섹터(반도체·자동차)에 **단기·부분적으로 우호적**일 수 있다. 그러나 강달러가 **글로벌 수요 둔화·긴축**과 동반될 때는 수요 위축이 단가효과를 압도해 수출·실적이 악화되고 외국인 자금 유출로 주가는 약세가 된다. 즉 부호는 동반 매크로 국면에 의존한다(조건부).

## 메커니즘
- (+) 달러↑/원화↓ → 수출 단가 원화환산↑ → 마진 개선(단가 채널).
- (−) 달러↑가 글로벌 긴축·수요둔화 신호일 때 → IT·내구재 수요↓ → 수출물량↓ → 실적↓ + 외국인 순매도 → 주가↓(수요·자금 채널).
- 순효과 = 단가효과 − 수요효과. 침체 동반 시 음(−)이 우세.

## 시차(리드/래그)
- DXY/원화는 한국 수출주에 약 **1~2개월 선행**(환율·수요 신호가 실적·주가에 시차를 두고 반영).
- 추정 근거: 2022 H2 원/달러 ~1,440원(13년 최저권)과 동시에 반도체 수출 YoY 둔화·전환, 코스피 약세.
- 한계: 단가효과와 수요효과가 상쇄해 부호가 국면별로 바뀜 → confidence med. 최근 6개월 재추정 필수.

## 과거 사례 근거
- 2022 H2: 강달러+수요둔화 동반 → 단가효과를 수요둔화가 압도, 반도체 사이클 하강(`cases/2022_금리인상_강달러.md`).

## 반례 / 한계
- 수요가 견조한 약달러→강달러 초기 국면에서는 단가효과로 수출주 우호 사례 존재(부호 반전).
- 반도체는 메모리 가격 사이클 자체가 강한 독립변수 → 환율 단독 해석 금지.
