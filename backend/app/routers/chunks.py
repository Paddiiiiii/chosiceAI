"""Chunk 管理接口"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.models.schemas import Chunk
from app.services.data_manager import data_manager

router = APIRouter(prefix="/api/v1/chunks", tags=["chunks"])


@router.get("", response_model=List[Chunk])
async def list_chunks(
    doc_id: Optional[str] = Query(None, description="文档 ID"),
    chunk_type: Optional[str] = Query(None, description="overview/detail"),
    phase: Optional[str] = Query(None),
    battle_type: Optional[str] = Query(None),
):
    """获取 Chunk 列表（支持过滤）"""
    if doc_id:
        chunks = data_manager.load_chunks(doc_id)
    else:
        chunks = data_manager.load_all_chunks()

    # 过滤
    if chunk_type:
        chunks = [c for c in chunks if c.chunk_type == chunk_type]
    if phase:
        chunks = [c for c in chunks if c.context_tags.phase == phase]
    if battle_type:
        chunks = [c for c in chunks if c.context_tags.battle_type == battle_type]

    return chunks


@router.get("/{chunk_id}", response_model=Chunk)
async def get_chunk(chunk_id: str):
    """获取单个 Chunk 详情"""
    chunk = data_manager.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(404, f"Chunk {chunk_id} not found")
    return chunk


@router.get("/stats/summary")
async def get_chunk_stats():
    """获取 Chunk 统计信息"""
    chunks = data_manager.load_all_chunks()
    stats = {
        "total": len(chunks),
        "by_type": {},
        "by_phase": {},
        "by_battle_type": {},
        "avg_char_count": 0,
    }
    total_chars = 0
    for c in chunks:
        stats["by_type"][c.chunk_type] = stats["by_type"].get(c.chunk_type, 0) + 1
        if c.context_tags.phase:
            stats["by_phase"][c.context_tags.phase] = stats["by_phase"].get(c.context_tags.phase, 0) + 1
        if c.context_tags.battle_type:
            bt = c.context_tags.battle_type
            stats["by_battle_type"][bt] = stats["by_battle_type"].get(bt, 0) + 1
        total_chars += c.metadata.char_count

    stats["avg_char_count"] = round(total_chars / len(chunks)) if chunks else 0
    return stats
