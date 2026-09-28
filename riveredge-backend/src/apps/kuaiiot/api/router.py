"""星数采主路由。

挂载方式与星 AI 一致：本模块导出 `router`，
应用安装启用后由 ApplicationRegistryService 挂到 `/api/v1/apps/kuaiiot`。
"""

from fastapi import APIRouter

from .analytics import router as analytics_router
from .command import router as command_router
from .control import router as control_router
from .edge import router as edge_router
from .group import router as group_router
from .ingest import router as ingest_router
from .message import router as message_router
from .prefill import router as prefill_router
from .product import router as product_router

router = APIRouter(tags=["App - 星数采"])
router.include_router(control_router)
router.include_router(ingest_router)
router.include_router(prefill_router)
router.include_router(edge_router)
router.include_router(analytics_router)
router.include_router(product_router)
router.include_router(command_router)
router.include_router(group_router)
router.include_router(message_router)
