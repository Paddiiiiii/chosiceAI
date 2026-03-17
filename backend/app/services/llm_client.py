"""DeepSeek LLM 客户端封装"""
import json
from typing import Optional
from openai import AsyncOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        self.model = settings.DEEPSEEK_MODEL

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> str:
        """调用 DeepSeek Chat API"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content.strip()
            logger.debug(f"LLM response length: {len(content)}")
            return content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def chat_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> dict:
        """调用 LLM 并解析 JSON 返回"""
        raw = await self.chat(prompt, system_prompt, temperature)
        # 尝试从 markdown 代码块中提取 JSON
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM JSON response: {raw[:200]}")
            return {}


llm_client = LLMClient()
