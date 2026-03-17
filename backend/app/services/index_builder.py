"""Step 2 - 索引构建服务（本地向量存储 + Elasticsearch）"""
from typing import List, Optional
from loguru import logger
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.config import settings
from app.models.schemas import Chunk, SynonymGroup
from app.services.embedding import embedding_service
from app.services.data_manager import data_manager
from app.services.vector_store import vector_store


class IndexBuilder:
    """构建本地向量索引和 ES BM25 索引"""

    def __init__(self):
        self._es_client: Optional[AsyncElasticsearch] = None

    # ──────────────── 向量索引 ────────────────

    async def build_vector_index(self, chunks: List[Chunk]) -> None:
        """构建本地向量索引"""
        if not chunks:
            logger.warning("No chunks to index")
            return

        # 生成向量
        texts = [f"{c.title_chain}\n{c.text}" for c in chunks]
        logger.info(f"Generating embeddings for {len(texts)} chunks...")
        embeddings = await embedding_service.encode(texts)

        # 构建元数据
        chunk_ids = [c.chunk_id for c in chunks]
        metadata_list = [
            {
                "phase": c.context_tags.phase,
                "battle_type": c.context_tags.battle_type,
                "scope": c.context_tags.scope,
                "chunk_type": c.chunk_type,
                "document_id": c.document_id,
            }
            for c in chunks
        ]

        # 先清空旧数据
        vector_store.drop()

        # 插入并持久化
        vector_store.insert(chunk_ids, embeddings, metadata_list)
        vector_store.save()

        logger.info(f"Vector index built: {len(chunks)} vectors")

    # ──────────────── Elasticsearch ────────────────

    def _get_es_client(self) -> AsyncElasticsearch:
        if self._es_client is None:
            self._es_client = AsyncElasticsearch(settings.ES_URL)
        return self._es_client

    def _build_synonym_list(self) -> List[str]:
        """从同义词配置构建 ES 同义词列表"""
        synonyms = data_manager.load_synonyms()
        return [", ".join(s.terms) for s in synonyms if len(s.terms) >= 2]

    async def build_es_index(self, chunks: List[Chunk]) -> None:
        """构建 ES BM25 索引"""
        if not chunks:
            logger.warning("No chunks to index in ES")
            return

        es = self._get_es_client()
        index_name = settings.ES_INDEX
        synonym_list = self._build_synonym_list()

        # 删除旧索引
        if await es.indices.exists(index=index_name):
            await es.indices.delete(index=index_name)
            logger.info(f"Deleted existing ES index: {index_name}")

        # 创建新索引
        body = {
            "settings": {
                "analysis": {
                    "filter": {
                        "military_synonyms": {
                            "type": "synonym",
                            "synonyms": synonym_list,
                        }
                    },
                    "analyzer": {
                        "military_cn_analyzer": {
                            "tokenizer": "ik_max_word",
                            "filter": ["lowercase", "military_synonyms"],
                        }
                    },
                }
            },
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": "ik_smart"},
                    "title_chain": {"type": "text", "analyzer": "ik_smart"},
                    "text": {"type": "text", "analyzer": "military_cn_analyzer"},
                    "phase": {"type": "keyword"},
                    "battle_type": {"type": "keyword"},
                    "scope": {"type": "keyword"},
                    "chunk_type": {"type": "keyword"},
                    "roles_mentioned": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                }
            },
        }
        await es.indices.create(index=index_name, body=body)
        logger.info(f"Created ES index: {index_name}")

        # 批量写入
        actions = [
            {
                "_index": index_name,
                "_id": c.chunk_id,
                "_source": {
                    "chunk_id": c.chunk_id,
                    "title": c.title,
                    "title_chain": c.title_chain,
                    "text": c.text,
                    "phase": c.context_tags.phase,
                    "battle_type": c.context_tags.battle_type,
                    "scope": c.context_tags.scope,
                    "chunk_type": c.chunk_type,
                    "roles_mentioned": c.roles_mentioned,
                    "document_id": c.document_id,
                },
            }
            for c in chunks
        ]
        success, errors = await async_bulk(es, actions)
        logger.info(f"ES bulk insert: {success} success, {len(errors) if errors else 0} errors")

    # ──────────────── 统一构建 ────────────────

    async def build_all_indexes(self) -> dict:
        """从所有已完成的文档构建索引"""
        chunks = data_manager.load_all_chunks()
        logger.info(f"Building indexes for {len(chunks)} total chunks")

        await self.build_vector_index(chunks)
        await self.build_es_index(chunks)

        return {"total_chunks": len(chunks), "status": "success"}

    async def close(self):
        if self._es_client:
            await self._es_client.close()


index_builder = IndexBuilder()
