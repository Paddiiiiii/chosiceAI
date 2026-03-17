"""检索调试接口"""
from fastapi import APIRouter
from app.models.schemas import SearchComparisonRequest, RetrievalOptions
from app.services.search import search_service

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.post("/comparison")
async def search_comparison(req: SearchComparisonRequest):
    """返回向量、BM25、图谱、RRF 多路检索结果对比（各通道可选）"""
    opts = req.retrieval or RetrievalOptions()
    result = await search_service.search_comparison(
        query=req.query,
        filters=req.filters,
        use_vector=opts.use_vector,
        use_bm25=opts.use_bm25,
        use_graph=opts.use_graph,
    )
    return result


@router.post("/refresh-cache")
async def refresh_cache():
    """刷新检索缓存"""
    search_service.refresh_cache()
    return {"message": "Cache refreshed", "total_chunks": len(search_service._chunks_cache)}
