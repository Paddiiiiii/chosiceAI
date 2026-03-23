# 任务路由系统 - API 接口文档

Base URL：`http://127.0.0.1:8000/api/v1`

每个接口均包含：**功能**、**使用场景**、**概述**。

---

## 一、路由与检索

### 1.1 POST /chat

| 项目 | 说明 |
|------|------|
| **功能** | 旅长自然语言指令 → 检索手册 → LLM 判定 → 返回牵头负责角色、参与协助、审批角色及依据 |
| **使用场景** | 旅长问「侦察计划该谁去做？」「谁负责组织战斗协同？」等，需快速得到责任分工和手册依据 |
| **概述** | 一站式路由接口，内部完成意图识别、三路检索（向量+BM25+图谱）、RRF 融合、LLM 路由判定。支持 `@角色` 强制指定牵头。 |

**请求体**：`{ "input": "自然语言", "context": { "phase": "战斗准备" }, "retrieval": { "use_vector": true, "use_bm25": true, "use_graph": true } }`

---

### 1.2 POST /search/comparison

| 项目 | 说明 |
|------|------|
| **功能** | 同时执行向量、BM25、图谱三路检索，并返回 RRF 融合结果，便于对比各通道效果 |
| **使用场景** | 调试检索质量、对比不同检索通道、获取 chunk_id 供后续图谱接口使用 |
| **概述** | 多路检索对比：返回 `vector_results`、`bm25_results`、`graph_results`、`rrf_results`（纯 RRF TopK），以及 **`rerank_results`**（与 `POST /chat` 一致的重排后 TopK）、**`rerank_meta`**（是否启用、pool 大小、跳过原因）。可通过 `retrieval` 控制启用哪些通道。 |

**请求体**：`{ "query": "检索词", "filters": { "phase": "战斗准备" }, "retrieval": { "use_vector": true, "use_bm25": true, "use_graph": true } }`

---

### 1.3 POST /search/refresh-cache

| 项目 | 说明 |
|------|------|
| **功能** | 重新从本地数据加载所有 Chunk 到内存缓存 |
| **使用场景** | 文档处理或图谱重建后，需刷新检索使用的 Chunk 缓存 |
| **概述** | 无请求体，调用后立即刷新。返回 `total_chunks` 数量。 |

---

### 1.4 POST /resolve

| 项目 | 说明 |
|------|------|
| **功能** | 自然语言查询 → 匹配 Task/TaskGroup 节点，返回 chunk_id、task_name 等 |
| **使用场景** | 在 Search 之后精确定位任务节点，或作为任务拆解、角色查询的前置步骤 |
| **概述** | 桥梁接口，无 LLM。内部调用混合检索，用 chunk_id 关联 Neo4j 节点，返回 `matches` 列表（含 `chunk_id`、`task_name`、`has_subtasks`）。 |

**请求体**：`{ "query": "组织侦察情报", "top_k": 3, "retrieval": { ... } }`

---

## 二、图谱接口（/graph）

### 2.1 POST /graph/rebuild

| 项目 | 说明 |
|------|------|
| **功能** | 重建 Neo4j 流程图谱，支持规则抽取与 LLM 语义补全 |
| **使用场景** | 文档处理完成后，首次构建或重新构建图谱；需补充 LED_BY、PRODUCES、DEPENDS_ON 时使用 `use_llm=true` |
| **概述** | 同步等待完成。Phase 1 规则抽取（Role/Phase/BattleType/Task/HAS_SUBTASK/NEXT_STEP/INVOLVES 等）；Phase 2 可选 LLM 抽取。返回节点/边统计。 |

**参数**：`?use_llm=false`（默认）或 `?use_llm=true`

---

### 2.2 GET /graph/stats

| 项目 | 说明 |
|------|------|
| **功能** | 返回图谱节点类型数量、关系统计 |
| **使用场景** | 检查图谱构建是否成功、了解图谱规模 |
| **概述** | 返回 `nodes`（如 Role: 18, Task: 120）、`relationships`（如 HAS_SUBTASK: 150）。 |

---

### 2.3 GET /graph/viz

