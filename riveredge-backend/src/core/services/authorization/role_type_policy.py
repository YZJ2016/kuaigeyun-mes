"""角色类型纯度规则（唯一真源）。

约定：一个用户绑定的角色要么全部是 ``station``（工位终端）类型、要么全部
不是——``station`` 不得与 ``internal`` / ``external`` 混挂。
所有用户-角色绑定/改绑入口（创建、更新、批量、导入、角色侧追加用户、
历史角色合并、自动绑 GUEST 等）都必须经这里校验。
"""

from __future__ import annotations

from typing import Iterable, Optional

from infra.exceptions.exceptions import ValidationError

ROLE_TYPE_INTERNAL = "internal"
ROLE_TYPE_EXTERNAL = "external"
ROLE_TYPE_STATION = "station"

MIXED_ROLE_TYPE_MESSAGE = "工位终端（station）角色不能与内部/外部角色混挂"
ROLE_TYPE_LOCKED_MESSAGE = "角色已绑定用户，不允许在 station 与非 station 类型间切换"


def is_station_role_type(role_type: object) -> bool:
    """规范化判断角色类型是否为 station。"""
    return str(role_type or "").strip().lower() == ROLE_TYPE_STATION


def assert_pure_role_types(role_types: Iterable[object]) -> None:
    """一组角色类型须「全 station」或「全非 station」，否则抛 ValidationError。"""
    has_station = False
    has_non_station = False
    for raw in role_types or ():
        if is_station_role_type(raw):
            has_station = True
        else:
            has_non_station = True
        if has_station and has_non_station:
            raise ValidationError(MIXED_ROLE_TYPE_MESSAGE)


async def assert_roles_assignment_pure(
    *,
    tenant_id: int,
    role_ids: Iterable[int],
    user_id: Optional[int] = None,
    using_db=None,
) -> None:
    """校验一组角色绑定结果的纯度（追加绑定/全量替换前的统一入口）。

    - ``role_ids``：本次要绑定的角色 ID。
    - ``user_id``：非空时把该用户已绑定角色并入判定（追加绑定场景）；
      为空则只校验本次角色集合（新建用户或全量替换场景）。
    """
    from core.models.role import Role
    from core.models.user_role import UserRole

    ids = {int(rid) for rid in role_ids or ()}
    if user_id is not None:
        existing = UserRole.filter(user_id=user_id)
        if using_db is not None:
            existing = existing.using_db(using_db)
        ids.update(int(rid) for rid in await existing.values_list("role_id", flat=True))
    if not ids:
        return
    role_query = Role.filter(
        id__in=list(ids), tenant_id=tenant_id, deleted_at__isnull=True
    )
    if using_db is not None:
        role_query = role_query.using_db(using_db)
    role_types = await role_query.values_list("role_type", flat=True)
    assert_pure_role_types(role_types)
