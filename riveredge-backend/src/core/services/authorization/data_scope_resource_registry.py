"""按资源注册数据范围字段画像（应用启动时注册，非硬编码在 DataScopeService 内）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DataScopeResourceProfile:
    """描述某 RBAC 资源在 ORM 行上的范围字段映射。"""

    applicant_user_id_field: str = "applicant_user_id"
    department_uuid_field: Optional[str] = "department_uuid"
    created_by_user_id_field: Optional[str] = None
    partner_code_field: Optional[str] = None
    partner_dimension: Optional[str] = None
    """无数据策略配置时的默认解析器（scope_custom resolver 名）；禁止在业务 service 内手写行过滤。"""
    no_policy_default_resolver: Optional[str] = None
    """
    显式「本人」策略时改用的解析器。父客户类资源须与无策略默认一致（负责人+协作已归属），
    禁止再走通用 SELF（仅 applicant 字段、不含协作人）。
    """
    self_scope_resolver: Optional[str] = None


_PROFILES: dict[str, DataScopeResourceProfile] = {}

# 仅用于行级校验的内部 scope 键（manifest 无对应功能码）→ 宿主模块功能键
_FUNCTION_GRANT_SOURCES: dict[str, str] = {}

# 引用展示：宿主单据 + 目标资源 → 行级 data scope 资源键（与保存门禁对齐）
_HOST_REFERENCE_DATA_SCOPES: dict[tuple[str, str], str] = {}


def normalize_resource_key(resource: str) -> str:
    return (resource or "").strip().lower()


def register_resource_profile(resource: str, profile: DataScopeResourceProfile) -> None:
    key = normalize_resource_key(resource)
    if not key:
        raise ValueError("resource 不能为空")
    _PROFILES[key] = profile


def get_resource_profile(resource: str) -> DataScopeResourceProfile:
    key = normalize_resource_key(resource)
    return _PROFILES.get(key) or DataScopeResourceProfile()


def register_data_scope_function_grant_source(scope_resource: str, host_module_resource: str) -> None:
    """scope 键参与数据范围时，用宿主模块已授功能角色/策略（如 *-customer 父客户校验）。"""
    scope_key = normalize_resource_key(scope_resource)
    host_key = normalize_resource_key(host_module_resource)
    if not scope_key or not host_key:
        raise ValueError("scope_resource 与 host_module_resource 均不能为空")
    _FUNCTION_GRANT_SOURCES[scope_key] = host_key


def resolve_data_scope_function_grant_resource(resource: str) -> str:
    key = normalize_resource_key(resource)
    return _FUNCTION_GRANT_SOURCES.get(key, key)


def register_host_reference_data_scope(
    target_resource: str,
    host_resource: str,
    scope_resource: str,
) -> None:
    """宿主单据引用目标资源时，列表/校验使用的行级 scope 键。"""
    target = normalize_resource_key(target_resource)
    host = normalize_resource_key(host_resource)
    scope = normalize_resource_key(scope_resource)
    if not target or not host or not scope:
        raise ValueError("target_resource、host_resource、scope_resource 均不能为空")
    _HOST_REFERENCE_DATA_SCOPES[(target, host)] = scope


def resolve_host_reference_data_scope(
    target_resource: str,
    host_resource: str | None,
) -> str | None:
    target = normalize_resource_key(target_resource)
    host = normalize_resource_key(host_resource or "")
    if not target or not host:
        return None
    return _HOST_REFERENCE_DATA_SCOPES.get((target, host))