| 项目 | 说明 |
|------|------|
| **功能** | 返回图谱可视化数据（节点、边、颜色配置），供前端 vis-network 渲染 |
| **使用场景** | 前端「图谱浏览」页展示流程图谱 |
| **概述** | 返回 `nodes`、`edges`、`labelColors`。节点含 id、label、group；边含 from、to、label。 |

**参数**：`?max_nodes=500`（默认，限制节点数量）

---

### 2.4 GET /graph/role_tasks

| 项目 | 说明 |
|------|------|
| **功能** | 查某角色在某阶段（或全部）涉及的所有任务及责任类型 |
| **使用场景** | 了解「参谋长在战斗准备阶段负责什么」「侦察情报要素有哪些任务」 |
| **概述** | 按 INVOLVES、LED_BY、APPROVED_BY 关系匹配。返回 `tasks` 列表，含 `task_name`、`chunk_id`、`responsibility`（led_by/involves/approved_by）、`parent_task`。 |

**参数**：`role`（必填）、`phase`（可选）

---

### 2.5 GET /graph/task_roles

| 项目 | 说明 |
|------|------|
| **功能** | 查某任务涉及的所有角色（牵头、审批、参与） |
| **使用场景** | 了解「制定侦察计划由谁拟制、谁审批」「下达预先号令谁负责」 |
| **概述** | 按 chunk_id 或 task_name 定位任务，返回 `roles.led_by`、`roles.approved_by`、`roles.involves`。 |

**参数**：`chunk_id` 或 `task_name`（二选一）

---

### 2.6 GET /graph/task_decompose

| 项目 | 说明 |
|------|------|
| **功能** | 查某任务的子步骤列表（HAS_SUBTASK 关系） |
| **使用场景** | 大任务拆解，如「组织侦察情报有哪些步骤」「战斗准备包含哪些工作」 |
| **概述** | 输入 TaskGroup 或 Task 的 chunk_id，返回 `subtasks` 列表，含 `task_name`、`chunk_id`、`led_by`、`produces`、`depends_on`。 |

**参数**：`chunk_id`（必填）

---

### 2.7 GET /graph/task_prerequisites

| 项目 | 说明 |
|------|------|
| **功能** | 查某任务的前置依赖链（NEXT_STEP、DEPENDS_ON 反向） |
| **使用场景** | 了解「制定侦察计划前需要先完成什么」「定下战斗决心的前置步骤」 |
| **概述** | 沿 NEXT_STEP、DEPENDS_ON 反向遍历，返回 `prerequisites` 列表，含 `task_name`、`chunk_id`、`relation`。 |

**参数**：`chunk_id`（必填）

---

### 2.8 GET /graph/task_products

| 项目 | 说明 |
|------|------|
| **功能** | 查某任务或某角色在某阶段应产出的成果/文书 |
| **使用场景** | 了解「制定侦察计划产出什么」「判断三情形成哪些报告」 |
| **概述** | 按 chunk_id 或 role+phase 查询，返回 `products` 列表，含 `product`、`source_task`、`chunk_id`。PRODUCES 关系需 LLM 抽取。 |

**参数**：`chunk_id` 或 `role`+`phase`（二选一）

---

### 2.9 GET /graph/task_detail

| 项目 | 说明 |
|------|------|
| **功能** | 查某任务的完整图谱关系及原文 |
| **使用场景** | 需要任务的全量信息（牵头、审批、参与、产物、依赖、前后步骤、原文） |
| **概述** | 返回 `graph_info`（led_by、approved_by、involves、produces、depends_on、parent_task、next_step、prev_step）及 `full_text`、`title_chain`。 |

**参数**：`chunk_id`（必填）

---

## 三、文档与 Chunk

### 3.1 GET /documents

| 项目 | 说明 |
|------|------|
| **功能** | 获取文档列表 |
| **使用场景** | 前端文档管理页、结构浏览页加载文档列表 |
| **概述** | 返回 `DocumentInfo` 列表，含 doc_id、filename、status、created_at 等。 |

---

### 3.2 GET /documents/{doc_id}

| 项目 | 说明 |
|------|------|
| **功能** | 获取单个文档详情 |
| **使用场景** | 查看文档状态、元数据 |
| **概述** | 按 doc_id 返回文档信息。 |

---

### 3.3 POST /documents/upload

