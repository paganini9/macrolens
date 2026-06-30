---
id: causal-0021
type: causal
indicators: [WTI, BRENT]
sectors: [자동차]
market: [US, KR]
direction: 유가 하락 → 가처분소득·소비심리 개선 → 자동차 수요 우호
confidence: med
lead_lag: leading
lag_window: "1~3개월(소비 반영)"
lag_method: "유가-가처분소득-내구재 수요 경로의 일반 메커니즘(정성)"
sources:
  - title: "Crude Oil Prices (FRED, WTI)"
    url: "https://fred.stlouisfed.org/series/DCOILWTICO"
  - title: "Gas prices and the economy (Investopedia)"
    url: "https://www.investopedia.com/articles/economics/08/gas-prices-economy.asp"
---
## 인과 명제
유가(WTI·Brent) 하락은 휘발유·운송비 부담을 낮춰 가계 가처분소득과 소비심리를 개선하고, 내구재인 **자동차** 수요에 시차를 두고 우호적으로 작용한다. 동시에 헤드라인 인플레 둔화로 통화정책 부담도 완화돼 간접 효과가 더해진다.

## 메커니즘
유가↓ → 연료비·물류비↓ → 가처분소득↑·소비심리↑ → 내구재(자동차) 수요↑. 헤드라인 인플레↓ → 금리 부담 완화(간접).

## 시차(리드/래그)
- 소비·수요 반영은 유가에 **약 1~3개월 후행**(유가가 선행 신호).
- 한계: 유가 하락이 '글로벌 수요 둔화發'이면 소득 효과보다 경기 우려가 우세.

## 반례 / 한계
- 전기차 비중이 커질수록 휘발유價 민감도는 약화.
- 유가 급락이 산유국·관련 산업 위축을 통해 일부 수요를 상쇄.
