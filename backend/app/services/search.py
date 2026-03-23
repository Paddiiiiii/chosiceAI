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
from app.services.rerank import rerank_service
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
        if not (query or "").strip():
            return []
        query_vector = await embedding_service.encode_for_vector_search(query)
        if not query_vector:
            return []

        results = await vector_store.search(
            query_vector=query_vector, top_k=top_k, filters=filters
        )
        items = [
            self._enrich_result(r["chunk_id"], r["score"], "vector")
            for r in results
        ]
        logger.debug(f"Vector search: {len(items)} results for '{query[:30]}...'")
        return items

    # ──────────────── BM25 检索 ────────────────

    def _build_bm25_body(
        self, query: str, filters: Optional[dict], top_k: int
    ) -> dict:
        """BM25：多字段 best_fields + 正文/标题链短语匹配 + 角色关键词，提高相关性与短语命中。"""
        filter_clauses = self._build_es_filter(filters)
        q = (query or "").strip()
        should = [
            {
                "multi_match": {
                    "query": q,
                    "fields": [
                        "text^3",
                        "title^2",
                        "title_chain^1.5",
                    ],
                    "type": "best_fields",
                    "tie_breaker": 0.35,
                }
            },
            {
                "match_phrase": {
                    "text": {
                        "query": q,
                        "boost": 2.8,
                        "slop": 2,
                    }
                }
            },
            {
                "match_phrase": {
                    "title_chain": {
                        "query": q,
                        "boost": 2.2,
                    }
                }
            },
            {
                "match": {
                    "roles_mentioned": {
                        "query": q,
                        "boost": 1.25,
                    }
                }
            },
        ]
        return {
            "query": {
                "bool": {
                    "filter": filter_clauses,
                    "should": should,
                    "minimum_should_match": 1,
                }
            },
            "size": top_k,
        }

    async def bm25_search(
        self, query: str, filters: Optional[dict] = None, top_k: int = None
    ) -> List[SearchResultItem]:
        top_k = top_k or settings.BM25_TOP_K
        es = self._get_es_client()
        if not (query or "").strip():
            return []

        body = self._build_bm25_body(query, filters, top_k)

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

        per_ch = settings.HYBRID_PER_CHANNEL_TOP_K
        tasks = {}
        if use_vector:
            tasks["vector"] = self.vector_search(query, filters, top_k=per_ch)
        if use_bm25:
            tasks["bm25"] = self.bm25_search(query, filters, top_k=per_ch)
        if use_graph:
            tasks["graph"] = self.graph_search(query, top_k=per_ch)

        if not tasks:
            logger.warning("All retrieval channels disabled, falling back to vector+bm25")
            tasks["vector"] = self.vector_search(query, filters, top_k=per_ch)
            tasks["bm25"] = self.bm25_search(query, filters, top_k=per_ch)

        keys = list(tasks.keys())
        raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        channel_results: Dict[str, List[SearchResultItem]] = {}
        for key, result in zip(keys, raw_results):
            if isinstance(result, Exception):
                logger.error(f"{key} search failed: {result}")
                channel_results[key] = []
            else:
                channel_results[key] = result

        wmap = {
            "vector": settings.RRF_WEIGHT_VECTOR,
            "bm25": settings.RRF_WEIGHT_BM25,
            "graph": settings.RRF_WEIGHT_GRAPH,
        }
        channels_for_rrf: List[List[Dict]] = []
        rrf_weights: List[float] = []
        for key in keys:
            items = channel_results.get(key, [])
            if items:
                channels_for_rrf.append(
                    [{"chunk_id": r.chunk_id, "score": r.score} for r in items]
                )
                rrf_weights.append(wmap[key])

        if not channels_for_rrf:
            return []

        fused = rrf_fuse(
            channels_for_rrf, k=settings.RRF_K, weights=rrf_weights
        )

        if not fused:
            return []

        pool_k = max(
            final_top_k,
            settings.RERANK_CANDIDATE_POOL
            if rerank_service.is_available()
            else final_top_k,
        )
        pool_k = min(pool_k, len(fused))
        candidates = [
            self._enrich_result(item["chunk_id"], item["rrf_score"], "rrf")
            for item in fused[:pool_k]
        ]

        if rerank_service.is_available():
            candidates = await rerank_service.rerank(query, candidates)

        results = candidates[:final_top_k]

        counts = ", ".join(f"{k}={len(v)}" for k, v in channel_results.items())
        logger.info(f"Hybrid search: {counts}, fused={len(fused)}, out={len(results)} for '{query[:30]}...'")
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

        per_ch = settings.HYBRID_PER_CHANNEL_TOP_K
        tasks = {}
        if use_vector:
            tasks["vector"] = self.vector_search(query, filters, top_k=per_ch)
        if use_bm25:
            tasks["bm25"] = self.bm25_search(query, filters, top_k=per_ch)
        if use_graph:
            tasks["graph"] = self.graph_search(query, top_k=per_ch)

        keys = list(tasks.keys())
        raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        channel_results: Dict[str, List[SearchResultItem]] = {}
        for key, result in zip(keys, raw_results):
            channel_results[key] = [] if isinstance(result, Exception) else result

        wmap = {
            "vector": settings.RRF_WEIGHT_VECTOR,
            "bm25": settings.RRF_WEIGHT_BM25,
            "graph": settings.RRF_WEIGHT_GRAPH,
        }
        channels_for_rrf: List[List[Dict]] = []
        rrf_weights: List[float] = []
        for key in keys:
            items = channel_results.get(key, [])
            if items:
                channels_for_rrf.append(
                    [{"chunk_id": r.chunk_id, "score": r.score} for r in items]
                )
                rrf_weights.append(wmap[key])

        rrf_results = []
        rerank_results = []
        rerank_meta: dict = {
            "configured": rerank_service.is_available(),
            "applied": False,
        }
        if channels_for_rrf:
            fused = rrf_fuse(
                channels_for_rrf, k=settings.RRF_K, weights=rrf_weights
            )
            rrf_results = [
                self._enrich_result(item["chunk_id"], item["rrf_score"], "rrf")
                for item in fused[: settings.FINAL_TOP_K]
            ]
            if fused and rerank_service.is_available():
                pool_k = min(len(fused), settings.RERANK_CANDIDATE_POOL)
                pool = [
                    self._enrich_result(item["chunk_id"], item["rrf_score"], "rrf")
                    for item in fused[:pool_k]
                ]
                reranked = await rerank_service.rerank(query, pool)
                rerank_results = reranked[: settings.FINAL_TOP_K]
                rerank_meta["applied"] = True
                rerank_meta["pool_size"] = pool_k
            elif fused:
                rerank_meta["reason"] = (
                    "rerank_disabled"
                    if not settings.RERANK_ENABLED
                    else "no_rerank_api_key"
                )

        return {
            "query": query,
            "vector_results": [r.model_dump() for r in channel_results.get("vector", [])],
            "bm25_results": [r.model_dump() for r in channel_results.get("bm25", [])],
            "graph_results": [r.model_dump() for r in channel_results.get("graph", [])],
            "rrf_results": [r.model_dump() for r in rrf_results],
            "rerank_results": [r.model_dump() for r in rerank_results],
            "rerank_meta": rerank_meta,
        }

    async def close(self):
        if self._es_client:
            await self._es_client.close()


search_service = SearchService()
