"""月结业财对账检查：应收/应付余额 vs 总账科目。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.kuaicaiwu.models.receivable import Receivable
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.services.gl.balance_service import BalanceService

_BUSINESS_TYPE_LABELS: Dict[str, str] = {
    "payable": "应付",
    "receivable": "应收",
    "purchase_invoice": "采购发票",
    "invoice": "发票",
    "settlement": "收付款结算",
    "payment": "付款",
    "receipt": "收款",
    "receipt_refund": "收款退款",
    "payment_refund": "付款退款",
    "fixed_asset": "固定资产折旧",
    "fixed_asset_adjustment": "固定资产调整",
    "fixed_asset_disposal": "固定资产处置",
    "fixed_asset_impairment": "固定资产减值",
    "fx_revaluation": "汇兑损益",
}

_SOURCE_DOC_TYPE_LABELS: Dict[str, str] = {
    "purchase_receipt": "采购入库单",
    "sales_delivery": "销售出库单",
    "purchase_order": "采购订单",
    "sales_order": "销售订单",
    "Receivable": "应收单",
    "receivable": "应收单",
    "Payable": "应付单",
    "payable": "应付单",
    "receipt": "收款单",
    "payment": "付款单",
    "purchase_invoice": "采购发票",
    "PurchaseInvoice": "采购发票",
    "sales_invoice": "销售发票",
    "SalesInvoice": "销售发票",
    "sales_return": "销售退货单",
    "purchase_return": "采购退货单",
    "fa_depr_run_line": "折旧计提行",
    "fa_depr_adjustment": "折旧调整",
    "fa_disposal": "资产处置",
    "fa_asset": "固定资产",
    "fixed_asset": "固定资产",
    "manual_import": "手工导入",
    # 历史写入 PascalCase（采购发票等事件曾用 PurchaseOrder）
    "PurchaseOrder": "采购订单",
    "SalesOrder": "销售订单",
    "PurchaseReceipt": "采购入库单",
    "SalesDelivery": "销售出库单",
}

_EVENT_TYPE_LABELS: Dict[str, str] = {
    "PURCHASE_INVOICE_CREATED": "采购发票创建",
    "INVOICE_CREATED": "销售发票创建",
    "PAYABLE_CREATED": "应付单创建",
    "RECEIVABLE_CREATED": "应收单创建",
    "SETTLEMENT_RECEIVABLE_COMPLETED": "应收核销完成",
    "SETTLEMENT_PAYABLE_COMPLETED": "应付核销完成",
    "PURCHASE_ORDER_TO_PREPAYMENT": "采购订单转预付",
    "SALES_ORDER_TO_PREPAYMENT": "销售订单转预收",
    "PAYMENT_REFUND_CONFIRMED": "付款退款确认",
    "RECEIPT_REFUND_CONFIRMED": "收款退款确认",
    "FA_DEPRECIATION": "固定资产折旧",
    "FA_IMPAIRMENT": "固定资产减值",
    "FA_DISPOSAL": "固定资产处置",
    "FX_REVALUATION_PERIOD_END": "期末汇兑损益",
}


def _pascal_to_snake(value: str) -> str:
    """PurchaseOrder → purchase_order；已是 snake/小写则原样小写。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if "_" in text or text.islower():
        return text.lower()
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


