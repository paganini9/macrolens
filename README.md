# MacroLens — 거시 전이 브리핑 Agent (코드 레포)

거시 지표를 한·미 산업 섹터·코인으로 전이 해석해 월 1회 점검 브리핑을 제공하는 제안형 Agent.

## 구조
```
macrolens/
├─ backend/   # FastAPI + LangGraph (api·graph·llm·data·rag·store·core)
├─ frontend/  # Streamlit 하이브리드 UI
├─ rag_corpus/# 지식 베이스 소스(news·knowledge·cases) — 수집 스케줄이 기록, RAG가 인덱싱
├─ .env.example  .gitignore
```

## 기획·설계 문서 (레포 상위 프로젝트 폴더)
- `../agents/` — Agent 지시문(기획·개발준비·수집·**03_dev_team 개발 스쿼드**)
- `../deliverables/개발준비/` — SRS·기술설계·수용기준
- `../docs/RAG_구축_가이드.md` — 파일→ChromaDB 적재(인덱싱) 설계
- `../deliverables/개발/_coordination/` — 개발 스쿼드 조정(task_board·contracts)

## 데이터 파이프라인
- 수집 스케줄(Claude)이 `rag_corpus/`에 .md 파일을 쓴다(임베딩 안 함).
- RAG 레이어가 앱 기동·검색 직전 멱등 인덱싱(`python -m app.rag.index`)으로 ChromaDB 동기화.

## 실행

### Docker (권장 — 로컬=컨테이너 패리티)
```bash
cp backend/.env.example backend/.env   # SOLAR_API_KEY 등 채우기(없어도 기동, 합성은 폴백)
docker compose up --build
```
- backend  → http://localhost:8200/api/v1/health  (컨테이너 8000)
- frontend → http://localhost:8202                (컨테이너 8501, backend 헬스 통과 후 기동)
- 영속: `backend_data` 볼륨에 Chroma·SQLite·ledger. `rag_corpus/`는 읽기 전용 마운트.
- Chroma는 backend 내 임베디드 PersistentClient(파일 기반) — 별도 chroma 컨테이너 불필요.

### 로컬 개발 (venv)
```powershell
# backend (8200)
cd backend; .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8200
# frontend (8202) — 별도 터미널
cd frontend; .\.venv\Scripts\Activate.ps1   # 최초: python -m venv .venv; pip install -r requirements.txt
streamlit run app.py --server.port 8202
```
- LLM provider 기본값 **solar**(`LLM_PROVIDER`). 키 없이 구조만 보려면 `LLM_PROVIDER=mock`.
- 테스트/게이트: `cd backend; .\.venv\Scripts\python.exe -m pytest -q` (회귀·수용기준 포함).

## 파일시스템 레이아웃 (env 주입)
| 항목 | 로컬 기본 | 컨테이너 | env |
|---|---|---|---|
| RAG 코퍼스(읽기) | `../rag_corpus` | `/app/rag_corpus` (ro) | `RAG_CORPUS_DIR` |
| Chroma(임베디드) | `./.chroma` | `/app/data/chroma` | `CHROMA_DIR` |
| SQLite(핀·히스토리) | `./macrolens.db` | `/app/data/macrolens.db` | `SQLITE_PATH` |
