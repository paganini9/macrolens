---
id: causal-0017
type: causal
indicators: [US10Y, CPI]
sectors: [코인, AI/SW]
market: [US, CRYPTO]
direction: 실질금리 상승 → 무수익·고듀레이션 자산 압박
confidence: high
lead_lag: coincident
lag_window: "0~1개월(밸류·가격)"
lag_method: "실질금리=명목-기대인플레가 무수익자산 기회비용을 결정하는 일반 원리(정성)"
sources:
  - title: "10-Year TIPS Real Yield (FRED, DFII10)"
    url: "https://fred.stlouisfed.org/series/DFII10"
  - title: "Real interest rate (Investopedia)"
    url: "https://www.investopedia.com/terms/r/realinterestrate.asp"
---
## 인과 명제
실질금리(명목금리 − 기대인플레)의 상승은 이자·배당이 없는 자산의 보유 기회비용을 키워, 무수익 위험자산인 **코인**과 먼 미래 현금흐름에 의존하는 **AI/SW** 성장주를 동시에 압박한다. 실질금리는 명목금리보다 위험자산 밸류에이션을 더 정밀하게 설명하는 변수다.

## 메커니즘
실질금리↑ → 무수익자산 보유 기회비용↑(코인) + 성장주 할인율↑(AI/SW) → 두 자산군 동반 디레이팅. 실질금리↓ 시 반대로 우호.

## 시차(리드/래그)
- 가격·밸류에이션에 **거의 동행~1개월** 반영.
- 한계: 기대인플레 측정(BEI)·실질금리 추정에 노이즈, 위험선호 변동과 분리 어려움.

## 반례 / 한계
- 실적 모멘텀(AI 수요)이 강하면 실질금리 상승에도 성장주가 버틴다.
- 코인은 ETF 자금·규제 등 고유 변수가 실질금리 효과를 압도하는 구간 존재.
