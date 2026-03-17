"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.routers import chat, documents, chunks, roles, review, search, synonyms, structure, level_patterns, graph, resolve
from app.services.search import search_service
from app.services.index_builder import index_builder
from app.services.graph_search import graph_search_service
from app.services.graph_builder import graph_builder


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 Military Task Router starting up...")
    # 启动时加载 Chunk 缓存
    try:
        search_service.refresh_cache()
    except Exception as e:
        logger.warning(f"Initial cache load failed (expected on first run): {e}")
    yield
    # 关闭时清理连接
    logger.info("Shutting down...")
    await search_service.close()
    await index_builder.close()
    await graph_search_service.close()
    await graph_builder.close()


app = FastAPI(
    title="任务路由智能系统",
    description="旅长说任意自然语言 → 系统路由到正确的牵头负责角色，并给出依据",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(chunks.router)
app.include_router(roles.router)
app.include_router(review.router)
app.include_router(search.router)
app.include_router(synonyms.router)
app.include_router(structure.router)
app.include_router(level_patterns.router)
app.include_router(graph.router)
app.include_router(resolve.router)


@app.get("/")
async def root():
    return {
        "name": "任务路由智能系统",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
