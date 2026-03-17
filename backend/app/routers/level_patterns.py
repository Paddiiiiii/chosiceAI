"""层级模式配置接口"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import re

from app.models.schemas import LevelPattern
from app.services.data_manager import data_manager

router = APIRouter(prefix="/api/v1/level-patterns", tags=["level-patterns"])


class PatternTestRequest(BaseModel):
    pattern: str
    test_text: str


@router.get("", response_model=List[LevelPattern])
async def get_patterns():
    """获取当前层级模式配置"""
    return data_manager.load_level_patterns()


@router.put("")
async def update_patterns(patterns: List[LevelPattern]):
    """更新全部层级模式"""
    data_manager.save_level_patterns(patterns)
    return {"message": "Patterns updated", "count": len(patterns)}


@router.post("/test")
async def test_pattern(req: PatternTestRequest):
    """测试正则表达式是否匹配"""
    try:
        regex = re.compile(req.pattern)
        match = regex.match(req.test_text)
        return {
            "matched": match is not None,
            "match_text": match.group(0) if match else None,
            "groups": list(match.groups()) if match else [],
        }
    except re.error as e:
        return {"error": f"Invalid regex: {e}", "matched": False}


@router.post("/reset")
async def reset_to_defaults():
    """恢复默认层级模式"""
    from app.services.data_manager import DEFAULT_LEVEL_PATTERNS
    data_manager.save_level_patterns(DEFAULT_LEVEL_PATTERNS)
    return {"message": "Reset to defaults", "count": len(DEFAULT_LEVEL_PATTERNS)}
