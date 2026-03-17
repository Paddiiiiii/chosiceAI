"""路由查询接口 - 核心 API"""
import re
from fastapi import APIRouter, HTTPException
from loguru import logger

from app.models.schemas import ChatRequest, ChatResponse
from app.services.intent import intent_service
from app.services.search import search_service
from app.services.router_judge import router_judge_service
from app.services.data_manager import data_manager

router = APIRouter(prefix="/api/v1", tags=["chat"])

# 匹配 @角色名 或 @角色名(实际角色) 或 @角色名（实际角色）
# 支持格式：@参谋长、@副参谋长(政治工作要素)、@某人（侦察情报要素）
AT_ROLE_PATTERN = re.compile(
    r"@([\u4e00-\u9fa5a-zA-Z]{2,10})"
    r"(?:[（(]([\u4e00-\u9fa5a-zA-Z\s]{2,15})[）)])?"
)


def _match_role(name: str, role_names: set) -> str | None:
    """将一个名字与角色注册表做匹配，返回匹配到的角色名或 None"""
    if not name:
        return None
    # 1. 精确匹配
    if name in role_names:
        return name
    # 2. 角色名包含输入（如输入"政治"匹配"政治工作要素"）— 优先匹配最短的角色名
    candidates = [r for r in role_names if name in r]
    if candidates:
        return min(candidates, key=len)
    # 3. 输入包含角色名（如输入"副参谋长"包含"参谋长"）— 优先匹配最长的角色名
    candidates = [r for r in role_names if r in name]
    if candidates:
        return max(candidates, key=len)
    return None


def _extract_at_role(text: str, role_registry) -> str | None:
    """
    从输入中提取 @角色。
    支持: @参谋长、@副参谋长(政治工作要素)、@某人（侦察情报要素）
    括号内的角色名优先级更高。
    """
    match = AT_ROLE_PATTERN.search(text)
    if not match:
        return None

    name_part = match.group(1)          # @后面的名字
    paren_part = match.group(2)         # 括号里的角色（可能为 None）
    role_names = {r.name for r in role_registry.roles}

    # 括号内的角色优先级最高
    if paren_part:
        result = _match_role(paren_part.strip(), role_names)
        if result:
            return result

    # 再匹配 @后面的名字
    result = _match_role(name_part, role_names)
    if result:
        return result

    return None


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    旅长输入 → 路由判定。

    Pipeline: 意图识别 → 双路检索 → RRF 融合 → LLM 路由判定
    支持 @角色 语法，被@的角色强制为牵头负责角色。
    """
    logger.info(f"Chat request: {request.input[:50]}...")

    role_registry = data_manager.load_role_registry()

    # 检测 @角色
    forced_lead = _extract_at_role(request.input, role_registry)
    if forced_lead:
        logger.info(f"Detected @role: '{forced_lead}', will force as lead")

    # 去掉 @角色(...) 后的文本用于检索
    clean_input = AT_ROLE_PATTERN.sub("", request.input).strip() or request.input

    # Step 1: 意图识别
    search_query = await intent_service.extract_search_query(clean_input)

    # Step 2+3: 双路检索 + RRF 融合
    search_results = await search_service.hybrid_search(
        query=search_query,
        filters=request.context,
    )

    if not search_results:
        return ChatResponse(
            result={
                "lead": forced_lead or "未匹配",
                "reasoning": "未找到相关手册规定" + (f"（旅长指定 {forced_lead} 牵头）" if forced_lead else ""),
                "confidence": 0.9 if forced_lead else 0.0,
            },
            search_results=[],
        )

    # Step 4: LLM 路由判定
    routing_result = await router_judge_service.judge(
        user_input=request.input,
        search_results=search_results,
        role_registry=role_registry,
        forced_lead=forced_lead,
    )

    return ChatResponse(
        result=routing_result,
        search_results=[r.model_dump() for r in search_results],
    )
