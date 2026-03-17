"""Step 1.1 - OCR 纠错服务"""
from typing import List, Tuple
from loguru import logger

from app.config import settings
from app.models.schemas import CorrectionItem, ReviewItem
from app.services.llm_client import llm_client

CORRECTION_PROMPT = """你是军事文献校对专家。以下是 OCR 扫描得到的军事教材段落，可能存在识别错误。
请纠正明显的 OCR 错误（错字、漏字、乱码），保持原文语义和表述不变。

规则：
1. 只修正明显的 OCR 识别错误，不改写原文表述
2. 无法推断的乱码段落，用 [OCR_ERROR] 标记
3. 输出纠正后的完整段落，再用 JSON 列出所有修改

输出格式：
```
纠正后的段落文字...
```

```json
[
  {{"original": "原始错误文字", "corrected": "纠正后文字", "type": "错误类型"}}
]
```

错误类型包括：garbled（乱码）, missing_char（缺字）, wrong_char（错字）, extra_char（多字）

原始段落：
{paragraph_text}"""


class OCRCorrectionService:
    """OCR 纠错服务：将文本分段送 LLM 纠错"""

    async def correct_text(
        self, text: str, chunk_size: int = None
    ) -> Tuple[str, List[CorrectionItem], List[ReviewItem]]:
        """
        对全文进行 OCR 纠错。

        Args:
            text: OCR 原始文本
            chunk_size: 每段大小（字符数）

        Returns:
            (纠正后全文, 纠错日志列表, 需审核条目列表)
        """
        chunk_size = chunk_size or settings.OCR_CHUNK_SIZE
        paragraphs = self._split_paragraphs(text, chunk_size)
        logger.info(f"OCR correction: {len(paragraphs)} segments to process")

        corrected_parts = []
        all_corrections: List[CorrectionItem] = []
        review_items: List[ReviewItem] = []
        current_line = 1

        for idx, para in enumerate(paragraphs):
            logger.info(f"Processing segment {idx + 1}/{len(paragraphs)}")
            try:
                corrected, corrections = await self._correct_paragraph(para, current_line)
                corrected_parts.append(corrected)
                all_corrections.extend(corrections)

                # 标记 OCR_ERROR 为审核条目
                if "[OCR_ERROR]" in corrected:
                    review_items.append(ReviewItem(
                        item_id=f"ocr_{idx}",
                        type="ocr_error",
                        description=f"段落 {idx + 1} 包含无法识别的乱码",
                        original_text=para[:200],
                        status="pending",
                    ))
            except Exception as e:
                logger.warning(f"Segment {idx + 1} correction failed: {e}, using original")
                corrected_parts.append(para)

            current_line += para.count("\n") + 1

        corrected_text = "\n".join(corrected_parts)
        logger.info(f"OCR correction done: {len(all_corrections)} corrections, {len(review_items)} reviews")
        return corrected_text, all_corrections, review_items

    async def _correct_paragraph(
        self, paragraph: str, line_offset: int
    ) -> Tuple[str, List[CorrectionItem]]:
        """纠正单个段落"""
        prompt = CORRECTION_PROMPT.format(paragraph_text=paragraph)
        response = await llm_client.chat(prompt)

        # 解析响应
        corrected_text = paragraph
        corrections: List[CorrectionItem] = []

        # 提取纠正后的文本（在第一个 ```json 之前的 ``` 块中）
        parts = response.split("```")
        if len(parts) >= 2:
            corrected_text = parts[1].strip()
            if corrected_text.startswith("json"):
                corrected_text = paragraph  # 解析失败用原文
            # 去掉可能的语言标记
            for lang in ["text", "plaintext", "txt"]:
                if corrected_text.startswith(lang):
                    corrected_text = corrected_text[len(lang):].strip()
                    break

        # 提取纠错 JSON
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
            try:
                import json
                items = json.loads(json_str)
                for item in items:
                    corrections.append(CorrectionItem(
                        line=line_offset,
                        original=item.get("original", ""),
                        corrected=item.get("corrected", ""),
                        type=item.get("type", "unknown"),
                        status="pending",
                    ))
            except Exception:
                pass

        return corrected_text, corrections

    def _split_paragraphs(self, text: str, max_size: int) -> List[str]:
        """按自然段分组，每组不超过 max_size 字符"""
        lines = text.strip().split("\n")
        segments = []
        current_segment = []
        current_size = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            if current_size + line_len > max_size and current_segment:
                segments.append("\n".join(current_segment))
                current_segment = []
                current_size = 0
            current_segment.append(line)
            current_size += line_len

        if current_segment:
            segments.append("\n".join(current_segment))

        return segments


ocr_correction_service = OCRCorrectionService()
