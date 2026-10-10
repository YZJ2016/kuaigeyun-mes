"""星数采 API 路由。

上游集成平台端点按原路径挂载（uuid 寻址）；
本地执行版端点（整型 id 寻址）统一挂在 /registry 前缀下，避免与上游裸路径碰撞。
"""

from fastapi import APIRouter

from .alerts import router as alerts_router
from .analytics import router as analytics_router
from .command import router as command_router
from .config import router as config_router
from .connections import router as connections_router
from .connectors import router as connectors_router
from .control import router as control_router
from .dashboard import router as dashboard_router
from .device_groups import router as device_groups_router
from .devices import router as devices_router
from .edge import router as edge_router
from .edge_configs import router as edge_configs_router
from .edge_runtime import router as edge_runtime_router
from .fill_context import router as fill_context_router
from .group import router as group_router
from .ingest import router as ingest_router
from .message import router as message_router
from .ops import router as ops_router
from .prefill import router as prefill_router
from .product import router as product_router
from .products import router as products_router
from .tags import router as tags_router

router = APIRouter(tags=["App - KuaiIoT - Overview"])

# 上游平台端点（uuid 寻址）
router.include_router(connections_router)
router.include_router(config_router)
router.include_router(products_router)
router.include_router(device_groups_router)
router.include_router(devices_router)
router.include_router(tags_router)
router.include_router(dashboard_router)
router.include_router(ingest_router)
router.include_router(connectors_router)
router.include_router(alerts_router)
router.include_router(edge_configs_router)
router.include_router(edge_runtime_router)
router.include_router(analytics_router)
router.include_router(ops_router)
router.include_router(fill_context_router)

# 本地执行版端点（整型 id 寻址），统一收敛在 /registry 下
router.include_router(control_router, prefix="/registry")
router.include_router(edge_router, prefix="/registry")
router.include_router(command_router, prefix="/registry")
router.include_router(group_router, prefix="/registry")
router.include_router(message_router, prefix="/registry")
router.include_router(prefill_router, prefix="/registry")
router.include_router(product_router, prefix="/registry")


@router.get("/health")
async def health_check():
    return {"status": "ok", "app": "kuaiiot"}
