"""电子制造行业包：扩展运行时钩子（profile 种子、standalone 启停、宿主 capability）。"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from apps.ind_electronics.profiles import resolve_electronics_profile_seed

HOST_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "host.esd.inspection": {
        "extension_id": "electronics.esd",
        "navigation_path": "/esd/inspection",
    },
}


def resolve_profile_seed(profile_key: str) -> Optional[Dict[str, Any]]:
    seed = resolve_electronics_profile_seed(profile_key)
    return copy.deepcopy(seed) if seed else None


async def apply_standalone(tenant_id: int, extension_id: str) -> None:
    if extension_id == "electronics.esd":
        from apps.ind_electronics.services.esd_seed_service import ensure_esd_catalog

        await ensure_esd_catalog(tenant_id)


async def revert_standalone(tenant_id: int, extension_id: str) -> None:
    if extension_id == "electronics.esd":
        from apps.ind_electronics.services.esd_seed_service import deactivate_esd_scheme

        await deactivate_esd_scheme(tenant_id)
