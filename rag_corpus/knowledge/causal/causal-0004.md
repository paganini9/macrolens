---
id: causal-0004
type: causal
indicators: [US10Y, FFR]
sectors: [금융]
market: [US, KR]
direction: 장기금리 상승(수익률곡선 가팔라짐) → 은행 순이자마진 개선
confidence: high
lead_lag: coincident
lag_window: "0~1분기(NIM 반영), 1~2분기(이자이익)"
lag_method: "은행 자산-부채 만기구조에서 도출한 일반 메커니즘(정성). 개발 단계 FRED/은행 실적으로 재확인 권장"
sources:
  - title: "Net interest margin (FRED, NIM)"
    url: "https://fred.stlouisfed.org/series/USNIM"
  - title: "Net Interest Margin (Investopedia)"
    url: "https://www.investopedia.com/terms/n/netinterestmargin.asp"
---
## 인과 명제
장기금리(US10Y) 상승과 수익률곡선의 가팔라짐(steepening)은 은행의 예대마진·순이자마진(NIM)을 넓혀 **금융(은행)** 섹터에 우호적이다. 은행은 단기로 조달해 장기로 운용하므로, 장단기 금리차가 커질수록 이자이익이 늘어난다. 다만 금리 급등이 신용위험·자산건전성 악화로 번지면 효과가 상쇄된다(조건부).

## 메커니즘
장기금리↑ → 신규 대출·채권 운용수익률↑(조달금리는 천천히 반영) → NIM 확대 → 이자이익↑. 단, 곡선 역전(장<단) 국면에서는 반대로 마진 압박.

## 시차(리드/래그)
- NIM은 금리 변화에 **거의 동행~1분기 내** 반영, 이자이익 증가는 1~2분기 후행.
- 한계: 자산-부채 듀레이션 갭, 예금 베타에 따라 은행별 편차. 부실채권 증가 시 마진 개선분이 상쇄.

## 반례 / 한계
- 장단기 역전(2022~23) 국면에서는 장기금리가 높아도 단기 조달비용이 더 빠르게 올라 마진이 눌릴 수 있다.
- 급격한 금리 상승은 보유채권 평가손(미실현손실)을 키워 자본·신뢰를 훼손(SVB 사례 참조).
