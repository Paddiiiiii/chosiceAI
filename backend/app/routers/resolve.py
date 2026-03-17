"""任务解析接口 — 自然语言 → 匹配 Task 节点"""
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.schemas import RetrievalOptions
from app.services.search import search_service
from app.services.graph_search import graph_search_service


class ResolveRequest(BaseModel):
    query: str
    top_k: int = 3
    retrieval: Optional[RetrievalOptions] = None


router = APIRouter(prefix="/api/v1", tags=["resolve"])


@router.post("/resolve")
async def resolve(req: ResolveRequest):
    """
    自然语言 → 匹配到的 Task 节点。

    内部流程（无 LLM）：
    1. 向量+BM25+图谱 混合检索 → Top-K 候选 Chunk
    2. 用 chunk_id 关联 Neo4j Task 节点，补充图谱元数据
    """
    opts = req.retrieval or RetrievalOptions()

    search_results = await search_service.hybrid_search(
        query=req.query,
        top_k=req.top_k,
        use_vector=opts.use_vector,
        use_bm25=opts.use_bm25,
        use_graph=opts.use_graph,
    )

    matches = []
    for sr in search_results:
        graph_detail = await graph_search_service.task_detail(chunk_id=sr.chunk_id)

        has_subtasks = False
        node_type = "Task"
        if "graph_info" in graph_detail:
            decompose = await graph_search_service.task_decompose(chunk_id=sr.chunk_id)
            has_subtasks = len(decompose.get("subtasks", [])) > 0
            node_type = "TaskGroup" if has_subtasks else "Task"

        matches.append({
            "chunk_id": sr.chunk_id,
            "task_name": graph_detail.get("task") or sr.title,
            "title_chain": sr.title_chain,
            "node_type": node_type,
            "phase": "",
            "has_subtasks": has_subtasks,
            "score": sr.score,
        })

    return {"matches": matches}
