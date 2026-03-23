"""交叉编码器重排：默认对接 SiliconFlow /rerank（如 bge-reranker-v2-m3）。"""
from __future__ import annotations

from typing import List

import httpx
from loguru import logger

from app.config import settings
from app.models.schemas import SearchResultItem


class RerankService:
    def api_key(self) -> str:
        k = (settings.RERANK_API_KEY or settings.SILICONFLOW_API_KEY or "").strip()
        return k

    def is_available(self) -> bool:
        return bool(settings.RERANK_ENABLED and self.api_key())

    def _doc_text(self, item: SearchResultItem) -> str:
        parts = [item.title_chain, item.title, item.text]
        raw = "\n".join(p for p in parts if p)
        if not raw:
            raw = item.chunk_id
        n = settings.RERANK_MAX_DOC_CHARS
        return raw if len(raw) <= n else raw[:n]

    async def rerank(self, query: str, items: List[SearchResultItem]) -> List[SearchResultItem]:
        """
        按 query 对候选 Chunk 重排序；失败或未配置时原样返回。
        """
        if not items:
            return []
        if not self.is_available():
            return items

        q = (query or "").strip()
        if not q:
            return items

        documents = [self._doc_text(it) for it in items]
        payload = {
            "model": settings.RERANK_MODEL,
            "query": q,
            "documents": documents,
            "top_n": len(documents),
            "return_documents": False,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.RERANK_TIMEOUT) as client:
                resp = await client.post(
                    settings.RERANK_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key()}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"Rerank API failed, using RRF order: {e}")
            return items

        rows = data.get("results") or []
        if not rows:
            logger.warning("Rerank API returned empty results, using RRF order")
            return items

        # 按相关性降序；同分保持 API 顺序
        rows = sorted(
            rows,
            key=lambda r: float(r.get("relevance_score") or r.get("score") or 0.0),
            reverse=True,
        )

        out: List[SearchResultItem] = []
        seen: set[int] = set()
        for r in rows:
            idx = r.get("index")
            if idx is None:
                continue
            try:
                i = int(idx)
            except (TypeError, ValueError):
                continue
            if i < 0 or i >= len(items) or i in seen:
                continue
            seen.add(i)
            sc = float(r.get("relevance_score") or r.get("score") or 0.0)
            out.append(
                items[i].model_copy(update={"score": sc, "source": "rerank"})
            )

        # 补全未出现在结果中的候选（兜底）
        for i, it in enumerate(items):
            if i not in seen:
                out.append(it.model_copy(update={"source": "rerank"}))

        logger.debug(f"Rerank: {len(items)} -> {len(out)} ordered")
        return out


rerank_service = RerankService()
