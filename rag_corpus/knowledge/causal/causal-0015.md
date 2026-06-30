---
id: causal-0015
type: causal
indicators: [신용스프레드, US10Y]
sectors: [금융, 코인]
market: [US, KR, CRYPTO]
direction: 신용 스프레드 확대 → 위험회피·금융 스트레스 신호
confidence: high
lead_lag: leading
lag_window: "0~2개월(위험자산 전이)"
lag_method: "하이일드 스프레드가 금융여건·신용위험을 선반영하는 일반 관찰(정성)"
sources:
  - title: "ICE BofA US High Yield Index OAS (FRED, BAMLH0A0HYM2)"
    url: "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"
  - title: "Credit spread (Investopedia)"
    url: "https://www.investopedia.com/terms/c/creditspread.asp"
---
## 인과 명제
하이일드 신용 스프레드(국채 대비 가산금리)의 확대는 금융여건 긴축과 신용위험 상승을 선반영하는 강력한 위험회피 신호로, **금융** 섹터와 **코인** 등 고베타 위험자산을 동반 압박한다. 스프레드 축소는 반대로 위험선호 회복을 시사한다.

## 메커니즘
신용 스프레드↑ → 차환·조달비용↑·디폴트 우려↑ → 금융여건 긴축 → 위험자산 디레이팅·자금 회수 → 금융주(신용비용)·코인(유동성) 동반 약세.

## 시차(리드/래그)
- 스프레드는 위험자산에 **0~2개월 선행**(금융 스트레스의 조기 경보).
- 한계: 스프레드 급등이 특정 섹터(에너지·부동산) 국지 이슈일 수 있어 전이 범위 판단 필요.

## 반례 / 한계
- 중앙은행의 신속한 유동성 공급(백스톱)이 스프레드 확대를 빠르게 되돌리면 전이가 차단된다.
- 스프레드가 낮은 수준에서의 소폭 확대는 노이즈일 수 있음.
