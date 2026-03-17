"""Step 3 - 双路并行检索 + RRF 融合"""
from typing import List, Dict, Optional
import asyncio
from loguru import logger
from elasticsearch import AsyncElasticsearch

from app.config import settings
from app.models.schemas import SearchResultItem, Chunk
from app.services.embedding import embedding_service
from app.services.data_manager import data_manager
from app.services.vector_store import vector_store
from app.utils.rrf import rrf_fuse


class SearchService:
    """双路并行检索 + RRF 融合服务"""

    def __init__(self):
        self._es_client: Optional[AsyncElasticsearch] = None
        self._chunks_cache: Dict[str, Chunk] = {}

    def _get_es_client(self) -> AsyncElasticsearch:
        if self._es_client is None:
            self._es_client = AsyncElasticsearch(settings.ES_URL)
        return self._es_client

    def refresh_cache(self):
        """刷新 Chunk 内存缓存"""
        chunks = data_manager.load_all_chunks()
        self._chunks_cache = {c.chunk_id: c for c in chunks}
        logger.info(f"Search cache refreshed: {len(self._chunks_cache)} chunks")

    def _enrich_result(self, chunk_id: str, score: float, source: str) -> SearchResultItem:
        """补全 Chunk 原文"""
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
        """本地向量检索"""
        top_k = top_k or settings.VECTOR_TOP_K

        # 生成查询向量
        query_vector = await embedding_service.encode_single(query)
        if not query_vector:
            return []

        # 本地检索
        results = vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            filters=filters,
        )

        items = []
        for r in results:
            items.append(self._enrich_result(
                chunk_id=r["chunk_id"],
                score=r["score"],
                source="vector",
            ))

        logger.debug(f"Vector search: {len(items)} results for '{query[:30]}...'")
        return items

    # ──────────────── BM25 检索 ────────────────

    async def bm25_search(
        self, query: str, filters: Optional[dict] = None, top_k: int = None
    ) -> List[SearchResultItem]:
        """ES BM25 关键词检索"""
        top_k = top_k or settings.BM25_TOP_K
        es = self._get_es_client()

        # 构建查询
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
            items = []
            for hit in response["hits"]["hits"]:
                items.append(self._enrich_result(
                    chunk_id=hit["_source"]["chunk_id"],
                    score=hit["_score"],
                    source="bm25",
                ))
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

    # ──────────────── 混合检索 + RRF ────────────────

    async def hybrid_search(
        self, query: str, filters: Optional[dict] = None, top_k: int = None
    ) -> List[SearchResultItem]:
        """双路并行检索 + RRF 融合"""
        final_top_k = top_k or settings.FINAL_TOP_K

        # 确保缓存已加载
        if not self._chunks_cache:
            self.refresh_cache()

        # 并行检索
        vector_task = self.vector_search(query, filters)
        bm25_task = self.bm25_search(query, filters)
        vector_results, bm25_results = await asyncio.gather(
            vector_task, bm25_task, return_exceptions=True
        )

        # 处理异常
        if isinstance(vector_results, Exception):
            logger.error(f"Vector search failed: {vector_results}")
            vector_results = []
        if isinstance(bm25_results, Exception):
            logger.error(f"BM25 search failed: {bm25_results}")
            bm25_results = []

        # RRF 融合
        vector_dicts = [{"chunk_id": r.chunk_id, "score": r.score} for r in vector_results]
        bm25_dicts = [{"chunk_id": r.chunk_id, "score": r.score} for r in bm25_results]

        fused = rrf_fuse([vector_dicts, bm25_dicts], k=settings.RRF_K)

        # 补全并返回 top-K
        results = []
        for item in fused[:final_top_k]:
            results.append(self._enrich_result(
                chunk_id=item["chunk_id"],
                score=item["rrf_score"],
                source="rrf",
            ))

        logger.info(
            f"Hybrid search: vector={len(vector_results)}, bm25={len(bm25_results)}, "
            f"fused={len(results)} for '{query[:30]}...'"
        )
        return results

    async def search_comparison(
        self, query: str, filters: Optional[dict] = None
    ) -> dict:
        """返回三路检索结果对比"""
        if not self._chunks_cache:
            self.refresh_cache()

        vector_results, bm25_results = await asyncio.gather(
            self.vector_search(query, filters),
            self.bm25_search(query, filters),
            return_exceptions=True,
        )

        if isinstance(vector_results, Exception):
            vector_results = []
        if isinstance(bm25_results, Exception):
            bm25_results = []

        # RRF 融合
        vector_dicts = [{"chunk_id": r.chunk_id, "score": r.score} for r in vector_results]
        bm25_dicts = [{"chunk_id": r.chunk_id, "score": r.score} for r in bm25_results]
        fused = rrf_fuse([vector_dicts, bm25_dicts], k=settings.RRF_K)

        rrf_results = []
        for item in fused[:settings.FINAL_TOP_K]:
            rrf_results.append(self._enrich_result(
                chunk_id=item["chunk_id"],
                score=item["rrf_score"],
                source="rrf",
            ))

        return {
            "query": query,
            "vector_results": [r.model_dump() for r in vector_results],
            "bm25_results": [r.model_dump() for r in bm25_results],
            "rrf_results": [r.model_dump() for r in rrf_results],
        }

    async def close(self):
        if self._es_client:
            await self._es_client.close()


search_service = SearchService()
