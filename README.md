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

## 실행 (예정)
`docker compose up` 또는 backend/frontend 개별 실행. 상세는 개발 진행 후 갱신.
