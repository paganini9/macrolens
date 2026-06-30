"""RAG chunking — type별 청킹 + 메타데이터 부착.

- causal: 1문서 = 1청크(이미 원자적, 분할 금지).
- case  : 섹션 단위(개요/전개/반응/교훈).
- news  : 섹션 단위(요약/지표/섹터/코인/인과관찰). '인과 관찰'은 별도 청크.

각 청크 메타데이터(가이드 4.4 필수): type, date/period, market, indicators[],
sectors[], event, confidence, lead_lag, lag_window, source(title), url.
Chroma 메타데이터는 스칼라만 허용하므로 리스트는 JSON 문자열로 직렬화해 저장한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .loader import LoadedDoc


@dataclass
class Chunk:
    chunk_id: str  # 문서id[#섹션]
    doc_id: str
    type: str  # causal | case | news
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


# 본문 섹션 헤더(## ...) 분할
_SECTION_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def _split_sections(body: str) -> list[tuple[str, str]]:
    """본문을 [(헤더, 내용)] 리스트로. 헤더 앞 프리앰블은 ('', ...)."""
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        return [("", body.strip())] if body.strip() else []
    out: list[tuple[str, str]] = []
    pre = body[: matches[0].start()].strip()
    if pre:
        out.append(("", pre))
    for i, m in enumerate(matches):
        header = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        out.append((header, content))
    return out


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        return [s]
    return [str(v)]


def _first_source(doc: LoadedDoc) -> dict[str, Any]:
    if doc.sources:
        return doc.sources[0]
    return {"title": doc.doc_id, "url": "", "publisher": "", "published_at": None}


def base_meta(doc: LoadedDoc) -> dict[str, Any]:
    """청크 공통 메타데이터(스칼라 + JSON 직렬화 리스트)."""
    m = doc.meta
    src = _first_source(doc)
    date_or_period = m.get("date") or m.get("period") or ""
    sectors = _as_list(m.get("sectors"))
    indicators = _as_list(m.get("indicators"))
    market = _as_list(m.get("market"))
    meta: dict[str, Any] = {
        "doc_id": doc.doc_id,
        "type": str(m.get("type", "")),
        "path": doc.path,
        "date": str(date_or_period),
        "event": str(m.get("event", "") or ""),
        "confidence": str(m.get("confidence", "") or ""),
        "lead_lag": str(m.get("lead_lag", "") or ""),
        "lag_window": str(m.get("lag_window", "") or ""),
        # 필터용: 리스트는 JSON 문자열로(Chroma 메타 스칼라 제약). 검색 시 contains 필터.
        "sectors": json.dumps(sectors, ensure_ascii=False),
        "indicators": json.dumps(indicators, ensure_ascii=False),
        "market": json.dumps(market, ensure_ascii=False),
        # 출처 추적
        "source_title": str(src.get("title", "") or ""),
        "url": str(src.get("url", "") or ""),
        "published_at": str(src.get("published_at") or ""),
    }
    return meta


def _causal_chunks(doc: LoadedDoc) -> list[Chunk]:
    text = doc.body.strip()
    meta = base_meta(doc)
    meta["section"] = "전체"
    return [Chunk(chunk_id=doc.doc_id, doc_id=doc.doc_id, type="causal", text=text, meta=meta)]


def _section_chunks(doc: LoadedDoc, type_: str, causal_obs_keys: tuple[str, ...] = ()) -> list[Chunk]:
    out: list[Chunk] = []
    sections = _split_sections(doc.body)
    idx = 0
    for header, content in sections:
        if not content:
            continue
        meta = base_meta(doc)
        meta["section"] = header or "본문"
        # 인과 관찰 섹션 표시(news 의 별도 청크 강조용)
        is_causal_obs = any(k in header for k in causal_obs_keys) if causal_obs_keys else False
        meta["is_causal_observation"] = bool(is_causal_obs)
        slug = re.sub(r"\s+", "_", header)[:24] if header else f"sec{idx}"
        chunk_id = f"{doc.doc_id}#{slug}" if header else f"{doc.doc_id}#sec{idx}"
        out.append(Chunk(chunk_id=chunk_id, doc_id=doc.doc_id, type=type_, text=content, meta=meta))
        idx += 1
    return out


def chunk_doc(doc: LoadedDoc) -> list[Chunk]:
    """문서 type에 따라 청킹."""
    t = str(doc.meta.get("type", "")).lower()
    if t == "causal":
        return _causal_chunks(doc)
    if t == "case":
        return _section_chunks(doc, "case")
    if t == "news":
        # '인과 관찰'/'인과관찰' 섹션을 별도 청크로 표시
        return _section_chunks(doc, "news", causal_obs_keys=("인과 관찰", "인과관찰"))
    # 알 수 없는 type → 안전하게 1청크
    return _causal_chunks(doc)


def collection_for(type_: str) -> str:
    """type → Chroma 컬렉션명."""
    return {
        "causal": "kb_causal",
        "case": "kb_cases",
        "news": "kb_news",
    }.get(type_, "kb_causal")


def meta_list(meta: dict[str, Any], key: str) -> list[str]:
    """JSON 직렬화된 리스트 메타데이터를 다시 list로."""
    raw = meta.get(key)
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw:
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return [str(x) for x in v]
        except Exception:
            return [raw]
    return []
