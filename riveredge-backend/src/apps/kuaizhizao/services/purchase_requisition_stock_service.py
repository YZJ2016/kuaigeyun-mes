"""采购申请历史入口：委托 MaterialLineStockService（勿删，避免旧 import 断裂）。"""

from __future__ import annotations

from typing import Any, Dict, List

from apps.kuaizhizao.services.material_line_stock_service import MaterialLineStockService


class PurchaseRequisitionStockService:
    @staticmethod
    async def material_on_hand_by_warehouse(
        tenant_id: int,
        material_ids: List[int],
    ) -> Dict[str, Any]:
        return await MaterialLineStockService.material_on_hand_by_warehouse(
            tenant_id, material_ids
        )
