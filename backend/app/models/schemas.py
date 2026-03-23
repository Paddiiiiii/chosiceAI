"""所有 Pydantic 数据模型"""
from __future__ import annotations

from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ──────────────────── Chunk 相关 ────────────────────

class ContextTags(BaseModel):
    phase: str = ""
    battle_type: str = ""
    scope: str = "旅"


class ChunkMetadata(BaseModel):
    source_file: str = ""
    line_start: int = 0
    line_end: int = 0
    char_count: int = 0
    has_ocr_error: bool = False


class Chunk(BaseModel):
    chunk_id: str
    chunk_type: Literal["overview", "detail"] = "detail"
    title: str
    title_chain: str = ""
    parent_id: Optional[str] = None
    children_ids: List[str] = Field(default_factory=list)
    level: int = 0
    text: str = ""
    context_tags: ContextTags = Field(default_factory=ContextTags)
    roles_mentioned: List[str] = Field(default_factory=list)
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    document_id: str = ""


# ──────────────────── 角色相关 ────────────────────

class Role(BaseModel):
    role_id: str
    name: str
    mention_count: int = 0
    status: Literal["approved", "pending", "rejected"] = "approved"  # 审批状态
    source: Literal["manual", "auto"] = "manual"  # 来源：人工/自动提取


class RoleRegistry(BaseModel):
    version: str = "1.0"
    source_files: List[str] = Field(default_factory=list)
    roles: List[Role] = Field(default_factory=list)


# ──────────────────── OCR 纠错 ────────────────────

class CorrectionItem(BaseModel):
    line: int = 0
    original: str = ""
    corrected: str = ""
    type: str = ""  # garbled, missing_char, wrong_char
    status: str = "pending"  # pending, approved, rejected, modified


# ──────────────────── 审核条目 ────────────────────

class ReviewItem(BaseModel):
    item_id: str
    chunk_id: str = ""
    document_id: str = ""
    type: str = ""  # ocr_error, role_annotation, structure
    description: str = ""
    original_text: str = ""
    status: str = "pending"  # pending, resolved, ignored


# ──────────────────── 层级模式 ────────────────────

class LevelPattern(BaseModel):
    level: int
    pattern: str
    description: str = ""
    example: str = ""


# ──────────────────── 同义词 ────────────────────

class SynonymGroup(BaseModel):
    id: int = 0
    terms: List[str] = Field(default_factory=list)


# ──────────────────── 文档管理 ────────────────────

class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    status: str = "uploaded"  # uploaded, correcting, parsing, chunking, indexing, completed, error
    error_message: str = ""
    chunk_count: int = 0
    created_at: str = ""
    updated_at: str = ""


# ──────────────────── 结构树 ────────────────────

class TreeNode(BaseModel):
    id: str = ""
    level: int = 0
    title: str = ""
    children: List[TreeNode] = Field(default_factory=list)
    text: str = ""  # 节点自身文本（概述）
    line_start: int = 0
    line_end: int = 0


TreeNode.model_rebuild()


# ──────────────────── 检索选项 ────────────────────

class RetrievalOptions(BaseModel):
    use_vector: bool = True
    use_bm25: bool = True
    use_graph: bool = True


# ──────────────────── Chat / 路由 ────────────────────

class ChatRequest(BaseModel):
    input: str
    context: Optional[dict] = None  # {"phase": "战斗准备", "battle_type": "进攻战斗"}
    retrieval: Optional[RetrievalOptions] = None


class RoutingBasis(BaseModel):
    chunk_id: str = ""
    title_chain: str = ""
    text_snippet: str = ""


class RoutingResult(BaseModel):
    lead: str = ""
    participants: List[str] = Field(default_factory=list)
    approver: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.0
    basis: Optional[RoutingBasis] = None


class ChatResponse(BaseModel):
    result: RoutingResult
    search_results: Optional[List[dict]] = None


# ──────────────────── 检索结果 ────────────────────

class SearchResultItem(BaseModel):
    chunk_id: str = ""
    title: str = ""
    title_chain: str = ""
    text: str = ""
    score: float = 0.0
    source: str = ""  # vector, bm25, graph, rrf


class SearchComparisonRequest(BaseModel):
    query: str
    filters: Optional[dict] = None
    retrieval: Optional[RetrievalOptions] = None


class SearchComparisonResponse(BaseModel):
    query: str
    vector_results: List[SearchResultItem] = Field(default_factory=list)
    bm25_results: List[SearchResultItem] = Field(default_factory=list)
    graph_results: List[SearchResultItem] = Field(default_factory=list)
    rrf_results: List[SearchResultItem] = Field(default_factory=list)
