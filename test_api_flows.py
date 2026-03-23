#!/usr/bin/env python3
"""
接口验证脚本 - 以「组织侦察情报」为贯穿示例

用法：
  python scripts/test_api_flows.py --demo              # 贯穿示例：组织侦察情报串联 5 场景
  python scripts/test_api_flows.py                    # 运行全部场景（通用用例）
  python scripts/test_api_flows.py --scene 1          # 仅运行场景 1
  python scripts/test_api_flows.py --scene 2 --role 参谋长 --phase 战斗准备

前置：服务已启动 (python main.py)，文档已处理，图谱已构建
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import httpx
except ImportError:
    print("请安装: pip install httpx")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8000/api/v1"
TIMEOUT = 60.0

# 组织侦察情报 贯穿示例的 chunk_id（与接口验证手册、技术方案一致）
ANCHOR_CHUNK = "ch2_s01_p01_01_sub05"       # （5）判断三情。
SUB_CHUNK = "ch2_s01_p02_01_sub06"       # 	（6）判断三情。


def _post(path: str, data: dict) -> dict:
    r = httpx.post(f"{BASE_URL}{path}", json=data, timeout=TIMEOUT, trust_env=False)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict = None) -> dict:
    r = httpx.get(f"{BASE_URL}{path}", params=params or {}, timeout=TIMEOUT, trust_env=False)
    r.raise_for_status()
    return r.json()


def _retrieval():
    return {"use_vector": True, "use_bm25": True, "use_graph": True}


def _get_top5_chunk_ids(query: str):
    """Search 取前 5 个 chunk，提取 chunk_id 列表"""
    search_res = _post("/search/comparison", {
        "query": query,
        "filters": None,
        "retrieval": _retrieval(),
    })
    rrf = search_res.get("rrf_results", [])
    chunk_ids = [r.get("chunk_id") for r in rrf[:5] if r.get("chunk_id")]
    return chunk_ids


def run_demo():
    """贯穿示例：以组织侦察情报串联 5 个场景"""
    print("\n" + "=" * 70)
    print("贯穿示例：组织侦察情报")
    print("=" * 70)

    retrieval = _retrieval()
    query = "组织侦察情报的流程"

    # ─── 场景 1：任务拆解 ───
    print("\n【场景 1】任务拆解")
    print("-" * 50)
    print(f"[Step 1] POST /search/comparison  query={query!r}")
    chunk_ids = _get_top5_chunk_ids(query)
    if not chunk_ids:
        chunk_ids = [ANCHOR_CHUNK]
    print(f"  -> 前 5 个 chunk_id: {chunk_ids}")

    print(f"\n[Step 2] GET /graph/task_decompose  对 5 个 chunk 分别调用并融合")
    seen = set()
    all_subtasks = []
    for cid in chunk_ids:
        decomp = _get("/graph/task_decompose", {"chunk_id": cid})
        for s in decomp.get("subtasks", []):
            sid = s.get("chunk_id")
            if sid and sid not in seen:
                seen.add(sid)
                all_subtasks.append(s)
    for i, s in enumerate(all_subtasks[:15], 1):
        print(f"     {i}. {s.get('task_name')} (led_by={s.get('led_by')})")
    if len(all_subtasks) > 15:
        print(f"     ... 共 {len(all_subtasks)} 步")

    # ─── 场景 2：找对应人员（基于前 5 个 chunk 融合） ───
    print("\n【场景 2】找对应人员 - 基于前 5 个 chunk 融合")
    print("-" * 50)
    print(f"[GET] /graph/task_roles  对前 5 个 chunk 分别调用并融合")
    roles_by_task = {}
    for cid in chunk_ids:
        roles_res = _get("/graph/task_roles", {"chunk_id": cid})
        task_name = roles_res.get("task") or cid
        roles = roles_res.get("roles", {})
        if roles.get("led_by") or roles.get("approved_by") or roles.get("involves"):
            roles_by_task[task_name] = roles
    for task, roles in list(roles_by_task.items())[:5]:
        print(f"  -> {task}: 牵头={roles.get('led_by')} 审批={roles.get('approved_by')} 参与={roles.get('involves')}")

    print(f"\n[GET] /graph/role_tasks  role=参谋长  phase=战斗准备")
    rt_res = _get("/graph/role_tasks", {"role": "参谋长", "phase": "战斗准备"})
    for t in rt_res.get("tasks", [])[:5]:
        print(f"     - {t.get('task_name')} ({t.get('responsibility')})")

    # ─── 场景 3：任务流程（前 5 个 chunk 的前置依赖融合） ───
    print("\n【场景 3】任务流程 - 前 5 个 chunk 的前置依赖融合")
    print("-" * 50)
    print(f"[GET] /graph/task_prerequisites  对前 5 个 chunk 分别调用并融合")
    seen_preq = set()
    for cid in chunk_ids:
        try:
            preq = _get("/graph/task_prerequisites", {"chunk_id": cid})
            for p in preq.get("prerequisites", []):
                key = (p.get("chunk_id"), p.get("task_name"))
                if (p.get("chunk_id") or p.get("task_name")) and key not in seen_preq:
                    seen_preq.add(key)
                    print(f"     - {p.get('task_name')} ({p.get('relation')}) [from {preq.get('task')}]")
        except httpx.HTTPStatusError:
            pass

    # ─── 场景 4：任务产出（前 5 个 chunk 的产物融合） ───
    print("\n【场景 4】任务产出 - 前 5 个 chunk 的产物融合")
    print("-" * 50)
    print(f"[GET] /graph/task_products  对前 5 个 chunk 分别调用并融合")
    seen_prod = set()
    for cid in chunk_ids:
        prod = _get("/graph/task_products", {"chunk_id": cid})
        for p in prod.get("products", []):
            name = p.get("product")
            if name and name not in seen_prod:
                seen_prod.add(name)
                print(f"     - {name} (source={p.get('source_task')})")
    if not seen_prod:
        print("     (无产物，需 LLM 抽取 PRODUCES)")

    # ─── 场景 5：路由判定 ───
    print("\n【场景 5】路由判定 - 侦察计划该谁去做？")
    print("-" * 50)
    print("[POST] /chat  input='侦察计划该谁去做？'")
    chat_res = _post("/chat", {"input": "侦察计划该谁去做？", "context": {"phase": "战斗准备"}, "retrieval": retrieval})
    r = chat_res.get("result", {})
    print(f"  -> 牵头: {r.get('lead')}")
    print(f"  -> 参与: {r.get('participants')}")
    print(f"  -> 依据: {r.get('reasoning', '')[:150]}...")

    print("\n" + "=" * 70)
    print("贯穿示例完成")
    print("=" * 70)


def scene1_task_decompose():
    """场景 1：任务拆解（前 5 个 chunk 融合）"""
    print("\n" + "=" * 60)
    print("场景 1：任务拆解")
    print("=" * 60)

    query = "判断三情的流程"

    print(f"\n[Step 1] POST /search/comparison  query={query!r}")
    chunk_ids = _get_top5_chunk_ids(query)
    if not chunk_ids:
        print("  [无结果]")
        return
    print(f"  -> 前 5 个 chunk_id: {chunk_ids}")

    print(f"\n[Step 2] GET /graph/task_decompose  对 5 个 chunk 分别调用并融合")
    seen = set()
    all_subtasks = []
    for cid in chunk_ids:
        decomp = _get("/graph/task_decompose", {"chunk_id": cid})
        for s in decomp.get("subtasks", []):
            sid = s.get("chunk_id")
            if sid and sid not in seen:
                seen.add(sid)
                all_subtasks.append(s)
    for i, s in enumerate(all_subtasks, 1):
        print(f"     {i}. {s.get('task_name')} (led_by={s.get('led_by')})")


def scene2_find_personnel(role: str = None, phase: str = None):
    """场景 2：找对应人员"""
    print("\n" + "=" * 60)
    print("场景 2：找对应人员")
    print("=" * 60)

    if role:
        print(f"\n[GET] /graph/role_tasks  role={role!r}  phase={phase or '(全部)'}")
        res = _get("/graph/role_tasks", {"role": role, "phase": phase})
        for t in res.get("tasks", [])[:8]:
            print(f"     - {t.get('task_name')} ({t.get('responsibility')})")
    else:
        query = "判断三情"
        print(f"\n[Step 1] POST /search/comparison  query={query!r}")
        chunk_ids = _get_top5_chunk_ids(query)
        if not chunk_ids:
            chunk_ids = [ANCHOR_CHUNK]
        print(f"  -> 前 5 个 chunk_id: {chunk_ids}")

        print(f"\n[Step 2] GET /graph/task_roles  对前 5 个 chunk 分别调用并融合")
        for cid in chunk_ids:
            res = _get("/graph/task_roles", {"chunk_id": cid})
            roles = res.get("roles", {})
            if roles.get("led_by") or roles.get("approved_by") or roles.get("involves"):
                print(f"  -> {res.get('task')}: 牵头={roles.get('led_by')} 审批={roles.get('approved_by')} 参与={roles.get('involves')}")


def scene3_task_flow(chunk_id: str = None):
    """场景 3：任务流程（前置依赖）"""
    print("\n" + "=" * 60)
    print("场景 3：任务流程")
    print("=" * 60)

    cid = chunk_id or SUB_CHUNK
    print(f"\n[GET] /graph/task_prerequisites  chunk_id={cid}")
    try:
        res = _get("/graph/task_prerequisites", {"chunk_id": cid})
        for p in res.get("prerequisites", []):
            print(f"     - {p.get('task_name')} ({p.get('relation')})")
    except httpx.HTTPStatusError as e:
        print(f"  -> {e}")


def scene4_task_products(chunk_id: str = None, role: str = None, phase: str = None):
    """场景 4：任务产出"""
    print("\n" + "=" * 60)
    print("场景 4：任务产出")
    print("=" * 60)

    if chunk_id:
        print(f"\n[GET] /graph/task_products  chunk_id={chunk_id}")
        res = _get("/graph/task_products", {"chunk_id": chunk_id})
    elif role:
        print(f"\n[GET] /graph/task_products  role={role!r}  phase={phase or '(全部)'}")
        res = _get("/graph/task_products", {"role": role, "phase": phase})
    else:
        print(f"\n[GET] /graph/task_products  chunk_id={SUB_CHUNK}")
        res = _get("/graph/task_products", {"chunk_id": SUB_CHUNK})

    for p in res.get("products", []):
        print(f"     - {p.get('product')} (source={p.get('source_task')})")
    if not res.get("products"):
        print("     (无产物)")


def scene5_routing():
    """场景 5：路由判定"""
    print("\n" + "=" * 60)
    print("场景 5：路由判定")
    print("=" * 60)

    cases = ["判断三情该谁去做？", "谁负找完成作战任务的条件和弱项？", "形成结论谁来协调组织？",
             "形成哪些成果？"]
    for i, inp in enumerate(cases, 1):
        print(f"\n[用例 {i}] POST /chat  input={inp!r}")
        try:
            res = _post("/chat", {"input": inp, "context": None, "retrieval": _retrieval()})
            r = res.get("result", {})
            print(f"  -> 牵头: {r.get('lead')}  置信度: {r.get('confidence')}")
        except Exception as e:
            print(f"  -> {e}")


def main():
    parser = argparse.ArgumentParser(description="接口验证脚本")
    parser.add_argument("--demo", action="store_true", help="贯穿示例：组织侦察情报串联 5 场景")
    parser.add_argument("--scene", type=int, choices=[1, 2, 3, 4, 5], help="只运行指定场景")
    parser.add_argument("--role", type=str, help="场景 2 角色名")
    parser.add_argument("--phase", type=str, help="场景 2/4 阶段")
    parser.add_argument("--chunk-id", type=str, help="场景 3/4 指定 chunk_id")
    args = parser.parse_args()

    # 健康检查：重试 3 次，禁用代理（避免 502）
    health_url = "http://127.0.0.1:8000/health"
    for attempt in range(3):
        try:
            r = httpx.get(health_url, timeout=10.0, trust_env=False)
            r.raise_for_status()
            break
        except Exception as e:
            if attempt < 2:
                print(f"  等待服务... ({attempt + 1}/3)")
                time.sleep(2)
            else:
                print(f"服务未启动: {e}\n请先执行: python main.py")
                sys.exit(1)

    if args.demo:
        run_demo()
        return

    scenes = {args.scene} if args.scene else {1, 2, 3, 4, 5}
    if 1 in scenes:
        scene1_task_decompose()
    if 2 in scenes:
        scene2_find_personnel(role=args.role, phase=args.phase)
    if 3 in scenes:
        scene3_task_flow(chunk_id=args.chunk_id)
    if 4 in scenes:
        scene4_task_products(chunk_id=args.chunk_id, role=args.role, phase=args.phase)
    if 5 in scenes:
        scene5_routing()

    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
