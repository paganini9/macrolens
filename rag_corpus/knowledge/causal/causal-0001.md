---
id: causal-0001
type: causal
indicators: [FFR, US10Y]
sectors: [성장주, 반도체, 2차전지]
market: [US, KR]
direction: 금리 상승 → 성장주·반도체 약세
confidence: high
lead_lag: coincident
lag_window: "0~1개월(가격), 3~6개월(실적)"
lag_estimated_on: 2022-12-31
lag_method: "2022 국면 타임라인 관찰(가격 동행, 펀더멘털 후행). ※개발 단계에서 최근 6개월 FRED/yfinance 교차상관으로 재추정 필요"
period_examples: [2022-H1, 2022-H2]
sources:
  - title: "2022 stock market decline"
    url: "https://en.wikipedia.org/wiki/2022_stock_market_decline"
  - title: "Chart: The Most Aggressive Tightening Cycle in Decades"
    url: "https://www.statista.com/chart/28437/interest-rate-hikes-in-past-tightening-cycles/"
---
## 인과 명제
정책금리(FFR)·장기금리(US10Y) 상승은 할인율을 높여 장기 현금흐름 비중이 큰 **성장주·반도체** 밸류에이션을 압박한다. 가격은 거의 동행해 반응하나, 반도체는 업황(수요·재고) 둔화가 더해질 때 실적이 수개월 후행해 추가 약세로 이어질 수 있다. (조건부: 인하 전환·완화 기대 시 동일 메커니즘이 반대로 작동.)

## 메커니즘
금리↑ → 미래현금흐름 할인율↑ → 듀레이션 긴 자산 현재가치↓(성장주·반도체) → (반도체) 수요 둔화·재고조정 동반 시 실적↓ → 추가 디레이팅.

## 시차(리드/래그)
- 가격: **동행~1개월 이내**(밸류에이션 즉시 반영).
- 실적/업황: **약 3~6개월 후행**(메모리 가격·수출에 시차).
- 추정 근거: 2022년 금리 급등 구간에서 나스닥 -33.1%·SOX 약 -35%가 가격에 빠르게 반영된 반면, 한국 반도체 수출 YoY 둔화는 하반기로 갈수록 심화.
- 한계: 단일 국면 관찰. 시차는 국면 의존적 → 개발 단계에서 최근 6개월 데이터로 교차상관 재추정.

## 과거 사례 근거
- 2022 H1~H2: FFR +425bp, US10Y 급등 → 나스닥 -33.1%, SOX ~-35%(`cases/2022_금리인상_강달러.md`).

## 반례 / 한계
- 2023~24 AI 랠리: 금리가 높게 유지됐음에도 반도체(엔비디아 등)는 강세 — **실적 모멘텀(AI 수요)이 금리 역풍을 압도**한 사례. 금리는 필요조건이 아니며, 수요 사이클과 함께 봐야 함(백로그 #6과 연계).
