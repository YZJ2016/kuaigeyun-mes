"""工作台待办事项深链（get_todos link 与 handle_todo redirect 唯一真源）。"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

APP = "/apps/kuaizhizao"

# todo_id 前缀 → handle_todo 成功提示
TODO_HANDLE_MESSAGES: dict[str, str] = {
    "work_order_": "请前往工单详情页进行处理",
    "exception_material_": "请前往缺料异常详情页进行处理",
    "exception_delay_": "请前往延期异常详情页进行处理",
    "exception_quality_": "请前往质量异常详情页进行处理",
    "inventory_alert_": "请前往库存预警详情页进行处理",
    "purchase_receipt_": "请前往采购入库处理",
    "finished_goods_receipt_": "请前往入库管理处理成品入库",
    "production_return_": "请前往入库管理处理生产退料",
    "other_inbound_": "请前往其他入库处理",
    "material_borrow_": "请前往借料单处理",
    "material_return_": "请前往还料单处理",
    "material_call_": "请前往叫料处理",
    "receipt_notice_": "请前往收货通知处理",
    "production_picking_": "请前往出库管理处理生产领料",
    "sales_delivery_": "请前往出库管理处理销售出库",
    "other_outbound_": "请前往其他出库处理",
    "purchase_requisition_": "请前往采购申请审核",
    "purchase_return_": "请前往采购退货处理",
    "shipment_notice_": "请前往发货通知处理",
    "sales_return_": "请前往销售退货处理",
    "equipment_fault_": "请前往设备故障处理",
    "inspection_incoming_": "请前往来料检验处理",
    "inspection_process_": "请前往过程检验处理",
    "inspection_finished_": "请前往成品检验处理",
}


def _parse_entity_id(todo_id: str, prefix: str) -> Optional[int]:
    if not todo_id.startswith(prefix):
        return None
    raw = todo_id[len(prefix) :]
    try:
        entity_id = int(raw)
    except ValueError:
        return None
    return entity_id if entity_id > 0 else None


def _inbound_hub_link(document_type: str, receipt_id: int) -> str:
    query = urlencode({"documentType": document_type, "receipt_id": receipt_id})
    return f"{APP}/warehouse-management/inbound?{query}"


def _outbound_hub_link(outbound_type: str, entity_id: int) -> str:
    query = urlencode({"outbound_type": outbound_type, "id": entity_id})
    return f"{APP}/warehouse-management/outbound?{query}"


def _highlight_link(path: str, entity_id: int) -> str:
    return f"{path}?highlight={entity_id}"


def build_dashboard_todo_link(
    todo_id: str,
    *,
    entity_uuid: Optional[str] = None,
) -> Optional[str]:
    """根据待办 id 生成前端深链路径；未知类型返回 None。"""
    if todo_id.startswith("work_order_"):
        entity_id = _parse_entity_id(todo_id, "work_order_")
        if entity_id:
            return f"{APP}/production-execution/work-orders/{entity_id}"

    if todo_id.startswith("exception_material_"):
        entity_id = _parse_entity_id(todo_id, "exception_material_")
        if entity_id:
            return _highlight_link(f"{APP}/production-execution/material-shortage-exceptions", entity_id)

    if todo_id.startswith("exception_delay_"):
        entity_id = _parse_entity_id(todo_id, "exception_delay_")
        if entity_id:
            return _highlight_link(f"{APP}/production-execution/delivery-delay-exceptions", entity_id)

    if todo_id.startswith("exception_quality_"):
        entity_id = _parse_entity_id(todo_id, "exception_quality_")
        if entity_id:
            return _highlight_link(f"{APP}/production-execution/quality-exceptions", entity_id)

    if todo_id.startswith("inventory_alert_"):
        entity_id = _parse_entity_id(todo_id, "inventory_alert_")
        if entity_id:
            return _highlight_link(f"{APP}/warehouse-management/inventory-alert", entity_id)

    if todo_id.startswith("purchase_receipt_"):
        entity_id = _parse_entity_id(todo_id, "purchase_receipt_")
        if entity_id:
            return _inbound_hub_link("purchase_receipt", entity_id)

    if todo_id.startswith("finished_goods_receipt_"):
        entity_id = _parse_entity_id(todo_id, "finished_goods_receipt_")
        if entity_id:
            return _inbound_hub_link("finished_goods_receipt", entity_id)

    if todo_id.startswith("production_return_"):
        entity_id = _parse_entity_id(todo_id, "production_return_")
        if entity_id:
            return _inbound_hub_link("production_return", entity_id)

    if todo_id.startswith("other_inbound_"):
        entity_id = _parse_entity_id(todo_id, "other_inbound_")
        if entity_id:
            return _inbound_hub_link("other_inbound", entity_id)

    if todo_id.startswith("material_borrow_"):
        entity_id = _parse_entity_id(todo_id, "material_borrow_")
        if entity_id:
            return f"{APP}/warehouse-management/material-borrows?id={entity_id}"

    if todo_id.startswith("material_return_"):
        entity_id = _parse_entity_id(todo_id, "material_return_")
        if entity_id:
            return _inbound_hub_link("material_return", entity_id)

    if todo_id.startswith("material_call_"):
        entity_id = _parse_entity_id(todo_id, "material_call_")
        if entity_id:
            query = urlencode({"tab": "material_call", "highlight": entity_id})
            return f"{APP}/warehouse-management/batching-center?{query}"

    if todo_id.startswith("receipt_notice_"):
        entity_id = _parse_entity_id(todo_id, "receipt_notice_")
        if entity_id:
            return _highlight_link(f"{APP}/purchase-management/receipt-notices", entity_id)

    if todo_id.startswith("production_picking_"):
        entity_id = _parse_entity_id(todo_id, "production_picking_")
        if entity_id:
            return _outbound_hub_link("production_picking", entity_id)

    if todo_id.startswith("sales_delivery_"):
        entity_id = _parse_entity_id(todo_id, "sales_delivery_")
        if entity_id:
            return _outbound_hub_link("sales_delivery", entity_id)

    if todo_id.startswith("other_outbound_"):
        entity_id = _parse_entity_id(todo_id, "other_outbound_")
        if entity_id:
            return _outbound_hub_link("other_outbound", entity_id)

    if todo_id.startswith("purchase_requisition_"):
        entity_id = _parse_entity_id(todo_id, "purchase_requisition_")
        if entity_id:
            return f"{APP}/purchase-management/purchase-requisitions?requisitionId={entity_id}"

    if todo_id.startswith("purchase_return_"):
        entity_id = _parse_entity_id(todo_id, "purchase_return_")
        if entity_id:
            return _outbound_hub_link("purchase_return", entity_id)

    if todo_id.startswith("shipment_notice_"):
        entity_id = _parse_entity_id(todo_id, "shipment_notice_")
        if entity_id:
            return _highlight_link(f"{APP}/sales-management/shipment-notices", entity_id)

    if todo_id.startswith("sales_return_"):
        entity_id = _parse_entity_id(todo_id, "sales_return_")
        if entity_id:
            return _highlight_link(f"{APP}/sales-management/sales-returns", entity_id)

    if todo_id.startswith("equipment_fault_"):
        if entity_uuid:
            return f"{APP}/equipment-management/equipment-faults?uuid={entity_uuid}"
        entity_id = _parse_entity_id(todo_id, "equipment_fault_")
        if entity_id:
            return f"{APP}/equipment-management/equipment-faults?highlight={entity_id}"

    if todo_id.startswith("inspection_incoming_"):
        entity_id = _parse_entity_id(todo_id, "inspection_incoming_")
        if entity_id:
            return f"{APP}/quality-management/incoming-inspection?id={entity_id}"

    if todo_id.startswith("inspection_process_"):
        entity_id = _parse_entity_id(todo_id, "inspection_process_")
        if entity_id:
            return f"{APP}/quality-management/process-inspection?process_inspection_id={entity_id}"

    if todo_id.startswith("inspection_finished_"):
        entity_id = _parse_entity_id(todo_id, "inspection_finished_")
        if entity_id:
            return (
                f"{APP}/quality-management/finished-goods-inspection"
                f"?finished_goods_inspection_id={entity_id}"
            )

    return None


def dashboard_todo_handle_message(todo_id: str) -> str:
    for prefix, message in TODO_HANDLE_MESSAGES.items():
        if todo_id.startswith(prefix):
            return message
    return "正在跳转到对应单据"
