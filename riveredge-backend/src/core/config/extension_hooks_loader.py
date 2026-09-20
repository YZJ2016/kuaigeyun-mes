"""按 manifest code 动态加载各模块 extension_hooks。"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Dict, Optional

from core.config.extension_provider import app_code_to_python_package


def load_extension_hooks_module(app_code: str) -> Optional[ModuleType]:
    pkg = app_code_to_python_package(app_code)
    if not pkg:
        return None
    try:
        return importlib.import_module(f"apps.{pkg}.extension_hooks")
    except ModuleNotFoundError:
        return None


def resolve_profile_seed_from_hooks(app_code: str, profile_key: str) -> Optional[Dict[str, Any]]:
    mod = load_extension_hooks_module(app_code)
    if mod is None:
        return None
    resolver = getattr(mod, "resolve_profile_seed", None)
    if not callable(resolver):
        return None
    return resolver(profile_key)


async def apply_standalone_via_hooks(tenant_id: int, app_code: str, extension_id: str) -> None:
    mod = load_extension_hooks_module(app_code)
    if mod is None:
        return
    fn = getattr(mod, "apply_standalone", None)
    if not callable(fn):
        return
    await fn(tenant_id, extension_id)


async def revert_standalone_via_hooks(tenant_id: int, app_code: str, extension_id: str) -> None:
    mod = load_extension_hooks_module(app_code)
    if mod is None:
        return
    fn = getattr(mod, "revert_standalone", None)
    if not callable(fn):
        return
    await fn(tenant_id, extension_id)


def host_capabilities_from_hooks(app_code: str) -> Dict[str, Dict[str, Any]]:
    mod = load_extension_hooks_module(app_code)
    if mod is None:
        return {}
    raw = getattr(mod, "HOST_CAPABILITIES", None)
    if not isinstance(raw, dict):
        return {}
    return dict(raw)
