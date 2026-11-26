"""scope_custom 解析器注册表（应用可注册 partner / outsourced_unit 等）。"""

from __future__ import annotations

from typing import Awaitable, Callable, Dict

from tortoise.expressions import Q

from core.services.authorization.data_scope_resource_registry import DataScopeResourceProfile

ScopeQResolver = Callable[["ScopeResolveContext"], Awaitable[Q | None]]

_REGISTRY: Dict[str, ScopeQResolver] = {}


class ScopeResolveContext:
    __slots__ = (
        "tenant_id",
        "user_id",
        "resource",
        "profile",
        "scope_payload",
        "department_uuid",
        "department_uuids",
        "department_user_ids",
    )

    def __init__(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource: str,
        profile: DataScopeResourceProfile,
        scope_payload: dict | None,
        department_uuid: str | None,
        department_user_ids: list[int],
        department_uuids: list[str] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.resource = resource
        self.profile = profile
        self.scope_payload = scope_payload or {}
        uuids = [str(x).strip() for x in (department_uuids or []) if str(x).strip()]
        if not uuids and department_uuid:
            uuids = [str(department_uuid).strip()]
        self.department_uuids = uuids
        self.department_uuid = uuids[0] if uuids else department_uuid
        self.department_user_ids = department_user_ids


def register_scope_resolver(name: str, resolver: ScopeQResolver) -> None:
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("解析器名称不能为空")
    _REGISTRY[key] = resolver


def get_scope_resolver(name: str) -> ScopeQResolver | None:
    return _REGISTRY.get((name or "").strip().lower())
