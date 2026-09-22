"""委外结算服务：按委外收货行结算加工费，支持扣款、红字、应付与成本调差。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.kuaizhizao.models.outsource_settlement import OutsourceSettlement, OutsourceSettlementItem
from apps.kuaizhizao.models.outsource_work_order import (
    OutsourceMaterialReceipt,
    OutsourceProductReturn,
    OutsourceWorkOrder,
)
from apps.kuaizhizao.schemas.outsource_settlement import (
    OutsourceMaterialDeductionPreviewResponse,
    OutsourceSettleableReceiptResponse,
    OutsourceSettlementAudit,
    OutsourceSettlementCreate,
    OutsourceSettlementDocumentChainResponse,
    OutsourceSettlementDocumentChainStep,
    OutsourceSettlementInvoicePreviewItem,
    OutsourceSettlementInvoicePreviewResponse,
    OutsourceSettlementItemCreate,
    OutsourceSettlementItemResponse,
    OutsourceSettlementListEnvelope,
    OutsourceSettlementPayableLink,
    OutsourceSettlementReconciliationPreviewRequest,
    OutsourceSettlementReconciliationPreviewResponse,
    OutsourceSettlementReject,
    OutsourceSettlementResponse,
    OutsourceSettlementUpdate,
)
from apps.kuaizhizao.services.outsource_material_deduction_service import OutsourceMaterialDeductionService
from apps.kuaizhizao.services.outsource_settlement_finance_bridge import OutsourceSettlementFinanceBridge
from apps.kuaizhizao.utils.outsource_settlement_helpers import (
    LINE_TYPE_MATERIAL_DEDUCTION,
    LINE_TYPE_PROCESSING,
    LINE_TYPE_RETURN_CREDIT,
    SETTLEMENT_KIND_CREDIT,
    receipt_base_qty,
)
from apps.master_data.models.supplier import Supplier
from core.utils.timezone_utils import resolve_business_datetime, today_site_str, to_api_isoformat
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User


class OutsourceSettlementService:
    @staticmethod
    def _gen_settlement_code() -> str:
        return f"WWJS{today_site_str()}{uuid.uuid4().hex[:6].upper()}"

    @classmethod
    async def _load_supplier(cls, tenant_id: int, supplier_id: int) -> Supplier:
        supplier = await Supplier.filter(
            id=supplier_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not supplier:
            raise NotFoundError(f"供应商不存在: {supplier_id}")
        return supplier

    @classmethod
    async def _returned_qty_by_receipt(cls, tenant_id: int, receipt_ids: Sequence[int]) -> Dict[int, Decimal]:
        if not receipt_ids:
            return {}
        rows = await OutsourceProductReturn.filter(
            tenant_id=tenant_id,
            outsource_material_receipt_id__in=list(receipt_ids),
            status="completed",
            deleted_at__isnull=True,
        ).all()
        totals: Dict[int, Decimal] = {}
        for row in rows:
            rid = int(row.outsource_material_receipt_id or 0)
            if rid <= 0:
                continue
            totals[rid] = totals.get(rid, Decimal("0")) + Decimal(str(row.quantity or 0))
        return totals

    @classmethod
    async def _pending_qty_by_receipt(
        cls,
        tenant_id: int,
        receipt_ids: Sequence[int],
        *,
        exclude_settlement_id: Optional[int] = None,
    ) -> Dict[int, Decimal]:
        if not receipt_ids:
            return {}
        item_q = OutsourceSettlementItem.filter(
            tenant_id=tenant_id,
            outsource_material_receipt_id__in=list(receipt_ids),
            line_type=LINE_TYPE_PROCESSING,
            deleted_at__isnull=True,
        )
        if exclude_settlement_id is not None:
            item_q = item_q.exclude(settlement_id=exclude_settlement_id)
        items = await item_q.all()
        if not items:
            return {}
        settlement_ids = {int(i.settlement_id) for i in items}
        settlements = await OutsourceSettlement.filter(
            tenant_id=tenant_id,
            id__in=list(settlement_ids),
            status__in=["草稿", "待审核"],
            deleted_at__isnull=True,
        ).all()
        open_ids = {s.id for s in settlements}
        totals: Dict[int, Decimal] = {}
        for item in items:
            if item.settlement_id not in open_ids:
                continue
            rid = int(item.outsource_material_receipt_id or 0)
            if rid <= 0:
                continue
            totals[rid] = totals.get(rid, Decimal("0")) + Decimal(str(item.settlement_quantity or 0))
        return totals

    @classmethod
    async def _resolve_settleable_qty(
        cls,
        tenant_id: int,
        receipt: OutsourceMaterialReceipt,
        *,
        exclude_settlement_id: Optional[int] = None,
    ) -> Decimal:
        base = receipt_base_qty(receipt)
        returned = (await cls._returned_qty_by_receipt(tenant_id, [receipt.id])).get(receipt.id, Decimal("0"))
        settled = Decimal(str(receipt.settled_quantity or 0))
        pending = (await cls._pending_qty_by_receipt(
            tenant_id, [receipt.id], exclude_settlement_id=exclude_settlement_id
        )).get(receipt.id, Decimal("0"))
        return base - returned - settled - pending

    @classmethod
    async def _load_receipt_context(
        cls,
        tenant_id: int,
        receipt_id: int,
    ) -> tuple[OutsourceMaterialReceipt, OutsourceWorkOrder]:
        receipt = await OutsourceMaterialReceipt.filter(
            tenant_id=tenant_id,
            id=receipt_id,
            deleted_at__isnull=True,
        ).first()
        if not receipt:
            raise ValidationError(f"委外收货单不存在: {receipt_id}")
        if receipt.status != "completed":
            raise ValidationError(f"委外收货单 {receipt.code} 未完成，不可结算")
        work_order = await OutsourceWorkOrder.filter(
            tenant_id=tenant_id,
            id=receipt.outsource_work_order_id,
            deleted_at__isnull=True,
        ).first()
        if not work_order:
            raise ValidationError(f"委外工单不存在: {receipt.outsource_work_order_id}")
        return receipt, work_order

    @classmethod
    async def _normalize_processing_item(
        cls,
        tenant_id: int,
        supplier_id: int,
        item: OutsourceSettlementItemCreate,
        *,
        exclude_settlement_id: Optional[int] = None,
        line_no: int,
    ) -> dict:
        receipt_id = int(item.outsource_material_receipt_id or 0)
        receipt, work_order = await cls._load_receipt_context(tenant_id, receipt_id)
        if int(work_order.supplier_id) != int(supplier_id):
            raise ValidationError(f"收货单 {receipt.code} 供应商与结算单供应商不一致")
        settleable = await cls._resolve_settleable_qty(
            tenant_id, receipt, exclude_settlement_id=exclude_settlement_id
        )
        qty = Decimal(str(item.settlement_quantity))
        if qty <= 0:
            raise ValidationError(f"收货单 {receipt.code} 结算数量须大于 0")
        if qty > settleable:
            raise ValidationError(f"收货单 {receipt.code} 可结算数量 {settleable}，超出 {qty}")
        unit_price = Decimal(str(item.unit_price))
        amount = (qty * unit_price).quantize(Decimal("0.01"))
        return {
            "line_no": line_no,
            "line_type": LINE_TYPE_PROCESSING,
            "outsource_material_receipt_id": receipt.id,
            "receipt_code": receipt.code,
            "outsource_work_order_id": work_order.id,
            "outsource_work_order_code": work_order.code,
            "product_code": work_order.product_code,
            "product_name": work_order.product_name,
            "unit": receipt.unit,
            "settlement_quantity": qty,
            "unit_price": unit_price,
            "amount": amount,
            "notes": (item.notes or "").strip() or None,
        }

    @classmethod
    async def _normalize_deduction_item(
        cls,
        tenant_id: int,
        supplier_id: int,
        item: OutsourceSettlementItemCreate,
        *,
        line_no: int,
    ) -> dict:
        wo_id = int(item.outsource_work_order_id or 0)
        work_order = await OutsourceWorkOrder.filter(
            tenant_id=tenant_id,
            id=wo_id,
            deleted_at__isnull=True,
        ).first()
        if not work_order:
            raise ValidationError(f"委外工单不存在: {wo_id}")
        if int(work_order.supplier_id) != int(supplier_id):
            raise ValidationError(f"工单 {work_order.code} 供应商与结算单不一致")

        previews = await OutsourceMaterialDeductionService.preview_deductions(
            tenant_id, supplier_id=supplier_id, work_order_ids=[wo_id]
        )
        basis_amount = Decimal(str(item.deduction_basis_amount)).quantize(Decimal("0.01"))
        matching = [
            p for p in previews
            if p.outsource_work_order_id == wo_id
            and p.deduction_amount == basis_amount
            and p.overrun_qty == Decimal(str(item.settlement_quantity))
        ]
        if not matching:
            raise ValidationError(f"工单 {work_order.code} 超耗扣款快照与系统计算不一致，请重新计算")

        qty = Decimal(str(item.settlement_quantity))
        unit_price = Decimal(str(item.unit_price))
        expected_amount = (qty * unit_price).quantize(Decimal("0.01"))
        if expected_amount != basis_amount:
            raise ValidationError(f"工单 {work_order.code} 扣款金额与快照不一致")

        return {
            "line_no": line_no,
            "line_type": LINE_TYPE_MATERIAL_DEDUCTION,
            "outsource_material_receipt_id": None,
            "receipt_code": None,
            "outsource_work_order_id": work_order.id,
            "outsource_work_order_code": work_order.code,
            "product_code": work_order.product_code,
            "product_name": work_order.product_name,
            "unit": "件",
            "deduction_basis_qty": Decimal(str(item.deduction_basis_qty)),
            "deduction_basis_amount": basis_amount,
            "settlement_quantity": qty,
            "unit_price": unit_price,
            "amount": basis_amount,
            "notes": (item.notes or "").strip() or None,
        }

    @classmethod
    async def _normalize_items(
        cls,
        tenant_id: int,
        supplier_id: int,
        items: Sequence[OutsourceSettlementItemCreate],
        *,
        exclude_settlement_id: Optional[int] = None,
        settlement_kind: str = "normal",
    ) -> List[dict]:
        if not items:
            raise ValidationError("请至少添加一条结算明细")
        if getattr(settlement_kind, "strip", lambda: settlement_kind)() == SETTLEMENT_KIND_CREDIT:
            raise ValidationError("红字结算单不可手工编辑明细")
        normalized: List[dict] = []
        seen_receipts: set[int] = set()
        seen_wo_deduction: set[int] = set()
        line_no = 0
        for item in items:
            lt = (item.line_type or LINE_TYPE_PROCESSING).strip()
            line_no += 1
            if lt == LINE_TYPE_PROCESSING:
                receipt_id = int(item.outsource_material_receipt_id or 0)
                if receipt_id in seen_receipts:
                    raise BusinessLogicError(f"结算明细收货单重复: {receipt_id}")
                seen_receipts.add(receipt_id)
                normalized.append(
                    await cls._normalize_processing_item(
                        tenant_id, supplier_id, item,
                        exclude_settlement_id=exclude_settlement_id,
                        line_no=line_no,
                    )
                )
            elif lt == LINE_TYPE_MATERIAL_DEDUCTION:
                wo_id = int(item.outsource_work_order_id or 0)
                if wo_id in seen_wo_deduction:
                    raise BusinessLogicError(f"同一工单扣款行重复: {wo_id}")
                seen_wo_deduction.add(wo_id)
                normalized.append(
                    await cls._normalize_deduction_item(
                        tenant_id, supplier_id, item, line_no=line_no
                    )
                )
            else:
                raise ValidationError(f"不支持的行类型: {lt}")
        return normalized

    @classmethod
    def _calc_total(cls, items: Sequence[dict]) -> Decimal:
        total = Decimal("0")
        for row in items:
            amount = Decimal(str(row["amount"]))
            lt = row.get("line_type", LINE_TYPE_PROCESSING)
            if lt == LINE_TYPE_MATERIAL_DEDUCTION:
                total -= amount
            else:
                total += amount
        return total.quantize(Decimal("0.01"))

    @classmethod
    async def _load_items(cls, tenant_id: int, settlement_id: int) -> List[OutsourceSettlementItem]:
        return await OutsourceSettlementItem.filter(
            tenant_id=tenant_id,
            settlement_id=settlement_id,
            deleted_at__isnull=True,
        ).order_by("line_no", "id")

    @classmethod
    async def _collect_payables(
        cls,
        tenant_id: int,
        settlement: OutsourceSettlement,
        items: List[OutsourceSettlementItem],
    ) -> List[OutsourceSettlementPayableLink]:
        from apps.kuaicaiwu.constants.finance_source_types import (
            PAYABLE_SOURCE_OUTSOURCE_RECEIPT,
            PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT,
            PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT_CREDIT,
        )
        from apps.kuaicaiwu.models.payable import Payable
        receipt_ids = [
            int(i.outsource_material_receipt_id)
            for i in items
            if i.outsource_material_receipt_id
        ]
        source_types = [
            PAYABLE_SOURCE_OUTSOURCE_RECEIPT,
            PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT,
            PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT_CREDIT,
        ]
        payables = await Payable.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            is_active=True,
        ).filter(
            Q(source_type__in=source_types, source_id=settlement.id)
            | Q(source_type=PAYABLE_SOURCE_OUTSOURCE_RECEIPT, source_id__in=receipt_ids or [0])
        ).all()

        links: List[OutsourceSettlementPayableLink] = []
        seen: set[int] = set()
        for p in payables:
            if p.id in seen:
                continue
            seen.add(p.id)
            inv_status = "已开票" if getattr(p, "invoice_received", False) else "未开票"
            links.append(
                OutsourceSettlementPayableLink(
                    payable_id=int(p.id),
                    payable_code=getattr(p, "payable_code", None),
                    source_type=str(p.source_type or ""),
                    total_amount=Decimal(str(p.total_amount or 0)),
                    invoice_status=inv_status,
                )
            )
        return links

    @classmethod
    async def _derive_invoice_status(cls, payables: List[OutsourceSettlementPayableLink]) -> Optional[str]:
        if not payables:
            return "未开票"
        statuses = {p.invoice_status for p in payables if p.invoice_status}
        if not statuses:
            return "未开票"
        if statuses == {"已开票"}:
            return "已开票"
        if "未开票" in statuses and len(statuses) == 1:
            return "未开票"
        return "部分开票"

    @classmethod
    async def _to_response(
        cls,
        row: OutsourceSettlement,
        items: Optional[List[OutsourceSettlementItem]] = None,
    ) -> OutsourceSettlementResponse:
        if items is None:
            items = await cls._load_items(row.tenant_id, row.id)
        payables = await cls._collect_payables(row.tenant_id, row, items)
        payload = {
            "id": row.id,
            "settlement_code": row.settlement_code,
            "supplier_id": row.supplier_id,
            "supplier_code": row.supplier_code,
            "supplier_name": row.supplier_name,
            "business_date": row.business_date,
            "total_amount": Decimal(str(row.total_amount or 0)),
            "status": row.status,
            "settlement_kind": getattr(row, "settlement_kind", None) or "normal",
            "auto_generated": bool(getattr(row, "auto_generated", False)),
            "source_doc_type": getattr(row, "source_doc_type", None),
            "source_doc_id": getattr(row, "source_doc_id", None),
            "reviewer_id": row.reviewer_id,
            "reviewer_name": row.reviewer_name,
            "reviewed_at": to_api_isoformat(row.reviewed_at) if row.reviewed_at else None,
            "review_remarks": row.review_remarks,
            "payable_id": row.payable_id,
            "payable_code": row.payable_code,
            "invoice_status": await cls._derive_invoice_status(payables),
            "notes": row.notes,
            "created_at": to_api_isoformat(row.created_at) if row.created_at else None,
            "updated_at": to_api_isoformat(row.updated_at) if row.updated_at else None,
            "created_by_name": getattr(row, "created_by_name", None),
            "updated_by_name": getattr(row, "updated_by_name", None),
            "items": [
                OutsourceSettlementItemResponse(
                    id=i.id,
                    line_no=i.line_no,
                    line_type=getattr(i, "line_type", None) or LINE_TYPE_PROCESSING,
                    outsource_material_receipt_id=i.outsource_material_receipt_id,
                    receipt_code=i.receipt_code,
                    outsource_work_order_id=i.outsource_work_order_id,
                    outsource_work_order_code=i.outsource_work_order_code,
                    product_code=i.product_code,
                    product_name=i.product_name,
                    unit=i.unit,
                    outsource_product_return_id=getattr(i, "outsource_product_return_id", None),
                    deduction_basis_qty=(
                        Decimal(str(i.deduction_basis_qty))
                        if getattr(i, "deduction_basis_qty", None) is not None
                        else None
                    ),
                    deduction_basis_amount=(
                        Decimal(str(i.deduction_basis_amount))
                        if getattr(i, "deduction_basis_amount", None) is not None
                        else None
                    ),
                    settlement_quantity=Decimal(str(i.settlement_quantity or 0)),
                    unit_price=Decimal(str(i.unit_price or 0)),
                    amount=Decimal(str(i.amount or 0)),
                    notes=i.notes,
                )
                for i in items
            ],
            "payables": payables,
        }
        return OutsourceSettlementResponse.model_validate(payload)

    @classmethod
    async def preview_deductions(
        cls,
        tenant_id: int,
        *,
        supplier_id: int,
        work_order_ids: List[int],
    ) -> List[OutsourceMaterialDeductionPreviewResponse]:
        rows = await OutsourceMaterialDeductionService.preview_deductions(
            tenant_id, supplier_id=supplier_id, work_order_ids=work_order_ids
        )
        return [
            OutsourceMaterialDeductionPreviewResponse(
                outsource_work_order_id=r.outsource_work_order_id,
                outsource_work_order_code=r.outsource_work_order_code,
                material_id=r.material_id,
                material_code=r.material_code,
                material_name=r.material_name,
                standard_qty=r.standard_qty,
                actual_qty=r.actual_qty,
                overrun_qty=r.overrun_qty,
                unit_price=r.unit_price,
                deduction_amount=r.deduction_amount,
            )
            for r in rows
        ]

    @classmethod
    async def list_settleable_receipts(
        cls,
        tenant_id: int,
        *,
        supplier_id: int,
        exclude_settlement_id: Optional[int] = None,
    ) -> List[OutsourceSettleableReceiptResponse]:
        receipts = await OutsourceMaterialReceipt.filter(
            tenant_id=tenant_id,
            status="completed",
            deleted_at__isnull=True,
        ).order_by("-received_at", "-id").all()
        if not receipts:
            return []
        owo_ids = {int(r.outsource_work_order_id) for r in receipts}
        work_orders = await OutsourceWorkOrder.filter(
            tenant_id=tenant_id,
            id__in=list(owo_ids),
            supplier_id=supplier_id,
            deleted_at__isnull=True,
        ).all()
        owo_by_id = {w.id: w for w in work_orders}
        receipt_ids = [r.id for r in receipts if r.outsource_work_order_id in owo_by_id]
        returned_map = await cls._returned_qty_by_receipt(tenant_id, receipt_ids)
        pending_map = await cls._pending_qty_by_receipt(
            tenant_id, receipt_ids, exclude_settlement_id=exclude_settlement_id
        )
        result: List[OutsourceSettleableReceiptResponse] = []
        for receipt in receipts:
            work_order = owo_by_id.get(receipt.outsource_work_order_id)
            if not work_order:
                continue
            base = receipt_base_qty(receipt)
            returned = returned_map.get(receipt.id, Decimal("0"))
            settled = Decimal(str(receipt.settled_quantity or 0))
            pending = pending_map.get(receipt.id, Decimal("0"))
            settleable = base - returned - settled - pending
            if settleable <= 0:
                continue
            unit_price = Decimal(str(receipt.unit_price or work_order.unit_price or 0))
            result.append(
                OutsourceSettleableReceiptResponse(
                    id=receipt.id,
                    code=receipt.code,
                    outsource_work_order_id=work_order.id,
                    outsource_work_order_code=work_order.code,
                    supplier_id=work_order.supplier_id,
                    supplier_code=work_order.supplier_code,
                    supplier_name=work_order.supplier_name,
                    product_code=work_order.product_code,
                    product_name=work_order.product_name,
                    unit=receipt.unit,
                    qualified_quantity=base,
                    returned_quantity=returned,
                    settled_quantity=settled,
                    pending_settlement_quantity=pending,
                    settleable_quantity=settleable,
                    unit_price=unit_price,
                    received_at=to_api_isoformat(receipt.received_at) if receipt.received_at else None,
                )
            )
        return result

    @classmethod
    async def create(
        cls,
        tenant_id: int,
        data: OutsourceSettlementCreate,
        current_user: User,
    ) -> OutsourceSettlementResponse:
        supplier = await cls._load_supplier(tenant_id, data.supplier_id)
        normalized = await cls._normalize_items(tenant_id, supplier.id, data.items)
        total = cls._calc_total(normalized)
        async with in_transaction():
            payload = {
                "tenant_id": tenant_id,
                "settlement_code": cls._gen_settlement_code(),
                "supplier_id": supplier.id,
                "supplier_code": supplier.code,
                "supplier_name": supplier.name,
                "business_date": data.business_date,
                "total_amount": total,
                "status": "草稿",
                "settlement_kind": "normal",
                "auto_generated": False,
                "notes": (data.notes or "").strip() or None,
            }
            apply_create_audit(payload, current_user)
            row = await OutsourceSettlement.create(**payload)
            created_items: List[OutsourceSettlementItem] = []
            for item_row in normalized:
                item_payload = {"tenant_id": tenant_id, "settlement_id": row.id, **item_row}
                apply_create_audit(item_payload, current_user)
                created_items.append(await OutsourceSettlementItem.create(**item_payload))
        return await cls._to_response(row, created_items)

    @classmethod
    async def get(cls, tenant_id: int, settlement_id: int) -> OutsourceSettlementResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        return await cls._to_response(row)

    @classmethod
    async def list_settlements(
        cls,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        supplier_id: Optional[int] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> OutsourceSettlementListEnvelope:
        query = OutsourceSettlement.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if supplier_id is not None:
            query = query.filter(supplier_id=supplier_id)
        if status:
            query = query.filter(status=status.strip())
        if keyword:
            kw = keyword.strip()
            if kw:
                query = query.filter(
                    Q(settlement_code__icontains=kw)
                    | Q(supplier_name__icontains=kw)
                    | Q(supplier_code__icontains=kw)
                )
        total = await query.count()
        rows = await query.order_by("-created_at", "-id").offset(skip).limit(limit)
        return OutsourceSettlementListEnvelope(
            items=[await cls._to_response(r) for r in rows],
            total=total,
        )

    @classmethod
    async def update(
        cls,
        tenant_id: int,
        settlement_id: int,
        data: OutsourceSettlementUpdate,
        current_user: User,
    ) -> OutsourceSettlementResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        if row.status != "草稿":
            raise ValidationError("仅草稿状态可编辑")
        if getattr(row, "settlement_kind", "normal") == SETTLEMENT_KIND_CREDIT and getattr(row, "auto_generated", False):
            dump = data.model_dump(exclude_unset=True)
            allowed = {}
            if "business_date" in dump:
                allowed["business_date"] = dump["business_date"]
            if "notes" in dump:
                allowed["notes"] = (dump.get("notes") or "").strip() or None
            if dump.get("items") is not None:
                raise ValidationError("自动生成的红字结算单不可修改明细")
            if allowed:
                apply_update_audit(allowed, current_user)
                await OutsourceSettlement.filter(id=settlement_id, tenant_id=tenant_id).update(**allowed)
            row = await OutsourceSettlement.get(id=settlement_id, tenant_id=tenant_id)
            return await cls._to_response(row)

        dump = data.model_dump(exclude_unset=True)
        items_payload = dump.pop("items", None)
        if "notes" in dump:
            dump["notes"] = (dump.get("notes") or "").strip() or None
        async with in_transaction():
            created_items: Optional[List[OutsourceSettlementItem]] = None
            if items_payload is not None:
                normalized = await cls._normalize_items(
                    tenant_id,
                    row.supplier_id,
                    [OutsourceSettlementItemCreate.model_validate(x) for x in items_payload],
                    exclude_settlement_id=settlement_id,
                )
                await OutsourceSettlementItem.filter(
                    tenant_id=tenant_id,
                    settlement_id=settlement_id,
                ).delete()
                created_items = []
                for item_row in normalized:
                    item_payload = {"tenant_id": tenant_id, "settlement_id": settlement_id, **item_row}
                    apply_create_audit(item_payload, current_user)
                    created_items.append(await OutsourceSettlementItem.create(**item_payload))
                dump["total_amount"] = cls._calc_total(normalized)
            if dump:
                apply_update_audit(dump, current_user)
                await OutsourceSettlement.filter(id=settlement_id, tenant_id=tenant_id).update(**dump)
            row = await OutsourceSettlement.get(id=settlement_id, tenant_id=tenant_id)
        return await cls._to_response(row, created_items)

    @classmethod
    async def submit(cls, tenant_id: int, settlement_id: int, current_user: User) -> OutsourceSettlementResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        if row.status != "草稿":
            raise BusinessLogicError("仅草稿状态可提交审核")
        items = await cls._load_items(tenant_id, settlement_id)
        if not items:
            raise ValidationError("请至少添加一条结算明细")
        dump = {"status": "待审核"}
        apply_update_audit(dump, current_user)
        await OutsourceSettlement.filter(id=settlement_id, tenant_id=tenant_id).update(**dump)
        row = await OutsourceSettlement.get(id=settlement_id, tenant_id=tenant_id)
        return await cls._to_response(row, items)

    @classmethod
    async def _apply_cost_adjustments(
        cls,
        tenant_id: int,
        items: Sequence[OutsourceSettlementItem],
        *,
        reverse: bool = False,
    ) -> None:
        from apps.kuaicaiwu.services.inventory_cost_service import InventoryCostService

        cost_svc = InventoryCostService()
        for item in items:
            if getattr(item, "line_type", LINE_TYPE_PROCESSING) != LINE_TYPE_PROCESSING:
                continue
            if not item.outsource_material_receipt_id:
                continue
            receipt = await OutsourceMaterialReceipt.get(
                tenant_id=tenant_id, id=item.outsource_material_receipt_id
            )
            work_order = await OutsourceWorkOrder.get(
                tenant_id=tenant_id, id=receipt.outsource_work_order_id
            )
            if not work_order.product_id:
                continue
            proc_cost = Decimal(str(receipt.processing_unit_cost or receipt.unit_price or 0))
            delta = (Decimal(str(item.unit_price)) - proc_cost) * Decimal(str(item.settlement_quantity))
            delta = delta.quantize(Decimal("0.01"))
            if delta == 0:
                continue
            await cost_svc.adjust_material_cost_for_outsource_settlement(
                tenant_id,
                material_id=int(work_order.product_id),
                adjustment_amount=delta,
                settlement_id=int(item.settlement_id),
                receipt_id=int(receipt.id),
                reverse=reverse,
            )

    @classmethod
    async def audit(
        cls,
        tenant_id: int,
        settlement_id: int,
        data: OutsourceSettlementAudit,
        current_user: User,
    ) -> OutsourceSettlementResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        if row.status != "待审核":
            raise BusinessLogicError("仅待审核状态可审核通过")
        if row.business_date is None:
            raise ValidationError("审核前须填写业务日期")
        items = await cls._load_items(tenant_id, settlement_id)
        if not items:
            raise ValidationError("请至少添加一条结算明细")

        async with in_transaction():
            for item in items:
                lt = getattr(item, "line_type", LINE_TYPE_PROCESSING)
                if lt == LINE_TYPE_MATERIAL_DEDUCTION:
                    continue
                if not item.outsource_material_receipt_id:
                    continue
                receipt = await OutsourceMaterialReceipt.get(
                    tenant_id=tenant_id,
                    id=item.outsource_material_receipt_id,
                )
                qty = Decimal(str(item.settlement_quantity or 0))
                if lt == LINE_TYPE_PROCESSING:
                    settleable = await cls._resolve_settleable_qty(
                        tenant_id, receipt, exclude_settlement_id=settlement_id
                    )
                    if qty > settleable:
                        raise ValidationError(f"收货单 {receipt.code} 可结算数量不足")
                new_settled = Decimal(str(receipt.settled_quantity or 0)) + qty
                if new_settled < 0:
                    raise ValidationError(f"收货单 {receipt.code} 已结算数量不足冲减")
                await OutsourceMaterialReceipt.filter(id=receipt.id, tenant_id=tenant_id).update(
                    settled_quantity=new_settled,
                )

            receipt_ids = [
                int(i.outsource_material_receipt_id)
                for i in items
                if i.outsource_material_receipt_id
            ]
            provisional = await OutsourceSettlementFinanceBridge.sum_provisional_payables(
                tenant_id, receipt_ids
            )
            settlement_total = Decimal(str(row.total_amount or 0))
            diff = (settlement_total - provisional).quantize(Decimal("0.01"))

            payable_id = await OutsourceSettlementFinanceBridge.create_settlement_payable_delta(
                tenant_id=tenant_id,
                settlement=row,
                receipt_ids=receipt_ids,
                created_by=current_user.id,
            )
            payable_code = None
            if payable_id:
                from apps.kuaicaiwu.models.payable import Payable

                payable = await Payable.get_or_none(tenant_id=tenant_id, id=payable_id)
                payable_code = getattr(payable, "payable_code", None) if payable else None
            elif OutsourceSettlementFinanceBridge.requires_payable_on_audit(row, diff):
                raise BusinessLogicError("未能生成差额应付，请检查财务配置")

            await cls._apply_cost_adjustments(tenant_id, items, reverse=False)

            dump = {
                "status": "已审核",
                "reviewer_id": current_user.id,
                "reviewer_name": current_user.full_name or current_user.username,
                "reviewed_at": resolve_business_datetime(),
                "review_remarks": (data.review_remarks or "").strip() or None,
                "payable_id": payable_id,
                "payable_code": payable_code,
            }
            apply_update_audit(dump, current_user)
            await OutsourceSettlement.filter(id=settlement_id, tenant_id=tenant_id).update(**dump)
            row = await OutsourceSettlement.get(id=settlement_id, tenant_id=tenant_id)
        return await cls._to_response(row, items)

    @classmethod
    async def reject(
        cls,
        tenant_id: int,
        settlement_id: int,
        data: OutsourceSettlementReject,
        current_user: User,
    ) -> OutsourceSettlementResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        if row.status != "待审核":
            raise BusinessLogicError("仅待审核状态可驳回")
        dump = {
            "status": "草稿",
            "reviewer_id": current_user.id,
            "reviewer_name": current_user.full_name or current_user.username,
            "reviewed_at": resolve_business_datetime(),
            "review_remarks": data.review_remarks.strip(),
        }
        apply_update_audit(dump, current_user)
        await OutsourceSettlement.filter(id=settlement_id, tenant_id=tenant_id).update(**dump)
        row = await OutsourceSettlement.get(id=settlement_id, tenant_id=tenant_id)
        return await cls._to_response(row)

    @classmethod
    async def revoke(
        cls,
        tenant_id: int,
        settlement_id: int,
        current_user: User,
    ) -> OutsourceSettlementResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        if row.status != "已审核":
            raise BusinessLogicError("仅已审核状态可撤回审核")
        items = await cls._load_items(tenant_id, settlement_id)

        await OutsourceSettlementFinanceBridge.assert_payable_revokable(tenant_id, row.payable_id)

        async with in_transaction():
            await OutsourceSettlementFinanceBridge.soft_delete_payable(tenant_id, row.payable_id)
            await cls._apply_cost_adjustments(tenant_id, items, reverse=True)

            for item in items:
                lt = getattr(item, "line_type", LINE_TYPE_PROCESSING)
                if lt == LINE_TYPE_MATERIAL_DEDUCTION:
                    continue
                if not item.outsource_material_receipt_id:
                    continue
                receipt = await OutsourceMaterialReceipt.get(
                    tenant_id=tenant_id,
                    id=item.outsource_material_receipt_id,
                )
                qty = Decimal(str(item.settlement_quantity or 0))
                new_settled = Decimal(str(receipt.settled_quantity or 0)) - qty
                if new_settled < 0:
                    raise BusinessLogicError(f"收货单 {receipt.code} 已结算数量异常")
                await OutsourceMaterialReceipt.filter(id=receipt.id, tenant_id=tenant_id).update(
                    settled_quantity=new_settled,
                )
            dump = {
                "status": "草稿",
                "payable_id": None,
                "payable_code": None,
                "reviewer_id": None,
                "reviewer_name": None,
                "reviewed_at": None,
                "review_remarks": None,
            }
            apply_update_audit(dump, current_user)
            await OutsourceSettlement.filter(id=settlement_id, tenant_id=tenant_id).update(**dump)
            row = await OutsourceSettlement.get(id=settlement_id, tenant_id=tenant_id)
        return await cls._to_response(row, items)

    @classmethod
    async def delete(cls, tenant_id: int, settlement_id: int, current_user: User) -> None:
        row = await OutsourceSettlement.filter(
            id=settlement_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        if row.status != "草稿":
            raise BusinessLogicError("仅草稿状态可删除")
        dump = {"deleted_at": resolve_business_datetime()}
        apply_update_audit(dump, current_user)
        await OutsourceSettlement.filter(id=settlement_id, tenant_id=tenant_id).update(**dump)

    @classmethod
    async def reconciliation_preview(
        cls,
        tenant_id: int,
        data: OutsourceSettlementReconciliationPreviewRequest,
    ) -> OutsourceSettlementReconciliationPreviewResponse:
        supplier = await cls._load_supplier(tenant_id, data.supplier_id)
        wo_q = OutsourceWorkOrder.filter(
            tenant_id=tenant_id,
            supplier_id=supplier.id,
            deleted_at__isnull=True,
        )
        if data.outsource_work_order_ids:
            wo_q = wo_q.filter(id__in=data.outsource_work_order_ids)
        work_orders = await wo_q.all()
        wo_ids = [w.id for w in work_orders]

        receipts = await OutsourceMaterialReceipt.filter(
            tenant_id=tenant_id,
            outsource_work_order_id__in=wo_ids or [0],
            status="completed",
            deleted_at__isnull=True,
        ).all()

        processing_total = Decimal("0")
        settled_total = Decimal("0")
        for r in receipts:
            base = receipt_base_qty(r)
            unit = Decimal(str(r.unit_price or 0))
            processing_total += base * unit
            settled_total += Decimal(str(r.settled_quantity or 0)) * unit

        previews = await OutsourceMaterialDeductionService.preview_deductions(
            tenant_id, supplier_id=supplier.id, work_order_ids=wo_ids
        )
        deduction_total = sum((p.deduction_amount for p in previews), Decimal("0"))

        receipt_ids = [r.id for r in receipts]
        provisional = await OutsourceSettlementFinanceBridge.sum_provisional_payables(
            tenant_id, receipt_ids
        )

        from apps.kuaicaiwu.constants.finance_source_types import PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT
        from apps.kuaicaiwu.models.payable import Payable

        settlement_payables = await Payable.filter(
            tenant_id=tenant_id,
            source_type=PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT,
            deleted_at__isnull=True,
            is_active=True,
            supplier_id=supplier.id,
        ).all()
        settlement_payable_total = sum(
            (Decimal(str(p.total_amount or 0)) for p in settlement_payables), Decimal("0")
        )

        unsettled = (processing_total - settled_total - deduction_total).quantize(Decimal("0.01"))

        return OutsourceSettlementReconciliationPreviewResponse(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            processing_total=processing_total.quantize(Decimal("0.01")),
            deduction_total=deduction_total.quantize(Decimal("0.01")),
            settled_total=settled_total.quantize(Decimal("0.01")),
            unsettled_total=unsettled,
            provisional_payable_total=provisional,
            settlement_payable_total=settlement_payable_total.quantize(Decimal("0.01")),
        )

    @classmethod
    async def invoice_preview(
        cls,
        tenant_id: int,
        settlement_id: int,
    ) -> OutsourceSettlementInvoicePreviewResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id, tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        items = await cls._load_items(tenant_id, settlement_id)
        payables = await cls._collect_payables(tenant_id, row, items)
        preview_items = [
            OutsourceSettlementInvoicePreviewItem(
                payable_id=p.payable_id,
                payable_code=p.payable_code,
                source_type=p.source_type,
                amount=p.total_amount,
                description=f"{p.source_type} {p.payable_code or p.payable_id}",
            )
            for p in payables
        ]
        total = sum((p.amount for p in preview_items), Decimal("0")).quantize(Decimal("0.01"))
        return OutsourceSettlementInvoicePreviewResponse(
            settlement_id=row.id,
            supplier_id=row.supplier_id,
            supplier_name=row.supplier_name,
            items=preview_items,
            total_amount=total,
        )

    @classmethod
    async def document_chain(
        cls,
        tenant_id: int,
        settlement_id: int,
    ) -> OutsourceSettlementDocumentChainResponse:
        row = await OutsourceSettlement.filter(
            id=settlement_id, tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError(f"委外结算单不存在: {settlement_id}")
        items = await cls._load_items(tenant_id, settlement_id)
        steps: List[OutsourceSettlementDocumentChainStep] = []

        wo_ids = {int(i.outsource_work_order_id) for i in items if i.outsource_work_order_id}
        for wo_id in wo_ids:
            wo = await OutsourceWorkOrder.get_or_none(tenant_id=tenant_id, id=wo_id)
            if wo:
                steps.append(
                    OutsourceSettlementDocumentChainStep(
                        step="1", doc_type="outsource_work_order",
                        doc_id=wo.id, doc_code=wo.code, status=wo.status,
                    )
                )

        for item in items:
            if item.outsource_material_receipt_id:
                rec = await OutsourceMaterialReceipt.get_or_none(
                    tenant_id=tenant_id, id=item.outsource_material_receipt_id
                )
                if rec:
                    steps.append(
                        OutsourceSettlementDocumentChainStep(
                            step="3", doc_type="outsource_material_receipt",
                            doc_id=rec.id, doc_code=rec.code, status=rec.status,
                        )
                    )

        steps.append(
            OutsourceSettlementDocumentChainStep(
                step="4", doc_type="outsource_settlement",
                doc_id=row.id, doc_code=row.settlement_code, status=row.status,
            )
        )

        payables = await cls._collect_payables(tenant_id, row, items)
        for p in payables:
            steps.append(
                OutsourceSettlementDocumentChainStep(
                    step="5", doc_type="payable",
                    doc_id=p.payable_id, doc_code=p.payable_code,
                    status=p.invoice_status,
                )
            )

        return OutsourceSettlementDocumentChainResponse(
            settlement_id=row.id,
            steps=steps,
        )
