"""Milvus 向量存储：建库、全量重建索引、过滤检索（COSINE + HNSW）。"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Dict, List, Optional

from loguru import logger
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.config import settings

# 与 Chunk / 索引构建侧字段一致（VARCHAR 需声明 max_length）
_CHUNK_ID_MAX = 256
_TAG_MAX = 128
_CHUNK_TYPE_MAX = 32
_DOC_ID_MAX = 256

_INDEX_TYPE = "HNSW"
_METRIC = "COSINE"
_HNSW_M = 16
_HNSW_EF_CONSTRUCTION = 256
_SEARCH_EF = 64

_INSERT_BATCH = 512


def _milvus_str_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _filter_expr(filters: Optional[Dict[str, Any]]) -> Optional[str]:
    if not filters:
        return None
    parts: List[str] = []
    if filters.get("phase"):
        parts.append(f"phase == {_milvus_str_literal(str(filters['phase']))}")
    if filters.get("battle_type"):
        parts.append(f"battle_type == {_milvus_str_literal(str(filters['battle_type']))}")
    if filters.get("scope"):
        parts.append(f"scope == {_milvus_str_literal(str(filters['scope']))}")
    if not parts:
        return None
    return " and ".join(parts)


class MilvusVectorStore:
    """Milvus 单例：同步 SDK 通过 asyncio.to_thread 挂到事件循环，并用 asyncio.Lock 串行化调用。"""

    def __init__(self) -> None:
        self._io_lock = asyncio.Lock()

    def _connect_sync(self) -> None:
        alias = "default"
        if connections.has_connection(alias):
            return
        connections.connect(
            alias=alias,
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )
        logger.info(
            "Milvus connected: {}:{} collection={}",
            settings.MILVUS_HOST,
            settings.MILVUS_PORT,
            settings.MILVUS_COLLECTION,
        )

    def _disconnect_sync(self) -> None:
        alias = "default"
        if connections.has_connection(alias):
            connections.disconnect(alias)
            logger.info("Milvus disconnected")

    def _schema(self) -> CollectionSchema:
        dim = settings.EMBEDDING_DIM
        fields = [
            FieldSchema(
                name="chunk_id",
                dtype=DataType.VARCHAR,
                is_primary=True,
                auto_id=False,
                max_length=_CHUNK_ID_MAX,
            ),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
            FieldSchema(name="phase", dtype=DataType.VARCHAR, max_length=_TAG_MAX),
            FieldSchema(name="battle_type", dtype=DataType.VARCHAR, max_length=_TAG_MAX),
            FieldSchema(name="scope", dtype=DataType.VARCHAR, max_length=_TAG_MAX),
            FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=_CHUNK_TYPE_MAX),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=_DOC_ID_MAX),
        ]
        return CollectionSchema(fields=fields, description="Military manual chunks")

    def _sync_rebuild(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        metadata_list: List[Dict[str, Any]],
    ) -> None:
        self._connect_sync()
        name = settings.MILVUS_COLLECTION

        if utility.has_collection(name):
            utility.drop_collection(name)
            logger.info("Milvus collection dropped: {}", name)

        if not chunk_ids:
            logger.info("Milvus rebuild skipped: no chunks")
            return

        dim = settings.EMBEDDING_DIM
        for i, v in enumerate(vectors):
            if len(v) != dim:
                raise ValueError(
                    f"Embedding dim mismatch at row {i}: got {len(v)}, expected {dim}"
                )

        schema = self._schema()
        collection = Collection(name=name, schema=schema)

        phases: List[str] = []
        battle_types: List[str] = []
        scopes: List[str] = []
        chunk_types: List[str] = []
        document_ids: List[str] = []
        for i, meta in enumerate(metadata_list):
            phases.append(str(meta.get("phase") or ""))
            battle_types.append(str(meta.get("battle_type") or ""))
            scopes.append(str(meta.get("scope") or ""))
            chunk_types.append(str(meta.get("chunk_type") or ""))
            document_ids.append(str(meta.get("document_id") or ""))

        total = len(chunk_ids)
        for start in range(0, total, _INSERT_BATCH):
            end = min(start + _INSERT_BATCH, total)
            collection.insert(
                [
                    chunk_ids[start:end],
                    [list(map(float, v)) for v in vectors[start:end]],
                    phases[start:end],
                    battle_types[start:end],
                    scopes[start:end],
                    chunk_types[start:end],
                    document_ids[start:end],
                ]
            )
            logger.debug("Milvus insert batch {}-{}", start, end)

        collection.flush()
        index_params = {
            "index_type": _INDEX_TYPE,
            "metric_type": _METRIC,
            "params": {"M": _HNSW_M, "efConstruction": _HNSW_EF_CONSTRUCTION},
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        collection.load()
        logger.info("Milvus rebuild done: {} entities", collection.num_entities)

    def _sync_search(
        self,
        query_vector: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        self._connect_sync()
        name = settings.MILVUS_COLLECTION
        if not utility.has_collection(name):
            return []

        collection = Collection(name)
        if collection.num_entities == 0:
            return []

        collection.load()
        expr = _filter_expr(filters)
        dim = settings.EMBEDDING_DIM
        if len(query_vector) != dim:
            logger.warning("Query vector dim {} != {}", len(query_vector), dim)
            return []

        q = [list(map(float, query_vector))]
        search_params = {"metric_type": _METRIC, "params": {"ef": _SEARCH_EF}}
        limit = max(1, min(top_k, 16384))

        raw = collection.search(
            data=q,
            anns_field="embedding",
            param=search_params,
            limit=limit,
            expr=expr,
            output_fields=["chunk_id"],
            consistency_level="Strong",
        )

        out: List[Dict[str, Any]] = []
        for hits in raw:
            for hit in hits:
                # COSINE：distance = 1 - cos_sim，越小越相似
                cos_sim = 1.0 - float(hit.distance)
                if not math.isfinite(cos_sim):
                    cos_sim = 0.0
                score = max(0.0, min(1.0, cos_sim))
                cid = hit.id or getattr(hit, "pk", None)
                if cid is None and getattr(hit, "entity", None):
                    cid = hit.entity.get("chunk_id")
                if cid is None:
                    continue
                out.append({"chunk_id": str(cid), "score": score})
        return out

    async def rebuild(
        self,
        chunk_ids: List[str],
        vectors: List[List[float]],
        metadata_list: List[Dict[str, Any]],
    ) -> None:
        async with self._io_lock:
            await asyncio.to_thread(self._sync_rebuild, chunk_ids, vectors, metadata_list)

    async def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        async with self._io_lock:
            return await asyncio.to_thread(
                self._sync_search, query_vector, top_k, filters
            )

    async def shutdown(self) -> None:
        async with self._io_lock:
            await asyncio.to_thread(self._disconnect_sync)


vector_store = MilvusVectorStore()
