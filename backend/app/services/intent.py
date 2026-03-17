"""Step 3.2 - 意图识别服务"""
from loguru import logger

from app.services.llm_client import llm_client

INTENT_PROMPT = """你是军事指挥辅助系统的意图识别模块。请提取旅长输入的核心任务描述，
用于后续检索和路由判定。

输入：{user_input}

输出 JSON：
{{
  "search_query": "提取出的核心任务描述，用于检索"
}}"""


class IntentService:
    """意图识别：提取核心任务描述用于检索"""

    async def extract_search_query(self, user_input: str) -> str:
        """
        从用户输入中提取检索 query。

        降级策略：LLM 调用失败时，直接用原始输入做检索。

        Args:
            user_input: 旅长的原始输入

        Returns:
            提取出的检索 query
        """
        try:
            prompt = INTENT_PROMPT.format(user_input=user_input)
            result = await llm_client.chat_json(prompt)
            search_query = result.get("search_query", "")
            if search_query:
                logger.info(f"Intent extracted: '{user_input[:30]}...' -> '{search_query}'")
                return search_query
        except Exception as e:
            logger.warning(f"Intent extraction failed: {e}, using raw input")

        # 降级：使用原始输入
        logger.info(f"Using raw input as search query: '{user_input[:50]}...'")
        return user_input


intent_service = IntentService()
