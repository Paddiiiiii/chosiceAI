"""流程图谱 API — 构建 + 查询"""
from typing import Optional
from fastapi import APIRouter, Query

from app.services.graph_builder import graph_builder
from app.services.graph_search import graph_search_service

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


# ──────────────── 图谱构建 ────────────────

@router.post("/rebuild")
async def rebuild_graph(use_llm: bool = False):
    """
    重建 Neo4j 流程图谱（同步等待完成后返回结果）。

    - use_llm=false（默认）：仅规则抽取（快速，零误差骨架）
    - use_llm=true：规则抽取 + LLM 语义抽取（慢，补充 LED_BY/DEPENDS_ON/PRODUCES）
    """
    try:
        result = await graph_builder.rebuild(use_llm=use_llm)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/stats")
async def graph_stats():
    """返回图谱节点/关系统计"""
    return await graph_search_service.graph_stats()


@router.get("/viz")
async def graph_viz(max_nodes: int = Query(500, ge=1, le=2000)):
    """返回图谱可视化数据（节点+边），供前端渲染"""
    return await graph_search_service.get_graph_for_viz(max_nodes=max_nodes)


# ──────────────── 角色职责查询 ────────────────

@router.get("/role_tasks")
async def role_tasks(
    role: str = Query(..., description="角色名"),
    phase: Optional[str] = Query(None, description="阶段"),
):
    """查某角色在某阶段的所有任务"""
    return await graph_search_service.role_tasks(role=role, phase=phase)


# ──────────────── 任务角色分工 ────────────────

@router.get("/task_roles")
async def task_roles(
    chunk_id: Optional[str] = Query(None),
    task_name: Optional[str] = Query(None),
):
    """查某任务涉及的所有角色（chunk_id 或 task_name 二选一）"""
    return await graph_search_service.task_roles(chunk_id=chunk_id, task_name=task_name)


# ──────────────── 任务拆解 ────────────────

@router.get("/task_decompose")
async def task_decompose(chunk_id: str = Query(...)):
    """查某任务的子步骤"""
    return await graph_search_service.task_decompose(chunk_id=chunk_id)


# ──────────────── 前置依赖 ────────────────

@router.get("/task_prerequisites")
async def task_prerequisites(chunk_id: str = Query(...)):
    """查某任务的前置依赖链"""
    return await graph_search_service.task_prerequisites(chunk_id=chunk_id)


# ──────────────── 任务产物 ────────────────

@router.get("/task_products")
async def task_products(
    chunk_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
):
    """查任务产物（支持按 chunk_id 或 role+phase）"""
    return await graph_search_service.task_products(chunk_id=chunk_id, role=role, phase=phase)


# ──────────────── 任务详情 ────────────────

@router.get("/task_detail")
async def task_detail(chunk_id: str = Query(...)):
    """查某任务的完整信息（图谱关系 + 原文）"""
    from app.services.data_manager import data_manager

    graph_info = await graph_search_service.task_detail(chunk_id=chunk_id)

    chunk = data_manager.get_chunk(chunk_id)
    if chunk:
        graph_info["full_text"] = chunk.text
        graph_info["title_chain"] = chunk.title_chain
        if chunk.parent_id:
            parent_chunk = data_manager.get_chunk(chunk.parent_id)
            if parent_chunk:
                graph_info["parent_overview_text"] = parent_chunk.text

    return graph_info
