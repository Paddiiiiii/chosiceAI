"""轻量级本地向量存储（替代 Milvus，适用于 Windows / 小规模数据）
使用 numpy 做余弦相似度检索，数据持久化到 JSON 文件。
对 ~200 个 chunk 性能完全足够。
"""
import json
import numpy as np
from typing import List, Dict, Optional
from pathlib import Path
from loguru import logger

from app.config import settings


class LocalVectorStore:
    """基于 numpy 的本地向量存储"""

    def __init__(self):
        self._vectors: Optional[np.ndarray] = None  # shape: (n, dim)
        self._metadata: List[Dict] = []  # 每个向量对应的元数据
        self._store_path = Path(settings.DATA_DIR) / "vector_store.json"
        self._loaded = False

    def _ensure_loaded(self):
        """懒加载"""
        if not self._loaded and self._store_path.exists():
            self.load()

    def insert(self, chunk_ids: List[str], vectors: List[List[float]], metadata_list: List[Dict]):
        """插入向量和元数据"""
        self._vectors = np.array(vectors, dtype=np.float32)
        self._metadata = []
        for i, chunk_id in enumerate(chunk_ids):
            meta = metadata_list[i] if i < len(metadata_list) else {}
            meta["chunk_id"] = chunk_id
            self._metadata.append(meta)
        self._loaded = True
        logger.info(f"Inserted {len(chunk_ids)} vectors into local store")

    def save(self):
        """持久化到文件"""
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "vectors": self._vectors.tolist() if self._vectors is not None else [],
            "metadata": self._metadata,
        }
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        logger.info(f"Vector store saved: {len(self._metadata)} vectors -> {self._store_path}")

    def load(self):
        """从文件加载"""
        if not self._store_path.exists():
            logger.warning(f"Vector store file not found: {self._store_path}")
            return
        with open(self._store_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._vectors = np.array(data["vectors"], dtype=np.float32) if data["vectors"] else None
        self._metadata = data["metadata"]
        self._loaded = True
        logger.info(f"Vector store loaded: {len(self._metadata)} vectors")

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        余弦相似度检索

        Returns:
            [{"chunk_id": "xxx", "score": 0.85}, ...]
        """
        self._ensure_loaded()

        if self._vectors is None or len(self._metadata) == 0:
            return []

        query = np.array(query_vector, dtype=np.float32)

        # 先按过滤条件筛选索引
        valid_indices = self._apply_filters(filters)
        if not valid_indices:
            return []

        # 取出有效向量
        valid_vectors = self._vectors[valid_indices]

        # 余弦相似度 = dot(a, b) / (|a| * |b|)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []

        vec_norms = np.linalg.norm(valid_vectors, axis=1)
        # 避免除零
        vec_norms = np.where(vec_norms == 0, 1e-10, vec_norms)

        similarities = np.dot(valid_vectors, query) / (vec_norms * query_norm)

        # 取 top-k
        k = min(top_k, len(similarities))
        top_indices = np.argsort(similarities)[::-1][:k]

        results = []
        for idx in top_indices:
            orig_idx = valid_indices[idx]
            results.append({
                "chunk_id": self._metadata[orig_idx]["chunk_id"],
                "score": float(similarities[idx]),
            })

        return results

    def _apply_filters(self, filters: Optional[Dict]) -> List[int]:
        """返回满足过滤条件的索引列表"""
        if not filters:
            return list(range(len(self._metadata)))

        valid = []
        for i, meta in enumerate(self._metadata):
            match = True
            for key, value in filters.items():
                if value and meta.get(key) != value:
                    match = False
                    break
            if match:
                valid.append(i)
        return valid

    def drop(self):
        """清空存储"""
        self._vectors = None
        self._metadata = []
        if self._store_path.exists():
            self._store_path.unlink()
        logger.info("Vector store dropped")

    @property
    def count(self) -> int:
        self._ensure_loaded()
        return len(self._metadata)


# 全局单例
vector_store = LocalVectorStore()
