"""Step 1.4 - 角色提及标注服务"""
from typing import List
from loguru import logger

from app.models.schemas import Chunk, RoleRegistry, Role, ReviewItem


class RoleAnnotatorService:
    """对每个 Chunk 扫描文本中提到的角色"""

    def annotate_chunks(
        self, chunks: List[Chunk], role_registry: RoleRegistry
    ) -> tuple[List[Chunk], List[ReviewItem]]:
        """
        对每个 Chunk 标注 roles_mentioned。

        Args:
            chunks: Chunk 列表
            role_registry: 角色注册表

        Returns:
            (标注后的 Chunk 列表, 需审核条目列表)
        """
        role_names = [
            r.name for r in role_registry.roles
            if getattr(r, "status", "approved") == "approved"
        ]
        review_items: List[ReviewItem] = []
        mention_counts: dict = {name: 0 for name in role_names}

        for chunk in chunks:
            found_roles = []
            for role_name in role_names:
                if role_name in chunk.text or role_name in chunk.title:
                    found_roles.append(role_name)
                    mention_counts[role_name] += 1

            chunk.roles_mentioned = found_roles

            # 标记没有角色提及但可能应该有的 Chunk
            # 规则：detail 类型 Chunk 如果超过 100 字但没有任何角色提及
            if (
                chunk.chunk_type == "detail"
                and len(chunk.text) > 100
                and not found_roles
            ):
                review_items.append(ReviewItem(
                    item_id=f"role_{chunk.chunk_id}",
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    type="role_annotation",
                    description=f"Chunk '{chunk.title}' 超过100字但未发现任何角色提及",
                    original_text=chunk.text[:200],
                    status="pending",
                ))

        # 更新角色注册表的 mention_count
        for role in role_registry.roles:
            role.mention_count = mention_counts.get(role.name, 0)

        annotated_count = sum(1 for c in chunks if c.roles_mentioned)
        logger.info(
            f"Role annotation done: {annotated_count}/{len(chunks)} chunks have role mentions, "
            f"{len(review_items)} review items"
        )
        return chunks, review_items

    def update_registry_from_chunks(
        self, role_registry: RoleRegistry, chunks: List[Chunk]
    ) -> RoleRegistry:
        """从所有 Chunk 更新角色的 mention_count"""
        counts: dict = {}
        for chunk in chunks:
            for role_name in chunk.roles_mentioned:
                counts[role_name] = counts.get(role_name, 0) + 1

        for role in role_registry.roles:
            role.mention_count = counts.get(role.name, 0)

        # 更新来源文件列表
        source_files = set(role_registry.source_files)
        for chunk in chunks:
            if chunk.metadata.source_file:
                source_files.add(chunk.metadata.source_file)
        role_registry.source_files = list(source_files)

        return role_registry


role_annotator_service = RoleAnnotatorService()
