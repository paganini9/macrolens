---
id: causal-0016
type: causal
indicators: [US2Y, US10Y]
sectors: [반도체, 자동차]
market: [US, KR]
direction: 장단기 금리 역전 → 경기침체 선행 신호 → 경기민감 섹터 부담
confidence: med
lead_lag: leading
lag_window: "6~18개월(침체 전이)"
lag_method: "수익률곡선 역전-침체 선행성에 관한 일반 관찰(정성). 시차는 국면별 변동 큼"
sources:
  - title: "Inverted yield curve (Wikipedia)"
    url: "https://en.wikipedia.org/wiki/Inverted_yield_curve"
  - title: "10Y-2Y Treasury Spread (FRED, T10Y2Y)"
    url: "https://fred.stlouisfed.org/series/T10Y2Y"
---
## 인과 명제
미 국채 장단기(10년-2년) 금리의 역전은 역사적으로 경기침체를 선행해온 신호로, 침체 우려가 현실화되면 수요 사이클에 민감한 **반도체·자동차** 등 경기민감 섹터의 이익 추정에 하방 압력을 준다. 다만 역전과 침체 사이 시차가 길고 가변적이어서 타이밍 신호로는 불확실하다.

## 메커니즘
단기금리↑(긴축)·장기금리 상대적 안정 → 곡선 역전 → 미래 성장·인플레 둔화 기대 → 경기민감 수요(IT·내구재) 둔화 우려 → 반도체·자동차 이익 추정↓.

## 시차(리드/래그)
- 역전에서 침체까지 **약 6~18개월**의 긴 선행(시점 불확실성 큼).
- 한계: 역전이 항상 침체로 이어지지는 않으며(거짓신호), 시차가 매번 다름.

## 반례 / 한계
- 곡선 정상화 과정(역전 해소)이 오히려 침체 임박 신호인 경우도 있어 단일 해석 위험.
- AI 등 구조적 수요가 강하면 경기 둔화에도 반도체가 차별적으로 강세일 수 있다.
