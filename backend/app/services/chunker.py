"""Step 1.3 - 通用分块服务"""
from typing import List, Optional
from loguru import logger

from app.models.schemas import Chunk, ContextTags, ChunkMetadata
from app.services.structure_parser import ParsedNode


# context_tags 推导关键词
PHASE_KEYWORDS = ["战斗准备", "战斗实施", "主要样式"]
BATTLE_TYPE_KEYWORDS = ["进攻战斗", "防御战斗"]


class ChunkerService:
    """将结构树转化为 Chunk 列表"""

    def chunk_tree(
        self,
        root: ParsedNode,
        document_id: str,
        source_file: str,
        min_chars: int = 50,
        max_chars: int = 800,
    ) -> List[Chunk]:
        """
        将结构树转化为 Chunk 列表。

        规则：
        - 叶节点 → detail Chunk
        - 非叶节点 → overview Chunk（标题 + 子标题前的总述文字）
        - 最小 50 字：过短合并到父级
        - 最大 800 字：超长按自然段拆分

        Args:
            root: 结构树根节点
            document_id: 文档 ID
            source_file: 源文件名
            min_chars: 最小字数
            max_chars: 最大字数

        Returns:
            Chunk 列表
        """
        chunks: List[Chunk] = []
        self._walk_tree(root, chunks, [], document_id, source_file, min_chars, max_chars)
        logger.info(f"Chunking done: {len(chunks)} chunks generated")
        return chunks

    def _walk_tree(
        self,
        node: ParsedNode,
        chunks: List[Chunk],
        ancestors: List[ParsedNode],
        document_id: str,
        source_file: str,
        min_chars: int,
        max_chars: int,
    ):
        if node.level == 0:
            # 根节点，直接处理子节点
            for child in node.children:
                self._walk_tree(child, chunks, [node], document_id, source_file, min_chars, max_chars)
            return

        title_chain = self._build_title_chain(ancestors, node)
        context_tags = self._derive_context_tags(ancestors, node)
        has_children = len(node.children) > 0

        if has_children:
            # 非叶节点：生成 overview Chunk（标题 + 总述文字）
            overview_text = node.full_text
            if overview_text and len(overview_text) >= min_chars:
                chunk = self._make_chunk(
                    node=node,
                    chunk_type="overview",
                    text=overview_text,
                    title_chain=title_chain,
                    context_tags=context_tags,
                    document_id=document_id,
                    source_file=source_file,
                    children_ids=[c.node_id for c in node.children],
                    parent_id=ancestors[-1].node_id if ancestors else None,
                )
                chunks.append(chunk)

            # 递归处理子节点
            new_ancestors = ancestors + [node]
            for child in node.children:
                self._walk_tree(child, chunks, new_ancestors, document_id, source_file, min_chars, max_chars)
        else:
            # 叶节点：生成 detail Chunk
            text = node.full_text
            if not text:
                return  # 空节点跳过

            if len(text) < min_chars and ancestors:
                # 过短，不单独成块（将来可以合并到父级）
                # 但仍然生成，标记为短文本
                pass

            if len(text) > max_chars:
                # 超长，按自然段拆分
                parts = self._split_long_text(text, max_chars)
                for i, part in enumerate(parts):
                    part_id = f"{node.node_id}_part{i + 1}"
                    chunk = self._make_chunk(
                        node=node,
                        chunk_type="detail",
                        text=part,
                        title_chain=title_chain,
                        context_tags=context_tags,
                        document_id=document_id,
                        source_file=source_file,
                        chunk_id_override=part_id,
                        parent_id=ancestors[-1].node_id if ancestors else None,
                    )
                    chunks.append(chunk)
            else:
                chunk = self._make_chunk(
                    node=node,
                    chunk_type="detail",
                    text=text,
                    title_chain=title_chain,
                    context_tags=context_tags,
                    document_id=document_id,
                    source_file=source_file,
                    parent_id=ancestors[-1].node_id if ancestors else None,
                )
                chunks.append(chunk)

    def _make_chunk(
        self,
        node: ParsedNode,
        chunk_type: str,
        text: str,
        title_chain: str,
        context_tags: ContextTags,
        document_id: str,
        source_file: str,
        chunk_id_override: str = None,
        children_ids: List[str] = None,
        parent_id: str = None,
    ) -> Chunk:
        return Chunk(
            chunk_id=chunk_id_override or node.node_id,
            chunk_type=chunk_type,
            title=node.title,
            title_chain=title_chain,
            parent_id=parent_id if parent_id != "root" else None,
            children_ids=children_ids or [],
            level=node.level,
            text=text,
            context_tags=context_tags,
            roles_mentioned=[],
            metadata=ChunkMetadata(
                source_file=source_file,
                line_start=node.line_start,
                line_end=node.line_end,
                char_count=len(text),
                has_ocr_error="[OCR_ERROR]" in text,
            ),
            document_id=document_id,
        )

    def _build_title_chain(self, ancestors: List[ParsedNode], current: ParsedNode) -> str:
        parts = []
        for a in ancestors:
            if a.level > 0:  # 跳过根节点
                parts.append(a.title)
        parts.append(current.title)
        return " > ".join(parts)

    def _derive_context_tags(self, ancestors: List[ParsedNode], current: ParsedNode) -> ContextTags:
        """从祖先标题自动推导 context_tags"""
        tags = ContextTags()
        all_nodes = ancestors + [current]

        for node in all_nodes:
            title = node.title

            # Level 2 → battle_type
            if node.level == 2:
                for kw in BATTLE_TYPE_KEYWORDS:
                    if kw in title:
                        tags.battle_type = kw
                        break
                # 如果没有匹配到预设关键词，用标题本身
                if not tags.battle_type:
                    clean = self._remove_level_marker(title, node.level)
                    if clean:
                        tags.battle_type = clean

            # Level 3 → phase
            elif node.level == 3:
                for kw in PHASE_KEYWORDS:
                    if kw in title:
                        tags.phase = kw
                        break
                if not tags.phase:
                    clean = self._remove_level_marker(title, node.level)
                    if clean:
                        tags.phase = clean

        return tags

    def _remove_level_marker(self, title: str, level: int) -> str:
        """移除标题中的层级标记，返回纯文字"""
        import re
        markers = {
            1: r'^第[一二三四五六七八九十百]+章\s*',
            2: r'^第[一二三四五六七八九十百]+节\s*',
            3: r'^[一二三四五六七八九十]+、\s*',
            4: r'^（[一二三四五六七八九十]+）\s*',
            5: r'^\d+[\.．、]\s*',
            6: r'^（\d+）\s*',
            7: r'^[①②③④⑤⑥⑦⑧⑨⑩]\s*',
        }
        pattern = markers.get(level, "")
        if pattern:
            return re.sub(pattern, "", title).strip()
        return title.strip()

    def _split_long_text(self, text: str, max_chars: int) -> List[str]:
        """将超长文本按自然段拆分"""
        sentences = text.replace("。", "。\n").split("\n")
        parts = []
        current_part = []
        current_len = 0

        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            if current_len + len(s) > max_chars and current_part:
                parts.append("".join(current_part))
                current_part = []
                current_len = 0
            current_part.append(s)
            current_len += len(s)

        if current_part:
            parts.append("".join(current_part))

        return parts if parts else [text]


chunker_service = ChunkerService()