class GlIntegrationReconcileService:
    async def month_end_checks(
        self,
        tenant_id: int,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        bals = await BalanceService().account_balance_sheet(
            tenant_id, year, month, include_unposted=False
        )

        def gl_ending(code: str) -> Decimal:
            total = Decimal("0")
            for r in bals:
                if r["account_code"] == code or str(r["account_code"]).startswith(code):
                    total += Decimal(str(r["ending_debit"])) - Decimal(str(r["ending_credit"]))
            return total

        # 应收账款业务余额（未核销）
        ar_rows = await Receivable.filter(tenant_id=tenant_id, deleted_at__isnull=True).all()
        ar_open = Decimal("0")
        for r in ar_rows:
            remaining = getattr(r, "remaining_amount", None)
            if remaining is None:
                amount = Decimal(str(getattr(r, "amount", 0) or 0))
                settled = Decimal(str(getattr(r, "settled_amount", 0) or 0))
                remaining = amount - settled
            ar_open += Decimal(str(remaining or 0))
        ar_gl = gl_ending("1122")
        checks.append(
            {
                "name": "应收账款 vs 1122",
                "business_balance": float(ar_open),
                "gl_balance": float(ar_gl),
                "diff": float(ar_open - ar_gl),
                "ok": abs(ar_open - ar_gl) < Decimal("0.01"),
            }
        )

        ap_rows = await Payable.filter(tenant_id=tenant_id, deleted_at__isnull=True).all()
        ap_open = Decimal("0")
        for r in ap_rows:
            remaining = getattr(r, "remaining_amount", None)
            if remaining is None:
                amount = Decimal(str(getattr(r, "amount", 0) or 0))
                settled = Decimal(str(getattr(r, "settled_amount", 0) or 0))
                remaining = amount - settled
            ap_open += Decimal(str(remaining or 0))
        # 应付科目贷方余额，业务正数余额对应 GL 贷方 → 用 credit-debit
        ap_gl_raw = Decimal("0")
        for r in bals:
            if r["account_code"] == "2202" or str(r["account_code"]).startswith("2202"):
                ap_gl_raw += Decimal(str(r["ending_credit"])) - Decimal(str(r["ending_debit"]))
        checks.append(
            {
                "name": "应付账款 vs 2202",
                "business_balance": float(ap_open),
                "gl_balance": float(ap_gl_raw),
                "diff": float(ap_open - ap_gl_raw),
                "ok": abs(ap_open - ap_gl_raw) < Decimal("0.01"),
            }
        )

        # 存货粗对：1403+1405 期末借方（仅提示，无数量账则仅金额）
        inv_gl = gl_ending("1403") + gl_ending("1405")
        checks.append(
            {
                "name": "存货科目余额（1403+1405）",
                "business_balance": None,
                "gl_balance": float(inv_gl),
                "diff": None,
                "ok": True,
                "note": "存货数量金额以仓储/成本模块为准，此处仅列示总账余额供核对",
            }
        )

        return {
            "period": f"{year:04d}-{month:02d}",
            "ok": all(c.get("ok") for c in checks if c.get("business_balance") is not None),
            "checks": checks,
        }

    @staticmethod
    def business_type_label(business_type: Optional[str]) -> str:
        key = str(business_type or "").strip()
        if not key:
            return "其他"
        return _BUSINESS_TYPE_LABELS.get(key, key)

    @staticmethod
    def source_doc_type_label(source_doc_type: Optional[str]) -> str:
        key = str(source_doc_type or "").strip()
        if not key:
            return "其他"
        if key in _SOURCE_DOC_TYPE_LABELS:
            return _SOURCE_DOC_TYPE_LABELS[key]
        lowered = key.lower()
        if lowered in _SOURCE_DOC_TYPE_LABELS:
            return _SOURCE_DOC_TYPE_LABELS[lowered]
        snake = _pascal_to_snake(key)
        if snake and snake in _SOURCE_DOC_TYPE_LABELS:
            return _SOURCE_DOC_TYPE_LABELS[snake]
        return key

    @staticmethod
    def event_type_label(event_type: Optional[str]) -> str:
        key = str(event_type or "").strip()
        if not key:
            return ""
        return _EVENT_TYPE_LABELS.get(key, key)

    async def _list_source_doc_type_options(
        self,
        tenant_id: int,
        *,
        business_type: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        from apps.kuaicaiwu.models.accounting_event import AccountingEvent

        q = AccountingEvent.filter(tenant_id=tenant_id).exclude(source_doc_type__isnull=True)
        if business_type:
            q = q.filter(business_type=business_type)
        raw = await q.distinct().values_list("source_doc_type", flat=True)
        types = sorted(
            {str(t).strip() for t in raw if t and str(t).strip()},
            key=lambda x: self.source_doc_type_label(x),
        )
        return [
            {"value": doc_type, "label": self.source_doc_type_label(doc_type)} for doc_type in types
        ]

    async def list_accounting_events_for_voucher(
        self,
        tenant_id: int,
        *,
        business_type: Optional[str] = None,
        source_doc_type: Optional[str] = None,
        voucher_status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """列出可生成凭证的会计事件，附带是否已生成凭证。"""
        from apps.kuaicaiwu.models.accounting_event import AccountingEvent
        from apps.kuaicaiwu.models.voucher import Voucher

        generated_event_ids = await Voucher.filter(
            tenant_id=tenant_id,
            source_event_id__isnull=False,
            deleted_at__isnull=True,
        ).exclude(status="cancelled").values_list("source_event_id", flat=True)
        generated_ids = sorted({int(i) for i in generated_event_ids if i})

        q = AccountingEvent.filter(tenant_id=tenant_id)
        if business_type:
            q = q.filter(business_type=business_type)
        if source_doc_type:
            q = q.filter(source_doc_type=source_doc_type)
        if voucher_status == "pending":
            if generated_ids:
                q = q.exclude(id__in=generated_ids)
        elif voucher_status == "generated":
            if generated_ids:
                q = q.filter(id__in=generated_ids)
            else:
                all_types_empty = await AccountingEvent.filter(tenant_id=tenant_id).distinct().values_list(
                    "business_type", flat=True
                )
                bt_empty = sorted(
                    {str(t).strip() for t in all_types_empty if t and str(t).strip()},
                    key=lambda x: GlIntegrationReconcileService.business_type_label(x),
                )
                source_doc_types_empty = await self._list_source_doc_type_options(
                    tenant_id, business_type=business_type
                )
                return {
                    "items": [],
                    "total": 0,
                    "business_types": bt_empty,
                    "source_doc_types": source_doc_types_empty,
                }

        all_types = await AccountingEvent.filter(tenant_id=tenant_id).distinct().values_list(
            "business_type", flat=True
        )
        business_types = sorted(
            {str(t).strip() for t in all_types if t and str(t).strip()},
            key=lambda x: GlIntegrationReconcileService.business_type_label(x),
        )
        source_doc_types = await self._list_source_doc_type_options(
            tenant_id, business_type=business_type
        )

        total = await q.count()
        events = await q.order_by("-event_date", "-id").offset(skip).limit(limit).all()
        event_ids = [int(ev.id) for ev in events]
        voucher_by_event: Dict[int, Voucher] = {}
        if event_ids:
            vouchers = await Voucher.filter(
                tenant_id=tenant_id,
                source_event_id__in=event_ids,
                deleted_at__isnull=True,
            ).exclude(status="cancelled").all()
            for voucher in vouchers:
                eid = int(voucher.source_event_id or 0)
                if eid and eid not in voucher_by_event:
                    voucher_by_event[eid] = voucher

        items: List[Dict[str, Any]] = []
        for ev in events:
            voucher = voucher_by_event.get(int(ev.id))
            has_voucher = voucher is not None
            items.append(
                {
                    "id": ev.id,
                    "event_code": ev.event_code,
                    "event_type": ev.event_type,
                    "event_type_label": self.event_type_label(ev.event_type),
                    "business_type": ev.business_type,
                    "business_type_label": self.business_type_label(ev.business_type),
                    "source_doc_type": ev.source_doc_type,
                    "source_doc_type_label": self.source_doc_type_label(ev.source_doc_type),
                    "source_doc_id": ev.source_doc_id,
                    "source_doc_code": ev.source_doc_code,
                    "target_doc_type": ev.target_doc_type,
                    "target_doc_id": ev.target_doc_id,
                    "target_doc_code": ev.target_doc_code,
                    "amount": float(ev.amount or 0),
                    "currency": ev.currency,
                    "event_date": ev.event_date.isoformat() if ev.event_date else None,
                    "notes": ev.notes
                    or self.event_type_label(ev.event_type)
                    or None,
                    "has_voucher": has_voucher,
                    "voucher_id": voucher.id if voucher else None,
                    "voucher_code": voucher.voucher_code if voucher else None,
                    "voucher_status": voucher.status if voucher else None,
                }
            )

        return {
            "items": items,
            "total": total,
            "business_types": business_types,
            "source_doc_types": source_doc_types,
        }

    async def generate_vouchers_from_pending_events(
        self,
        tenant_id: int,
        operator_id: int,
        *,
        event_ids: Optional[List[int]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        from apps.kuaicaiwu.models.accounting_event import AccountingEvent
        from apps.kuaicaiwu.models.voucher import Voucher
        from apps.kuaicaiwu.services.posting_service import PostingService

        if event_ids:
            ids = sorted({int(i) for i in event_ids if i})
            events = await AccountingEvent.filter(tenant_id=tenant_id, id__in=ids).order_by("-id").all()
        else:
            events = await AccountingEvent.filter(tenant_id=tenant_id).order_by("-id").limit(limit * 3).all()

        posting = PostingService()
        created = []
        skipped = 0
        errors: List[str] = []
        for ev in events:
            exists = await Voucher.filter(
                tenant_id=tenant_id,
                source_event_id=ev.id,
                deleted_at__isnull=True,
            ).exclude(status="cancelled").exists()
            if exists:
                skipped += 1
                continue
            try:
                v = await posting.create_draft_voucher_from_event(tenant_id, ev.id, operator_id)
                created.append(posting.voucher_to_dict(v))
                if not event_ids and len(created) >= limit:
                    break
            except Exception as exc:
                skipped += 1
                errors.append(f"{ev.event_code}: {exc}")
                continue
        return {
            "created_count": len(created),
            "skipped": skipped,
            "vouchers": created,
            "errors": errors[:20],
        }

    async def obsolete_vouchers_from_events(
        self,
        tenant_id: int,
        *,
        event_ids: List[int],
    ) -> Dict[str, Any]:
        """作废由业务事件生成的未记账凭证（制单/已审核）。"""
        from apps.kuaicaiwu.models.voucher import Voucher
        from apps.kuaicaiwu.services.posting_service import PostingService
        from infra.exceptions.exceptions import ValidationError

        ids = sorted({int(i) for i in event_ids if i})
        if not ids:
            raise ValidationError("请选择要作废的会计事件")

        vouchers = await Voucher.filter(
            tenant_id=tenant_id,
            source_event_id__in=ids,
            deleted_at__isnull=True,
        ).exclude(status="cancelled").all()
        if not vouchers:
            raise ValidationError("所选事件没有可作废的凭证")

        posting = PostingService()
        obsoleted = 0
        skipped = 0
        for voucher in vouchers:
            if voucher.status == "posted":
                skipped += 1
                continue
            if voucher.status == "reviewed":
                await posting.unreview_voucher(tenant_id, voucher.id)
            elif voucher.status != "draft":
                skipped += 1
                continue
            await posting.cancel_voucher(tenant_id, voucher.id)
            obsoleted += 1
        return {"obsoleted_count": obsoleted, "skipped": skipped}
