"""Step 1.2 - 结构层级解析服务"""
import re
from typing import List, Tuple, Optional
from loguru import logger

from app.models.schemas import LevelPattern


class ParsedNode:
    """解析出的结构树节点"""

    def __init__(
        self,
        level: int = 0,
        raw_title: str = "",
        title: str = "",
        node_id: str = "",
        line_start: int = 0,
    ):
        self.level = level
        self.raw_title = raw_title
        self.title = title
        self.node_id = node_id
        self.line_start = line_start
        self.line_end: int = 0
        self.text_lines: List[str] = []
        self.children: List['ParsedNode'] = []
        self.parent: Optional['ParsedNode'] = None

    @property
    def full_text(self) -> str:
        return "\n".join(self.text_lines).strip()

    def to_dict(self) -> dict:
        return {
            "id": self.node_id,
            "level": self.level,
            "title": self.title,
            "text": self.full_text,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "children": [c.to_dict() for c in self.children],
        }


# 中文数字→阿拉伯数字映射
CN_NUMS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}

CIRCLED_NUMS = {
    "①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5,
    "⑥": 6, "⑦": 7, "⑧": 8, "⑨": 9, "⑩": 10,
}


class StructureParser:
    """文档结构层级解析器"""

    def parse(
        self, text: str, patterns: List[LevelPattern], root_title: str = "作战指挥手册"
    ) -> ParsedNode:
        """
        解析文本的层级结构，构建结构树。

        Args:
            text: 纠错后的全文
            patterns: 层级模式列表
            root_title: 根节点标题

        Returns:
            结构树根节点
        """
        lines = text.strip().split("\n")
        compiled = [(p.level, re.compile(p.pattern)) for p in patterns]

        root = ParsedNode(level=0, title=root_title, node_id="root")
        stack: List[ParsedNode] = [root]
        id_counters: dict = {}  # 用于生成唯一 ID

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            matched = False
            for level, regex in compiled:
                m = regex.match(stripped)
                if m:
                    # 提取标题
                    title, content_tail = self._extract_title(stripped, m, level)
                    node_id = self._generate_id(stack, level, id_counters)

                    new_node = ParsedNode(
                        level=level,
                        raw_title=stripped,
                        title=title,
                        node_id=node_id,
                        line_start=line_num,
                    )

                    # 如果标题行尾部有内容文本，加入 text_lines
                    if content_tail:
                        new_node.text_lines.append(content_tail)

                    # 弹出栈中同级或更低级的节点
                    while len(stack) > 1 and stack[-1].level >= level:
                        popped = stack.pop()
                        popped.line_end = line_num - 1

                    # 加入父节点的 children
                    parent = stack[-1]
                    new_node.parent = parent
                    parent.children.append(new_node)
                    stack.append(new_node)
                    matched = True
                    break

            if not matched:
                # 非标题行，作为当前节点的内容文本
                if len(stack) > 1:
                    stack[-1].text_lines.append(stripped)
                else:
                    root.text_lines.append(stripped)

        # 关闭所有剩余节点
        for node in stack:
            if node.line_end == 0:
                node.line_end = len(lines)

        node_count = self._count_nodes(root)
        logger.info(f"Structure parsed: {node_count} nodes across {len(lines)} lines")
        return root

    def _extract_title(self, line: str, match: re.Match, level: int) -> Tuple[str, str]:
        """
        从匹配行中提取标题和剩余内容。

        规则：
        - 高层标题（level 1~3，如"第X章"、"第X节"、"X、"）：整行作为标题
        - 数字序号标题（level 5~7，如"1." "（1）" "①"）：在第一个句号"。"处截断，
          句号之前（含序号）为标题，之后为正文内容
        - 中间层（level 4）：在第一个句号处截断
        - 短行（<=30字且无句号）：整行作为标题
        """
        # 高层标题（章、节、X、）整行就是标题
        if level <= 3:
            return line, ""

        # 数字序号标题 (level 4~7): 在第一个句号处截断
        # 找到第一个中文句号
        period_idx = line.find("。")
        if period_idx > 0:
            title_part = line[:period_idx + 1].strip()  # 包含句号
            content_part = line[period_idx + 1:].strip()
            return title_part, content_part

        # 没有句号的情况：短行整行作为标题
        if len(line) <= 60:
            return line, ""

        # 长行无句号：match部分作为标题，余下作内容
        match_end = match.end()
        title_part = line[:match_end].strip()
        rest = line[match_end:].strip()
        if rest:
            return title_part, rest

        return line, ""

    def _generate_id(
        self, stack: List[ParsedNode], level: int, counters: dict
    ) -> str:
        """根据栈中的祖先节点生成 ID"""
        # 找到父节点
        parent_id = ""
        for node in reversed(stack):
            if node.level < level:
                parent_id = node.node_id
                break

        # 更新计数器
        counter_key = parent_id + f"_L{level}"
        counters[counter_key] = counters.get(counter_key, 0) + 1
        seq = counters[counter_key]

        # 生成 ID
        level_prefix = {1: "ch", 2: "s", 3: "p", 4: "t", 5: "", 6: "sub", 7: "it"}
        prefix = level_prefix.get(level, f"L{level}_")

        if parent_id and parent_id != "root":
            return f"{parent_id}_{prefix}{seq:02d}" if prefix else f"{parent_id}_{seq:02d}"
        else:
            return f"{prefix}{seq}" if prefix else f"n{seq}"

    def _count_nodes(self, node: ParsedNode) -> int:
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count


structure_parser = StructureParser()
