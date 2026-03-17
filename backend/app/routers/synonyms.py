"""同义词管理接口"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.models.schemas import SynonymGroup
from app.services.data_manager import data_manager

router = APIRouter(prefix="/api/v1/synonyms", tags=["synonyms"])


class SynonymCreateRequest(BaseModel):
    terms: List[str]


@router.get("", response_model=List[SynonymGroup])
async def list_synonyms():
    """获取所有同义词组"""
    return data_manager.load_synonyms()


@router.post("", response_model=SynonymGroup)
async def add_synonym(req: SynonymCreateRequest):
    """添加同义词组"""
    synonyms = data_manager.load_synonyms()
    max_id = max((s.id for s in synonyms), default=0)
    new_group = SynonymGroup(id=max_id + 1, terms=req.terms)
    synonyms.append(new_group)
    data_manager.save_synonyms(synonyms)
    return new_group


@router.put("/{syn_id}", response_model=SynonymGroup)
async def update_synonym(syn_id: int, req: SynonymCreateRequest):
    """更新同义词组"""
    synonyms = data_manager.load_synonyms()
    for s in synonyms:
        if s.id == syn_id:
            s.terms = req.terms
            data_manager.save_synonyms(synonyms)
            return s
    raise HTTPException(404, f"Synonym group {syn_id} not found")


@router.delete("/{syn_id}")
async def delete_synonym(syn_id: int):
    """删除同义词组"""
    synonyms = data_manager.load_synonyms()
    synonyms = [s for s in synonyms if s.id != syn_id]
    data_manager.save_synonyms(synonyms)
    return {"message": f"Synonym group {syn_id} deleted"}
