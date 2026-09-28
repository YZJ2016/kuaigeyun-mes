"""星报表主路由。

挂载方式与开源应用一致：本模块导出 `router`，
由 ApplicationRegistryService 挂到 `/api/v1/apps/kuaireport`。
"""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import APIRouter

from .data_sources import router as data_sources_router
from .execute import router as execute_router

router = APIRouter(tags=["App - 星报表"])
router.include_router(data_sources_router)
router.include_router(execute_router)


def include_slice_routers(parent: APIRouter) -> None:
    """按文件名加载 slices/*.py。目录不存在或还没有切片文件时直接返回。"""
    slices_dir = Path(__file__).resolve().parent / "slices"
    if not slices_dir.is_dir():
        return
    for path in sorted(slices_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = importlib.import_module(f"apps.kuaireport.api.slices.{path.stem}")
        slice_router = getattr(module, "router", None)
        if slice_router is not None:
            parent.include_router(slice_router)


include_slice_routers(router)