| 项目 | 说明 |
|------|------|
| **功能** | 上传 .txt 手册原文 |
| **使用场景** | 新增手册文档 |
| **概述** |  multipart/form-data，字段 `file`。返回新建的 DocumentInfo。 |

---

### 3.4 POST /documents/{doc_id}/process

| 项目 | 说明 |
|------|------|
| **功能** | 处理文档：OCR 纠错、结构解析、分块、角色标注 |
| **使用场景** | 上传后首次处理，或重新解析结构 |
| **概述** | 异步任务，完成后生成 chunks.json、role_registry 更新等。 |

---

### 3.5 POST /documents/{doc_id}/reprocess

| 项目 | 说明 |
|------|------|
| **功能** | 重新处理文档（与 process 类似，覆盖已有结果） |
| **使用场景** | 修正 OCR、调整层级配置后重新分块 |
| **概述** | 覆盖 chunks、结构树等。 |

---

### 3.6 DELETE /documents/{doc_id}

| 项目 | 说明 |
|------|------|
| **功能** | 删除文档及其相关数据 |
| **使用场景** | 移除错误上传或过期文档 |
| **概述** | 删除文档记录及 doc 目录下所有文件。 |

---

### 3.7 POST /documents/build-indexes

| 项目 | 说明 |
|------|------|
| **功能** | 构建向量索引（Milvus）和 BM25 索引（Elasticsearch） |
| **使用场景** | 文档处理完成后，构建检索索引 |
| **概述** | 遍历所有已处理文档的 chunks，写入 Milvus 和 ES。依赖 Embedding 服务。 |

---

### 3.8 GET /documents/{doc_id}/original-text

| 项目 | 说明 |
|------|------|
| **功能** | 获取文档原始文本 |
| **使用场景** | OCR 审核、查看原文 |
| **概述** | 返回 original.txt 内容。 |

---

### 3.9 GET /documents/{doc_id}/corrected-text

| 项目 | 说明 |
|------|------|
| **功能** | 获取 OCR 纠错后的文本 |
| **使用场景** | 查看纠错结果 |
| **概述** | 返回 corrected_text.txt 内容。 |

---

### 3.10 GET /chunks

| 项目 | 说明 |
|------|------|
| **功能** | 获取 Chunk 列表，支持按 doc_id、chunk_type、phase、battle_type 过滤 |
| **使用场景** | Chunk 详情页、结构浏览页关联 Chunk 列表 |
| **概述** | 返回 Chunk 列表，含 chunk_id、title、title_chain、text、roles_mentioned 等。 |

**参数**：`doc_id`、`chunk_type`、`phase`、`battle_type`（均可选）

---

### 3.11 GET /chunks/{chunk_id}

| 项目 | 说明 |
|------|------|
| **功能** | 获取单个 Chunk 详情 |
| **使用场景** | 查看某 Chunk 的完整内容和元数据 |
| **概述** | 按 chunk_id 返回 Chunk 对象。 |

---

### 3.12 GET /chunks/stats/summary

| 项目 | 说明 |
|------|------|
| **功能** | 获取 Chunk 统计信息（总数、按类型/阶段/战斗类型分布） |
| **使用场景** | 数据概览、调试 |
| **概述** | 返回 total、by_type、by_phase、by_battle_type、avg_char_count。 |

---

## 四、结构树

### 4.1 GET /structure

| 项目 | 说明 |
|------|------|
| **功能** | 获取所有文档的结构概览 |
| **使用场景** | 结构浏览页选择文档 |
| **概述** | 返回各文档的章节树概要。 |

---

### 4.2 GET /structure/{doc_id}

| 项目 | 说明 |
|------|------|
| **功能** | 获取单文档的章节结构树 |
| **使用场景** | 结构浏览页展示树形结构 |
| **概述** | 返回 chapter_tree.json 内容，含层级、标题、关联 Chunk。 |

---

## 五、角色管理

### 5.1 GET /roles

| 项目 | 说明 |
|------|------|
| **功能** | 获取角色注册表（含待审批角色） |
| **使用场景** | 角色管理页展示、路由判定候选列表 |
| **概述** | 返回 RoleRegistry，含 roles 列表（role_id、name、mention_count、status、source）。 |

---

### 5.2 POST /roles

