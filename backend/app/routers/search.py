"""检索调试接口"""
from fastapi import APIRouter
from app.models.schemas import SearchComparisonRequest, SearchComparisonResponse
from app.services.search import search_service

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.post("/comparison")
async def search_comparison(req: SearchComparisonRequest):
    """返回向量、BM25、RRF 三路检索结果对比"""
    result = await search_service.search_comparison(
        query=req.query, filters=req.filters
    )
    return result


@router.post("/refresh-cache")
async def refresh_cache():
    """刷新检索缓存"""
    search_service.refresh_cache()
    return {"message": "Cache refreshed", "total_chunks": len(search_service._chunks_cache)}
