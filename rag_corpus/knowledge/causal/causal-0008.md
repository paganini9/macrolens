---
id: causal-0008
type: causal
indicators: [CPI, CORE_PCE]
sectors: [AI/SW, 반도체]
market: [US, KR]
direction: 인플레 재가속 → 긴축기대 → 성장주·반도체 압박
confidence: high
lead_lag: leading
lag_window: "0~1개월(기대 반영), 1~2개월(정책 경로)"
lag_method: "물가 서프라이즈 → 금리기대 → 밸류에이션 경로의 일반 메커니즘(정성)"
sources:
  - title: "Core PCE (FRED, PCEPILFE)"
    url: "https://fred.stlouisfed.org/series/PCEPILFE"
  - title: "Consumer Price Index (BLS)"
    url: "https://www.bls.gov/cpi/"
---
## 인과 명제
CPI·코어 PCE의 재가속은 시장의 금리인하 기대를 후퇴시키고 추가 긴축 가능성을 높여, 고밸류에이션 **AI/SW·반도체** 성장주의 할인율을 끌어올린다. 인플레 서프라이즈는 금리 기대를 통해 성장주 밸류에이션에 즉각 전이된다.

## 메커니즘
코어 인플레↑(서프라이즈) → 연내 인하 기대↓·기간 프리미엄↑ → 실질금리·할인율↑ → 듀레이션 긴 성장주(AI/SW·반도체) 현재가치↓.

## 시차(리드/래그)
- 발표 당일~수일 내 **즉시** 금리 기대·주가에 반영(선행 0~1개월).
- 한계: 동일 인플레라도 고용·성장 동반 강세면 '굿 인플레'로 해석돼 충격이 완화될 수 있음.

## 반례 / 한계
- AI 실적 모멘텀이 강한 국면(2023~)에서는 높은 금리에도 반도체·AI가 강세 — 수요 사이클이 금리 역풍을 압도.
- 디스인플레로 전환되면 동일 메커니즘이 반대로(밸류 회복) 작동.
