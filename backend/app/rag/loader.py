"""RAG loader — .md 파일의 YAML front-matter + 본문을 견고하게 파싱한다.

코퍼스 종류별 front-matter 스키마가 조금씩 다르다(causal/case는 dict sources,
news는 "title / url / publisher / published_at" 형태의 문자열 sources). 본 모듈은
PyYAML이 있으면 사용하고, 없으면 내장 미니 파서로 폴백해 환경 의존을 최소화한다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

try:  # PyYAML 권장(견고). 없으면 폴백.
    import yaml  # type: ignore

    _HAS_YAML = True
except Exception:  # pragma: no cover - 환경 의존
    yaml = None  # type: ignore
    _HAS_YAML = False


_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# news 의 문자열 source: 'title: "..." / url: "..." / publisher: "..." / published_at: "..."'
_KV_RE = re.compile(r'(\w+)\s*:\s*"([^"]*)"')


@dataclass
class LoadedDoc:
    """파싱된 단일 문서."""

    doc_id: str
    path: str  # 코퍼스 루트 기준 상대경로(예: news/2026-06-30.md)
    meta: dict[str, Any]
    body: str
    sources: list[dict[str, Any]] = field(default_factory=list)


def split_front_matter(text: str) -> tuple[str, str]:
    """텍스트를 (front_matter_raw, body)로 분리. front-matter 없으면 ('', text)."""
    text = text.lstrip("﻿")  # BOM 제거
    m = _FRONT_RE.match(text)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def _coerce_scalar(val: str) -> Any:
    v = val.strip()
    if not v:
        return ""
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(p) for p in _split_top_level(inner)]
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    return v


def _split_top_level(s: str) -> list[str]:
    """대괄호/따옴표를 존중하며 콤마 분리."""
    out: list[str] = []
    depth = 0
    quote = ""
    buf = ""
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            buf += ch
        elif ch in "[":
            depth += 1
            buf += ch
        elif ch in "]":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


def _parse_front_matter_fallback(raw: str) -> dict[str, Any]:
    """PyYAML 없이 동작하는 미니 front-matter 파서.

    지원: `key: scalar`, `key: [a, b]`, `key:` 다음 줄들의 `  - item`(문자열/dict 라인).
    """
    meta: dict[str, Any] = {}
    lines = raw.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^(\w[\w/]*)\s*:(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest:
            meta[key] = _coerce_scalar(rest)
            i += 1
            continue
        # 블록 리스트 수집
        items: list[Any] = []
        i += 1
        while i < len(lines):
            ln = lines[i]
            stripped = ln.strip()
            if not stripped:
                i += 1
                continue
            if not ln.startswith(" "):
                break
            if stripped.startswith("- "):
                item_text = stripped[2:].strip()
                items.append(_parse_list_item(item_text, lines, i))
                i += 1
                # dict 형태(다음 줄들이 더 들여쓰기된 key: val)면 흡수
                while i < len(lines) and lines[i].startswith("    ") and ":" in lines[i] and not lines[i].strip().startswith("- "):
                    kk, _, vv = lines[i].strip().partition(":")
                    if isinstance(items[-1], dict):
                        items[-1][kk.strip()] = _coerce_scalar(vv.strip())
                    i += 1
            else:
                break
        if items:
            meta[key] = items
    return meta


def _parse_list_item(item_text: str, lines: list[str], idx: int) -> Any:
    """리스트 항목을 dict 또는 문자열로 변환."""
    # 'title: "..." / url: "..."' (news) 또는 'title: "..."'(첫 줄 dict)
    if "/" in item_text and _KV_RE.search(item_text):
        return _parse_news_source_string(item_text)
    m = re.match(r"^(\w+)\s*:\s*(.*)$", item_text)
    if m:
        return {m.group(1): _coerce_scalar(m.group(2))}
    return _coerce_scalar(item_text)


def _parse_news_source_string(s: str) -> dict[str, Any]:
    """'title: "..." / url: "..." / publisher: "..." / published_at: "..."' → dict."""
    out: dict[str, Any] = {}
    for k, v in _KV_RE.findall(s):
        out[k] = v
    return out


def parse_front_matter(raw: str) -> dict[str, Any]:
    """front-matter 문자열을 dict로. PyYAML 우선, 실패 시 폴백."""
    if not raw.strip():
        return {}
    if _HAS_YAML:
        try:
            data = yaml.safe_load(raw)
            if isinstance(data, dict):
                return _postprocess_yaml(data)
        except Exception:
            pass
    return _parse_front_matter_fallback(raw)


def _postprocess_yaml(data: dict[str, Any]) -> dict[str, Any]:
    """PyYAML 결과 정규화 — news 의 문자열 source 들을 dict 로 변환."""
    src = data.get("sources")
    if isinstance(src, list):
        norm: list[Any] = []
        for item in src:
            if isinstance(item, str) and _KV_RE.search(item):
                norm.append(_parse_news_source_string(item))
            else:
                norm.append(item)
        data["sources"] = norm
    return data


def normalize_sources(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """meta['sources']를 dict 리스트로 표준화([{title,url,publisher,published_at}])."""
    raw = meta.get("sources") or []
    out: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        raw = [raw]
    for item in raw:
        if isinstance(item, dict):
            out.append(
                {
                    "title": str(item.get("title", "")),
                    "url": str(item.get("url", "")),
                    "publisher": str(item.get("publisher", "")),
                    "published_at": (
                        str(item["published_at"]) if item.get("published_at") else None
                    ),
                }
            )
        elif isinstance(item, str):
            if _KV_RE.search(item):
                d = _parse_news_source_string(item)
                out.append(
                    {
                        "title": d.get("title", ""),
                        "url": d.get("url", ""),
                        "publisher": d.get("publisher", ""),
                        "published_at": d.get("published_at") or None,
                    }
                )
            else:
                out.append({"title": item, "url": "", "publisher": "", "published_at": None})
    return out


def _infer_doc_id(meta: dict[str, Any], rel_path: str) -> str:
    if meta.get("id"):
        return str(meta["id"])
    base = os.path.basename(rel_path)
    return os.path.splitext(base)[0]


def _infer_type(meta: dict[str, Any], rel_path: str) -> str:
    t = meta.get("type")
    if t in ("causal", "case", "news"):
        return str(t)
    p = rel_path.replace("\\", "/").lower()
    if "/news/" in p or p.startswith("news/"):
        return "news"
    if "/cases/" in p or p.startswith("cases/"):
        return "case"
    if "/causal/" in p or "/knowledge/" in p:
        return "causal"
    return "causal"


def load_text(text: str, rel_path: str) -> LoadedDoc:
    """문자열 + 상대경로로부터 LoadedDoc 생성."""
    raw_fm, body = split_front_matter(text)
    meta = parse_front_matter(raw_fm)
    meta.setdefault("type", _infer_type(meta, rel_path))
    sources = normalize_sources(meta)
    doc_id = _infer_doc_id(meta, rel_path)
    return LoadedDoc(
        doc_id=doc_id,
        path=rel_path.replace("\\", "/"),
        meta=meta,
        body=body.strip(),
        sources=sources,
    )


def load_file(abs_path: str, corpus_root: str) -> LoadedDoc:
    """파일 경로로부터 LoadedDoc 생성. rel_path는 corpus_root 기준."""
    with open(abs_path, "r", encoding="utf-8") as f:
        text = f.read()
    rel_path = os.path.relpath(abs_path, corpus_root).replace("\\", "/")
    return load_text(text, rel_path)


def iter_corpus_files(corpus_root: str) -> list[str]:
    """코퍼스 루트 아래 인덱싱 대상 .md 파일 절대경로 목록.

    `_`로 시작하는 메타 파일(_manifest.csv, _causal_backlog.md 등)·index/ 는 제외.
    """
    out: list[str] = []
    for dirpath, _dirs, files in os.walk(corpus_root):
        rel_dir = os.path.relpath(dirpath, corpus_root).replace("\\", "/")
        if rel_dir.startswith("index"):
            continue
        for fn in files:
            if not fn.endswith(".md"):
                continue
            if fn.startswith("_"):
                continue
            out.append(os.path.join(dirpath, fn))
    return sorted(out)
