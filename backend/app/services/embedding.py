"""Embedding 服务封装（支持 Ollama API）"""
import httpx
from typing import List
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class EmbeddingService:
    def __init__(self):
        self.url = settings.EMBEDDING_URL
        self.model = settings.EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIM

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def encode(self, texts: List[str]) -> List[List[float]]:
        """
        批量文本向量化（通过 Ollama API 逐条请求）。

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        if not texts:
            return []

        embeddings = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for i, text in enumerate(texts):
                try:
                    resp = await client.post(
                        self.url,
                        json={"model": self.model, "prompt": text},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    embedding = data.get("embedding", [])
                    embeddings.append(embedding)

                    if (i + 1) % 20 == 0:
                        logger.info(f"Embedding progress: {i + 1}/{len(texts)}")

                except Exception as e:
                    logger.error(f"Embedding failed for text {i}: {e}")
                    raise

        logger.info(f"Encoded {len(texts)} texts -> {len(embeddings)} vectors (dim={len(embeddings[0]) if embeddings else '?'})")
        return embeddings

    async def encode_single(self, text: str) -> List[float]:
        """单条文本向量化"""
        result = await self.encode([text])
        return result[0] if result else []


embedding_service = EmbeddingService()
