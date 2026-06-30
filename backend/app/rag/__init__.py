"""RAG 레이어 — 인덱싱(loader·chunking·index) + 검색(retriever).

공개 표면: Retriever 구현(ChromaRetriever/MockRetriever)과 팩토리, Indexer.
"""
from __future__ import annotations

from .index import Indexer, index_incremental
from .retriever import ChromaRetriever, MockRetriever, get_retriever

__all__ = [
    "Indexer",
    "index_incremental",
    "ChromaRetriever",
    "MockRetriever",
    "get_retriever",
]