| 项目 | 说明 |
|------|------|
| **功能** | 新增角色（人工添加，默认 approved） |
| **使用场景** | 角色管理页「新增角色」 |
| **概述** | 请求体 `{ "name": "角色名" }`，自动生成 role_id。 |

---

### 5.3 PUT /roles/{role_id}

| 项目 | 说明 |
|------|------|
| **功能** | 更新角色名称 |
| **使用场景** | 角色管理页「编辑」 |
| **概述** | 请求体 `{ "name": "新名称" }`。 |

---

### 5.4 DELETE /roles/{role_id}

| 项目 | 说明 |
|------|------|
| **功能** | 删除角色 |
| **使用场景** | 角色管理页「删除」 |
| **概述** | 从注册表中移除该角色。 |

---

### 5.5 POST /roles/extract

| 项目 | 说明 |
|------|------|
| **功能** | 从文档内容中自动提取角色（LLM），新角色为 pending 待审批 |
| **使用场景** | 角色管理页「自动提取」按钮 |
| **概述** | 分析 chunks 文本，提取主语/责任主体，去重后以 status=pending 加入。返回 extracted、added 数量。 |

---

### 5.6 POST /roles/{role_id}/approve

| 项目 | 说明 |
|------|------|
| **功能** | 审批通过：将 pending 角色设为 approved |
| **使用场景** | 角色管理页对待审批角色点击「同意」 |
| **概述** | 修改 status 为 approved，该角色将参与路由判定和图谱构建。 |

---

### 5.7 POST /roles/{role_id}/reject

| 项目 | 说明 |
|------|------|
| **功能** | 审批拒绝：删除该 pending 角色 |
| **使用场景** | 角色管理页对待审批角色点击「不同意」 |
| **概述** | 仅对 status=pending 的角色有效，删除后不可恢复。 |

---

## 六、审核、同义词、层级配置

### 6.1 GET /review/items

| 项目 | 说明 |
|------|------|
| **功能** | 获取审核条目列表（OCR、异常等） |
| **使用场景** | 异常审核页、OCR 审核页 |
| **概述** | 支持 doc_id、type、status 过滤。 |

---

### 6.2 PUT /review/items/{item_id}

| 项目 | 说明 |
|------|------|
| **功能** | 更新审核条目状态 |
| **使用场景** | 人工标记已处理 |
| **概述** | 请求体 `{ "status": "approved" }` 等。 |

---

### 6.3 GET /review/corrections

| 项目 | 说明 |
|------|------|
| **功能** | 获取某文档的 OCR 纠错列表 |
| **使用场景** | OCR 审核页 |
| **概述** | 参数 doc_id，返回纠错条目。 |

---

### 6.4 PUT /review/corrections/{index}

| 项目 | 说明 |
|------|------|
| **功能** | 更新某条纠错内容 |
| **使用场景** | OCR 审核页修改纠错结果 |
| **概述** | 参数 doc_id，请求体含 original、corrected 等。 |

---

### 6.5 GET /synonyms

| 项目 | 说明 |
|------|------|
| **功能** | 获取同义词组列表 |
| **使用场景** | 同义词管理页 |
| **概述** | 返回 SynonymGroup 列表，用于 BM25 检索扩展。 |

---

### 6.6 POST /synonyms、PUT /synonyms/{id}、DELETE /synonyms/{id}

| 项目 | 说明 |
|------|------|
| **功能** | 增删改同义词组 |
| **使用场景** | 同义词管理页维护 |
| **概述** | 同义词用于检索时扩展查询词。 |

---

### 6.7 GET /level-patterns、PUT /level-patterns

| 项目 | 说明 |
|------|------|
| **功能** | 获取/更新标题层级正则配置 |
| **使用场景** | 层级配置页，调整结构解析规则 |
| **概述** | LevelPattern 定义各级标题的正则，用于 chunk 层级划分。 |

---

## 七、其他

### 7.1 GET /

| 项目 | 说明 |
|------|------|
| **功能** | 根路径，返回系统基本信息 |
| **使用场景** | 健康检查、版本信息 |
| **概述** | 返回 name、version、docs 链接。 |

---

### 7.2 GET /health

| 项目 | 说明 |
|------|------|
| **功能** | 健康检查 |
| **使用场景** | 启动脚本、监控探活 |
| **概述** | 返回 `{ "status": "ok" }`。 |
