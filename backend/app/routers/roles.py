"""角色管理接口"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.models.schemas import Role, RoleRegistry
from app.services.data_manager import data_manager

router = APIRouter(prefix="/api/v1/roles", tags=["roles"])


class RoleCreateRequest(BaseModel):
    name: str


class RoleUpdateRequest(BaseModel):
    name: str


@router.get("", response_model=RoleRegistry)
async def get_roles():
    """获取角色注册表"""
    return data_manager.load_role_registry()


@router.post("", response_model=Role)
async def add_role(req: RoleCreateRequest):
    """添加新角色"""
    registry = data_manager.load_role_registry()
    # 检查重复
    for r in registry.roles:
        if r.name == req.name:
            raise HTTPException(400, f"Role '{req.name}' already exists")
    # 生成 ID
    max_id = 0
    for r in registry.roles:
        try:
            num = int(r.role_id.replace("R", ""))
            max_id = max(max_id, num)
        except ValueError:
            pass
    new_role = Role(role_id=f"R{max_id + 1:02d}", name=req.name, mention_count=0)
    registry.roles.append(new_role)
    data_manager.save_role_registry(registry)
    return new_role


@router.put("/{role_id}", response_model=Role)
async def update_role(role_id: str, req: RoleUpdateRequest):
    """更新角色名称"""
    registry = data_manager.load_role_registry()
    for role in registry.roles:
        if role.role_id == role_id:
            role.name = req.name
            data_manager.save_role_registry(registry)
            return role
    raise HTTPException(404, f"Role {role_id} not found")


@router.delete("/{role_id}")
async def delete_role(role_id: str):
    """删除角色"""
    registry = data_manager.load_role_registry()
    registry.roles = [r for r in registry.roles if r.role_id != role_id]
    data_manager.save_role_registry(registry)
    return {"message": f"Role {role_id} deleted"}
