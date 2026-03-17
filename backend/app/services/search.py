"""三路可选混合检索（向量 + BM25 + 图谱）+ RRF 融合"""
from typing import List, Dict, Optional
import asyncio
from loguru import logger
from elasticsearch import AsyncElasticsearch

from app.config import settings
from app.models.schemas import SearchResultItem, Chunk
from app.services.embedding import embedding_service
from app.services.data_manager import data_manager
from app.services.vector_store import vector_store
from app.services.graph_search import graph_search_service
from app.utils.rrf import rrf_fuse


class SearchService:

    def __init__(self):
        self._es_client: Optional[AsyncElasticsearch] = None
        self._chunks_cache: Dict[str, Chunk] = {}

    def _get_es_client(self) -> AsyncElasticsearch:
        if self._es_client is None:
            self._es_client = AsyncElasticsearch(settings.ES_URL)
        return self._es_client

    def refresh_cache(self):
        chunks = data_manager.load_all_chunks()
        self._chunks_cache = {c.chunk_id: c for c in chunks}
        logger.info(f"Search cache refreshed: {len(self._chunks_cache)} chunks")

    def _enrich_result(self, chunk_id: str, score: float, source: str) -> SearchResultItem:
        chunk = self._chunks_cache.get(chunk_id)
        if chunk:
            return SearchResultItem(
                chunk_id=chunk_id,
                title=chunk.title,
                title_chain=chunk.title_chain,
                text=chunk.text,
                score=score,
                source=source,
            )
        return SearchResultItem(chunk_id=chunk_id, score=score, source=source)

    # ──────────────── 向量检索 ────────────────

    async def vector_search(
        self, query: str, filters: Optional[dict] = None, top_k: int = None
    ) -> List[SearchResultItem]:
        top_k = top_k or settings.VECTOR_TOP_K
        query_vector = await embedding_service.encode_single(query)
        if not query_vector:
            return []

        results = vector_store.search(
            query_vector=query_vector, top_k=top_k, filters=filters
        )
        items = [
            self._enrich_result(r["chunk_id"], r["score"], "vector")
            for r in results
        ]
        logger.debug(f"Vector search: {len(items)} results for '{query[:30]}...'")
        return items

    # ──────────────── BM25 检索 ────────────────

    async def bm25_search(
        self, query: str, filters: Optional[dict] = None, top_k: int = None
    ) -> List[SearchResultItem]:
        top_k = top_k or settings.BM25_TOP_K
        es = self._get_es_client()

        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["text^3", "title^2", "title_chain"],
                    "type": "best_fields",
                }
            }
        ]
        filter_clauses = self._build_es_filter(filters)

        body = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "size": top_k,
        }

        try:
            response = await es.search(index=settings.ES_INDEX, body=body)
            items = [
                self._enrich_result(hit["_source"]["chunk_id"], hit["_score"], "bm25")
                for hit in response["hits"]["hits"]
            ]
            logger.debug(f"BM25 search: {len(items)} results for '{query[:30]}...'")
            return items
        except Exception as e:
            logger.error(f"ES search failed: {e}")
            return []

    def _build_es_filter(self, filters: Optional[dict]) -> List[dict]:
        if not filters:
            return []
        clauses = []
        if filters.get("phase"):
            clauses.append({"term": {"phase": filters["phase"]}})
        if filters.get("battle_type"):
            clauses.append({"term": {"battle_type": filters["battle_type"]}})
        if filters.get("scope"):
            clauses.append({"term": {"scope": filters["scope"]}})
        return clauses

    # ──────────────── 图谱检索 ────────────────

    async def graph_search(
        self, query: str, top_k: int = None
    ) -> List[SearchResultItem]:
        top_k = top_k or settings.VECTOR_TOP_K
        results = await graph_search_service.search_tasks(query, top_k=top_k)
        items = [
            self._enrich_result(r["chunk_id"], r["score"], "graph")
            for r in results
        ]
        logger.debug(f"Graph search: {len(items)} results for '{query[:30]}...'")
        return items

    # ──────────────── 三路混合检索 + RRF ────────────────

    async def hybrid_search(
        self,
        query: str,
        filters: Optional[dict] = None,
        top_k: int = None,
        use_vector: bool = True,
        use_bm25: bool = True,
        use_graph: bool = True,
    ) -> List[SearchResultItem]:
        final_top_k = top_k or settings.FINAL_TOP_K

        if not self._chunks_cache:
            self.refresh_cache()

        tasks = {}
        if use_vector:
            tasks["vector"] = self.vector_search(query, filters)
        if use_bm25:
            tasks["bm25"] = self.bm25_search(query, filters)
        if use_graph:
            tasks["graph"] = self.graph_search(query)

        if not tasks:
            logger.warning("All retrieval channels disabled, falling back to vector+bm25")
            tasks["vector"] = self.vector_search(query, filters)
            tasks["bm25"] = self.bm25_search(query, filters)

        keys = list(tasks.keys())
        raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        channel_results: Dict[str, List[SearchResultItem]] = {}
        for key, result in zip(keys, raw_results):
            if isinstance(result, Exception):
                logger.error(f"{key} search failed: {result}")
                channel_results[key] = []
            else:
                channel_results[key] = result

        channels_for_rrf = [
            [{"chunk_id": r.chunk_id, "score": r.score} for r in items]
            for items in channel_results.values()
            if items
        ]

        if not channels_for_rrf:
            return []

        fused = rrf_fuse(channels_for_rrf, k=settings.RRF_K)

        results = [
            self._enrich_result(item["chunk_id"], item["rrf_score"], "rrf")
            for item in fused[:final_top_k]
        ]

        counts = ", ".join(f"{k}={len(v)}" for k, v in channel_results.items())
        logger.info(f"Hybrid search: {counts}, fused={len(results)} for '{query[:30]}...'")
        return results

    # ──────────────── 三路对比（调试用） ────────────────

    async def search_comparison(
        self,
        query: str,
        filters: Optional[dict] = None,
        use_vector: bool = True,
        use_bm25: bool = True,
        use_graph: bool = True,
    ) -> dict:
        if not self._chunks_cache:
            self.refresh_cache()

        tasks = {}
        if use_vector:
            tasks["vector"] = self.vector_search(query, filters)
        if use_bm25:
            tasks["bm25"] = self.bm25_search(query, filters)
        if use_graph:
            tasks["graph"] = self.graph_search(query)

        keys = list(tasks.keys())
        raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        channel_results: Dict[str, List[SearchResultItem]] = {}
        for key, result in zip(keys, raw_results):
            channel_results[key] = [] if isinstance(result, Exception) else result

        channels_for_rrf = [
            [{"chunk_id": r.chunk_id, "score": r.score} for r in items]
            for items in channel_results.values()
            if items
        ]

        rrf_results = []
        if channels_for_rrf:
            fused = rrf_fuse(channels_for_rrf, k=settings.RRF_K)
            rrf_results = [
                self._enrich_result(item["chunk_id"], item["rrf_score"], "rrf")
                for item in fused[:settings.FINAL_TOP_K]
            ]

        return {
            "query": query,
            "vector_results": [r.model_dump() for r in channel_results.get("vector", [])],
            "bm25_results": [r.model_dump() for r in channel_results.get("bm25", [])],
            "graph_results": [r.model_dump() for r in channel_results.get("graph", [])],
            "rrf_results": [r.model_dump() for r in rrf_results],
        }

    async def close(self):
        if self._es_client:
            await self._es_client.close()


search_service = SearchService()
