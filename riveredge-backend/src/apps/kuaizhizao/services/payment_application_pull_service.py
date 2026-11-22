"""
从采购订单/入库/往来对账/应付创建付款申请
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from apps.kuaicaiwu.models.payable import Payable
from apps.kuaizhizao.models.purchase_order import PurchaseOrder
from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
from apps.kuaizhizao.schemas.payment_application import (
    PaymentApplicationCreate,
    PaymentApplicationLineCreate,
)
from apps.kuaizhizao.services.document_action_policy.purchase_order import (
    assert_purchase_order_capability,
    derive_purchase_order_capabilities,
)
from apps.kuaizhizao.services.document_action_policy.enricher import (
    _order_prepayment_linked_by_ids,
)
from apps.kuaizhizao.services.payable_open_amount_service import PayableOpenAmountService
from apps.kuaizhizao.services.payment_application_service import PaymentApplicationService
from infra.exceptions.exceptions import NotFoundError, BusinessLogicError, ValidationError


def _department_payload_from_model(model: Any, *, label: str) -> Dict[str, Any]:
    did = int(getattr(model, "department_id", None) or 0)
    dname = str(getattr(model, "department_name", None) or "").strip()
    if did <= 0 or not dname:
        raise BusinessLogicError(f"{label}未填写申请部门，无法下推付款申请")
    return {"department_id": did, "department_name": dname}


async def _department_payload_from_payable(tenant_id: int, payable: Payable) -> Dict[str, Any]:
    """从应付来源入库单/采购订单解析申请部门。"""
    src_type = str(payable.source_type or "").strip()
    src_id = int(payable.source_id or 0)
    if _is_purchase_receipt_payable_source(src_type) and src_id:
        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=src_id, deleted_at__isnull=True
        )
        if receipt:
            return _department_payload_from_model(receipt, label="采购入库单")
    if _is_purchase_order_payable_source(src_type) and src_id:
        order = await PurchaseOrder.get_or_none(
            tenant_id=tenant_id, id=src_id, deleted_at__isnull=True
        )
        if order:
            return _department_payload_from_model(order, label="采购订单")
    code = str(payable.payable_code or payable.id)
    raise BusinessLogicError(
        f"应付单 {code} 无法解析申请部门，请从采购入库或采购订单来源下推"
    )


def _payment_reason_for_payables(payable_codes: Sequence[str]) -> str:
    codes = [str(c or "").strip() for c in payable_codes if str(c or "").strip()]
    if not codes:
        return "往来对账应付货款请款"
    if len(codes) == 1:
        return f"往来对账应付 {codes[0]} 货款请款"
    head = "、".join(codes[:5])
    if len(codes) > 5:
        return f"往来对账应付 {head} 等{len(codes)}单货款请款"
    return f"往来对账应付 {head} 货款请款"


def _payment_reason_for_purchase_orders(order_codes: Sequence[str]) -> str:
    """下推付款申请必填付款事由：按源采购订单编码生成草稿说明，保存前可改。"""
    codes = [str(code or "").strip() for code in order_codes if str(code or "").strip()]
    if not codes:
        return "采购订单预付请款"
    if len(codes) == 1:
        return f"采购订单 {codes[0]} 预付请款"
    head = "、".join(codes[:5])
    if len(codes) > 5:
        return f"采购订单 {head} 等{len(codes)}单预付请款"
    return f"采购订单 {head} 预付请款"


def _payment_reason_for_purchase_receipts(receipt_codes: Sequence[str]) -> str:
    codes = [str(code or "").strip() for code in receipt_codes if str(code or "").strip()]
    if not codes:
        return "采购入库单货款请款"
    if len(codes) == 1:
        return f"采购入库单 {codes[0]} 货款请款"
    head = "、".join(codes[:5])
    if len(codes) > 5:
        return f"采购入库单 {head} 等{len(codes)}单货款请款"
    return f"采购入库单 {head} 货款请款"


def prepayment_application_base_amount(order: Any) -> Decimal:
    """付款申请自采购订单取单：有预付计划用预付额，否则用订单价税合计。"""
    from apps.kuaicaiwu.services.finance_tax import quantize_money
    from apps.kuaicaiwu.services.purchase_settlement import (
        purchase_order_settlement_gross,
    )

    gross = purchase_order_settlement_gross(order)
    prepay = Decimal(str(getattr(order, "prepayment_amount", 0) or 0))
    if prepay <= 0:
        return gross
    prepay_q = quantize_money(prepay)
    if gross > 0 and prepay_q > gross:
        return gross
    # 预付额等于未税合计且小于价税合计时，可请款仍是预付计划写入的基数
    return prepay_q


def compute_prepayment_application_remaining(order: Any, reserved: Decimal) -> Decimal:
    return max(Decimal("0"), prepayment_application_base_amount(order) - reserved)


def _is_purchase_order_payable_source(source_type: str) -> bool:
    st = str(source_type or "").strip()
    sl = st.lower().replace("-", "_")
    return sl in {"purchase_order", "purchaseorder"} or st == "订单里程碑"


def _is_purchase_receipt_payable_source(source_type: str) -> bool:
    from apps.kuaicaiwu.constants.finance_source_types import (
        PAYABLE_SOURCE_PURCHASE_RECEIPT,
    )

    st = str(source_type or "").strip()
    sl = st.lower().replace("-", "_")
    return st == PAYABLE_SOURCE_PURCHASE_RECEIPT or sl in {"purchase_receipt", "purchasereceipt"}


async def _batch_payable_pull_display_fields(
    tenant_id: int, payables: Sequence[Payable]
) -> Dict[int, Dict[str, Optional[str]]]:
    po_ids: set[int] = set()
    receipt_ids: set[int] = set()
    for payable in payables:
        sid = int(getattr(payable, "source_id", 0) or 0)
        if sid <= 0:
            continue
        st = str(getattr(payable, "source_type", "") or "")
        if _is_purchase_order_payable_source(st):
            po_ids.add(sid)
        elif _is_purchase_receipt_payable_source(st):
            receipt_ids.add(sid)

    po_by_id: Dict[int, PurchaseOrder] = {}
    if po_ids:
        orders = await PurchaseOrder.filter(
            tenant_id=tenant_id, id__in=list(po_ids), deleted_at__isnull=True
        )
        po_by_id = {int(o.id): o for o in orders}

    receipt_by_id: Dict[int, PurchaseReceipt] = {}
    if receipt_ids:
        receipts = await PurchaseReceipt.filter(
            tenant_id=tenant_id, id__in=list(receipt_ids), deleted_at__isnull=True
        )
        receipt_by_id = {int(r.id): r for r in receipts}

    out: Dict[int, Dict[str, Optional[str]]] = {}
    for payable in payables:
        pid = int(payable.id)
        dept: Optional[str] = None
        applicant: Optional[str] = None
        sid = int(getattr(payable, "source_id", 0) or 0)
        st = str(getattr(payable, "source_type", "") or "")
        if sid > 0 and _is_purchase_order_payable_source(st):
            order = po_by_id.get(sid)
            if order:
                dname = str(getattr(order, "department_name", "") or "").strip()
                dept = dname or None
                buyer = str(getattr(order, "buyer_name", "") or "").strip()
                applicant = buyer or None
        elif sid > 0 and _is_purchase_receipt_payable_source(st):
            receipt = receipt_by_id.get(sid)
            if receipt:
                dname = str(getattr(receipt, "department_name", "") or "").strip()
                dept = dname or None
                buyer = str(getattr(receipt, "buyer_name", "") or "").strip()
                applicant = buyer or None
        out[pid] = {"department_name": dept, "applicant_name": applicant}
    return out


class PaymentApplicationPullService:
    def __init__(self) -> None:
        self._apps = PaymentApplicationService()
        self._open = PayableOpenAmountService()

    @staticmethod
    def _normalize_source_ids(source_ids: Sequence[int]) -> List[int]:
        seen: set[int] = set()
        ordered: List[int] = []
        for raw in source_ids:
            sid = int(raw)
            if sid <= 0 or sid in seen:
                continue
            seen.add(sid)
            ordered.append(sid)
        if not ordered:
            raise ValidationError("请至少选择一张源单")
        return ordered

    # 与应付可请款占用对齐：草稿/已提交/待审核即占预付额度，避免保存后下一单取单口径错乱
    _PREPAY_APP_RESERVE_STATUSES = frozenset(
        {
            "草稿",
            "DRAFT",
            "已提交",
            "SUBMITTED",
            "待审核",
            "PENDING",
            "已批准",
            "部分付款",
            "已付款",
            "APPROVED",
            "AUDITED",
            "已通过",
        }
    )
    _PREPAY_APP_EXCLUDED_FOR_DIRECT_PO_PREPAY = frozenset(
        {"已驳回", "已作废", "Cancelled", "cancelled", "REJECTED", "CANCELLED"}
    )

    async def has_prepayment_application_by_order_ids(
        self, tenant_id: int, purchase_order_ids: List[int]
    ) -> Dict[int, bool]:
        """采购订单是否已有预付类付款申请（非驳回/作废），用于禁止再走 PO 直拉预付款。"""
        result: Dict[int, bool] = {oid: False for oid in purchase_order_ids}
        if not purchase_order_ids:
            return result
        from apps.kuaizhizao.models.payment_application import (
            PaymentApplication,
            PaymentApplicationLine,
        )

        lines = await PaymentApplicationLine.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            source_id__in=purchase_order_ids,
            line_kind="prepayment",
        ).all()
        if not lines:
            return result
        app_ids = {int(line.application_id) for line in lines}
        apps = await PaymentApplication.filter(
            tenant_id=tenant_id,
            id__in=list(app_ids),
            deleted_at__isnull=True,
        ).all()
        app_status = {int(app.id): str(app.status or "").strip() for app in apps}
        for line in lines:
            oid = int(line.source_id or 0)
            if oid not in result:
                continue
            status = app_status.get(int(line.application_id), "")
            if status in self._PREPAY_APP_EXCLUDED_FOR_DIRECT_PO_PREPAY:
                continue
            result[oid] = True
        return result

    async def prepayment_reserved_by_order_ids(
        self, tenant_id: int, purchase_order_ids: List[int]
    ) -> Dict[int, Decimal]:
        result: Dict[int, Decimal] = {oid: Decimal("0") for oid in purchase_order_ids}
        if not purchase_order_ids:
            return result
        from apps.kuaizhizao.models.payment_application import PaymentApplication, PaymentApplicationLine

        lines = await PaymentApplicationLine.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            source_id__in=purchase_order_ids,
            line_kind="prepayment",
        ).all()
        if not lines:
            return result
        app_ids = {int(l.application_id) for l in lines}
        apps = await PaymentApplication.filter(
            tenant_id=tenant_id,
            id__in=list(app_ids),
            deleted_at__isnull=True,
            status__in=list(self._PREPAY_APP_RESERVE_STATUSES),
        ).all()
        active_app_ids = {int(a.id) for a in apps if str(a.status) != "已驳回"}
        for line in lines:
            oid = int(line.source_id or 0)
            if oid not in result or int(line.application_id) not in active_app_ids:
                continue
            req = Decimal(str(line.request_amount or 0))
            paid = Decimal(str(line.paid_amount or 0))
            result[oid] += max(Decimal("0"), req - paid)
        return result

    async def prepayment_payment_occupied_by_order_ids(
        self, tenant_id: int, purchase_order_ids: List[int]
    ) -> Dict[int, Decimal]:
        """直拉采购订单的预付付款单占用（不含作废）。"""
        result: Dict[int, Decimal] = {oid: Decimal("0") for oid in purchase_order_ids}
        if not purchase_order_ids:
            return result
        from apps.kuaicaiwu.models.payment import Payment
        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

        lines = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            source_id__in=purchase_order_ids,
            deleted_at__isnull=True,
        ).all()
        if not lines:
            return result
        payment_ids = {int(ln.payment_id) for ln in lines if ln.payment_id}
        live = await Payment.filter(
            tenant_id=tenant_id,
            id__in=list(payment_ids),
            deleted_at__isnull=True,
            settlement_type="prepayment",
        ).exclude(status="Cancelled").all()
        live_ids = {int(p.id) for p in live}
        for ln in lines:
            if int(ln.payment_id or 0) not in live_ids:
                continue
            oid = int(ln.source_id or 0)
            if oid not in result:
                continue
            result[oid] += Decimal(str(ln.amount or 0))
        return result

    async def _sum_prepayment_application_reserved(
        self, tenant_id: int, purchase_order_id: int
    ) -> Decimal:
        reserved_map = await self.prepayment_reserved_by_order_ids(
            tenant_id, [purchase_order_id]
        )
        return reserved_map.get(purchase_order_id, Decimal("0"))

    async def preview_from_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
        amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        order = await PurchaseOrder.get_or_none(tenant_id=tenant_id, id=purchase_order_id)
        if not order:
            raise NotFoundError(f"采购订单不存在: {purchase_order_id}")
        from infra.services.business_config_service import BusinessConfigService

        prepay_map = await _order_prepayment_linked_by_ids(
            tenant_id, [purchase_order_id], source_type="purchase_order", target_type="payment"
        )
        reserved = await self._sum_prepayment_application_reserved(tenant_id, purchase_order_id)
        payment_occ = (
            await self.prepayment_payment_occupied_by_order_ids(
                tenant_id, [purchase_order_id]
            )
        ).get(purchase_order_id, Decimal("0"))
        max_push = compute_prepayment_application_remaining(
            order, reserved + payment_occ
        )
        order_base_amount = prepayment_application_base_amount(order)
        require_app = await BusinessConfigService().get_finance_require_payment_application(
            tenant_id
        )
        # 须用 push_payment_application（与列表 capabilities / 取单勾选同源），
        # 禁止误用 push_prepayment：组织开启「预付款须走付款申请」时后者恒为否。
        caps = derive_purchase_order_capabilities(
            order,
            has_prepayment_payment=prepay_map.get(purchase_order_id, False),
            require_payment_application=require_app,
            prepayment_application_remaining=max_push,
        )
        app_cap = caps.push_payment_application
        allowed = bool(app_cap.allowed) and max_push > 0
        preview_items: List[Dict[str, Any]] = []
        if allowed:
            from apps.kuaizhizao.services.payment_application_line_materials import (
                lines_from_purchase_order_items,
            )

            req_amt = Decimal(str(amount)) if amount is not None else max_push
            if req_amt > max_push:
                raise ValidationError(f"申请金额超过可预付请款额度 {max_push}")
            if req_amt <= 0:
                raise ValidationError("申请金额必须大于 0")
            line_models = await lines_from_purchase_order_items(
                tenant_id=tenant_id,
                order=order,
                request_amount=req_amt,
                line_kind="prepayment",
            )
            preview_items = [
                ln.model_dump(by_alias=True, mode="json") for ln in line_models
            ]
        return {
            "target_type": "payment_application",
            "source_type": "purchase_order",
            "source_id": purchase_order_id,
            "source_code": order.order_code,
            "order_code": order.order_code,
            "max_push_quantity": float(max_push),
            "source_order_amount": float(order_base_amount),
            "summary": (
                f"将按采购订单 {order.order_code} 生成预付类付款申请（可请款 {max_push}）"
                if allowed
                else "当前采购订单不可下推付款申请"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": app_cap.reason if not app_cap.allowed else (
                "payment_application.pull_from_purchase_order.no_amount" if max_push <= 0 else None
            ),
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier_name,
        }

    async def create_from_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
        amount: Decimal,
        created_by: int,
    ):
        preview = await self.preview_from_purchase_order(tenant_id, purchase_order_id)
        if preview.get("has_blocking_issues"):
            raise BusinessLogicError(preview.get("blocking_reason") or "不可下推付款申请")
        max_push = Decimal(str(preview.get("max_push_quantity") or 0))
        if amount > max_push:
            raise ValidationError(f"申请金额超过可预付请款额度 {max_push}")
        order = await PurchaseOrder.get(id=purchase_order_id)
        if not order.supplier_id:
            raise BusinessLogicError("采购订单未指定供应商")
        from apps.kuaizhizao.services.payment_application_line_materials import (
            lines_from_purchase_order_items,
        )

        items = await lines_from_purchase_order_items(
            tenant_id=tenant_id,
            order=order,
            request_amount=amount,
            line_kind="prepayment",
        )
        create = PaymentApplicationCreate(
            supplier_id=int(order.supplier_id),
            supplier_name=str(order.supplier_name or ""),
            application_kind="prepayment",
            items=items,
            payment_reason=_payment_reason_for_purchase_orders([str(order.order_code or "")]),
            **_department_payload_from_model(order, label="采购订单"),
        )
        return await self._apps.create_application(
            tenant_id, create, created_by, skip_manual_create_auto_submit=True
        )

    async def create_from_purchase_orders(
        self,
        tenant_id: int,
        purchase_order_ids: Sequence[int],
        created_by: int,
    ):
        ids = self._normalize_source_ids(purchase_order_ids)
        if len(ids) == 1:
            preview = await self.preview_from_purchase_order(tenant_id, ids[0])
            if preview.get("has_blocking_issues"):
                raise BusinessLogicError(preview.get("blocking_reason") or "不可下推付款申请")
            max_push = Decimal(str(preview.get("max_push_quantity") or 0))
            return await self.create_from_purchase_order(
                tenant_id, ids[0], max_push, created_by
            )

        from apps.kuaizhizao.services.payment_application_line_materials import (
            lines_from_purchase_order_items,
        )

        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        merged_items: List[PaymentApplicationLineCreate] = []
        order_codes: List[str] = []

        for oid in ids:
            preview = await self.preview_from_purchase_order(tenant_id, oid)
            if preview.get("has_blocking_issues"):
                code = str(preview.get("source_code") or oid)
                reason = preview.get("blocking_reason") or "不可下推付款申请"
                raise BusinessLogicError(f"采购订单 {code}: {reason}")
            sid = int(preview.get("supplier_id") or 0)
            if not sid:
                raise BusinessLogicError("采购订单未指定供应商")
            if supplier_id is None:
                supplier_id = sid
                supplier_name = str(preview.get("supplier_name") or "")
            elif sid != supplier_id:
                raise BusinessLogicError("多笔一起加载须为同一供应商")

            max_push = Decimal(str(preview.get("max_push_quantity") or 0))
            if max_push <= 0:
                code = str(preview.get("source_code") or oid)
                raise BusinessLogicError(f"采购订单 {code} 无可请款额度")

            order = await PurchaseOrder.get(id=oid)
            order_codes.append(
                str(getattr(order, "order_code", None) or preview.get("source_code") or oid)
            )
            merged_items.extend(
                await lines_from_purchase_order_items(
                    tenant_id=tenant_id,
                    order=order,
                    request_amount=max_push,
                    line_kind="prepayment",
                )
            )

        if not merged_items:
            raise BusinessLogicError("所选采购订单无可合并的请款明细")

        first_order = await PurchaseOrder.get(id=ids[0])
        create = PaymentApplicationCreate(
            supplier_id=int(supplier_id),
            supplier_name=str(supplier_name or ""),
            application_kind="prepayment",
            items=merged_items,
            payment_reason=_payment_reason_for_purchase_orders(order_codes),
            **_department_payload_from_model(first_order, label="采购订单"),
        )
        return await self._apps.create_application(
            tenant_id, create, created_by, skip_manual_create_auto_submit=True
        )

    async def push_payment_application_open_by_receipt_ids(
        self, tenant_id: int, receipt_ids: List[int]
    ) -> Dict[int, bool]:
        result: Dict[int, bool] = {int(rid): False for rid in receipt_ids}
        if not receipt_ids:
            return result
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_receipt",
            source_id__in=receipt_ids,
            target_type="payable",
        ).all()
        payable_ids = {int(r.target_id) for r in rels if r.target_id}
        if not payable_ids:
            return result
        payables = await Payable.filter(
            tenant_id=tenant_id, id__in=list(payable_ids), deleted_at__isnull=True
        ).all()
        payable_by_id = {int(p.id): p for p in payables}
        for rel in rels:
            rid = int(rel.source_id or 0)
            pid = int(rel.target_id or 0)
            payable = payable_by_id.get(pid)
            if not payable or rid not in result:
                continue
            max_req = await self._open.max_request_for_payable(tenant_id, payable)
            if max_req > 0:
                result[rid] = True
        return result

    async def _payable_for_receipt(self, tenant_id: int, receipt_id: int) -> Payable:
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_receipt",
            source_id=receipt_id,
            target_type="payable",
        ).first()
        if not rel or not rel.target_id:
            raise BusinessLogicError("该入库单尚未生成应付单，请先确认入库或创建应付")
        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=int(rel.target_id), deleted_at__isnull=True
        )
        if not payable:
            raise NotFoundError("应付单不存在")
        return payable

    async def preview_from_purchase_receipt(
        self,
        tenant_id: int,
        purchase_receipt_id: int,
        amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=purchase_receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"采购入库单不存在: {purchase_receipt_id}")

        code = str(receipt.receipt_code or purchase_receipt_id)
        try:
            payable = await self._payable_for_receipt(tenant_id, purchase_receipt_id)
        except (BusinessLogicError, NotFoundError) as e:
            return {
                "target_type": "payment_application",
                "source_type": "purchase_receipt",
                "source_id": purchase_receipt_id,
                "source_code": code,
                "has_blocking_issues": True,
                "blocking_reason": str(e),
                "supplier_id": getattr(receipt, "supplier_id", None),
                "supplier_name": getattr(receipt, "supplier_name", None),
                "max_push_quantity": 0.0,
                "items": [],
            }

        max_req = await self._open.max_request_for_payable(tenant_id, payable)
        allowed = max_req > 0
        req_amount = Decimal(str(amount)) if amount is not None else max_req
        if req_amount > max_req:
            raise ValidationError(f"申请金额超过可请款 {max_req}")
        if req_amount <= 0:
            allowed = False

        preview_items: List[Dict[str, Any]] = []
        if allowed:
            from apps.kuaizhizao.services.payment_application_line_materials import (
                lines_from_purchase_receipt_items,
            )

            line_models = await lines_from_purchase_receipt_items(
                tenant_id=tenant_id,
                receipt_id=purchase_receipt_id,
                receipt_code=code,
                payable=payable,
                request_amount=req_amount,
                line_kind="goods",
                source_type="purchase_receipt",
            )
            preview_items = [
                ln.model_dump(by_alias=True, mode="json") for ln in line_models
            ]

        return {
            "target_type": "payment_application",
            "source_type": "purchase_receipt",
            "source_id": purchase_receipt_id,
            "source_code": code,
            "max_push_quantity": float(max_req),
            "summary": (
                f"将按采购入库单 {code} 生成货款类付款申请（可请款 {max_req}）"
                if allowed
                else "该入库单当前不可创建付款申请"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": (
                "purchase_receipt.push_payment_application.no_open_amount"
                if max_req <= 0
                else None
            ),
            "supplier_id": payable.supplier_id,
            "supplier_name": payable.supplier_name,
        }

    async def create_from_purchase_receipt(
        self,
        tenant_id: int,
        purchase_receipt_id: int,
        amount: Optional[Decimal],
        created_by: int,
    ):
        preview = await self.preview_from_purchase_receipt(
            tenant_id, purchase_receipt_id, amount=amount
        )
        if preview.get("has_blocking_issues"):
            raise BusinessLogicError(preview.get("blocking_reason") or "不可下推付款申请")
        payable = await self._payable_for_receipt(tenant_id, purchase_receipt_id)
        items_raw = preview.get("items") or []
        if not items_raw:
            raise BusinessLogicError("该入库单无可请款明细")
        items = [PaymentApplicationLineCreate.model_validate(row) for row in items_raw]
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=purchase_receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"采购入库单不存在: {purchase_receipt_id}")
        create = PaymentApplicationCreate(
            supplier_id=int(payable.supplier_id),
            supplier_name=str(payable.supplier_name or ""),
            application_kind="goods",
            items=items,
            payment_reason=_payment_reason_for_purchase_receipts([str(receipt.receipt_code or "")]),
            **_department_payload_from_model(receipt, label="采购入库单"),
        )
        return await self._apps.create_application(
            tenant_id, create, created_by, skip_manual_create_auto_submit=True
        )

    async def create_from_purchase_receipts(
        self,
        tenant_id: int,
        purchase_receipt_ids: Sequence[int],
        created_by: int,
    ):
        ids = self._normalize_source_ids(purchase_receipt_ids)
        if len(ids) == 1:
            return await self.create_from_purchase_receipt(
                tenant_id, ids[0], None, created_by
            )

        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        merged_items: List[PaymentApplicationLineCreate] = []
        receipt_codes: List[str] = []

        for rid in ids:
            preview = await self.preview_from_purchase_receipt(tenant_id, rid)
            if preview.get("has_blocking_issues"):
                code = str(preview.get("source_code") or rid)
                reason = preview.get("blocking_reason") or "不可下推付款申请"
                raise BusinessLogicError(f"采购入库单 {code}: {reason}")
            receipt_codes.append(str(preview.get("source_code") or rid))
            sid = int(preview.get("supplier_id") or 0)
            if not sid:
                raise BusinessLogicError("入库单未指定供应商")
            if supplier_id is None:
                supplier_id = sid
                supplier_name = str(preview.get("supplier_name") or "")
            elif sid != supplier_id:
                raise BusinessLogicError("多笔一起加载须为同一供应商")

            for row in preview.get("items") or []:
                merged_items.append(PaymentApplicationLineCreate.model_validate(row))

        if not merged_items:
            raise BusinessLogicError("所选入库单无可合并的请款明细")

        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        first_receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=ids[0], deleted_at__isnull=True
        )
        if not first_receipt:
            raise NotFoundError(f"采购入库单不存在: {ids[0]}")
        create = PaymentApplicationCreate(
            supplier_id=int(supplier_id),
            supplier_name=str(supplier_name or ""),
            application_kind="goods",
            items=merged_items,
            payment_reason=_payment_reason_for_purchase_receipts(receipt_codes),
            **_department_payload_from_model(first_receipt, label="采购入库单"),
        )
        return await self._apps.create_application(
            tenant_id, create, created_by, skip_manual_create_auto_submit=True
        )

    async def create_from_reconciliation(
        self,
        tenant_id: int,
        supplier_id: int,
        items: List[Dict[str, Any]],
        created_by: int,
    ):
        lines: List[PaymentApplicationLineCreate] = []
        payable_codes: List[str] = []
        dept_payload: Optional[Dict[str, Any]] = None
        first_payable: Optional[Payable] = None
        for row in items:
            doc_type = str(row.get("doc_type") or "").strip().lower().replace("-", "_")
            doc_id = int(row.get("doc_id") or 0)
            amount = Decimal(str(row.get("amount") or 0))
            if amount <= 0 or not doc_id:
                raise ValidationError("对账行金额或单据无效")
            if doc_type == "payable":
                payable = await Payable.get_or_none(
                    tenant_id=tenant_id, id=doc_id, deleted_at__isnull=True
                )
                if not payable or int(payable.supplier_id) != supplier_id:
                    raise ValidationError(f"应付单 {doc_id} 不可用")
                max_req = await self._open.max_request_for_payable(tenant_id, payable)
                if amount > max_req:
                    raise ValidationError(f"应付 {payable.payable_code} 超过可请款 {max_req}")
                row_dept = await _department_payload_from_payable(tenant_id, payable)
                if dept_payload is None:
                    dept_payload = row_dept
                    first_payable = payable
                elif row_dept != dept_payload:
                    raise BusinessLogicError("所选应付单申请部门不一致，请分拆下推")
                payable_codes.append(str(payable.payable_code or doc_id))
                from apps.kuaizhizao.services.payment_application_line_materials import (
                    lines_for_payable,
                )

                lines.extend(
                    await lines_for_payable(
                        tenant_id=tenant_id,
                        payable=payable,
                        request_amount=amount,
                        source_type="document_reconciliation",
                        source_id=doc_id,
                        source_code=payable.payable_code,
                        line_kind="goods",
                    )
                )
            else:
                raise ValidationError(f"暂不支持从 {doc_type} 对账下推，请选用应付单")
        if not lines or not first_payable or not dept_payload:
            raise ValidationError("无有效对账行")
        create = PaymentApplicationCreate(
            supplier_id=supplier_id,
            supplier_name=str(first_payable.supplier_name or ""),
            application_kind="goods",
            items=lines,
            payment_reason=_payment_reason_for_payables(payable_codes),
            **dept_payload,
        )
        return await self._apps.create_application(tenant_id, create, created_by)

    async def list_payable_pull_lines(
        self,
        tenant_id: int,
        supplier_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        approved_reviews = ("已审核", "APPROVED", "审核通过")
        from apps.kuaicaiwu.constants.finance_source_types import (
            PAYABLE_SOURCE_PURCHASE_RETURN,
        )

        query = (
            Payable.filter(
                tenant_id=tenant_id,
                supplier_id=supplier_id,
                deleted_at__isnull=True,
                remaining_amount__gt=0,
                review_status__in=approved_reviews,
            )
            .exclude(status="已结清")
            .exclude(source_type=PAYABLE_SOURCE_PURCHASE_RETURN)
        )
        kw = str(keyword or "").strip()
        if kw:
            from tortoise.expressions import Q

            query = query.filter(Q(payable_code__icontains=kw))
        payables = await query.offset(skip).limit(limit).order_by("-created_at")
        display_by_id = await _batch_payable_pull_display_fields(tenant_id, payables)
        rows = []
        for p in payables:
            max_req = await self._open.max_request_for_payable(tenant_id, p)
            if max_req <= 0:
                continue
            display = display_by_id.get(int(p.id), {})
            rows.append(
                {
                    "payable_id": p.id,
                    "payable_code": p.payable_code,
                    "remaining_amount": float(p.remaining_amount or 0),
                    "total_amount": float(p.total_amount or 0),
                    "max_request_amount": float(max_req),
                    "supplier_name": p.supplier_name,
                    "business_date": p.business_date.isoformat() if p.business_date else None,
                    "due_date": p.due_date.isoformat() if p.due_date else None,
                    "status": str(p.status or ""),
                    "department_name": display.get("department_name"),
                    "applicant_name": display.get("applicant_name"),
                }
            )
        return {"data": rows, "total": len(rows)}

    async def list_for_payment_pull(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        supplier_id: Optional[int] = None,
        application_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.payment_application import PaymentApplication

        query = PaymentApplication.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status__in=["已批准", "部分付款"],
            remaining_amount__gt=0,
        )
        if supplier_id:
            query = query.filter(supplier_id=supplier_id)
        kind = str(application_kind or "").strip()
        if kind:
            query = query.filter(application_kind=kind)
        kw = str(keyword or "").strip()
        if kw:
            from tortoise.expressions import Q

            query = query.filter(
                Q(application_code__icontains=kw) | Q(supplier_name__icontains=kw)
            )
        total = await query.count()
        apps = await query.offset(skip).limit(limit).order_by("-created_at")
        rows = []
        for app in apps:
            rows.append(
                {
                    "id": app.id,
                    "code": f"{app.application_code} - {app.supplier_name}",
                    "application_code": app.application_code,
                    "application_kind": str(app.application_kind or "goods"),
                    "expected_payment_date": (
                        app.expected_payment_date.isoformat() if app.expected_payment_date else None
                    ),
                    "supplier_id": int(app.supplier_id or 0) or None,
                    "supplier_name": app.supplier_name,
                    "remaining_amount": float(app.remaining_amount or 0),
                    "capabilities": {
                        "pull_payment": {"allowed": True, "reason": None},
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def preview_pull_for_payment(
        self, tenant_id: int, application_id: int
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.payment_application import PaymentApplication

        app = await PaymentApplication.get_or_none(
            tenant_id=tenant_id, id=application_id, deleted_at__isnull=True
        )
        if not app:
            raise NotFoundError(f"付款申请单不存在: {application_id}")
        remaining = Decimal(str(app.remaining_amount or 0))
        allowed = str(app.status) in ("已批准", "部分付款") and remaining > 0
        code = str(app.application_code or application_id)
        pushable = float(remaining)
        return {
            "target_type": "payment",
            "source_type": "payment_application",
            "source_id": application_id,
            "source_code": code,
            "summary": (
                f"将从付款申请 {code} 创建付款单（可付款 ¥{pushable:,.2f}）"
                if allowed
                else f"付款申请 {code} 当前不可加载付款单"
            ),
            "supplier_id": app.supplier_id,
            "supplier_name": app.supplier_name,
            "items": [
                {
                    "item_id": application_id,
                    "source_code": code,
                    "supplier_name": str(getattr(app, "supplier_name", "") or ""),
                    "max_push_quantity": pushable,
                }
            ],
            "has_blocking_issues": not allowed,
            "blocking_reason": None if allowed else "payment.pull_from_payment_application.not_allowed",
            "tip": "付款金额不可超过申请单待付余额；确认过账后回写申请单已付金额。",
            "max_push_total": pushable,
            "require_payment_voucher": bool(getattr(app, "require_payment_voucher", False)),
            "counterparty_account_name": getattr(app, "supplier_account_name", None),
            "counterparty_bank_name": getattr(app, "supplier_bank_name", None),
            "counterparty_bank_account": getattr(app, "supplier_bank_account", None),
            "payment_method": getattr(app, "payment_method", None),
            "advance_payee_id": getattr(app, "advance_payee_id", None),
            "advance_payee_name": getattr(app, "advance_payee_name", None),
        }
