"""
菜单徽章分区进程内缓存（L1）+ singleflight。

- 避免每次命中都读 PostgreSQL cache 桶（远程库 RTT 高）。
- 按 tenant + user + permission_version + section 分区，未过期分区直接复用。
"""

from __future__ import annotations

import asyncio
import copy
import os
import time
from typing import Any, Awaitable, Callable

SectionFragment = dict[str, Any]

_SECTION_TTL_SEC = max(15, int(os.getenv("MENU_BADGE_SECTION_CACHE_TTL", "90")))

_store: dict[tuple[int, int, int, str], tuple[float, SectionFragment]] = {}
_inflight: dict[tuple[int, int, int, str], asyncio.Future[SectionFragment]] = {}


def _cache_key(tenant_id: int, user_id: int, permission_version: int, section_key: str) -> tuple[int, int, int, str]:
    return (int(tenant_id), int(user_id), int(permission_version), section_key)


async def get_or_compute_section(
    *,
    tenant_id: int,
    user_id: int,
    permission_version: int,
    section_key: str,
    compute: Callable[[], Awaitable[SectionFragment]],
    bypass_cache: bool = False,
) -> SectionFragment:
    ck = _cache_key(tenant_id, user_id, permission_version, section_key)
    now = time.monotonic()
    if not bypass_cache:
        hit = _store.get(ck)
        if hit is not None and now - hit[0] < _SECTION_TTL_SEC:
            return copy.deepcopy(hit[1])

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[SectionFragment] = loop.create_future()
    existing = _inflight.setdefault(ck, fut)
    if existing is not fut:
        return copy.deepcopy(await existing)

    try:
        fragment = await compute()
        payload: SectionFragment = dict(fragment) if fragment else {}
        _store[ck] = (time.monotonic(), payload)
        fut.set_result(payload)
        return copy.deepcopy(payload)
    except Exception as exc:
        if not fut.done():
            fut.set_exception(exc)
        raise
    finally:
        if _inflight.get(ck) is fut:
            _inflight.pop(ck, None)


def invalidate_menu_badge_section_cache(*, tenant_id: int | None = None) -> None:
    """权限/菜单大变更后可清进程内分区缓存（permission_version 变更也会自然 miss）。"""
    if tenant_id is None:
        _store.clear()
        return
    tid = int(tenant_id)
    for key in list(_store.keys()):
        if key[0] == tid:
            _store.pop(key, None)


def touch_kuaizhizao_menu_badges_for_tenant(tenant_id: int) -> None:
    """单据/审批状态变更后立即使菜单与工作台角标缓存失效。"""
    invalidate_menu_badge_section_cache(tenant_id=int(tenant_id))
