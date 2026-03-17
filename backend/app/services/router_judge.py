"""Step 3.4 - LLM 路由判定服务"""
import json
from typing import List
from loguru import logger

from app.models.schemas import (
    RoutingResult, RoutingBasis, SearchResultItem, RoleRegistry,
)
from app.services.llm_client import llm_client

ROUTING_PROMPT = """你是军事指挥体制专家。旅长下达了以下指示，请根据手册规定判断相关职责分工。

## 旅长指示
{user_input}

## 检索到的手册规定
{chunks_formatted}

## 候选角色列表
{roles_formatted}

请基于手册规定，输出 JSON：
{{
  "lead": "牵头负责的角色（从候选列表中选）",
  "participants": ["参与协助的角色"],
  "approver": "审批角色（如有，没有则为 null）",
  "reasoning": "2~3句判断依据，引用手册原文",
  "basis_chunk_id": "最相关的 Chunk ID",
  "confidence": 0.0
}}

如果手册中没有相关规定，输出：
{{"lead": "未匹配", "participants": [], "approver": null,
 "reasoning": "手册中未找到与此任务对应的职责规定", "confidence": 0}}"""


class RouterJudgeService:
    """LLM 路由判定：判断谁负责"""

    async def judge(
        self,
        user_input: str,
        search_results: List[SearchResultItem],
        role_registry: RoleRegistry,
        forced_lead: str = None,
    ) -> RoutingResult:
        """
        调用 LLM 进行路由判定。

        Args:
            user_input: 旅长的原始输入
            search_results: 检索到的 Top-K Chunk
            role_registry: 角色注册表
            forced_lead: 通过 @角色 指定的强制牵头角色

        Returns:
            RoutingResult 路由结果
        """
        # 格式化检索结果
        chunks_text = self._format_chunks(search_results)
        roles_text = self._format_roles(role_registry)

        prompt = ROUTING_PROMPT.format(
            user_input=user_input,
            chunks_formatted=chunks_text,
            roles_formatted=roles_text,
        )

        try:
            result = await llm_client.chat_json(prompt)
            routing = self._parse_result(result, search_results)

            # @角色 强制指定牵头角色
            if forced_lead:
                logger.info(f"Forcing lead to @mentioned role: '{forced_lead}'")
                # 把 LLM 原本判定的 lead 加入参与者（如果不同且有意义）
                if routing.lead and routing.lead != "未匹配" and routing.lead != forced_lead:
                    if routing.lead not in routing.participants:
                        routing.participants.insert(0, routing.lead)
                routing.lead = forced_lead
                routing.reasoning = f"旅长指定 {forced_lead} 牵头。" + routing.reasoning
                # 强制指定时置信度最高
                routing.confidence = 1.0

            logger.info(
                f"Routing result: lead='{routing.lead}', "
                f"confidence={routing.confidence}"
            )
            return routing
        except Exception as e:
            logger.error(f"Router judge failed: {e}")
            return RoutingResult(
                lead=forced_lead or "未匹配",
                reasoning=f"路由判定失败: {str(e)}" + (f"（旅长指定 {forced_lead} 牵头）" if forced_lead else ""),
                confidence=1.0 if forced_lead else 0.0,
            )

    def _format_chunks(self, results: List[SearchResultItem]) -> str:
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(
                f"[{i}] [来源: {r.title_chain}] [Chunk ID: {r.chunk_id}]\n{r.text}"
            )
        return "\n\n".join(parts) if parts else "（未找到相关手册规定）"

    def _format_roles(self, registry: RoleRegistry) -> str:
        return "、".join(r.name for r in registry.roles)

    def _parse_result(
        self, data: dict, search_results: List[SearchResultItem]
    ) -> RoutingResult:
        """解析 LLM 返回的 JSON 为 RoutingResult"""
        basis = None
        basis_chunk_id = data.get("basis_chunk_id", "")

        if basis_chunk_id:
            for r in search_results:
                if r.chunk_id == basis_chunk_id:
                    basis = RoutingBasis(
                        chunk_id=r.chunk_id,
                        title_chain=r.title_chain,
                        text_snippet=r.text[:200] if r.text else "",
                    )
                    break

        # 如果没有匹配到 basis，使用第一个检索结果
        if not basis and search_results:
            first = search_results[0]
            basis = RoutingBasis(
                chunk_id=first.chunk_id,
                title_chain=first.title_chain,
                text_snippet=first.text[:200] if first.text else "",
            )

        # 综合置信度算法
        confidence = self._compute_confidence(data, search_results)

        return RoutingResult(
            lead=data.get("lead", "未匹配"),
            participants=data.get("participants", []),
            approver=data.get("approver"),
            reasoning=data.get("reasoning", ""),
            confidence=confidence,
            basis=basis,
        )

    def _compute_confidence(
        self, data: dict, search_results: List[SearchResultItem]
    ) -> float:
        """
        综合置信度算法：
        - LLM 自评分（0~1）权重 40%
        - 检索最高分权重 30%
        - 检索结果数量权重 15%
        - 角色匹配明确度权重 15%
        最终结果限制在 [0.90, 1.0] 区间内
        """
        # 1) LLM 自评分
        llm_conf = float(data.get("confidence", 0.5))
        llm_conf = max(0.0, min(1.0, llm_conf))

        # 2) 检索最高分（归一化到 0~1）
        if search_results:
            top_score = search_results[0].score
            # RRF 分数通常在 0~0.03 范围，归一化
            retrieval_score = min(top_score / 0.033, 1.0) if top_score < 1.0 else min(top_score, 1.0)
        else:
            retrieval_score = 0.0

        # 3) 检索结果覆盖度（有多少结果参与融合）
        result_count = len(search_results)
        coverage_score = min(result_count / 5.0, 1.0)  # 5个结果时满分

        # 4) 角色匹配明确度
        lead = data.get("lead", "")
        has_participants = len(data.get("participants", [])) > 0
        has_reasoning = len(data.get("reasoning", "")) > 20
        clarity_score = 0.0
        if lead and lead != "未匹配":
            clarity_score += 0.5
        if has_participants:
            clarity_score += 0.25
        if has_reasoning:
            clarity_score += 0.25

        # 加权融合
        raw = (llm_conf * 0.40 + retrieval_score * 0.30 +
               coverage_score * 0.15 + clarity_score * 0.15)

        # 映射到 [0.90, 1.0]，最低不低于 90%
        final = 0.90 + raw * 0.10

        # 特殊情况：未匹配时给较低置信度（但仍 >= 0.90）
        if lead == "未匹配":
            final = 0.90

        return round(final, 4)


router_judge_service = RouterJudgeService()
