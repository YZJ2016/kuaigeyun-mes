"""
手动建单自动提交生命周期（业务自动化）。

生效：全局 ``automation.manual_create_auto_submit`` OR 单证
``automation.manual_create_doc_<node_key>``。

行为：仅调用各单据既有 submit（有审批流→待审核；无审批流→已确认）。
禁止在此路径使用 is_auto_approve 旁通过审。

下推建单须传 skip=True，与 push_default_mode 分工。

质检执行类（来料/工序/成品/出货/巡检等）创建后需填报结果再审核，不纳入本开关。
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 页面新建草稿后可「提交」的快制造审核节点（排除变更单/投诉多业务型/质检执行单）
MANUAL_CREATE_LIFECYCLE_DOCS: Tuple[Dict[str, str], ...] = (
    {"node_key": "sales_order", "category": "sales", "name": "销售订单"},
    {"node_key": "sales_forecast", "category": "sales", "name": "销售预测"},
    {"node_key": "sales_contract", "category": "sales", "name": "框架合同"},
    {"node_key": "quotation", "category": "sales", "name": "报价单"},
    {"node_key": "shipment_notice", "category": "sales", "name": "发货通知单"},
    {"node_key": "sales_delivery", "category": "sales", "name": "销售出库"},
    {"node_key": "sales_return", "category": "sales", "name": "销售退货单"},
    {"node_key": "demand", "category": "planning", "name": "需求"},
    {"node_key": "purchase_order", "category": "procurement", "name": "采购订单"},
    {"node_key": "purchase_request", "category": "procurement", "name": "采购申请"},
    {"node_key": "payment_application", "category": "procurement", "name": "付款申请"},
    {"node_key": "purchase_inquiry", "category": "procurement", "name": "采购询价"},
    {"node_key": "purchase_return", "category": "procurement", "name": "采购退货"},
    {"node_key": "receipt_notice", "category": "procurement", "name": "收货通知"},
    {"node_key": "purchase_receipt", "category": "procurement", "name": "采购入库"},
    {"node_key": "work_order", "category": "production", "name": "生产工单"},
    {"node_key": "rework_order", "category": "production", "name": "返工单"},
    {"node_key": "reporting_record", "category": "production", "name": "报工记录"},
    {"node_key": "production_picking", "category": "warehouse", "name": "生产领料"},
    {"node_key": "freight_bill", "category": "warehouse", "name": "运费单"},
    {"node_key": "other_income", "category": "finance", "name": "其他费用收入"},
    {"node_key": "other_expense", "category": "finance", "name": "其他费用支出"},
)

MANUAL_CREATE_LIFECYCLE_NODE_KEYS = frozenset(d["node_key"] for d in MANUAL_CREATE_LIFECYCLE_DOCS)

SubmitFn = Callable[[int, int, int], Awaitable[Any]]


def flat_param_key_for_doc(node_key: str) -> str:
    """业务配置扁平键：parameters.automation.manual_create_doc_<node_key>。"""
    return f"manual_create_doc_{str(node_key or '').strip()}"


def default_manual_create_doc_params() -> Dict[str, bool]:
    return {flat_param_key_for_doc(d["node_key"]): False for d in MANUAL_CREATE_LIFECYCLE_DOCS}


async def is_manual_create_auto_submit_enabled(tenant_id: int, node_key: str) -> bool:
    """全局开 或 单证开 → 生效。"""
    key = str(node_key or "").strip()
    if key not in MANUAL_CREATE_LIFECYCLE_NODE_KEYS:
        return False
    from infra.services.business_config_service import BusinessConfigService

    cfg = BusinessConfigService()
    if await cfg.manual_create_auto_submit_global(tenant_id):
        return True
    return await cfg.manual_create_auto_submit_for_doc(tenant_id, key)


async def apply_manual_create_auto_submit(
    *,
    tenant_id: int,
    node_key: str,
    entity_id: int,
    operator_id: int,
    skip: bool = False,
) -> bool:
    """
    手动建单后尝试自动提交。

    Returns:
        True 若已尝试提交；False 若跳过。
    """
    if skip:
        return False
    key = str(node_key or "").strip()
    if not await is_manual_create_auto_submit_enabled(tenant_id, key):
        return False
    submit = _resolve_submitter(key)
    if submit is None:
        logger.warning("手动建单自动提交：未注册 submitter node_key=%s", key)
        return False
    try:
        await submit(tenant_id, int(entity_id), int(operator_id))
        return True
    except Exception as exc:
        logger.warning(
            "手动建单自动提交失败 tenant=%s node=%s id=%s err=%s",
            tenant_id,
            key,
            entity_id,
            exc,
        )
        return False


def _resolve_submitter(node_key: str) -> Optional[SubmitFn]:
    async def _sales_order(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.sales_order_service import SalesOrderService

        return await SalesOrderService().submit_sales_order(tid, eid, oid)

    async def _sales_forecast(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.sales_service import SalesForecastService

        return await SalesForecastService().submit_forecast(tid, eid, oid)

    async def _sales_contract(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.sales_contract_service import SalesContractService

        return await SalesContractService().submit_contract(tid, eid, oid)

    async def _quotation(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.quotation_service import QuotationService

        return await QuotationService().submit_quotation(tid, eid, oid)

    async def _shipment_notice(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.shipment_notice_service import ShipmentNoticeService

        return await ShipmentNoticeService().submit_shipment_notice(tid, eid, oid)

    async def _sales_delivery(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.warehouse_service import SalesDeliveryService

        return await SalesDeliveryService().submit_sales_delivery(tid, eid, oid)

    async def _sales_return(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.warehouse_service import SalesReturnService

        return await SalesReturnService().submit_sales_return(tid, eid, oid)

    async def _demand(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.demand_service import DemandService

        return await DemandService().submit_demand(tid, eid, oid)

    async def _purchase_order(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.purchase_service import PurchaseService

        return await PurchaseService().submit_purchase_order(tid, eid, oid)

    async def _purchase_request(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.purchase_requisition_service import PurchaseRequisitionService

        return await PurchaseRequisitionService().submit_requisition(tid, eid, oid)

    async def _payment_application(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.payment_application_service import PaymentApplicationService

        return await PaymentApplicationService().submit_application(tid, eid, oid)

    async def _purchase_inquiry(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.purchase_inquiry_service import PurchaseInquiryService

        return await PurchaseInquiryService().submit_inquiry(tid, eid, oid)

    async def _purchase_return(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.warehouse_service import PurchaseReturnService

        return await PurchaseReturnService().submit_purchase_return(tid, eid, oid)

    async def _receipt_notice(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.receipt_notice_service import ReceiptNoticeService

        return await ReceiptNoticeService().submit_receipt_notice(tid, eid, oid)

    async def _purchase_receipt(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.warehouse_service import PurchaseReceiptService

        return await PurchaseReceiptService().submit_purchase_receipt(tid, eid, oid)

    async def _work_order(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        return await WorkOrderService().submit_work_order(tid, eid, oid)

    async def _rework_order(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.rework_order_service import ReworkOrderService

        return await ReworkOrderService().submit_rework_order(tid, eid, oid)

    async def _reporting_record(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.reporting_service import ReportingService

        return await ReportingService().submit_reporting_record(tid, eid, oid)

    async def _production_picking(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.warehouse_service import ProductionPickingService

        return await ProductionPickingService().submit_production_picking(tid, eid, oid)

    async def _freight_bill(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaizhizao.services.freight_bill_service import FreightBillService

        return await FreightBillService().submit_freight_bill(tid, eid, oid)

    async def _other_income(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaicaiwu.services.other_income_service import OtherIncomeService

        return await OtherIncomeService().submit_income(tid, eid, oid)

    async def _other_expense(tid: int, eid: int, oid: int) -> Any:
        from apps.kuaicaiwu.services.other_expense_service import OtherExpenseService

        return await OtherExpenseService().submit_expense(tid, eid, oid)

    registry: Dict[str, SubmitFn] = {
        "sales_order": _sales_order,
        "sales_forecast": _sales_forecast,
        "sales_contract": _sales_contract,
        "quotation": _quotation,
        "shipment_notice": _shipment_notice,
        "sales_delivery": _sales_delivery,
        "sales_return": _sales_return,
        "demand": _demand,
        "purchase_order": _purchase_order,
        "purchase_request": _purchase_request,
        "payment_application": _payment_application,
        "purchase_inquiry": _purchase_inquiry,
        "purchase_return": _purchase_return,
        "receipt_notice": _receipt_notice,
        "purchase_receipt": _purchase_receipt,
        "work_order": _work_order,
        "rework_order": _rework_order,
        "reporting_record": _reporting_record,
        "production_picking": _production_picking,
        "freight_bill": _freight_bill,
        "other_income": _other_income,
        "other_expense": _other_expense,
    }
    return registry.get(node_key)


def iter_manual_create_lifecycle_docs(
    *,
    category: Optional[str] = None,
) -> Iterable[Dict[str, str]]:
    for doc in MANUAL_CREATE_LIFECYCLE_DOCS:
        if category and doc["category"] != category:
            continue
        yield doc


def parameter_keys_for_manual_create_lifecycle() -> List[str]:
    keys = ["parameters.automation.manual_create_auto_submit"]
    for doc in MANUAL_CREATE_LIFECYCLE_DOCS:
        keys.append(f"parameters.automation.{flat_param_key_for_doc(doc['node_key'])}")
    return keys
