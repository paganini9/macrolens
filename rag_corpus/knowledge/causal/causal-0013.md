---
id: causal-0013
type: causal
indicators: [BOK_BASE]
sectors: [금융]
market: [KR]
direction: 한국 기준금리 인상 → 은행 마진(+) vs 내수·가계부채(−)
confidence: med
lead_lag: coincident
lag_window: "0~1분기(마진), 2~4분기(내수·연체)"
lag_method: "정책금리-예대금리 전이 및 가계부채 부담 경로 기반 일반 메커니즘(정성)"
sources:
  - title: "Bank of Korea base rate (BOK)"
    url: "https://www.bok.or.kr/eng/main/contents.do?menuNo=400037"
  - title: "Monetary policy (Investopedia)"
    url: "https://www.investopedia.com/terms/m/monetary-policy.asp"
---
## 인과 명제
한국은행 기준금리(BOK_BASE) 인상은 은행의 예대금리차를 단기적으로 넓혀 **금융(은행)** 이자이익에 우호적이나, 가계부채 부담·연체율 상승과 내수·부동산 위축을 통해 중기적으로는 신용비용을 키운다. 순효과는 인상 속도와 가계 레버리지 수준에 의존한다(조건부).

## 메커니즘
- (+) 기준금리↑ → 대출금리가 예금금리보다 빠르게 반영 → NIM↑ → 이자이익↑.
- (−) 가계 이자부담↑ → 소비·부동산↓ → 연체·신용비용↑ → 충당금 부담.

## 시차(리드/래그)
- 마진 효과는 **0~1분기**로 빠르고, 내수 위축·연체 증가는 **2~4분기** 후행.
- 한계: 변동금리 비중·예금 베타에 따라 전이 속도 상이.

## 반례 / 한계
- 인하 사이클로 전환되면 마진은 축소되나 신용비용·내수는 개선.
- 부동산 PF 등 특정 부문 부실은 금리와 별개로 금융 섹터를 압박할 수 있다.
