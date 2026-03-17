"""文档结构树接口"""
from fastapi import APIRouter, HTTPException
from typing import Optional

from app.services.data_manager import data_manager

router = APIRouter(prefix="/api/v1/structure", tags=["structure"])


@router.get("/{doc_id}")
async def get_structure(doc_id: str):
    """获取文档结构树"""
    tree = data_manager.load_tree(doc_id)
    if not tree:
        raise HTTPException(404, f"Structure tree for {doc_id} not found")
    return tree


@router.get("")
async def list_all_structures():
    """获取所有文档的结构树摘要"""
    docs = data_manager.list_documents()
    result = []
    for doc in docs:
        tree = data_manager.load_tree(doc.doc_id)
        result.append({
            "doc_id": doc.doc_id,
            "filename": doc.filename,
            "has_tree": tree is not None,
            "status": doc.status,
        })
    return result
