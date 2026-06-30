---
id: causal-0020
type: causal
indicators: [FFR, US10Y]
sectors: [금융, AI/SW]
market: [US, KR]
direction: 금리 인하 전환 → 성장주 밸류 회복(+) vs 은행 마진 축소(−)
confidence: med
lead_lag: leading
lag_window: "0~1개월(밸류), 1~2분기(은행 마진)"
lag_method: "인하 사이클의 섹터별 비대칭 효과에 관한 일반 메커니즘(정성)"
sources:
  - title: "Federal Funds Rate (FRED, FEDFUNDS)"
    url: "https://fred.stlouisfed.org/series/FEDFUNDS"
  - title: "Interest Rate (Investopedia)"
    url: "https://www.investopedia.com/terms/i/interestrate.asp"
---
## 인과 명제
금리 인하 사이클로의 전환은 섹터별로 비대칭적이다. 할인율 하락으로 고듀레이션 **AI/SW** 성장주 밸류에이션은 회복되는 반면, **금융(은행)**은 자산수익률·예대마진 축소로 이자이익이 눌릴 수 있다. 인하 기대 형성 단계에서는 성장주가 먼저 반응한다.

## 메커니즘
- (성장주 +) 금리↓ → 할인율↓ → 듀레이션 긴 성장주 현재가치↑.
- (은행 −) 대출금리·운용수익률↓(예금금리는 천천히) → NIM 축소 → 이자이익↓.

## 시차(리드/래그)
- 성장주 밸류는 인하 기대에 **즉시~1개월** 선행, 은행 마진 축소는 **1~2분기** 후행.
- 한계: 인하가 '경기둔화 대응'이면 은행 신용비용 우려가 마진 효과보다 클 수 있음.

## 반례 / 한계
- 가파른 인하는 거래량·자산건전성 개선으로 은행에 우호적일 수도 있음(경로 의존).
- 인하가 침체 신호로 해석되면 성장주도 이익 추정 하향으로 상승이 제한.
