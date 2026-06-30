---
id: causal-0002
type: causal
indicators: [DXY, FFR]
sectors: [코인]
market: [CRYPTO]
direction: 강달러·긴축(유동성 축소) → 코인 약세
confidence: high
lead_lag: leading
lag_window: "0~4주"
lag_estimated_on: 2022-12-31
lag_method: "2022 국면 관찰(유동성 민감 자산 선행 반응). ※개발 단계 최근 6개월 교차상관 재추정 필요"
period_examples: [2022-H1, 2022-H2]
sources:
  - title: "From $250,000 to $10,000 price calls: how market watchers got it wrong with bitcoin in 2022"
    url: "https://www.cnbc.com/2022/12/23/bitcoin-price-calls-in-2022-how-the-market-got-it-wrong.html"
  - title: "U.S. dollar index (DXY) historical data 1973-2026"
    url: "https://www.statista.com/statistics/1404145/us-dollar-index-historical-chart/"
---
## 인과 명제
금리 인상·QT로 인한 **유동성 축소와 강달러(DXY 상승)**는 위험자산 중 가장 투기적·고듀레이션인 **코인**을 빠르게 압박한다. 코인은 유동성 민감도가 높아 주식보다 선행적으로 반응하며, 레버리지 누적 시 긴축 후반에 연쇄 청산으로 낙폭이 증폭된다.

## 메커니즘
유동성↓·실질금리↑ → 무수익 위험자산 기회비용↑ → 코인 수요↓ → (레버리지·스테이블코인 페그·CeFi 취약성) → 강제청산·신뢰위기 증폭.

## 시차(리드/래그)
- **선행 0~4주**: DXY·실질금리 상승에 코인이 주식보다 먼저·크게 반응.
- 추정 근거: 2022년 BTC $47k→$16k(약 -64%), 금리/유동성 충격이 LUNA·3AC·FTX 사고로 증폭.
- 한계: 코인 자체 사고(FTX 등)와 거시 효과가 혼재 → 순수 거시 시차 분리 어려움. 재추정 필요.

## 과거 사례 근거
- 2022: 긴축·강달러 구간에서 BTC 약 -64%, 위험자산 중 최대 낙폭(`cases/2022_금리인상_강달러.md`).

## 반례 / 한계
- 코인 고유 이벤트(규제·ETF 승인·반감기)가 거시를 압도하는 구간 존재 → 거시만으로 방향 단정 금지.
- 강달러가 완화로 전환(2022.10~) 시 코인도 선행 반등 신호.
