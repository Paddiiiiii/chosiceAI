"""审核管理接口"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.models.schemas import ReviewItem, CorrectionItem
from app.services.data_manager import data_manager

router = APIRouter(prefix="/api/v1/review", tags=["review"])


class UpdateReviewRequest(BaseModel):
    status: str  # resolved, ignored


class UpdateCorrectionRequest(BaseModel):
    status: str  # approved, rejected, modified
    corrected: Optional[str] = None


# ──────────────── 审核条目 ────────────────

@router.get("/items", response_model=List[ReviewItem])
async def list_reviews(
    doc_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
):
    """获取审核条目列表"""
    if doc_id:
        items = data_manager.load_reviews(doc_id)
    else:
        items = data_manager.load_all_reviews()

    if status:
        items = [i for i in items if i.status == status]
    if type:
        items = [i for i in items if i.type == type]
    return items


@router.put("/items/{item_id}")
async def update_review(item_id: str, doc_id: str, req: UpdateReviewRequest):
    """更新审核条目状态"""
    items = data_manager.load_reviews(doc_id)
    for item in items:
        if item.item_id == item_id:
            item.status = req.status
            data_manager.save_reviews(doc_id, items)
            return item
    raise HTTPException(404, f"Review item {item_id} not found")


# ──────────────── OCR 纠错条目 ────────────────

@router.get("/corrections", response_model=List[CorrectionItem])
async def list_corrections(doc_id: str = Query(...)):
    """获取 OCR 纠错日志"""
    return data_manager.load_corrections(doc_id)


@router.get("/corrections/context")
async def get_correction_context(
    doc_id: str = Query(...),
    line: int = Query(0, description="纠错条目的行号"),
    original: str = Query("", description="纠正前的原文片段"),
    corrected: str = Query("", description="纠正后的文本片段"),
):
    """
    获取纠错条目所在 chunk 的正文。
    优先通过文本内容匹配 chunk（最精确），匹配不到再按行号回退。
    """
    chunks = data_manager.load_chunks(doc_id)

    def _find_chunk_by_text(keyword: str):
        """在所有 chunk 正文中搜索包含 keyword 的最小 chunk"""
        if not keyword:
            return None
        kw_flat = keyword.replace("\n", "").replace(" ", "")
        found = None
        for c in chunks:
            text_flat = c.text.replace("\n", "").replace(" ", "")
            if kw_flat in text_flat:
                if found is None or len(c.text) < len(found.text):
                    found = c
        return found

    best_chunk = None

    # ── 策略1: 在 chunk 正文中搜索 corrected 文本（chunks 是纠正后文本生成的） ──
    best_chunk = _find_chunk_by_text(corrected)

    # ── 策略2: 搜索 original 文本 ──
    if not best_chunk:
        best_chunk = _find_chunk_by_text(original)

    # ── 策略3: 子串模糊匹配（取前20字符搜索） ──
    if not best_chunk:
        for keyword in [corrected, original]:
            if not keyword:
                continue
            sub = keyword.replace("\n", "").replace("。", "").replace("，", "").replace(" ", "")[:20]
            if len(sub) < 4:
                continue
            best_chunk = _find_chunk_by_text(sub)
            if best_chunk:
                break

    # ── 策略4: 行号匹配（最后回退） ──
    if not best_chunk and line > 0:
        best_span = float("inf")
        for c in chunks:
            ls = c.metadata.line_start
            le = c.metadata.line_end
            if ls <= line <= le:
                span = le - ls
                if span < best_span:
                    best_span = span
                    best_chunk = c

    if best_chunk:
        # 决定用哪个文本做高亮标记（优先能在 chunk 中找到的那个）
        highlight = ""
        text_flat = best_chunk.text.replace("\n", "").replace(" ", "")
        if corrected and corrected.replace("\n", "").replace(" ", "") in text_flat:
            highlight = corrected
        elif original and original.replace("\n", "").replace(" ", "") in text_flat:
            highlight = original

        return {
            "chunk_id": best_chunk.chunk_id,
            "title": best_chunk.title,
            "title_chain": best_chunk.title_chain,
            "text": best_chunk.text,
            "highlight": highlight,
        }

    # ── 全部匹配失败，读纠正后文本附近行 ──
    text = data_manager.get_corrected_text(doc_id)
    if not text:
        text = data_manager.get_original_text(doc_id)
    if not text:
        raise HTTPException(404, "文档文本未找到")

    all_lines = text.split("\n")
    target = max(1, line or 1)
    start = max(0, target - 1 - 5)
    end = min(len(all_lines), target - 1 + 6)
    fallback_text = "\n".join(all_lines[start:end])

    return {
        "chunk_id": "",
        "title": f"第 {line} 行附近" if line else "未匹配到 Chunk",
        "title_chain": "",
        "text": fallback_text,
        "highlight": original or corrected or "",
    }


@router.put("/corrections/{index}")
async def update_correction(index: int, doc_id: str, req: UpdateCorrectionRequest):
    """更新纠错条目"""
    items = data_manager.load_corrections(doc_id)
    if index < 0 or index >= len(items):
        raise HTTPException(404, "Correction index out of range")

    items[index].status = req.status
    if req.corrected is not None:
        items[index].corrected = req.corrected
    data_manager.save_corrections(doc_id, items)
    return items[index]


@router.get("/stats")
async def review_stats():
    """审核统计"""
    docs = data_manager.list_documents()
    total_reviews = 0
    pending = 0
    resolved = 0
    total_corrections = 0
    corrections_pending = 0

    for doc in docs:
        reviews = data_manager.load_reviews(doc.doc_id)
        total_reviews += len(reviews)
        pending += sum(1 for r in reviews if r.status == "pending")
        resolved += sum(1 for r in reviews if r.status == "resolved")

        corrections = data_manager.load_corrections(doc.doc_id)
        total_corrections += len(corrections)
        corrections_pending += sum(1 for c in corrections if c.status == "pending")

    return {
        "total_reviews": total_reviews,
        "pending_reviews": pending,
        "resolved_reviews": resolved,
        "total_corrections": total_corrections,
        "pending_corrections": corrections_pending,
    }
