"""의존성 결선(레이어 → 그래프). 프로세스 단일 인스턴스.

- store/collector/retriever/llm 는 각 레이어 팩토리로 생성.
- retriever/collector 가 실패하면(오프라인·키 없음) mock 으로 폴백해 가용성 유지.
- 그래프는 deps 를 주입해 1회 빌드(상태 비저장; store 는 참조 공유).
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.data import MockDataCollector, get_collector
from app.graph.build import GraphApp, build_graph
from app.llm.provider import get_llm
from app.rag import MockRetriever, get_retriever
from app.store import get_store

logger = get_logger(__name__)


class Container:
    """결선된 싱글턴 보관소. 그래프는 provider 별로 캐시한다(사용자 선택 지원)."""

    def __init__(self) -> None:
        self.store = None
        self.collector = None
        self.retriever = None
        self.llm = None
        self.graph: Optional[GraphApp] = None
        self.chroma_status = "pending"
        self.default_provider = "solar"
        self._graphs: dict[str, GraphApp] = {}

    def build(self) -> None:
        self.default_provider = (settings.llm_provider or "solar").lower()
        self.store = get_store()
        self.llm = get_llm()
        try:
            self.collector = get_collector()
        except Exception as e:  # pragma: no cover - 방어
            logger.warning("collector init failed → MockDataCollector: %s", e)
            self.collector = MockDataCollector()
        try:
            self.retriever = get_retriever()
        except Exception as e:  # pragma: no cover
            logger.warning("retriever init failed → MockRetriever: %s", e)
            self.retriever = MockRetriever()
        self.graph = self._build_graph_for(self.llm)
        self._graphs = {self.default_provider: self.graph}

    def _build_graph_for(self, llm) -> GraphApp:
        return build_graph(
            llm=llm, collector=self.collector, retriever=self.retriever, store=self.store
        )

    def graph_for(self, provider: Optional[str]) -> GraphApp:
        """provider 별 그래프(캐시). 미지정/미설정이면 기본 그래프를 반환."""
        name = (provider or self.default_provider).lower()
        if name == self.default_provider or not provider:
            return self.graph  # type: ignore[return-value]
        cached = self._graphs.get(name)
        if cached is not None:
            return cached
        graph = self._build_graph_for(get_llm(name))
        self._graphs[name] = graph
        return graph

    def index_rag(self) -> None:
        """lifespan 기동 시 1회 증분 인덱싱(파일→Chroma)."""
        try:
            n = self.retriever.index_incremental()
            self.chroma_status = "ok"
            logger.info("RAG index_incremental upserted=%s", n)
        except Exception as e:  # pragma: no cover - Chroma/모델 미가용 허용
            self.chroma_status = "degraded"
            logger.warning("RAG indexing skipped/degraded: %s", e)


container = Container()
