"""从文章内容中自动提取角色（LLM），待人工审批"""
import json
from typing import List
from loguru import logger

from app.models.schemas import Role, RoleRegistry
from app.services.data_manager import data_manager
from app.services.llm_client import llm_client


class RoleExtractorService:
    """基于 LLM 从文档内容中提取军事组织体制中的角色/主语"""

    async def extract_roles(self) -> dict:
        """
        从所有已处理文档的 chunks 中提取角色。
        新角色以 status=pending, source=auto 加入，需人工审批。
        已存在的角色名（含 approved/pending）不重复添加。
        """
        chunks = data_manager.load_all_chunks()
        registry = data_manager.load_role_registry()

        existing_names = {r.name for r in registry.roles}
        # 兼容旧数据：无 status 字段视为 approved
        approved_names = {
            r.name for r in registry.roles
            if getattr(r, "status", "approved") == "approved"
        }

        if not chunks:
            return {"status": "ok", "extracted": 0, "added": 0, "message": "无文档内容可分析"}

        # 采样文本：取各 chunk 的 title + text 前 200 字，避免超长
        samples = []
        for c in chunks[:100]:  # 最多 100 个 chunk
            s = f"【{c.title}】{c.text[:200]}"
            if s.strip():
                samples.append(s)
        text_block = "\n\n".join(samples[:30])  # 最多 30 段，控制 token
        if len(text_block) > 8000:
            text_block = text_block[:8000] + "..."

        prompt = f"""你是军事组织体制分析专家。以下是从《作战指挥手册》中抽取的文本片段。
请从中识别出所有作为「主语」或「责任主体」出现的角色/部门/要素名称。
例如：指挥员、参谋长、筹划决策要素、侦察情报要素、作战部门、政治工作部 等。

要求：
1. 只提取在文中明确作为主语或责任主体的角色名
2. 输出 JSON 数组，如 ["角色1", "角色2"]
3. 不要编造，只提取文中出现的
4. 同一角色多种表述取最规范的（如「旅长」可统一为「指挥员」）

文本片段：
---
{text_block}
---

输出严格 JSON 数组，例如：["指挥员", "参谋长", "筹划决策要素"]"""

        try:
            raw = await llm_client.chat(prompt)
        except Exception as e:
            logger.error(f"Role extraction LLM failed: {e}")
            return {"status": "error", "message": str(e), "extracted": 0, "added": 0}

        # 解析 JSON 数组
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        if not raw.strip():
            return {"status": "ok", "extracted": 0, "added": 0, "message": "未解析到角色"}

        try:
            parsed = json.loads(raw)
            names = parsed if isinstance(parsed, list) else [parsed]
            names = [str(n).strip() for n in names if n and str(n).strip()]
        except Exception as e:
            logger.warning(f"Parse role list failed: {raw[:100]}, {e}")
            return {"status": "error", "message": f"解析失败: {e}", "extracted": 0, "added": 0}

        extracted = len(names)
        added = 0
        max_id = 0
        for r in registry.roles:
            try:
                num = int(r.role_id.replace("R", ""))
                max_id = max(max_id, num)
            except ValueError:
                pass

        for name in names:
            if name in existing_names:
                continue
            existing_names.add(name)
            max_id += 1
            new_role = Role(
                role_id=f"R{max_id:02d}",
                name=name,
                mention_count=0,
                status="pending",
                source="auto",
            )
            registry.roles.append(new_role)
            added += 1

        data_manager.save_role_registry(registry)
        logger.info(f"Role extraction: {extracted} extracted, {added} added (pending)")
        return {
            "status": "ok",
            "extracted": extracted,
            "added": added,
            "message": f"提取 {extracted} 个角色，新增 {added} 个待审批",
        }


role_extractor_service = RoleExtractorService()
