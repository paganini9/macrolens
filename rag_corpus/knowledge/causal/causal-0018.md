---
id: causal-0018
type: causal
indicators: [AI_CAPEX, SOX]
sectors: [반도체, AI/SW, 에너지/화학]
market: [US, KR]
direction: AI 캐펙스(설비투자) 확대 → 반도체·전력 수요 견인
confidence: med
lead_lag: leading
lag_window: "1~3분기(수주·실적 반영)"
lag_method: "하이퍼스케일러 캐펙스 가이던스가 반도체 수주에 선행하는 일반 관찰(정성)"
sources:
  - title: "AI boom (Wikipedia)"
    url: "https://en.wikipedia.org/wiki/AI_boom"
  - title: "Data centres and data transmission networks (IEA)"
    url: "https://www.iea.org/energy-system/buildings/data-centres-and-data-transmission-networks"
---
## 인과 명제
빅테크·하이퍼스케일러의 AI 설비투자(캐펙스) 확대는 AI 가속기·HBM·첨단공정 수요를 끌어올려 **반도체·AI/SW**에 우호적이며, 데이터센터 전력 수요 증가를 통해 **에너지/화학**(전력·인프라) 수요에도 파급된다. 금리와 무관하게 작동하는 구조적 수요 사이클이라는 점이 특징이다.

## 메커니즘
AI 캐펙스 가이던스↑ → 가속기·HBM·장비 발주↑ → 반도체 수주·실적↑ + 데이터센터 전력수요↑ → 발전·전력기기·에너지 수요↑.

## 시차(리드/래그)
- 캐펙스 발표는 반도체 수주·실적에 **약 1~3분기 선행**.
- 한계: 캐펙스 둔화·과잉투자 우려가 부각되면 동일 경로가 역방향으로 빠르게 반전.

## 반례 / 한계
- 거시 긴축이 강해도 AI 수요가 이를 압도해 반도체가 차별적 강세를 보인 사례(2023~).
- 전력·인프라 병목이 캐펙스 실현을 제약하면 수요 전이가 지연될 수 있다.
