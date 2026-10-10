"""快制造 — 移动端工作台导航：manifest.mobile_workbench 为唯一真源。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from apps.kuaizhizao.services.menu_badge_counts_service import fetch_menu_badge_counts
from core.services.application.application_service import ApplicationService
from core.services.authorization.data_scope_service import DataScopeService
from core.services.authorization.effective_access_service import EffectiveUserAccess
from core.services.authorization.user_permission_service import UserPermissionService
from infra.models.user import User

_MANIFEST_PATH = ApplicationService._get_plugins_directory() / "kuaizhizao" / "manifest.json"

# 手机工作台首屏分区 scope 顺序（与 riveredge-app/mobile workbenchService 一致）
MOBILE_WORKBENCH_HOME_SCOPES: tuple[str, ...] = (
    "workshop",
    "warehouse",
    "quality",
    "equipment",
    "mold",
    "common",
)

_manifest_cache: tuple[float, dict[str, Any]] | None = None


def _load_mobile_workbench_config() -> dict[str, Any]:
    global _manifest_cache
    if not _MANIFEST_PATH.is_file():
        raise RuntimeError(f"Kuaizhizao manifest 缺失: {_MANIFEST_PATH}")
    mtime = _MANIFEST_PATH.stat().st_mtime
    if _manifest_cache is not None and _manifest_cache[0] == mtime:
        return _manifest_cache[1]
    data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    cfg = data.get("mobile_workbench")
    if not isinstance(cfg, dict):
        raise RuntimeError("manifest.json 缺少 mobile_workbench 配置")
    _manifest_cache = (mtime, cfg)
    return cfg


def _resolve_permissions_any(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if isinstance(item, str) and str(item).strip()]


def _perm_set_contains(user_perms: set[str], code: str | None) -> bool:
    if not code or not str(code).strip():
        return False
    return UserPermissionService._normalize_permission_code(code) in user_perms


def _perm_set_overlaps(user_perms: set[str], codes: list[str]) -> bool:
    if not codes:
        return False
    normalized = {
        UserPermissionService._normalize_permission_code(c)
        for c in codes
        if c and str(c).strip()
    }
    return bool(user_perms & normalized)


def _is_external_partner_from_roles(roles: tuple[Any, ...] | list[Any], *, admin_bypass: bool) -> bool:
    if admin_bypass:
        return False
    return any(
        (getattr(role, "role_type", "") or "").strip().lower() == "external"
        and (getattr(role, "external_partner_type", "") or "").strip()
        for role in roles
    )


async def _user_is_external_partner(tenant_id: int, user: User) -> bool:
    if await UserPermissionService.is_admin_bypass(user, tenant_id):
        return False
    roles = await DataScopeService._load_active_roles(user.id, tenant_id)
    return _is_external_partner_from_roles(roles, admin_bypass=False)


def _filter_scope_sections(
    scope_cfg: dict[str, Any],
    *,
    user_perms: set[str],
    is_external_partner: bool,
    admin_bypass: bool,
) -> list[dict[str, Any]]:
    if scope_cfg.get("hide_when_external_partner") and is_external_partner:
        return []

    sections_out: list[dict[str, Any]] = []
    for section in scope_cfg.get("sections") or []:
        if not isinstance(section, dict):
            continue
        entries_out: list[dict[str, Any]] = []
        for entry in section.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("internal_only") and is_external_partner:
                continue
            if entry.get("outsource_only") and not is_external_partner:
                continue
            permission = (entry.get("permission") or "").strip()
            permissions_any = _resolve_permissions_any(entry.get("permissions_any"))
            if not admin_bypass:
                base = _perm_set_contains(user_perms, permission) if permission else False
                ext = _perm_set_overlaps(user_perms, permissions_any) if permissions_any else False
                if not (base or ext):
                    continue
            route = (entry.get("route") or "").strip()
            if not route:
                continue
            item: dict[str, Any] = {
                "key": (entry.get("key") or "").strip() or "entry",
                "label": (entry.get("label") or "").strip() or route,
                "route": route,
                "icon": (entry.get("icon") or "app").strip(),
            }
            icon_group = (entry.get("icon_group") or "").strip()
            if icon_group:
                item["icon_group"] = icon_group
            if entry.get("solo_row"):
                item["solo_row"] = True
            badge_keys = _entry_badge_keys(entry)
            if badge_keys:
                item["_badge_keys"] = badge_keys
            entries_out.append(item)
        if not entries_out:
            continue
        sections_out.append(
            {
                "key": (section.get("key") or "").strip() or "section",
                # 空标题表示不展示分区名（由手机端跳过渲染）；禁止回退「工作台」
                "title": (section.get("title") or "").strip(),
                "entries": entries_out,
            }
        )
    return sections_out


def _entry_badge_keys(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("badge_key")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _open_badge_count(triple: Any) -> int:
    if isinstance(triple, (int, float)):
        n = int(triple)
        return n if n > 0 else 0
    if not isinstance(triple, dict):
        return 0
    overdue = int(triple.get("overdue") or 0)
    pending = int(triple.get("pending") or 0)
    in_progress = int(triple.get("in_progress") or 0)
    n = overdue + pending + in_progress
    return n if n > 0 else 0


def apply_workbench_badge_counts(
    sections: list[dict[str, Any]],
    counts: dict[str, Any],
) -> list[dict[str, Any]]:
    """把 menu-badge-counts 的待办数挂到入口上。无 badge_key 的入口为 0。"""
    for section in sections:
        for entry in section.get("entries") or []:
            keys = entry.pop("_badge_keys", None) or []
            total = 0
            for key in keys:
                total += _open_badge_count(counts.get(key))
            entry["badge_count"] = total
    return sections


# 移动端工作台按 scope 并行调用，徽章集计按 (tenant,user) 共享一次计算；
# TTL 与 PC 菜单徽章（dashboards._cached_menu_badge_counts, 45s）对齐。
_MOBILE_BADGE_TTL = 45.0
_mobile_badge_cache: dict[tuple[int, int], tuple[float, dict]] = {}
_mobile_badge_inflight: dict[tuple[int, int], "asyncio.Task[dict]"] = {}


async def _shared_menu_badge_counts(*, tenant_id: int, user: User) -> dict:
    key = (tenant_id, user.id)
    hit = _mobile_badge_cache.get(key)
    if hit is not None and time.monotonic() - hit[0] < _MOBILE_BADGE_TTL:
        return hit[1]
    task = _mobile_badge_inflight.get(key)
    if task is None or task.done():
        task = asyncio.ensure_future(fetch_menu_badge_counts(tenant_id, user))
        _mobile_badge_inflight[key] = task

        def _forget(t: asyncio.Task) -> None:
            if _mobile_badge_inflight.get(key) is t:
                _mobile_badge_inflight.pop(key, None)

        task.add_done_callback(_forget)
    result = await task
    _mobile_badge_cache[key] = (time.monotonic(), result)
    return result


async def attach_workbench_badge_counts(
    sections: list[dict[str, Any]],
    *,
    tenant_id: int,
    user: User,
) -> list[dict[str, Any]]:
    needed: set[str] = set()
    for section in sections:
        for entry in section.get("entries") or []:
            for key in entry.get("_badge_keys") or []:
                needed.add(str(key))
    if not needed:
        for section in sections:
            for entry in section.get("entries") or []:
                entry.pop("_badge_keys", None)
                entry["badge_count"] = 0
        return sections
    counts = await _shared_menu_badge_counts(tenant_id=tenant_id, user=user)
    return apply_workbench_badge_counts(sections, counts)


async def resolve_mobile_workbench_home(
    *,
    tenant_id: int,
    user: User,
    access: EffectiveUserAccess | None = None,
) -> list[dict[str, Any]]:
    cfg = _load_mobile_workbench_config()
    scopes = cfg.get("scopes")
    if not isinstance(scopes, dict):
        raise RuntimeError("mobile_workbench.scopes 配置无效")

    if access is None:
        from core.services.authorization.effective_access_service import EffectiveAccessService

        access = await EffectiveAccessService.get(user.id, tenant_id, user=user)
    user_perms = set(access.permission_codes)
    bypass = access.is_admin_bypass
    is_external = _is_external_partner_from_roles(access.roles, admin_bypass=bypass)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scope_key in MOBILE_WORKBENCH_HOME_SCOPES:
        scope_cfg = scopes.get(scope_key)
        if not isinstance(scope_cfg, dict):
            continue
        for section in _filter_scope_sections(
            scope_cfg,
            user_perms=user_perms,
            is_external_partner=is_external,
            admin_bypass=bypass,
        ):
            dedupe_key = f"{section.get('key')}:{section.get('title')}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            merged.append(section)
    return await attach_workbench_badge_counts(
        merged, tenant_id=tenant_id, user=user
    )


async def resolve_mobile_workbench(
    *,
    tenant_id: int,
    user: User,
    scope: str,
) -> list[dict[str, Any]]:
    scope_key = (scope or "").strip()
    if scope_key == "home":
        return await resolve_mobile_workbench_home(tenant_id=tenant_id, user=user)

    cfg = _load_mobile_workbench_config()
    scopes = cfg.get("scopes")
    if not isinstance(scopes, dict):
        raise RuntimeError("mobile_workbench.scopes 配置无效")

    scope_cfg = scopes.get(scope_key)
    if not isinstance(scope_cfg, dict):
        return []

    user_perms = await UserPermissionService.get_user_permissions(user.id, tenant_id)
    is_external = await _user_is_external_partner(tenant_id, user)
    bypass = await UserPermissionService.is_admin_bypass(user, tenant_id)
    return await attach_workbench_badge_counts(
        _filter_scope_sections(
            scope_cfg,
            user_perms=user_perms,
            is_external_partner=is_external,
            admin_bypass=bypass,
        ),
        tenant_id=tenant_id,
        user=user,
    )
