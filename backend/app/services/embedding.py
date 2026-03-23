"""Embedding 服务封装（主通道 Ollama，备用 SiliconFlow，失败时回退重试）"""
import httpx
from typing import List, Optional
from loguru import logger

from app.config import settings


class EmbeddingService:
    def __init__(self):
        self.url = settings.EMBEDDING_URL
        self.model = settings.EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIM
        self.sf_url = settings.SILICONFLOW_EMBEDDING_URL
        self.sf_model = settings.SILICONFLOW_EMBEDDING_MODEL
        self.sf_api_key = settings.SILICONFLOW_API_KEY

    async def _call_ollama(self, client: httpx.AsyncClient, text: str) -> Optional[List[float]]:
        """调用 Ollama 主通道"""
        resp = await client.post(
            self.url,
            json={"model": self.model, "prompt": text},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("embedding", [])

    async def _call_siliconflow(self, client: httpx.AsyncClient, text: str) -> Optional[List[float]]:
        """调用 SiliconFlow 备用通道"""
        resp = await client.post(
            self.sf_url,
            headers={"Authorization": f"Bearer {self.sf_api_key}"},
            json={"model": self.sf_model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        return items[0].get("embedding", []) if items else []

    async def _encode_one(self, client: httpx.AsyncClient, text: str, idx: int) -> Optional[List[float]]:
        """
        单条文本向量化，双通道回退：主通道(Ollama) -> 备用(SiliconFlow) -> 主通道重试
        """
        # 1. 先试主通道
        try:
            return await self._call_ollama(client, text)
        except Exception as e:
            logger.warning(f"Embedding Ollama failed for text {idx}, trying SiliconFlow: {e}")

        # 2. 备用通道 SiliconFlow
        try:
            return await self._call_siliconflow(client, text)
        except Exception as e:
            logger.warning(f"Embedding SiliconFlow failed for text {idx}, retrying Ollama: {e}")

        # 3. 再次尝试主通道
        try:
            return await self._call_ollama(client, text)
        except Exception as e:
            logger.error(f"Embedding failed for text {idx}: {e}")
            return None

    async def encode(self, texts: List[str]) -> List[List[float]]:
        """
        批量文本向量化（逐条请求 Ollama API）。
        单条失败时用零向量占位，不会导致整批崩溃。
        """
        if not texts:
            return []

        embeddings = []
        failed = 0
        async with httpx.AsyncClient(timeout=60.0) as client:
            for i, text in enumerate(texts):
                embedding = await self._encode_one(client, text, i)
                if embedding is None:
                    embeddings.append([0.0] * self.dim)
                    failed += 1
                else:
                    embeddings.append(embedding)

                if (i + 1) % 20 == 0:
                    logger.info(f"Embedding progress: {i + 1}/{len(texts)}")

        if failed:
            logger.warning(f"Embedding done: {len(texts)} texts, {failed} failed (zero-filled)")
        else:
            logger.info(f"Encoded {len(texts)} texts -> {len(embeddings)} vectors (dim={self.dim})")
        return embeddings

    async def encode_single(self, text: str) -> List[float]:
        """单条文本向量化（用于在线检索），失败时返回空列表"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                result = await self._encode_one(client, text, 0)
                return result if result is not None else []
        except Exception as e:
            logger.warning(f"encode_single failed, vector search will be skipped: {e}")
            return []

    def text_for_vector_retrieval(self, query: str) -> str:
        """与建索引段落格式对齐的可选前缀（如 BGE 检索指令），默认原样 query。"""
        q = (query or "").strip()
        prefix = (settings.EMBEDDING_QUERY_PREFIX or "").strip()
        if not prefix:
            return q
        if prefix.endswith(("\n", "。", "：", ":")):
            return f"{prefix}{q}"
        return f"{prefix} {q}"

    async def encode_for_vector_search(self, query: str) -> List[float]:
        """向量检索专用：先套用 EMBEDDING_QUERY_PREFIX 再向量化。"""
        return await self.encode_single(self.text_for_vector_retrieval(query))


embedding_service = EmbeddingService()
