"""JSON 数据文件管理"""
import json
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from loguru import logger

from app.config import settings
from app.models.schemas import (
    Chunk, RoleRegistry, Role, CorrectionItem,
    ReviewItem, LevelPattern, SynonymGroup, DocumentInfo, TreeNode,
)

# ──────────────── 默认角色关键词 ────────────────

DEFAULT_ROLE_KEYWORDS = [
    "指挥员", "参谋长", "筹划决策要素", "侦察情报要素",
    "指挥控制要素", "指挥保障要素", "政治工作要素",
    "后装保障要素", "后方指挥员", "作战部门", "作训部门",
    "保障部长", "机要部门", "旅政治工作部", "指挥机关",
    "战勤部门", "各业务部门", "各指挥要素",
]

# ──────────────── 默认层级模式 ────────────────

DEFAULT_LEVEL_PATTERNS = [
    LevelPattern(level=1, pattern=r'^第[一二三四五六七八九十百]+章\s*(.+)', description="第X章", example="第二章 合同战术基本理论"),
    LevelPattern(level=2, pattern=r'^第[一二三四五六七八九十百]+节\s*(.+)', description="第X节", example="第一节 进攻战斗"),
    LevelPattern(level=3, pattern=r'^[一二三四五六七八九十]+、(.+)', description="X、", example="一、战斗准备"),
    LevelPattern(level=4, pattern=r'^（[一二三四五六七八九十]+）(.+)', description="（X）", example="（一）传达任务"),
    LevelPattern(level=5, pattern=r'^\d+[\.．、](.+)', description="N.", example="1.下达预先号令"),
    LevelPattern(level=6, pattern=r'^（(\d+)）(.+)', description="（N）", example="（1）领会上级意图"),
    LevelPattern(level=7, pattern=r'^[①②③④⑤⑥⑦⑧⑨⑩](.+)', description="①②③", example="①本级任务"),
]

# ──────────────── 默认同义词 ────────────────

DEFAULT_SYNONYMS = [
    SynonymGroup(id=1, terms=["三情", "敌情 我情 战场环境"]),
    SynonymGroup(id=2, terms=["后装", "后勤保障 装备保障"]),
    SynonymGroup(id=3, terms=["筹划决策要素", "筹划要素"]),
    SynonymGroup(id=4, terms=["侦察情报要素", "情报要素"]),
    SynonymGroup(id=5, terms=["指挥保障要素", "通信保障要素"]),
]


