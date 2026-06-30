---
id: causal-0014
type: causal
indicators: [M2, FFR]
sectors: [코인]
market: [CRYPTO]
direction: 글로벌 유동성(M2) 확장 → 코인·위험자산 강세
confidence: med
lead_lag: leading
lag_window: "1~3개월(유동성 전이)"
lag_method: "유동성 사이클이 고베타 위험자산에 선행 전이되는 일반 관찰(정성)"
sources:
  - title: "Money Supply M2 (FRED, M2SL)"
    url: "https://fred.stlouisfed.org/series/M2SL"
  - title: "Money Supply (Investopedia)"
    url: "https://www.investopedia.com/terms/m/moneysupply.asp"
---
## 인과 명제
광의통화(M2)·글로벌 유동성의 확장은 위험자산 중 가장 유동성 민감도가 높은 **코인**에 선행적으로 우호적이다. 유동성이 풍부해지면 무수익·고베타 자산으로 자금이 흘러 코인 수요가 늘고, 반대로 긴축·유동성 축소기에는 가장 먼저·크게 빠진다.

## 메커니즘
유동성↑(M2↑·QE·완화) → 무위험수익 기회비용↓·위험선호↑ → 고베타 자산(코인) 수요↑. 긴축 시 역방향으로 선행 하락.

## 시차(리드/래그)
- 유동성 변화에 **약 1~3개월 선행** 반응(코인이 주식보다 빠름).
- 한계: 코인 고유 이벤트(ETF·규제·반감기)가 유동성 효과를 압도하는 구간 존재.

## 반례 / 한계
- 유동성이 풍부해도 코인 자체 신뢰위기(거래소 사고)면 하락 — 거시만으로 방향 단정 금지.
- M2 정의·집계 시차가 있어 실시간 신호로는 한계.
