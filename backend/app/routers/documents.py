"""文档管理接口"""
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from typing import List
from loguru import logger

from app.models.schemas import DocumentInfo
from app.services.data_manager import data_manager
from app.services.document_processor import document_processor
from app.services.index_builder import index_builder

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.get("", response_model=List[DocumentInfo])
async def list_documents():
    """获取所有文档列表"""
    return data_manager.list_documents()


@router.get("/{doc_id}", response_model=DocumentInfo)
async def get_document(doc_id: str):
    """获取单个文档信息"""
    doc = data_manager.get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Document {doc_id} not found")
    return doc


@router.post("/upload", response_model=DocumentInfo)
async def upload_document(file: UploadFile = File(...)):
    """上传新的 OCR 文本文件"""
    content = await file.read()
    text = content.decode("utf-8")
    doc = data_manager.create_document(filename=file.filename, text_content=text)
    logger.info(f"Uploaded document: {doc.doc_id} ({file.filename})")
    return doc


@router.post("/{doc_id}/process")
async def process_document(doc_id: str, background_tasks: BackgroundTasks):
    """触发文档处理（Step 1 全流程）"""
    doc = data_manager.get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Document {doc_id} not found")

    background_tasks.add_task(document_processor.process_document, doc_id)
    return {"message": f"Processing started for {doc_id}", "doc_id": doc_id}


@router.post("/{doc_id}/reprocess")
async def reprocess_document(doc_id: str, background_tasks: BackgroundTasks):
    """从结构解析步骤开始重新处理"""
    doc = data_manager.get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Document {doc_id} not found")

    background_tasks.add_task(document_processor.reprocess_from_parsing, doc_id)
    return {"message": f"Re-processing started for {doc_id}"}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档"""
    data_manager.delete_document(doc_id)
    return {"message": f"Document {doc_id} deleted"}


@router.post("/build-indexes")
async def build_indexes(background_tasks: BackgroundTasks):
    """构建/重建所有索引（Step 2）"""
    background_tasks.add_task(index_builder.build_all_indexes)
    return {"message": "Index building started"}


@router.get("/{doc_id}/original-text")
async def get_original_text(doc_id: str):
    """获取原始文本"""
    text = data_manager.get_original_text(doc_id)
    return {"doc_id": doc_id, "text": text}


@router.get("/{doc_id}/corrected-text")
async def get_corrected_text(doc_id: str):
    """获取纠错后文本"""
    text = data_manager.get_corrected_text(doc_id)
    return {"doc_id": doc_id, "text": text}