class DataManager:
    """管理所有 JSON 数据文件的读写"""

    def __init__(self):
        self._ensure_dirs()
        self._ensure_defaults()

    def _ensure_dirs(self):
        settings.data_path.mkdir(parents=True, exist_ok=True)
        settings.docs_path.mkdir(parents=True, exist_ok=True)

    def _ensure_defaults(self):
        """确保默认配置文件存在"""
        if not self._file("level_patterns.json").exists():
            self.save_level_patterns(DEFAULT_LEVEL_PATTERNS)
        if not self._file("synonyms.json").exists():
            self.save_synonyms(DEFAULT_SYNONYMS)
        if not self._file("role_registry.json").exists():
            roles = [Role(role_id=f"R{i+1:02d}", name=name, mention_count=0)
                     for i, name in enumerate(DEFAULT_ROLE_KEYWORDS)]
            self.save_role_registry(RoleRegistry(roles=roles))
        if not self._file("documents.json").exists():
            self._write_json("documents.json", [])

    def _file(self, name: str) -> Path:
        return settings.data_path / name

    def _doc_dir(self, doc_id: str) -> Path:
        p = settings.docs_path / doc_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _read_json(self, path: Path) -> any:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return None

    def _write_json(self, name_or_path, data) -> None:
        if isinstance(name_or_path, str):
            path = self._file(name_or_path)
        else:
            path = name_or_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    # ──────────────── 文档管理 ────────────────

    def list_documents(self) -> List[DocumentInfo]:
        data = self._read_json(self._file("documents.json")) or []
        return [DocumentInfo(**d) for d in data]

    def get_document(self, doc_id: str) -> Optional[DocumentInfo]:
        for doc in self.list_documents():
            if doc.doc_id == doc_id:
                return doc
        return None

    def create_document(self, filename: str, text_content: str) -> DocumentInfo:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        doc = DocumentInfo(
            doc_id=doc_id,
            filename=filename,
            status="uploaded",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        # 保存原始文本
        doc_dir = self._doc_dir(doc_id)
        (doc_dir / "original.txt").write_text(text_content, encoding="utf-8")
        # 更新文档列表
        docs = self.list_documents()
        docs.append(doc)
        self._write_json("documents.json", [d.model_dump() for d in docs])
        return doc

    def update_document(self, doc: DocumentInfo) -> None:
        doc.updated_at = datetime.now().isoformat()
        docs = self.list_documents()
        for i, d in enumerate(docs):
            if d.doc_id == doc.doc_id:
                docs[i] = doc
                break
        self._write_json("documents.json", [d.model_dump() for d in docs])

    def delete_document(self, doc_id: str) -> None:
        docs = [d for d in self.list_documents() if d.doc_id != doc_id]
        self._write_json("documents.json", [d.model_dump() for d in docs])
        import shutil
        doc_dir = self._doc_dir(doc_id)
        if doc_dir.exists():
            shutil.rmtree(doc_dir)

    def get_original_text(self, doc_id: str) -> str:
        path = self._doc_dir(doc_id) / "original.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_corrected_text(self, doc_id: str) -> str:
        path = self._doc_dir(doc_id) / "corrected_text.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def save_corrected_text(self, doc_id: str, text: str) -> None:
        (self._doc_dir(doc_id) / "corrected_text.txt").write_text(text, encoding="utf-8")

    # ──────────────── Chunks ────────────────

    def load_chunks(self, doc_id: str) -> List[Chunk]:
        data = self._read_json(self._doc_dir(doc_id) / "chunks.json") or []
        return [Chunk(**c) for c in data]

    def save_chunks(self, doc_id: str, chunks: List[Chunk]) -> None:
        self._write_json(
            self._doc_dir(doc_id) / "chunks.json",
            [c.model_dump() for c in chunks],
        )

    def load_all_chunks(self) -> List[Chunk]:
        all_chunks = []
        for doc in self.list_documents():
            if doc.status == "completed":
                all_chunks.extend(self.load_chunks(doc.doc_id))
        return all_chunks

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        for doc in self.list_documents():
            for chunk in self.load_chunks(doc.doc_id):
                if chunk.chunk_id == chunk_id:
                    return chunk
        return None

    # ──────────────── 纠错日志 ────────────────

    def load_corrections(self, doc_id: str) -> List[CorrectionItem]:
        data = self._read_json(self._doc_dir(doc_id) / "correction_log.json") or []
        return [CorrectionItem(**c) for c in data]

    def save_corrections(self, doc_id: str, items: List[CorrectionItem]) -> None:
        self._write_json(
            self._doc_dir(doc_id) / "correction_log.json",
            [c.model_dump() for c in items],
        )

    # ──────────────── 审核条目 ────────────────

    def load_reviews(self, doc_id: str) -> List[ReviewItem]:
        data = self._read_json(self._doc_dir(doc_id) / "review_items.json") or []
        return [ReviewItem(**r) for r in data]

    def save_reviews(self, doc_id: str, items: List[ReviewItem]) -> None:
        self._write_json(
            self._doc_dir(doc_id) / "review_items.json",
            [r.model_dump() for r in items],
        )

    def load_all_reviews(self) -> List[ReviewItem]:
        all_reviews = []
        for doc in self.list_documents():
            all_reviews.extend(self.load_reviews(doc.doc_id))
        return all_reviews

    # ──────────────── 结构树 ────────────────

    def load_tree(self, doc_id: str) -> Optional[dict]:
        return self._read_json(self._doc_dir(doc_id) / "chapter_tree.json")

    def save_tree(self, doc_id: str, tree: dict) -> None:
        self._write_json(self._doc_dir(doc_id) / "chapter_tree.json", tree)

    # ──────────────── 角色注册表 ────────────────

    def load_role_registry(self) -> RoleRegistry:
        data = self._read_json(self._file("role_registry.json"))
        return RoleRegistry(**data) if data else RoleRegistry()

    def save_role_registry(self, registry: RoleRegistry) -> None:
        self._write_json("role_registry.json", registry.model_dump())

    # ──────────────── 层级模式 ────────────────

    def load_level_patterns(self) -> List[LevelPattern]:
        data = self._read_json(self._file("level_patterns.json")) or []
        return [LevelPattern(**p) for p in data]

    def save_level_patterns(self, patterns: List[LevelPattern]) -> None:
        self._write_json("level_patterns.json", [p.model_dump() for p in patterns])

    # ──────────────── 同义词 ────────────────

    def load_synonyms(self) -> List[SynonymGroup]:
        data = self._read_json(self._file("synonyms.json")) or []
        return [SynonymGroup(**s) for s in data]

    def save_synonyms(self, synonyms: List[SynonymGroup]) -> None:
        self._write_json("synonyms.json", [s.model_dump() for s in synonyms])


data_manager = DataManager()
