# CLAUDE.md — MacroLens 개발 가이드 (Claude Code 필독)

거시 지표를 한·미 산업 섹터·코인으로 전이 해석해 월 1회 점검 브리핑을 제공하는 **제안형** Agent. 이 파일은 코딩 에이전트가 매 작업에서 따르는 규칙이다.

## 작업 환경 (반드시 준수)
- Python: **3.12 venv** (`backend/.venv`). 호스트 기본 3.14는 의존성 충돌 → 직접 사용 금지.
  - `cd backend; .\.venv\Scripts\Activate.ps1` 후 작업. 없으면 `& "C:\Users\jaehyunlee\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv`.
- 의존성: `backend/requirements.txt`(런타임) / `requirements-dev.txt`(개발). 새 패키지는 requirements에 추가 후 venv·Docker 양쪽 반영.
- 포트 = **MacroLens 전용 82xx** (다른 프로젝트 Docker와 충돌 회피):
  - backend 8200(→8000), frontend 8202(→8501), chroma 8201(→8000).
  - 로컬: `uvicorn app.main:app --reload --port 8200` → http://localhost:8200/api/v1/health
- 시크릿: `backend/.env`(`.env.example` 복사). **절대 커밋·출력 금지**(.gitignore 등록됨). RAG는 키 불필요, 데이터 레이어만 FRED·ECOS·FMP·ANTHROPIC 키 필요. Solar(Upstage) provider는 `SOLAR_API_KEY` + `../agents/03_dev_team/공유표준/참고_solar_upstage.md`(키 하드코딩 금지).

## 아키텍처 (레이어 경계 — 자기 담당 경로만 수정)
```
backend/app/
  api/    FastAPI 라우터·SSE·예외          (05)
  graph/  LangGraph State·노드·라우팅       (04)
  llm/    provider 추상화·프롬프트          (04)
  data/   외부 소스 클라이언트·캐시·정규화   (02)
  rag/    청킹·임베딩·Chroma·가중/시차 검색  (03)
  store/  SQLite(히스토리·핀)·FS            (06)
  core/   설정·로깅·예외·신뢰성·공유타입     (01, 완료)
frontend/ Streamlit 하이브리드 UI           (07)
rag_corpus/ 지식 베이스 소스(수집 스케줄 기록, RAG가 인덱싱)
```

## 계약 우선 (절대 규칙)
- 고정 계약: `../deliverables/개발/_coordination/contracts/` — api_standard·interface_contracts(v1)·error_model·state_schema·mocks.
- 레이어 간 타입은 **interface_contracts v1** 시그니처를 정확히 따른다(DataCollector·Retriever·Store·LLM·GraphApp).
- 공유 타입(Source·Metric·Evidence)은 `app/core/types.py`. 예외는 `app/core/exceptions.py`(AppError 계층).
- 계약 변경이 필요하면 코드부터 바꾸지 말고 `../deliverables/개발/_coordination/`에 변경 제안 기록(Change Control). 무단 계약 변경 금지.
- 의존 레이어가 미완이면 **계약을 만족하는 mock**(`contracts/mocks/`)으로 진행 — 서로 대기 금지.

## 핵심 설계 불변식
- 안전 가드레일은 그래프 **진입점**. 출력에 면책·불확실성 강제. 데이터 부족 시 "근거 부족" 분기(단정 금지).
- 환각 0: 수치는 데이터/출처에서만. LLM은 해석·표현 담당.
- 재현성: 분기 노드 temp=0 + structured output. 같은 입력 → 같은 경로.
- 라우팅 3원칙: 완전성·배타성·종료보장(검색 루프 상한 N).
- 코인은 섹터와 **분리** 표시. 섹터 유니버스(MVP 8): AI/SW·반도체·2차전지·자동차·금융·에너지/화학·바이오/헬스케어·인터넷/플랫폼.
- RAG 적재: 수집은 파일만, 인덱싱은 앱 lazy+startup(`index_incremental`/`ensure_synced`). 내용 해시로 신규/수정 upsert.

## 검증 (작업 종료 전)
- `pytest -q` (backend) 통과, 가능하면 `ruff check .`.
- API 표면은 `/api/v1/chat`·`/health`·`/pins`만(내부 그래프 비노출).
- 수용 기준·회귀셋: `../deliverables/개발준비/수용기준_및_테스트_시나리오.md`.

## 문서 위치 (작업 근거)
- 명세: `../deliverables/개발준비/`(SRS·기술설계·수용기준)
- 에이전트 지시문·표준: `../agents/03_dev_team/`(전문 Agent 9종·통신 프로토콜·의존성맵·공유표준)
- 작업 보드·상태: `../deliverables/개발/_coordination/`(task_board·status·integration_log)
- RAG 설계: `../docs/RAG_구축_가이드.md` / 화면: `../deliverables/기획/화면설계_와이어프레임.html`

## 현재 상태
- Phase 0(계약 freeze + core) **완료**. `/api/v1/health` 동작 확인(8200).
- 다음 Phase 1 병렬: 02 데이터 · 03 RAG · 06 퍼시스턴스 · 04 그래프(mock). 임계 경로 = 04 → 05 → 08 → 09.
