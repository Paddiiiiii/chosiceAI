"""Neo4j 流程图谱构建服务（规则抽取 + LLM 语义抽取）"""
import json
from typing import List, Dict, Optional
from loguru import logger
from neo4j import AsyncGraphDatabase, AsyncDriver

from app.config import settings
from app.models.schemas import Chunk, RoleRegistry
from app.services.data_manager import data_manager
from app.services.llm_client import llm_client


class GraphBuilder:

    def __init__(self):
        self._driver: Optional[AsyncDriver] = None

    def _get_driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
        return self._driver

    # ──────────────── 主入口 ────────────────

    async def rebuild(self, use_llm: bool = False) -> dict:
        """
        重建整个流程图谱。

        Phase 1: 规则抽取（确定性骨架）
        Phase 2: LLM 语义抽取（LED_BY / DEPENDS_ON / PRODUCES）— 可选
        """
        chunks = data_manager.load_all_chunks()
        role_registry = data_manager.load_role_registry()

        if not chunks:
            return {"status": "error", "message": "No chunks available"}

        driver = self._get_driver()

        async with driver.session() as session:
            await self._clear_graph(session)
            stats = await self._phase1_rule_extract(session, chunks, role_registry)

            if use_llm:
                llm_stats = await self._phase2_llm_extract(session, chunks, role_registry)
                stats.update(llm_stats)

        await self._create_indexes()

        stats["status"] = "success"
        logger.info(f"Graph rebuild complete: {stats}")
        return stats

    # ──────────────── Phase 1: 规则抽取 ────────────────

    async def _phase1_rule_extract(
        self, session, chunks: List[Chunk], role_registry: RoleRegistry
    ) -> dict:
        stats = {
            "roles": 0, "phases": 0, "battle_types": 0,
            "tasks": 0, "task_groups": 0,
            "has_subtask": 0, "next_step": 0, "involves": 0,
            "belongs_to": 0, "in_battle_type": 0,
        }

        role_names = [r.name for r in role_registry.roles]
        phases = set()
        battle_types = set()
        chunk_map: Dict[str, Chunk] = {c.chunk_id: c for c in chunks}

        for c in chunks:
            if c.context_tags.phase:
                phases.add(c.context_tags.phase)
            if c.context_tags.battle_type:
                battle_types.add(c.context_tags.battle_type)

        # 1) Role 节点
        for name in role_names:
            await session.run(
                "MERGE (r:Role {name: $name})",
                name=name,
            )
        stats["roles"] = len(role_names)

        # 2) Phase 节点
        for name in phases:
            await session.run("MERGE (:Phase {name: $name})", name=name)
        stats["phases"] = len(phases)

        # 3) BattleType 节点
        for name in battle_types:
            await session.run("MERGE (:BattleType {name: $name})", name=name)
        stats["battle_types"] = len(battle_types)

        # 4) Task / TaskGroup 节点
        for c in chunks:
            label = "TaskGroup" if c.chunk_type == "overview" else "Task"
            await session.run(
                f"MERGE (t:{label} {{chunk_id: $chunk_id}}) "
                "SET t.name = $name, t.description = $desc, t.level = $level",
                chunk_id=c.chunk_id,
                name=c.title,
                desc=c.text[:500] if c.text else "",
                level=c.level,
            )
            if label == "TaskGroup":
                stats["task_groups"] += 1
            else:
                stats["tasks"] += 1

        # 5) HAS_SUBTASK（parent → child）
        for c in chunks:
            if c.parent_id and c.parent_id in chunk_map:
                await session.run(
                    "MATCH (parent {chunk_id: $parent_id}) "
                    "MATCH (child {chunk_id: $child_id}) "
                    "MERGE (parent)-[:HAS_SUBTASK]->(child)",
                    parent_id=c.parent_id,
                    child_id=c.chunk_id,
                )
                stats["has_subtask"] += 1

        # 6) NEXT_STEP（同父节点下相邻 children 的顺序关系）
        parent_children: Dict[str, List[str]] = {}
        for c in chunks:
            if c.parent_id:
                parent_children.setdefault(c.parent_id, []).append(c.chunk_id)

        for parent_id, children_ids in parent_children.items():
            parent_chunk = chunk_map.get(parent_id)
            if parent_chunk and parent_chunk.children_ids:
                ordered = [cid for cid in parent_chunk.children_ids if cid in chunk_map]
            else:
                ordered = children_ids

            for i in range(len(ordered) - 1):
                await session.run(
                    "MATCH (a {chunk_id: $from_id}) "
                    "MATCH (b {chunk_id: $to_id}) "
                    "MERGE (a)-[:NEXT_STEP]->(b)",
                    from_id=ordered[i],
                    to_id=ordered[i + 1],
                )
                stats["next_step"] += 1

        # 7) INVOLVES（Task → Role，基于 roles_mentioned）
        for c in chunks:
            for role_name in c.roles_mentioned:
                if role_name in role_names:
                    await session.run(
                        "MATCH (t {chunk_id: $chunk_id}) "
                        "MATCH (r:Role {name: $role}) "
                        "MERGE (t)-[:INVOLVES]->(r)",
                        chunk_id=c.chunk_id,
                        role=role_name,
                    )
                    stats["involves"] += 1

        # 8) BELONGS_TO（Task → Phase）
        for c in chunks:
            if c.context_tags.phase:
                await session.run(
                    "MATCH (t {chunk_id: $chunk_id}) "
                    "MATCH (p:Phase {name: $phase}) "
                    "MERGE (t)-[:BELONGS_TO]->(p)",
                    chunk_id=c.chunk_id,
                    phase=c.context_tags.phase,
                )
                stats["belongs_to"] += 1

        # 9) IN_BATTLE_TYPE（Task → BattleType）
        for c in chunks:
            if c.context_tags.battle_type:
                await session.run(
                    "MATCH (t {chunk_id: $chunk_id}) "
                    "MATCH (bt:BattleType {name: $bt}) "
                    "MERGE (t)-[:IN_BATTLE_TYPE]->(bt)",
                    chunk_id=c.chunk_id,
                    bt=c.context_tags.battle_type,
                )
                stats["in_battle_type"] += 1

        logger.info(f"Phase 1 (rule extract) done: {stats}")
        return stats

    # ──────────────── Phase 2: LLM 语义抽取 ────────────────

    async def _phase2_llm_extract(
        self, session, chunks: List[Chunk], role_registry: RoleRegistry
    ) -> dict:
        stats = {"led_by": 0, "approved_by": 0, "produces": 0, "depends_on": 0}
        role_list_str = "、".join(r.name for r in role_registry.roles)

        detail_chunks = [c for c in chunks if c.chunk_type == "detail" and c.text]

        for c in detail_chunks:
            try:
                extraction = await self._llm_extract_one(c, role_list_str)
            except Exception as e:
                logger.warning(f"LLM extract failed for {c.chunk_id}: {e}")
                continue

            if extraction.get("led_by"):
                await session.run(
                    "MATCH (t {chunk_id: $cid}) "
                    "MATCH (r:Role {name: $role}) "
                    "MERGE (t)-[:LED_BY]->(r)",
                    cid=c.chunk_id,
                    role=extraction["led_by"],
                )
                stats["led_by"] += 1

            if extraction.get("approved_by"):
                await session.run(
                    "MATCH (t {chunk_id: $cid}) "
                    "MATCH (r:Role {name: $role}) "
                    "MERGE (t)-[:APPROVED_BY]->(r)",
                    cid=c.chunk_id,
                    role=extraction["approved_by"],
                )
                stats["approved_by"] += 1

            for product_name in extraction.get("produces", []):
                await session.run(
                    "MERGE (p:Product {name: $pname}) "
                    "WITH p "
                    "MATCH (t {chunk_id: $cid}) "
                    "MERGE (t)-[:PRODUCES]->(p)",
                    pname=product_name,
                    cid=c.chunk_id,
                )
                stats["produces"] += 1

            for dep_desc in extraction.get("depends_on", []):
                result = await session.run(
                    "CALL db.index.fulltext.queryNodes('task_fulltext', $q) "
                    "YIELD node, score WHERE score > 1.0 "
                    "RETURN node.chunk_id AS cid LIMIT 1",
                    q=dep_desc,
                )
                record = await result.single()
                if record:
                    await session.run(
                        "MATCH (t {chunk_id: $from_cid}) "
                        "MATCH (dep {chunk_id: $to_cid}) "
                        "MERGE (t)-[:DEPENDS_ON]->(dep)",
                        from_cid=c.chunk_id,
                        to_cid=record["cid"],
                    )
                    stats["depends_on"] += 1

        logger.info(f"Phase 2 (LLM extract) done: {stats}")
        return stats

    async def _llm_extract_one(self, chunk: Chunk, role_list: str) -> dict:
        prompt = f"""你是军事组织体制分析专家。以下是《作战指挥手册》中关于某项任务的描述。
请提取以下信息：

1. led_by：这项任务由谁牵头负责？（从候选角色列表中选）
2. approved_by：这项任务需要谁审批？（如有）
3. produces：这项任务应该产出什么成果/文书？（如有）
4. depends_on：这项任务在执行前需要先完成哪些前置任务？（如有，用任务名称描述）

候选角色列表：{role_list}

任务标题：{chunk.title}
上下文路径：{chunk.title_chain}
任务描述：{chunk.text}

输出严格 JSON：
{{"led_by": "角色名" | null, "approved_by": "角色名" | null, "produces": ["产物名1"] | [], "depends_on": ["前置任务描述1"] | []}}"""

        result = await llm_client.chat_json(prompt)
        return result

    # ──────────────── 工具方法 ────────────────

    async def _clear_graph(self, session):
        await session.run("MATCH (n) DETACH DELETE n")
        logger.info("Neo4j graph cleared")

    async def _create_indexes(self):
        driver = self._get_driver()
        async with driver.session() as session:
            index_statements = [
                "CREATE INDEX task_chunk IF NOT EXISTS FOR (t:Task) ON (t.chunk_id)",
                "CREATE INDEX taskgroup_chunk IF NOT EXISTS FOR (t:TaskGroup) ON (t.chunk_id)",
                "CREATE INDEX role_name IF NOT EXISTS FOR (r:Role) ON (r.name)",
                "CREATE INDEX product_name IF NOT EXISTS FOR (p:Product) ON (p.name)",
                "CREATE INDEX phase_name IF NOT EXISTS FOR (p:Phase) ON (p.name)",
            ]
            for stmt in index_statements:
                try:
                    await session.run(stmt)
                except Exception as e:
                    logger.warning(f"Index creation skipped: {e}")

            try:
                await session.run(
                    "CREATE FULLTEXT INDEX task_fulltext IF NOT EXISTS "
                    "FOR (t:Task|TaskGroup) ON EACH [t.name, t.description]"
                )
            except Exception as e:
                logger.warning(f"Fulltext index creation skipped: {e}")

        logger.info("Neo4j indexes ensured")

    async def close(self):
        if self._driver:
            await self._driver.close()
            self._driver = None


graph_builder = GraphBuilder()
