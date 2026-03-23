"""Neo4j 图谱检索与查询服务"""
from typing import List, Optional
from loguru import logger
from neo4j import AsyncGraphDatabase, AsyncDriver

from app.config import settings


class GraphSearchService:

    def __init__(self):
        self._driver: Optional[AsyncDriver] = None

    def _get_driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
        return self._driver

    # ──────────────── 全文检索（用于混合检索通道） ────────────────

    async def search_tasks(self, query: str, top_k: int = 10) -> List[dict]:
        """通过 Neo4j 全文索引检索 Task/TaskGroup 节点"""
        driver = self._get_driver()
        cypher = """
            CALL db.index.fulltext.queryNodes('task_fulltext', $query)
            YIELD node, score
            WHERE node.chunk_id IS NOT NULL
            RETURN node.chunk_id AS chunk_id,
                   node.name      AS task_name,
                   score
            ORDER BY score DESC
            LIMIT $top_k
        """
        try:
            async with driver.session() as session:
                result = await session.run(cypher, {"query": query, "top_k": top_k})
                records = await result.data()
            items = [
                {"chunk_id": r["chunk_id"], "task_name": r["task_name"], "score": float(r["score"])}
                for r in records
            ]
            logger.debug(f"Graph search: {len(items)} results for '{query[:30]}...'")
            return items
        except Exception as e:
            logger.error(f"Neo4j search failed: {e}")
            return []

    # ──────────────── 角色职责查询 ────────────────

    async def role_tasks(self, role: str, phase: Optional[str] = None) -> dict:
        """查某角色在某阶段的所有任务"""
        driver = self._get_driver()
        if phase:
            cypher = """
                MATCH (r:Role {name: $role})<-[rel:INVOLVES|LED_BY|APPROVED_BY]-(t)
                WHERE (t)-[:BELONGS_TO]->(:Phase {name: $phase})
                OPTIONAL MATCH (t)<-[:HAS_SUBTASK]-(parent)
                RETURN t.name AS task_name, t.chunk_id AS chunk_id,
                       type(rel) AS responsibility, parent.name AS parent_task
                ORDER BY t.level, t.name
            """
            params = {"role": role, "phase": phase}
        else:
            cypher = """
                MATCH (r:Role {name: $role})<-[rel:INVOLVES|LED_BY|APPROVED_BY]-(t)
                OPTIONAL MATCH (t)<-[:HAS_SUBTASK]-(parent)
                RETURN t.name AS task_name, t.chunk_id AS chunk_id,
                       type(rel) AS responsibility, parent.name AS parent_task
                ORDER BY t.level, t.name
            """
            params = {"role": role}

        try:
            async with driver.session() as session:
                result = await session.run(cypher, **params)
                records = await result.data()
            return {
                "role": role,
                "phase": phase,
                "tasks": [
                    {
                        "task_name": r["task_name"],
                        "chunk_id": r["chunk_id"],
                        "responsibility": r["responsibility"].lower(),
                        "parent_task": r["parent_task"],
                    }
                    for r in records
                ],
            }
        except Exception as e:
            logger.error(f"role_tasks query failed: {e}")
            return {"role": role, "phase": phase, "tasks": []}

    # ──────────────── 任务角色分工 ────────────────

    async def task_roles(self, chunk_id: Optional[str] = None, task_name: Optional[str] = None) -> dict:
        """查某任务涉及的所有角色"""
        driver = self._get_driver()

        if chunk_id:
            cypher = """
                MATCH (t {chunk_id: $id})-[rel:INVOLVES|LED_BY|APPROVED_BY]->(r:Role)
                RETURN t.name AS task_name, t.chunk_id AS chunk_id,
                       r.name AS role_name, type(rel) AS rel_type
            """
            params = {"id": chunk_id}
        elif task_name:
            cypher = """
                CALL db.index.fulltext.queryNodes('task_fulltext', $name)
                YIELD node, score
                WITH node AS t ORDER BY score DESC LIMIT 1
                MATCH (t)-[rel:INVOLVES|LED_BY|APPROVED_BY]->(r:Role)
                RETURN t.name AS task_name, t.chunk_id AS chunk_id,
                       r.name AS role_name, type(rel) AS rel_type
            """
            params = {"name": task_name}
        else:
            return {"task": None, "roles": {}}

        try:
            async with driver.session() as session:
                result = await session.run(cypher, **params)
                records = await result.data()

            if not records:
                return {"task": task_name or chunk_id, "chunk_id": chunk_id, "roles": {}}

            roles_grouped = {"led_by": None, "approved_by": None, "involves": []}
            actual_task_name = records[0]["task_name"]
            actual_chunk_id = records[0]["chunk_id"]

            for r in records:
                rel = r["rel_type"]
                name = r["role_name"]
                if rel == "LED_BY":
                    roles_grouped["led_by"] = name
                elif rel == "APPROVED_BY":
                    roles_grouped["approved_by"] = name
                elif rel == "INVOLVES":
                    roles_grouped["involves"].append(name)

            return {"task": actual_task_name, "chunk_id": actual_chunk_id, "roles": roles_grouped}
        except Exception as e:
            logger.error(f"task_roles query failed: {e}")
            return {"task": task_name or chunk_id, "roles": {}}

    # ──────────────── 任务拆解 ────────────────

    async def task_decompose(self, chunk_id: str) -> dict:
        """查某任务的子步骤"""
        driver = self._get_driver()
        cypher = """
            MATCH (tg {chunk_id: $cid})-[:HAS_SUBTASK]->(sub)
            OPTIONAL MATCH (sub)-[:LED_BY]->(r:Role)
            OPTIONAL MATCH (sub)-[:PRODUCES]->(p:Product)
            OPTIONAL MATCH (sub)-[:DEPENDS_ON]->(dep)
            RETURN sub.name AS task_name, sub.chunk_id AS chunk_id, sub.level AS level,
                   r.name AS led_by,
                   collect(DISTINCT p.name) AS produces,
                   collect(DISTINCT dep.name) AS depends_on
            ORDER BY sub.level, sub.name
        """
        try:
            async with driver.session() as session:
                parent_result = await session.run(
                    "MATCH (t {chunk_id: $cid}) RETURN t.name AS name", cid=chunk_id
                )
                parent = await parent_result.single()

                result = await session.run(cypher, cid=chunk_id)
                records = await result.data()

            subtasks = []
            for i, r in enumerate(records, 1):
                subtasks.append({
                    "step": i,
                    "task_name": r["task_name"],
                    "chunk_id": r["chunk_id"],
                    "led_by": r["led_by"],
                    "produces": [p for p in r["produces"] if p],
                    "depends_on": [d for d in r["depends_on"] if d],
                })

            return {
                "task": parent["name"] if parent else chunk_id,
                "chunk_id": chunk_id,
                "subtasks": subtasks,
            }
        except Exception as e:
            logger.error(f"task_decompose query failed: {e}")
            return {"task": chunk_id, "chunk_id": chunk_id, "subtasks": []}

    # ──────────────── 前置依赖 ────────────────

    async def task_prerequisites(self, chunk_id: str) -> dict:
        """查某任务的前置依赖链"""
        driver = self._get_driver()
        cypher = """
            MATCH (t {chunk_id: $cid})
            OPTIONAL MATCH path = (t)<-[:NEXT_STEP|DEPENDS_ON*1..5]-(pre)
            WITH t, pre, [r IN relationships(path) | type(r)] AS rel_types
            WHERE pre IS NOT NULL
            RETURN pre.name AS task_name, pre.chunk_id AS chunk_id,
                   rel_types[-1] AS relation
            ORDER BY length(rel_types)
        """
        try:
            async with driver.session() as session:
                task_result = await session.run(
                    "MATCH (t {chunk_id: $cid}) RETURN t.name AS name", cid=chunk_id
                )
                task = await task_result.single()

                result = await session.run(cypher, cid=chunk_id)
                records = await result.data()

            return {
                "task": task["name"] if task else chunk_id,
                "chunk_id": chunk_id,
                "prerequisites": [
                    {"task_name": r["task_name"], "chunk_id": r["chunk_id"], "relation": r["relation"]}
                    for r in records
                ],
            }
        except Exception as e:
            logger.error(f"task_prerequisites query failed: {e}")
            return {"task": chunk_id, "chunk_id": chunk_id, "prerequisites": []}

    # ──────────────── 任务产物 ────────────────

    async def task_products(
        self,
        chunk_id: Optional[str] = None,
        role: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> dict:
        """查任务产物（支持按 chunk_id 或按 role+phase）"""
        driver = self._get_driver()

        if chunk_id:
            cypher = """
                MATCH (t {chunk_id: $cid})-[:PRODUCES]->(p:Product)
                RETURN p.name AS product, t.name AS source_task, t.chunk_id AS chunk_id
            """
            params = {"cid": chunk_id}
        elif role:
            if phase:
                cypher = """
                    MATCH (r:Role {name: $role})<-[:LED_BY|INVOLVES]-(t)-[:PRODUCES]->(p:Product)
                    WHERE (t)-[:BELONGS_TO]->(:Phase {name: $phase})
                    RETURN p.name AS product, t.name AS source_task, t.chunk_id AS chunk_id
                """
                params = {"role": role, "phase": phase}
            else:
                cypher = """
                    MATCH (r:Role {name: $role})<-[:LED_BY|INVOLVES]-(t)-[:PRODUCES]->(p:Product)
                    RETURN p.name AS product, t.name AS source_task, t.chunk_id AS chunk_id
                """
                params = {"role": role}
        else:
            return {"products": []}

        try:
            async with driver.session() as session:
                result = await session.run(cypher, **params)
                records = await result.data()
            return {
                "role": role,
                "phase": phase,
                "chunk_id": chunk_id,
                "products": [
                    {"product": r["product"], "source_task": r["source_task"], "chunk_id": r["chunk_id"]}
                    for r in records
                ],
            }
        except Exception as e:
            logger.error(f"task_products query failed: {e}")
            return {"products": []}

    # ──────────────── 任务详情（图谱+原文） ────────────────

    async def task_detail(self, chunk_id: str) -> dict:
        """查某任务的完整信息（图谱关系 + 原文）"""
        driver = self._get_driver()
        cypher = """
            MATCH (t {chunk_id: $cid})
            OPTIONAL MATCH (t)-[:LED_BY]->(led:Role)
            OPTIONAL MATCH (t)-[:APPROVED_BY]->(app:Role)
            OPTIONAL MATCH (t)-[:INVOLVES]->(inv:Role)
            OPTIONAL MATCH (t)-[:PRODUCES]->(prod:Product)
            OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep)
            OPTIONAL MATCH (t)<-[:HAS_SUBTASK]-(parent)
            OPTIONAL MATCH (t)-[:NEXT_STEP]->(next_t)
            OPTIONAL MATCH (prev_t)-[:NEXT_STEP]->(t)
            RETURN t.name AS task_name, t.chunk_id AS chunk_id, t.description AS description,
                   led.name AS led_by, app.name AS approved_by,
                   collect(DISTINCT inv.name) AS involves,
                   collect(DISTINCT prod.name) AS produces,
                   collect(DISTINCT dep.name) AS depends_on,
                   parent.name AS parent_name, parent.chunk_id AS parent_chunk_id,
                   next_t.name AS next_name, next_t.chunk_id AS next_chunk_id,
                   prev_t.name AS prev_name, prev_t.chunk_id AS prev_chunk_id
        """
        try:
            async with driver.session() as session:
                result = await session.run(cypher, cid=chunk_id)
                record = await result.single()

            if not record:
                return {"chunk_id": chunk_id, "error": "not found"}

            return {
                "task": record["task_name"],
                "chunk_id": record["chunk_id"],
                "graph_info": {
                    "led_by": record["led_by"],
                    "approved_by": record["approved_by"],
                    "involves": [r for r in record["involves"] if r],
                    "produces": [p for p in record["produces"] if p],
                    "depends_on": [d for d in record["depends_on"] if d],
                    "parent_task": {"name": record["parent_name"], "chunk_id": record["parent_chunk_id"]}
                    if record["parent_name"] else None,
                    "next_step": {"name": record["next_name"], "chunk_id": record["next_chunk_id"]}
                    if record["next_name"] else None,
                    "prev_step": {"name": record["prev_name"], "chunk_id": record["prev_chunk_id"]}
                    if record["prev_name"] else None,
                },
            }
        except Exception as e:
            logger.error(f"task_detail query failed: {e}")
            return {"chunk_id": chunk_id, "error": str(e)}

    # ──────────────── 图谱可视化数据 ────────────────

    def _node_info(self, node):
        """
        从 Neo4j 返回的节点提取 label 和 props。
        兼容 Node 对象和 result.data() 序列化后的 dict。
        """
        if isinstance(node, dict):
            labels = node.get("labels") or node.get("label")
            if isinstance(labels, list) and labels:
                lbl = labels[0]
            elif isinstance(labels, str):
                lbl = labels
            else:
                lbl = "Node"
            props = {k: v for k, v in node.items() if k not in ("labels", "label", "element_id")}
            return lbl, props
        lbl = node.labels[0] if node.labels else "Node"
        props = dict(node)
        return lbl, props

    def _node_id(self, node) -> str:
        """生成节点唯一 id，优先用 chunk_id/name"""
        lbl, props = self._node_info(node)
        uid = props.get("chunk_id") or props.get("name")
        if uid:
            return f"{lbl}:{uid}"
        eid = node.get("element_id") if isinstance(node, dict) else getattr(node, "element_id", None)
        return eid or f"{lbl}:_{id(node)}"

    async def get_graph_for_viz(self, max_nodes: int = 500) -> dict:
        """
        返回图谱节点和边，供前端可视化。
        vis-network 格式：nodes [{id, label, group}], edges [{from, to, label}]
        """
        driver = self._get_driver()
        label_colors = {
            "Role": "#4CAF50",
            "Task": "#2196F3",
            "TaskGroup": "#2196F3",
            "Phase": "#FF9800",
            "BattleType": "#9C27B0",
            "Product": "#00BCD4",
        }
        default_color = "#757575"

        try:
            async with driver.session() as session:
                # 一次查询获取节点和边，通过路径采样
                result = await session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WITH a, r, b LIMIT $max
                    RETURN a, type(r) AS relType, b
                    """,
                    max=max_nodes * 2,  # 边数约等于节点数
                )
                records = await result.data()

            nodes_map = {}
            edges = []

            for rec in records:
                a, b, rel = rec.get("a"), rec.get("b"), rec.get("relType", "")
                for node in [a, b]:
                    if not node:
                        continue
                    nid = self._node_id(node)
                    if nid not in nodes_map:
                        lbl, props = self._node_info(node)
                        name = props.get("name") or props.get("chunk_id") or nid
                        nodes_map[nid] = {
                            "id": nid,
                            "label": str(name)[:30],
                            "group": lbl,
                            "title": f"{lbl}: {name}",
                        }
                if a and b and rel:
                    aid, bid = self._node_id(a), self._node_id(b)
                    edges.append({"from": aid, "to": bid, "label": rel, "title": rel})

            nodes = list(nodes_map.values())
            return {
                "nodes": nodes,
                "edges": edges,
                "labelColors": label_colors,
                "defaultColor": default_color,
            }
        except Exception as e:
            logger.error(f"get_graph_for_viz failed: {e}")
            return {"nodes": [], "edges": [], "labelColors": {}, "defaultColor": default_color}

    # ──────────────── 图谱统计 ────────────────

    async def graph_stats(self) -> dict:
        """返回图谱基础统计"""
        driver = self._get_driver()
        try:
            async with driver.session() as session:
                node_result = await session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
                )
                nodes = {r["label"]: r["cnt"] for r in await node_result.data()}

                rel_result = await session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt"
                )
                rels = {r["rel"]: r["cnt"] for r in await rel_result.data()}

            return {"nodes": nodes, "relationships": rels}
        except Exception as e:
            logger.error(f"graph_stats failed: {e}")
            return {"nodes": {}, "relationships": {}, "error": str(e)}

    async def close(self):
        if self._driver:
            await self._driver.close()
            self._driver = None


graph_search_service = GraphSearchService()
