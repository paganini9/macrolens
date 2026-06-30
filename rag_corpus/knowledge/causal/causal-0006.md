---
id: causal-0006
type: causal
indicators: [WTI, BRENT]
sectors: [에너지/화학]
market: [US, KR]
direction: 유가 상승 → 정유 정제마진(+) vs 화학 원가(−) 양면
confidence: med
lead_lag: coincident
lag_window: "0~1개월(정제마진), 1~2개월(화학 스프레드)"
lag_method: "정유·화학 밸류체인 원가구조 기반 일반 메커니즘(정성)"
sources:
  - title: "Crack spread (Wikipedia)"
    url: "https://en.wikipedia.org/wiki/Crack_spread"
  - title: "Crude Oil Prices (FRED, WTI)"
    url: "https://fred.stlouisfed.org/series/DCOILWTICO"
---
## 인과 명제
유가(WTI·Brent) 상승은 **에너지/화학** 섹터에 양면적이다. 정유·E&P는 판가·정제마진 개선으로 우호적이나, 석유화학은 원료(납사) 투입원가 상승으로 제품 스프레드가 눌릴 수 있다. 순효과는 하위 업종 비중과 수요 강도에 의존한다(조건부).

## 메커니즘
- (+) 유가↑ → 원유·정제품 판가↑, 보유재고 평가이익 → 정유·E&P 마진↑.
- (−) 유가↑ → 납사 등 화학 원료비↑ → 수요가 약하면 제품가 전가 실패 → 화학 스프레드↓.

## 시차(리드/래그)
- 정제마진은 유가에 **거의 동행**, 화학 스프레드는 제품가 전가 지연으로 **1~2개월 후행**.
- 한계: 정유 비중이 큰 기업은 (+), 화학 비중이 큰 기업은 (−)로 부호가 갈림.

## 반례 / 한계
- 수요 호황기에는 화학도 제품가 전가가 쉬워 유가 상승이 마진을 크게 훼손하지 않는다.
- 유가 급락기에는 정유 재고평가손이 발생해 단기 실적이 악화될 수 있다.
