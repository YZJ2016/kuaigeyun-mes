"""
采购发票加载门控：候选列表、预览、已开票金额汇总。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from tortoise.queryset import Q

from apps.kuaizhizao.utils.pull_query_date_filter import apply_pull_query_document_date_filter

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
from apps.kuaicaiwu.services.finance_tax import money_exceeds_max, money_to_json_float
from apps.kuaicaiwu.services.purchase_invoice_amounts import (
    purchase_invoice_occupancy_amount,
)
from apps.kuaizhizao.models.document_relation import DocumentRelation
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError


async def resolve_purchase_invoice_pull_ledger_posting_mode(
    tenant_id: int,
    *,
    partner_statement_ids: Optional[Sequence[int]] = None,
    receipt: Any = None,
    purchase_order: Any = None,
    payable: Any = None,
) -> str:
    """拉单预览立账方式：对账单优先，否则按源单应付确认策略映射。"""
    from apps.kuaicaiwu.models.partner_statement import PartnerStatement
    from apps.kuaizhizao.services.document_recognition import (
        ledger_posting_mode_from_payable_recognition,
        payable_recognition_from_doc,
    )

    if partner_statement_ids:
        stmt_ids = [int(s) for s in partner_statement_ids if int(s) > 0]
        if stmt_ids:
            stmts = await PartnerStatement.filter(
                tenant_id=tenant_id, id__in=stmt_ids, deleted_at__isnull=True
            ).all()
            if stmts:
                modes = {
                    str(getattr(stmt, "ledger_posting_mode", "") or "").strip()
                    for stmt in stmts
                }
                return "by_invoice" if "by_invoice" in modes else "immediate"
    if receipt is not None:
        return ledger_posting_mode_from_payable_recognition(payable_recognition_from_doc(receipt))
    if purchase_order is not None:
        return ledger_posting_mode_from_payable_recognition(
            payable_recognition_from_doc(purchase_order)
        )
    if payable is not None:
        return "immediate"
    return "immediate"


class PurchaseInvoicePullService(AppBaseService[PurchaseInvoice]):
    """采购发票（进项）加载门控服务"""

    _EXCLUDED_INVOICE_STATUSES = frozenset({"已作废", "已红冲"})

    @staticmethod
    def _purchase_order_settlement_total(order: Any) -> Decimal:
        from apps.kuaicaiwu.services.purchase_settlement import (
            purchase_order_settlement_gross,
        )

        return purchase_order_settlement_gross(order)

    _PO_ELIGIBLE_STATUSES = frozenset(
        {
            "AUDITED",
            "CONFIRMED",
            "IN_PROGRESS",
            "COMPLETED",
            "已审核",
            "已确认",
            "进行中",
            "已完成",
            "部分入库",
            "已入库",
            "已通过",
        }
    )

    _PR_ELIGIBLE_STATUSES = frozenset(
        {"已入库", "已完成", "部分入库", "COMPLETED", "completed"}
    )

    _PAYABLE_ELIGIBLE_REVIEW = frozenset({"已审核"})

    _PO_LEGACY_SOURCE_TYPES = frozenset({"purchase_order", "采购订单", "PurchaseOrder"})
    _PR_LEGACY_SOURCE_TYPES = frozenset({"purchase_receipt", "采购入库", "PurchaseReceipt"})

    def _derive_pull_capability(
        self,
        *,
        source_allowed: bool,
        preview_items: List[Dict[str, Any]],
        not_allowed_reason: str,
        no_lines_reason: str,
        already_pulled_reason: str,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        from apps.kuaicaiwu.constants.finance_source_types import (
            is_partner_statement_sourced_payable,
            is_purchase_return_offset_payable,
        )

        if is_purchase_return_offset_payable(source_type) or str(status or "").strip() == "已冲减":
            return False, "purchase_invoice.pull_from_payable.purchase_return_offset"
        if is_partner_statement_sourced_payable(source_type):
            return False, "purchase_invoice.pull_from_payable.partner_statement_source"
        if not source_allowed:
            return False, not_allowed_reason
        if not preview_items:
            return False, no_lines_reason
        pushable = any(float(row.get("max_push_quantity") or 0) > 0 for row in preview_items)
        if not pushable:
            return False, already_pulled_reason
        return True, None

    async def _sum_pushed_totals_by_source(
        self,
        tenant_id: int,
        source_type: str,
        source_ids: List[int],
        code_by_id: Dict[int, str],
    ) -> Dict[int, Decimal]:
        """按 DocumentRelation 归因已开票额；多源合并读 allocated_amount，缺省按源单总额比例分摊。"""
        from collections import defaultdict

        from apps.kuaicaiwu.services.invoice_source_allocation import (
            accumulate_attributed,
            attribute_invoice_total_to_sources,
            parse_relation_allocated_amount,
        )

        result: Dict[int, Decimal] = {sid: Decimal("0") for sid in source_ids}
        if not source_ids:
            return result

        id_set = {int(x) for x in source_ids}
        counted_invoice_ids: set[int] = set()

        seed_relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id__in=source_ids,
            target_type="purchase_invoice",
        ).all()
        invoice_ids = sorted({int(r.target_id) for r in seed_relations if r.target_id})

        by_invoice: Dict[int, List[DocumentRelation]] = defaultdict(list)
        all_source_ids: set[int] = set()
        if invoice_ids:
            full_relations = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type=source_type,
                target_type="purchase_invoice",
                target_id__in=invoice_ids,
            ).all()
            for rel in full_relations:
                if not rel.target_id or not rel.source_id:
                    continue
                by_invoice[int(rel.target_id)].append(rel)
                all_source_ids.add(int(rel.source_id))

        inv_map: Dict[int, PurchaseInvoice] = {}
        if invoice_ids:
            linked = await PurchaseInvoice.filter(
                tenant_id=tenant_id,
                id__in=invoice_ids,
                deleted_at__isnull=True,
            ).exclude(status__in=list(self._EXCLUDED_INVOICE_STATUSES))
            inv_map = {int(inv.id): inv for inv in linked}

        doc_id_list = sorted(all_source_ids | id_set)
        doc_totals = await self._document_settlement_totals_for_source(
            tenant_id, source_type, doc_id_list
        )

        for iid, rels in by_invoice.items():
            inv = inv_map.get(iid)
            if not inv:
                continue
            counted_invoice_ids.add(iid)
            entries = [
                (int(r.source_id), parse_relation_allocated_amount(getattr(r, "notes", None)))
                for r in rels
            ]
            if not entries:
                continue
            attributed = attribute_invoice_total_to_sources(
                purchase_invoice_occupancy_amount(inv),
                entries,
                doc_totals,
            )
            accumulate_attributed(
                result,
                ((sid, amt) for sid, amt in attributed.items() if sid in id_set),
            )

        if source_type == "purchase_order":
            orphans = await PurchaseInvoice.filter(
                tenant_id=tenant_id,
                purchase_order_id__in=source_ids,
                deleted_at__isnull=True,
            ).exclude(status__in=list(self._EXCLUDED_INVOICE_STATUSES))
            orphan_pending = [o for o in orphans if int(o.id) not in counted_invoice_ids]
            orphan_ids = [int(o.id) for o in orphan_pending]
            related_target_ids: set[int] = set()
            if orphan_ids:
                rel_rows = await DocumentRelation.filter(
                    tenant_id=tenant_id,
                    target_type="purchase_invoice",
                    target_id__in=orphan_ids,
                ).all()
                related_target_ids = {int(r.target_id) for r in rel_rows if r.target_id}
            for inv in orphan_pending:
                if int(inv.id) in related_target_ids:
                    continue
                if inv.purchase_order_id is None:
                    continue
                sid = int(inv.purchase_order_id)
                if sid in result:
                    result[sid] = (
                        result.get(sid, Decimal("0")) + purchase_invoice_occupancy_amount(inv)
                    )
        elif source_type == "purchase_receipt":
            # 入库来源已开票金额仅认 DocumentRelation；不再全表扫 notes。
            _ = code_by_id
        return result

    async def _document_settlement_totals_for_source(
        self,
        tenant_id: int,
        source_type: str,
        source_ids: List[int],
    ) -> Dict[int, Decimal]:
        if not source_ids:
            return {}
        if source_type == "purchase_order":
            from apps.kuaizhizao.models.purchase_order import PurchaseOrder

            orders = await PurchaseOrder.filter(
                tenant_id=tenant_id, id__in=source_ids, deleted_at__isnull=True
            ).all()
            return {
                int(o.id): self._purchase_order_settlement_total(o) for o in orders
            }
        if source_type == "purchase_receipt":
            from apps.kuaicaiwu.services.purchase_settlement import (
                batch_purchase_receipt_settlement_gross,
            )
            from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

            receipts = await PurchaseReceipt.filter(
                tenant_id=tenant_id, id__in=source_ids, deleted_at__isnull=True
            ).all()
            gross_map = await batch_purchase_receipt_settlement_gross(tenant_id, receipts)
            return {
                int(receipt.id): gross_map.get(int(receipt.id), Decimal("0"))
                for receipt in receipts
            }
        if source_type == "outsource_order_receipt":
            out: Dict[int, Decimal] = {}
            for sid in source_ids:
                out[int(sid)] = await self.outsource_order_receipt_settlement_gross(
                    tenant_id, int(sid)
                )
            return out
        return {}

    async def outsource_order_receipt_settlement_gross(
        self, tenant_id: int, batch_id: int
    ) -> Decimal:
        from apps.kuaizhizao.models.outsource_order import OutsourceOrder
        from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt
        from apps.kuaizhizao.utils.document_amount_write import line_total_qty_unit_price

        batch = await OutsourceOrderReceipt.get_or_none(
            tenant_id=tenant_id,
            id=int(batch_id),
            deleted_at__isnull=True,
        )
        if not batch:
            return Decimal("0")
        order = await OutsourceOrder.get_or_none(
            tenant_id=tenant_id,
            id=int(batch.outsource_order_id),
            deleted_at__isnull=True,
        )
        if not order:
            return Decimal("0")
        unit_price = Decimal(str(order.unit_price or 0))
        qual = Decimal(str(batch.qualified_quantity or 0))
        return line_total_qty_unit_price(qual, unit_price)

    async def _build_preview_items_for_outsource_order_receipt(
        self,
        tenant_id: int,
        batch_id: int,
        *,
        source_code: str,
    ) -> List[Dict[str, Any]]:
        from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt

        batch = await OutsourceOrderReceipt.get_or_none(
            tenant_id=tenant_id, id=int(batch_id), deleted_at__isnull=True
        )
        if batch and bool(getattr(batch, "invoice_receipt_complete", False)):
            return []
        gross = await self.outsource_order_receipt_settlement_gross(tenant_id, int(batch_id))
        pushed_map = await self._sum_pushed_totals_by_source(
            tenant_id,
            "outsource_order_receipt",
            [int(batch_id)],
            {int(batch_id): source_code},
        )
        pushed = pushed_map.get(int(batch_id), Decimal("0"))
        remaining = max(Decimal("0"), gross - pushed)
        if remaining <= 0:
            return []
        return [
            {
                "item_id": int(batch_id),
                "source_code": source_code,
                "max_push_quantity": float(remaining),
            }
        ]

    @staticmethod
    def _fifo_allocate_amount_by_preview_items(
        source_ids: Sequence[int],
        preview_items: Sequence[Dict[str, Any]],
        total_amount: Decimal,
    ) -> Dict[int, Decimal]:
        """按源单顺序与可开票余量，把发票价税合计拆到各源单。"""
        caps: Dict[int, Decimal] = {}
        for item in preview_items:
            iid = int(item.get("item_id") or 0)
            if iid <= 0:
                continue
            caps[iid] = caps.get(iid, Decimal("0")) + Decimal(
                str(item.get("max_push_quantity") or 0)
            )
        remaining = Decimal(str(total_amount or 0))
        if remaining < 0:
            remaining = Decimal("0")
        allocated: Dict[int, Decimal] = {}
        for sid in source_ids:
            sid_i = int(sid)
            take = min(caps.get(sid_i, Decimal("0")), remaining)
            if take < 0:
                take = Decimal("0")
            allocated[sid_i] = take
            remaining -= take
        if remaining > 0 and source_ids:
            last = int(source_ids[-1])
            allocated[last] = allocated.get(last, Decimal("0")) + remaining
        return allocated

    async def _sum_pushed_totals_by_payable(
        self,
        tenant_id: int,
        payable_ids: List[int],
        code_by_id: Dict[int, str],
    ) -> Dict[int, Decimal]:
        from collections import defaultdict

        from apps.kuaicaiwu.services.invoice_source_allocation import (
            accumulate_attributed,
            attribute_invoice_total_to_sources,
            parse_relation_allocated_amount,
        )

        result: Dict[int, Decimal] = {pid: Decimal("0") for pid in payable_ids}
        if not payable_ids:
            return result

        counted_invoice_ids: set[int] = set()
        id_set = set(int(x) for x in payable_ids)

        seed_relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payable",
            source_id__in=payable_ids,
            target_type="purchase_invoice",
        ).all()
        invoice_ids = sorted(
            {int(r.target_id) for r in seed_relations if r.target_id}
        )

        by_invoice: Dict[int, List[DocumentRelation]] = defaultdict(list)
        all_source_ids: set[int] = set()
        if invoice_ids:
            full_relations = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type="payable",
                target_type="purchase_invoice",
                target_id__in=invoice_ids,
            ).all()
            for rel in full_relations:
                if not rel.target_id or not rel.source_id:
                    continue
                by_invoice[int(rel.target_id)].append(rel)
                all_source_ids.add(int(rel.source_id))

        inv_map: Dict[int, PurchaseInvoice] = {}
        if invoice_ids:
            linked = await PurchaseInvoice.filter(
                tenant_id=tenant_id,
                id__in=invoice_ids,
                deleted_at__isnull=True,
            ).exclude(status__in=list(self._EXCLUDED_INVOICE_STATUSES))
            inv_map = {int(inv.id): inv for inv in linked}

        doc_id_list = sorted(all_source_ids | id_set)
        doc_totals: Dict[int, Decimal] = {
            int(row["id"]): Decimal(str(row.get("total_amount") or 0))
            for row in await Payable.filter(
                tenant_id=tenant_id, id__in=doc_id_list
            ).values("id", "total_amount")
        } if doc_id_list else {}

        for iid, rels in by_invoice.items():
            inv = inv_map.get(iid)
            if not inv:
                continue
            counted_invoice_ids.add(iid)
            entries = [
                (int(r.source_id), parse_relation_allocated_amount(getattr(r, "notes", None)))
                for r in rels
            ]
            if not entries:
                continue
            attributed = attribute_invoice_total_to_sources(
                purchase_invoice_occupancy_amount(inv),
                entries,
                doc_totals,
            )
            accumulate_attributed(
                result,
                ((sid, amt) for sid, amt in attributed.items() if sid in id_set),
            )

        direct_rows = await PurchaseInvoice.filter(
            tenant_id=tenant_id,
            payable_id__in=payable_ids,
            deleted_at__isnull=True,
        ).exclude(status__in=list(self._EXCLUDED_INVOICE_STATUSES))
        pending_direct = [
            inv for inv in direct_rows if int(inv.id) not in counted_invoice_ids
        ]
        if pending_direct:
            direct_ids = [int(inv.id) for inv in pending_direct]
            extra_rels = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type="payable",
                target_type="purchase_invoice",
                target_id__in=direct_ids,
            ).all()
            direct_by_invoice: Dict[int, List[DocumentRelation]] = defaultdict(list)
            extra_source_ids: set[int] = set()
            for rel in extra_rels:
                if not rel.target_id or not rel.source_id:
                    continue
                direct_by_invoice[int(rel.target_id)].append(rel)
                extra_source_ids.add(int(rel.source_id))
            extra_doc_totals: Dict[int, Decimal] = {
                int(row["id"]): Decimal(str(row.get("total_amount") or 0))
                for row in await Payable.filter(
                    tenant_id=tenant_id, id__in=sorted(extra_source_ids)
                ).values("id", "total_amount")
            } if extra_source_ids else {}
            for inv in pending_direct:
                iid = int(inv.id)
                rels = direct_by_invoice.get(iid) or []
                if rels:
                    entries = [
                        (
                            int(r.source_id),
                            parse_relation_allocated_amount(getattr(r, "notes", None)),
                        )
                        for r in rels
                    ]
                    attributed = attribute_invoice_total_to_sources(
                        purchase_invoice_occupancy_amount(inv),
                        entries,
                        extra_doc_totals,
                    )
                    accumulate_attributed(
                        result,
                        ((sid, amt) for sid, amt in attributed.items() if sid in id_set),
                    )
                    counted_invoice_ids.add(iid)
                    continue
                pid = int(inv.payable_id)
                if pid in result:
                    result[pid] = (
                        result.get(pid, Decimal("0")) + purchase_invoice_occupancy_amount(inv)
                    )
                    counted_invoice_ids.add(iid)

        # 应付已开票金额仅认 payable_id + DocumentRelation；不再全表扫 notes。
        _ = code_by_id
        return result

    def _payable_source_allowed(self, payable: Any) -> bool:
        from apps.kuaicaiwu.constants.finance_source_types import (
            is_partner_statement_sourced_payable,
            is_purchase_return_offset_payable,
        )

        source_type = (
            payable.get("source_type")
            if isinstance(payable, dict)
            else getattr(payable, "source_type", None)
        )
        status = str(
            (payable.get("status") if isinstance(payable, dict) else getattr(payable, "status", ""))
            or ""
        ).strip()
        if is_purchase_return_offset_payable(source_type) or status == "已冲减":
            return False
        if is_partner_statement_sourced_payable(source_type):
            return False
        review = str(
            (payable.get("review_status") if isinstance(payable, dict) else getattr(payable, "review_status", ""))
            or ""
        ).strip()
        total_raw = (
            payable.get("total_amount")
            if isinstance(payable, dict)
            else getattr(payable, "total_amount", 0)
        )
        total = Decimal(str(total_raw or 0))
        return review in self._PAYABLE_ELIGIBLE_REVIEW and total > 0

    async def _resolve_purchase_orders_from_payables(
        self,
        tenant_id: int,
        payables: List[Any],
    ) -> Dict[int, tuple[Optional[int], Optional[str]]]:
        """批量解析应付单关联采购订单，避免列表路径逐行查入库单。"""
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        result: Dict[int, tuple[Optional[int], Optional[str]]] = {}
        receipt_to_payable_ids: Dict[int, List[int]] = {}

        for payable in payables:
            pid = int(payable.id)
            source_type = str(getattr(payable, "source_type", "") or "").strip()
            source_id = getattr(payable, "source_id", None)
            source_code = str(getattr(payable, "source_code", "") or "").strip() or None
            if source_type in self._PO_LEGACY_SOURCE_TYPES and source_id:
                result[pid] = (int(source_id), source_code)
                continue
            if source_type in self._PR_LEGACY_SOURCE_TYPES and source_id:
                receipt_to_payable_ids.setdefault(int(source_id), []).append(pid)
                result[pid] = (None, None)
                continue
            result[pid] = (None, None)

        receipt_ids = list(receipt_to_payable_ids.keys())
        if receipt_ids:
            receipts = await PurchaseReceipt.filter(
                tenant_id=tenant_id,
                id__in=receipt_ids,
                deleted_at__isnull=True,
            ).values("id", "purchase_order_id", "purchase_order_code")
            for row in receipts:
                rid = int(row["id"])
                po_id = row.get("purchase_order_id")
                if not po_id:
                    continue
                resolved = (int(po_id), row.get("purchase_order_code"))
                for pid in receipt_to_payable_ids.get(rid, []):
                    result[pid] = resolved
        return result

    async def _resolve_purchase_order_from_payable(
        self,
        tenant_id: int,
        payable: Any,
    ) -> tuple[Optional[int], Optional[str]]:
        mapped = await self._resolve_purchase_orders_from_payables(tenant_id, [payable])
        return mapped.get(int(payable.id), (None, None))

    def _build_preview_item(
        self,
        *,
        source_id: int,
        source_code: str,
        supplier_name: str,
        quantity: Decimal,
        pushed: Decimal,
    ) -> Dict[str, Any]:
        qty = money_to_json_float(quantity)
        pushed_f = money_to_json_float(pushed)
        max_push = money_to_json_float(max(Decimal("0"), quantity - pushed))
        return {
            "item_id": int(source_id),
            "source_code": source_code,
            "supplier_name": supplier_name,
            "quantity": qty,
            "pushed_quantity": pushed_f,
            "max_push_quantity": max_push,
        }

    async def _build_preview_items_for_purchase_order(
        self,
        tenant_id: int,
        order: Any,
        *,
        pushed: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        oid = int(order.id)
        code = str(order.order_code or oid)
        total = self._purchase_order_settlement_total(order)
        if total <= 0:
            return []
        if pushed is None:
            pushed_map = await self._sum_pushed_totals_by_source(
                tenant_id, "purchase_order", [oid], {oid: code}
            )
            pushed = pushed_map.get(oid, Decimal("0"))
        return [
            self._build_preview_item(
                source_id=oid,
                source_code=code,
                supplier_name=str(getattr(order, "supplier_name", "") or ""),
                quantity=total,
                pushed=pushed,
            )
        ]

    async def _build_preview_items_for_purchase_receipt(
        self,
        tenant_id: int,
        receipt: Any,
        *,
        pushed: Optional[Decimal] = None,
        settlement_gross: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        rid = int(receipt.id)
        code = str(receipt.receipt_code or rid)
        if settlement_gross is not None:
            total = settlement_gross
        else:
            from apps.kuaicaiwu.services.purchase_settlement import (
                purchase_receipt_settlement_gross_async,
            )

            total = await purchase_receipt_settlement_gross_async(tenant_id, receipt)
        if total <= 0:
            return []
        if pushed is None:
            pushed_map = await self._sum_pushed_totals_by_source(
                tenant_id, "purchase_receipt", [rid], {rid: code}
            )
            pushed = pushed_map.get(rid, Decimal("0"))
        return [
            self._build_preview_item(
                source_id=rid,
                source_code=code,
                supplier_name=str(getattr(receipt, "supplier_name", "") or ""),
                quantity=total,
                pushed=pushed,
            )
        ]

    async def _build_preview_items_for_payable(
        self,
        tenant_id: int,
        payable: Any,
        *,
        pushed: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        pid = int(payable.id)
        code = str(payable.payable_code or pid)
        total = Decimal(str(payable.total_amount or 0))
        if total <= 0:
            return []
        if pushed is None:
            pushed_map = await self._sum_pushed_totals_by_payable(
                tenant_id, [pid], {pid: code}
            )
            pushed = pushed_map.get(pid, Decimal("0"))
        return [
            self._build_preview_item(
                source_id=pid,
                source_code=code,
                supplier_name=str(getattr(payable, "supplier_name", "") or ""),
                quantity=total,
                pushed=pushed,
            )
        ]

    async def preview_pull_from_purchase_order(
        self,
        tenant_id: int,
        order_id: int,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        order = await PurchaseOrder.get_or_none(
            tenant_id=tenant_id, id=order_id, deleted_at__isnull=True
        )
        if not order:
            raise NotFoundError(f"采购订单不存在: {order_id}")

        status = str(getattr(order, "status", "") or "").strip()
        settlement_total = self._purchase_order_settlement_total(order)
        source_allowed = status in self._PO_ELIGIBLE_STATUSES and settlement_total > 0
        preview_items = await self._build_preview_items_for_purchase_order(tenant_id, order)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="purchase_invoice.pull_from_purchase_order.not_allowed",
            no_lines_reason="purchase_invoice.pull_from_purchase_order.no_lines",
            already_pulled_reason="purchase_invoice.pull_from_purchase_order.already_pulled",
        )
        code = str(order.order_code or order_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        pushed_map = await self._sum_pushed_totals_by_source(
            tenant_id, "purchase_order", [int(order_id)], {int(order_id): code}
        )
        pushed_total = pushed_map.get(int(order_id), Decimal("0"))
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            build_purchase_order_invoice_detail_lines,
        )

        detail_lines = await build_purchase_order_invoice_detail_lines(
            tenant_id,
            int(order_id),
            header_pushed=pushed_total,
        )
        ledger_mode = await resolve_purchase_invoice_pull_ledger_posting_mode(
            tenant_id, purchase_order=order
        )
        return {
            "target_type": "purchase_invoice",
            "source_type": "purchase_order",
            "source_id": order_id,
            "source_code": code,
            "summary": (
                f"将从采购订单 {code} 创建采购发票（可开票 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"采购订单 {code} 当前不可加载采购发票"
            ),
            "items": preview_items,
            "detail_lines": detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": "价税合计不可超过可开票金额；删除未审核采购发票后，可开票金额自动回退。",
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier_name,
            "purchase_order_id": order.id,
            "purchase_order_code": code,
            "max_push_total": pushable,
            "ledger_posting_mode": ledger_mode,
        }

    async def preview_pull_from_purchase_orders(
        self,
        tenant_id: int,
        order_ids: Sequence[int],
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(order_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_purchase_order(tenant_id, ids[0])

        merged_items: List[Dict[str, Any]] = []
        merged_detail_lines: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        codes: List[str] = []
        purchase_order_id: Optional[int] = None
        purchase_order_code: Optional[str] = None
        fragment_modes: List[str] = []

        for oid in ids:
            fragment = await self.preview_pull_from_purchase_order(tenant_id, oid)
            fragment_modes.append(str(fragment.get("ledger_posting_mode") or "immediate"))
            if supplier_id is None:
                supplier_id = int(fragment.get("supplier_id") or 0)
                supplier_name = str(fragment.get("supplier_name") or "")
            elif int(fragment.get("supplier_id") or 0) != int(supplier_id or 0):
                raise BusinessLogicError("多笔一起加载须为同一供应商")

            codes.append(str(fragment.get("source_code") or oid))
            if fragment.get("has_blocking_issues"):
                reason = str(fragment.get("blocking_reason") or "")
                if reason:
                    blocking_reasons.append(reason)
            merged_items.extend(fragment.get("items") or [])
            for row in fragment.get("detail_lines") or []:
                line = dict(row)
                line["purchase_order_id"] = oid
                merged_detail_lines.append(line)
            if purchase_order_id is None and fragment.get("purchase_order_id"):
                purchase_order_id = int(fragment["purchase_order_id"])
                purchase_order_code = str(fragment.get("purchase_order_code") or "") or None

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        return {
            "target_type": "purchase_invoice",
            "source_type": "purchase_order",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 张采购订单创建采购发票（可开票合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选采购订单当前不可一起加载采购发票"
            ),
            "items": merged_items,
            "detail_lines": merged_detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": "价税合计不可超过可开票合计；多单时按订单顺序依次占用可开票余量。",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "purchase_order_id": purchase_order_id,
            "purchase_order_code": purchase_order_code,
            "max_push_total": float(max_push_total),
            "ledger_posting_mode": "by_invoice" if "by_invoice" in fragment_modes else "immediate",
        }

    async def preview_pull_from_purchase_receipt(
        self,
        tenant_id: int,
        receipt_id: int,
        *,
        partner_statement_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"采购入库单不存在: {receipt_id}")

        status = str(getattr(receipt, "status", "") or "").strip()
        from apps.kuaicaiwu.services.purchase_settlement import (
            purchase_receipt_settlement_gross_async,
        )

        settlement_total = await purchase_receipt_settlement_gross_async(tenant_id, receipt)
        from apps.kuaizhizao.services.document_recognition import (
            purchase_receipt_direct_invoice_pull_block_reason,
        )

        ledger_block = purchase_receipt_direct_invoice_pull_block_reason(receipt)
        if ledger_block and partner_statement_ids:
            from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
                receipts_covered_by_audited_partner_statements,
            )

            if await receipts_covered_by_audited_partner_statements(
                tenant_id, partner_statement_ids, [receipt_id]
            ):
                ledger_block = None
        source_allowed = (
            status in self._PR_ELIGIBLE_STATUSES and settlement_total > 0 and ledger_block is None
        )
        preview_items = await self._build_preview_items_for_purchase_receipt(tenant_id, receipt)
        if ledger_block:
            allowed, reason = False, ledger_block
        else:
            allowed, reason = self._derive_pull_capability(
                source_allowed=source_allowed,
                preview_items=preview_items,
                not_allowed_reason="purchase_invoice.pull_from_purchase_receipt.not_allowed",
                no_lines_reason="purchase_invoice.pull_from_purchase_receipt.no_lines",
                already_pulled_reason="purchase_invoice.pull_from_purchase_receipt.already_pulled",
            )
        code = str(receipt.receipt_code or receipt_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            build_purchase_receipt_finance_detail_lines,
        )

        detail_lines = await build_purchase_receipt_finance_detail_lines(
            tenant_id, receipt_id, "invoice"
        )
        preview = {
            "target_type": "purchase_invoice",
            "source_type": "purchase_receipt",
            "source_id": receipt_id,
            "source_code": code,
            "summary": (
                f"将从采购入库单 {code} 创建采购发票（可开票 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"采购入库单 {code} 当前不可加载采购发票"
            ),
            "items": preview_items,
            "detail_lines": detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": "价税合计须与所选入库行合计一致；未勾选行时按入库行顺序自动分摊。",
            "supplier_id": receipt.supplier_id,
            "supplier_name": receipt.supplier_name,
            "purchase_order_id": receipt.purchase_order_id,
            "purchase_order_code": receipt.purchase_order_code,
            "max_push_total": pushable,
            "ledger_posting_mode": await resolve_purchase_invoice_pull_ledger_posting_mode(
                tenant_id,
                partner_statement_ids=partner_statement_ids,
                receipt=receipt,
            ),
        }
        if partner_statement_ids:
            from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
                apply_invoice_budget_to_pull_preview,
                resolve_budget_for_statements,
            )

            budget = await resolve_budget_for_statements(
                tenant_id,
                partner_statement_ids,
                side="purchase",
                restrict_source_ids=[receipt_id],
            )
            apply_invoice_budget_to_pull_preview(preview, budget)
            cap_f = float(budget.invoiceable)
            if preview_items and allowed and not ledger_block and cap_f > 0:
                preview["has_blocking_issues"] = False
                preview["summary"] = (
                    f"将从对账单关联入库 {code} 创建采购发票（可开票 ¥{cap_f:,.2f}）"
                )
            elif cap_f <= 0:
                preview["has_blocking_issues"] = True
        from apps.kuaicaiwu.services.partner_statement_line_invoice_map import (
            maybe_attach_partner_statement_line_ids,
        )

        await maybe_attach_partner_statement_line_ids(
            tenant_id, partner_statement_ids, preview
        )
        return preview

    @staticmethod
    def _normalize_source_ids(source_ids: Sequence[int]) -> List[int]:
        ordered: List[int] = []
        seen: set[int] = set()
        for raw in source_ids:
            sid = int(raw)
            if sid <= 0 or sid in seen:
                continue
            seen.add(sid)
            ordered.append(sid)
        if not ordered:
            raise BusinessLogicError("请至少选择一张源单")
        return ordered

    async def preview_pull_from_purchase_receipts(
        self,
        tenant_id: int,
        receipt_ids: Sequence[int],
        *,
        partner_statement_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(receipt_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_purchase_receipt(
                tenant_id,
                ids[0],
                partner_statement_ids=partner_statement_ids,
            )

        merged_items: List[Dict[str, Any]] = []
        merged_detail_lines: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        codes: List[str] = []
        purchase_order_id: Optional[int] = None
        purchase_order_code: Optional[str] = None
        fragment_modes: List[str] = []

        for rid in ids:
            fragment = await self.preview_pull_from_purchase_receipt(
                tenant_id,
                rid,
                partner_statement_ids=partner_statement_ids,
            )
            fragment_modes.append(str(fragment.get("ledger_posting_mode") or "immediate"))
            if supplier_id is None:
                supplier_id = int(fragment.get("supplier_id") or 0)
                supplier_name = str(fragment.get("supplier_name") or "")
            elif int(fragment.get("supplier_id") or 0) != int(supplier_id or 0):
                raise BusinessLogicError("多笔一起加载须为同一供应商")

            codes.append(str(fragment.get("source_code") or rid))
            if fragment.get("has_blocking_issues"):
                reason = str(fragment.get("blocking_reason") or "")
                if reason:
                    blocking_reasons.append(reason)
            merged_items.extend(fragment.get("items") or [])
            for row in fragment.get("detail_lines") or []:
                line = dict(row)
                line["purchase_receipt_id"] = rid
                merged_detail_lines.append(line)
            if purchase_order_id is None and fragment.get("purchase_order_id"):
                purchase_order_id = int(fragment["purchase_order_id"])
                purchase_order_code = str(fragment.get("purchase_order_code") or "") or None
            elif (
                purchase_order_id is not None
                and fragment.get("purchase_order_id")
                and int(fragment["purchase_order_id"]) != int(purchase_order_id)
            ):
                # 同供应商多入库可跨多张采购订单；表头仅保留首张订单回显
                pass

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        preview = {
            "target_type": "purchase_invoice",
            "source_type": "purchase_receipt",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 张采购入库单创建采购发票（可开票合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选入库单当前不可一起加载采购发票"
            ),
            "items": merged_items,
            "detail_lines": merged_detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": "价税合计须与所选入库行合计一致；未勾选行时按各入库单可开票余量依次占用。",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "purchase_order_id": purchase_order_id,
            "purchase_order_code": purchase_order_code,
            "max_push_total": float(max_push_total),
            "ledger_posting_mode": "by_invoice" if "by_invoice" in fragment_modes else "immediate",
        }
        if partner_statement_ids:
            from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
                apply_invoice_budget_to_pull_preview,
                resolve_budget_for_statements,
            )

            budget = await resolve_budget_for_statements(
                tenant_id,
                partner_statement_ids,
                side="purchase",
                restrict_source_ids=ids,
            )
            apply_invoice_budget_to_pull_preview(preview, budget)
            cap_f = float(budget.invoiceable)
            if allowed and cap_f > 0:
                preview["has_blocking_issues"] = False
                preview["summary"] = (
                    f"将从对账单关联 {len(ids)} 张入库创建采购发票（可开票合计 ¥{cap_f:,.2f}）"
                )
            elif cap_f <= 0:
                preview["has_blocking_issues"] = True
        from apps.kuaicaiwu.services.partner_statement_line_invoice_map import (
            maybe_attach_partner_statement_line_ids,
        )

        await maybe_attach_partner_statement_line_ids(
            tenant_id, partner_statement_ids, preview
        )
        return preview

    async def preview_pull_from_outsource_order_receipt(
        self,
        tenant_id: int,
        batch_id: int,
        *,
        partner_statement_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.outsource_order import OutsourceOrder
        from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt

        batch = await OutsourceOrderReceipt.get_or_none(
            tenant_id=tenant_id, id=int(batch_id), deleted_at__isnull=True
        )
        if not batch:
            raise NotFoundError(f"工序委外收货批次不存在: {batch_id}")
        if bool(getattr(batch, "invoice_receipt_complete", False)):
            return {
                "target_type": "purchase_invoice",
                "source_type": "outsource_order_receipt",
                "source_id": int(batch_id),
                "source_code": str(batch.outsource_order_code or batch_id),
                "summary": f"工序委外收货批次 {batch_id} 已完成收票",
                "items": [],
                "detail_lines": [],
                "has_blocking_issues": True,
                "blocking_reason": "purchase_invoice.pull_from_outsource_order_receipt.already_pulled",
                "tip": "价税合计不可超过可开票金额；删除未审核采购发票后，可开票金额自动回退。",
                "supplier_id": 0,
                "supplier_name": "",
                "purchase_order_id": None,
                "purchase_order_code": None,
                "max_push_total": 0.0,
            }
        order = await OutsourceOrder.get_or_none(
            tenant_id=tenant_id,
            id=int(batch.outsource_order_id),
            deleted_at__isnull=True,
        )
        if not order:
            raise NotFoundError(f"工序委外单不存在: {batch.outsource_order_id}")

        settlement_total = await self.outsource_order_receipt_settlement_gross(
            tenant_id, int(batch_id)
        )
        code = f"{order.code}-{batch.id}"
        preview_items = await self._build_preview_items_for_outsource_order_receipt(
            tenant_id, int(batch_id), source_code=code
        )
        source_allowed = settlement_total > 0
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="purchase_invoice.pull_from_outsource_order_receipt.not_allowed",
            no_lines_reason="purchase_invoice.pull_from_outsource_order_receipt.no_lines",
            already_pulled_reason="purchase_invoice.pull_from_outsource_order_receipt.already_pulled",
        )
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            build_outsource_order_receipt_invoice_detail_lines,
        )

        detail_lines = await build_outsource_order_receipt_invoice_detail_lines(
            tenant_id, int(batch_id)
        )
        preview = {
            "target_type": "purchase_invoice",
            "source_type": "outsource_order_receipt",
            "source_id": int(batch_id),
            "source_code": code,
            "summary": (
                f"将从工序委外收货 {code} 创建采购发票（可开票 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"工序委外收货 {code} 当前不可加载采购发票"
            ),
            "items": preview_items,
            "detail_lines": detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": "价税合计不可超过可开票金额；删除未审核采购发票后，可开票金额自动回退。",
            "supplier_id": int(order.supplier_id or 0),
            "supplier_name": str(order.supplier_name or ""),
            "purchase_order_id": None,
            "purchase_order_code": None,
            "max_push_total": pushable,
        }
        if partner_statement_ids:
            from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
                apply_invoice_budget_to_pull_preview,
                resolve_budget_for_statements,
            )

            budget = await resolve_budget_for_statements(
                tenant_id,
                partner_statement_ids,
                side="purchase",
                restrict_source_ids=[int(batch_id)],
            )
            apply_invoice_budget_to_pull_preview(preview, budget)
            cap_f = float(budget.invoiceable)
            if preview_items and allowed and cap_f > 0:
                preview["has_blocking_issues"] = False
                preview["summary"] = (
                    f"将从对账单关联工序委外收货 {code} 创建采购发票（可开票 ¥{cap_f:,.2f}）"
                )
            elif cap_f <= 0:
                preview["has_blocking_issues"] = True
        preview["ledger_posting_mode"] = await resolve_purchase_invoice_pull_ledger_posting_mode(
            tenant_id,
            partner_statement_ids=partner_statement_ids,
            receipt=batch,
        )
        from apps.kuaicaiwu.services.partner_statement_line_invoice_map import (
            maybe_attach_partner_statement_line_ids,
        )

        await maybe_attach_partner_statement_line_ids(
            tenant_id, partner_statement_ids, preview
        )
        return preview

    async def preview_pull_from_outsource_order_receipts(
        self,
        tenant_id: int,
        batch_ids: Sequence[int],
        *,
        partner_statement_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(batch_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_outsource_order_receipt(
                tenant_id,
                ids[0],
                partner_statement_ids=partner_statement_ids,
            )

        merged_items: List[Dict[str, Any]] = []
        merged_detail_lines: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        codes: List[str] = []
        fragment_modes: List[str] = []
        for bid in ids:
            fragment = await self.preview_pull_from_outsource_order_receipt(
                tenant_id,
                bid,
                partner_statement_ids=None,
            )
            fragment_modes.append(str(fragment.get("ledger_posting_mode") or "immediate"))
            if supplier_id is None:
                supplier_id = int(fragment.get("supplier_id") or 0)
                supplier_name = str(fragment.get("supplier_name") or "")
            elif int(fragment.get("supplier_id") or 0) != int(supplier_id or 0):
                raise BusinessLogicError("多笔一起加载须为同一供应商")
            codes.append(str(fragment.get("source_code") or bid))
            if fragment.get("has_blocking_issues"):
                reason = str(fragment.get("blocking_reason") or "")
                if reason:
                    blocking_reasons.append(reason)
            merged_items.extend(fragment.get("items") or [])
            for row in fragment.get("detail_lines") or []:
                line = dict(row)
                line["outsource_order_receipt_id"] = int(bid)
                merged_detail_lines.append(line)

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        preview = {
            "target_type": "purchase_invoice",
            "source_type": "outsource_order_receipt",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 笔工序委外收货创建采购发票（可开票合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选工序委外收货当前不可一起加载采购发票"
            ),
            "items": merged_items,
            "detail_lines": merged_detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": "价税合计不可超过可开票金额；删除未审核采购发票后，可开票金额自动回退。",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "purchase_order_id": None,
            "purchase_order_code": None,
            "max_push_total": float(max_push_total),
            "ledger_posting_mode": "by_invoice" if "by_invoice" in fragment_modes else "immediate",
        }
        if partner_statement_ids:
            preview["ledger_posting_mode"] = await resolve_purchase_invoice_pull_ledger_posting_mode(
                tenant_id,
                partner_statement_ids=partner_statement_ids,
            )
            from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
                apply_invoice_budget_to_pull_preview,
                resolve_budget_for_statements,
            )

            budget = await resolve_budget_for_statements(
                tenant_id,
                partner_statement_ids,
                side="purchase",
                restrict_source_ids=ids,
            )
            apply_invoice_budget_to_pull_preview(preview, budget)
            cap_f = float(budget.invoiceable)
            if allowed and cap_f > 0:
                preview["has_blocking_issues"] = False
                preview["summary"] = (
                    f"将从对账单关联 {len(ids)} 笔工序委外收货创建采购发票（可开票合计 ¥{cap_f:,.2f}）"
                )
            elif cap_f <= 0:
                preview["has_blocking_issues"] = True
        from apps.kuaicaiwu.services.partner_statement_line_invoice_map import (
            maybe_attach_partner_statement_line_ids,
        )

        await maybe_attach_partner_statement_line_ids(
            tenant_id, partner_statement_ids, preview
        )
        return preview

    async def preview_pull_from_partner_statement_supplier_sources(
        self,
        tenant_id: int,
        *,
        receipt_ids: Sequence[int],
        outsource_order_receipt_ids: Sequence[int],
        partner_statement_ids: Sequence[int],
    ) -> Dict[str, Any]:
        receipt_list = self._normalize_source_ids(receipt_ids) if receipt_ids else []
        outsource_list = (
            self._normalize_source_ids(outsource_order_receipt_ids)
            if outsource_order_receipt_ids
            else []
        )
        if not receipt_list and not outsource_list:
            raise BusinessLogicError("请至少选择一笔对账单源单")
        if receipt_list and not outsource_list:
            return await self.preview_pull_from_purchase_receipts(
                tenant_id,
                receipt_list,
                partner_statement_ids=partner_statement_ids,
            )
        if outsource_list and not receipt_list:
            return await self.preview_pull_from_outsource_order_receipts(
                tenant_id,
                outsource_list,
                partner_statement_ids=partner_statement_ids,
            )

        receipt_preview = await self.preview_pull_from_purchase_receipts(
            tenant_id,
            receipt_list,
            partner_statement_ids=partner_statement_ids,
        )
        outsource_preview = await self.preview_pull_from_outsource_order_receipts(
            tenant_id,
            outsource_list,
            partner_statement_ids=partner_statement_ids,
        )
        if int(receipt_preview.get("supplier_id") or 0) != int(
            outsource_preview.get("supplier_id") or 0
        ):
            raise BusinessLogicError("多笔一起加载须为同一供应商")

        merged_items = (receipt_preview.get("items") or []) + (
            outsource_preview.get("items") or []
        )
        merged_detail = list(receipt_preview.get("detail_lines") or [])
        blocking = receipt_preview.get("has_blocking_issues") or outsource_preview.get(
            "has_blocking_issues"
        )
        blocking_reason = receipt_preview.get("blocking_reason") or outsource_preview.get(
            "blocking_reason"
        )
        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        all_source_ids = receipt_list + outsource_list
        preview = {
            "target_type": "purchase_invoice",
            "source_type": "purchase_receipt",
            "source_id": all_source_ids[0],
            "source_ids": all_source_ids,
            "receipt_ids": receipt_list,
            "outsource_order_receipt_ids": outsource_list,
            "source_code": "、".join(
                filter(
                    None,
                    [
                        str(receipt_preview.get("source_code") or ""),
                        str(outsource_preview.get("source_code") or ""),
                    ],
                )
            ),
            "summary": (
                f"将从对账单关联入库与工序委外收货创建采购发票（可开票合计 ¥{float(max_push_total):,.2f}）"
                if not blocking and max_push_total > 0
                else "所选对账单源单当前不可加载采购发票"
            ),
            "items": merged_items,
            "detail_lines": merged_detail,
            "has_blocking_issues": bool(blocking),
            "blocking_reason": blocking_reason,
            "tip": (
                "含税合计不可超过对账单可收票金额；"
                "含采购入库时须与所选入库行合计一致。"
            ),
            "supplier_id": receipt_preview.get("supplier_id"),
            "supplier_name": receipt_preview.get("supplier_name"),
            "purchase_order_id": receipt_preview.get("purchase_order_id"),
            "purchase_order_code": receipt_preview.get("purchase_order_code"),
            "max_push_total": float(max_push_total),
            "ledger_posting_mode": await resolve_purchase_invoice_pull_ledger_posting_mode(
                tenant_id,
                partner_statement_ids=partner_statement_ids,
                receipt=None,
            ),
        }
        if not preview.get("ledger_posting_mode"):
            preview["ledger_posting_mode"] = str(
                receipt_preview.get("ledger_posting_mode") or "immediate"
            )
        from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
            apply_invoice_budget_to_pull_preview,
            resolve_budget_for_statements,
        )

        budget = await resolve_budget_for_statements(
            tenant_id,
            partner_statement_ids,
            side="purchase",
            restrict_source_ids=all_source_ids,
        )
        apply_invoice_budget_to_pull_preview(preview, budget)
        cap_f = float(budget.invoiceable)
        if not preview["has_blocking_issues"] and cap_f > 0:
            preview["summary"] = (
                f"将从对账单关联源单创建采购发票（可开票合计 ¥{cap_f:,.2f}）"
            )
        elif cap_f <= 0:
            preview["has_blocking_issues"] = True
        from apps.kuaicaiwu.services.partner_statement_line_invoice_map import (
            maybe_attach_partner_statement_line_ids,
        )

        await maybe_attach_partner_statement_line_ids(
            tenant_id, partner_statement_ids, preview
        )
        return preview

    async def _validate_pull_receipt_lines_for_receipts(
        self,
        tenant_id: int,
        receipt_ids: Sequence[int],
        pull_receipt_lines: Sequence[Any],
        total_amount: Decimal,
        *,
        partner_statement_ids: Optional[Sequence[int]] = None,
    ) -> None:
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            build_slices_from_pull_receipt_line_selections,
        )
        from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

        item_ids: List[int] = []
        for raw in pull_receipt_lines:
            if hasattr(raw, "purchase_receipt_item_id"):
                item_ids.append(int(raw.purchase_receipt_item_id))
            elif isinstance(raw, dict):
                item_ids.append(int(raw["purchase_receipt_item_id"]))
            else:
                raise BusinessLogicError("行选择格式无效")

        rows = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id, id__in=item_ids, deleted_at__isnull=True
        ).all()
        item_to_receipt = {int(r.id): int(r.receipt_id) for r in rows}
        allowed_receipts = {int(rid) for rid in receipt_ids}

        grouped: Dict[int, List[Any]] = {}
        for raw in pull_receipt_lines:
            item_id = int(
                raw.purchase_receipt_item_id
                if hasattr(raw, "purchase_receipt_item_id")
                else raw["purchase_receipt_item_id"]
            )
            rid = item_to_receipt.get(item_id)
            if rid is None or rid not in allowed_receipts:
                raise BusinessLogicError(f"入库明细 {item_id} 不属于所选入库单")
            grouped.setdefault(rid, []).append(raw)

        subtotal = Decimal("0")
        for rid, selections in grouped.items():
            part = sum(
                Decimal(
                    str(
                        s.amount
                        if hasattr(s, "amount")
                        else s.get("amount", 0)
                    )
                )
                for s in selections
            )
            subtotal += part
            max_by = None
            if partner_statement_ids:
                from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
                    statement_scaled_receipt_line_caps,
                )

                max_by = await statement_scaled_receipt_line_caps(
                    tenant_id, int(rid), header_amount=part
                )
            await build_slices_from_pull_receipt_line_selections(
                tenant_id,
                int(rid),
                "invoice",
                selections,
                header_amount=part,
                max_push_by_item=max_by,
            )
        if abs(subtotal - Decimal(total_amount)) > Decimal("0.01"):
            raise BusinessLogicError(
                f"所选入库行金额合计 {subtotal} 与单据金额 {total_amount} 不一致"
            )

    async def record_multi_receipt_invoice_occupancy(
        self,
        tenant_id: int,
        receipt_ids: Sequence[int],
        invoice_id: int,
        total_amount: Decimal,
        *,
        pull_receipt_lines: Optional[Sequence[Any]] = None,
        created_by: Optional[int] = None,
    ) -> None:
        from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
            record_purchase_receipt_invoice_occupancy,
        )
        from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

        ids = self._normalize_source_ids(receipt_ids)
        if pull_receipt_lines:
            grouped: Dict[int, List[Any]] = {}
            for raw in pull_receipt_lines:
                item_id = int(
                    raw.purchase_receipt_item_id
                    if hasattr(raw, "purchase_receipt_item_id")
                    else raw["purchase_receipt_item_id"]
                )
                item = await PurchaseReceiptItem.get_or_none(
                    tenant_id=tenant_id, id=item_id, deleted_at__isnull=True
                )
                if not item:
                    raise BusinessLogicError(f"入库明细不存在: {item_id}")
                grouped.setdefault(int(item.receipt_id), []).append(raw)
            for rid, selections in grouped.items():
                part = sum(
                    Decimal(
                        str(
                            s.amount
                            if hasattr(s, "amount")
                            else s.get("amount", 0)
                        )
                    )
                    for s in selections
                )
                await record_purchase_receipt_invoice_occupancy(
                    tenant_id,
                    int(rid),
                    int(invoice_id),
                    part,
                    line_selections=selections,
                    created_by=created_by,
                )
            return

        remaining = Decimal(total_amount)
        for rid in ids:
            if remaining <= 0:
                break
            fragment = await self.preview_pull_from_purchase_receipt(tenant_id, int(rid))
            cap = Decimal("0")
            for item in fragment.get("items") or []:
                cap += Decimal(str(item.get("max_push_quantity") or 0))
            take = min(cap, remaining)
            if take <= 0:
                continue
            await record_purchase_receipt_invoice_occupancy(
                tenant_id,
                int(rid),
                int(invoice_id),
                take,
                line_selections=None,
                created_by=created_by,
            )
            remaining -= take

    async def preview_pull_from_payables(
        self,
        tenant_id: int,
        payable_ids: Sequence[int],
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(payable_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_payable(tenant_id, ids[0])

        merged_items: List[Dict[str, Any]] = []
        merged_detail_lines: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        codes: List[str] = []
        fragment_modes: List[str] = []

        for pid in ids:
            fragment = await self.preview_pull_from_payable(tenant_id, pid)
            fragment_modes.append(str(fragment.get("ledger_posting_mode") or "immediate"))
            if supplier_id is None:
                supplier_id = int(fragment.get("supplier_id") or 0)
                supplier_name = str(fragment.get("supplier_name") or "")
            elif int(fragment.get("supplier_id") or 0) != int(supplier_id or 0):
                raise BusinessLogicError("多笔一起加载须为同一供应商")

            codes.append(str(fragment.get("source_code") or pid))
            if fragment.get("has_blocking_issues"):
                reason = str(fragment.get("blocking_reason") or "")
                if reason:
                    blocking_reasons.append(reason)
            merged_items.extend(fragment.get("items") or [])
            for row in fragment.get("detail_lines") or []:
                line = dict(row)
                line["payable_id"] = pid
                merged_detail_lines.append(line)

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        return {
            "target_type": "purchase_invoice",
            "source_type": "payable",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 张应付单创建采购发票（可开票合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选应付单当前不可一起加载采购发票"
            ),
            "items": merged_items,
            "detail_lines": merged_detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": "价税合计不可超过可开票合计；有入库行占用时须与所选行金额一致。",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "max_push_total": float(max_push_total),
            "payable_id": ids[0],
            "payable_code": codes[0] if codes else None,
            "ledger_posting_mode": "by_invoice" if "by_invoice" in fragment_modes else "immediate",
        }

    async def preview_pull_from_payable(
        self,
        tenant_id: int,
        payable_id: int,
    ) -> Dict[str, Any]:
        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=payable_id, deleted_at__isnull=True
        )
        if not payable:
            raise NotFoundError(f"应付单不存在: {payable_id}")

        source_allowed = self._payable_source_allowed(payable)
        preview_items = await self._build_preview_items_for_payable(tenant_id, payable)
        po_id, po_code = await self._resolve_purchase_order_from_payable(tenant_id, payable)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="purchase_invoice.pull_from_payable.not_allowed",
            no_lines_reason="purchase_invoice.pull_from_payable.no_lines",
            already_pulled_reason="purchase_invoice.pull_from_payable.already_pulled",
            source_type=str(getattr(payable, "source_type", "") or ""),
            status=str(getattr(payable, "status", "") or ""),
        )
        code = str(payable.payable_code or payable_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            build_invoice_detail_lines_from_payable,
        )

        purchase_receipt_id, detail_lines = await build_invoice_detail_lines_from_payable(
            tenant_id, payable_id
        )
        return {
            "target_type": "purchase_invoice",
            "source_type": "payable",
            "source_id": payable_id,
            "source_code": code,
            "summary": (
                f"将从应付单 {code} 创建采购发票（可开票 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"应付单 {code} 当前不可加载采购发票"
            ),
            "items": preview_items,
            "detail_lines": detail_lines,
            "purchase_receipt_id": purchase_receipt_id,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": (
                "采购退货冲减应付不可从应付开采购发票；请对原蓝字业务收票或申请红字发票。"
                if reason == "purchase_invoice.pull_from_payable.purchase_return_offset"
                else (
                    (
                        "价税合计须与所选入库行合计一致；未勾选行时按应付行占用比例分摊。"
                        if purchase_receipt_id
                        else "价税合计不可超过可开票金额；删除未审核采购发票后，可开票金额自动回退。"
                    )
                    + ("有关联采购订单时将一并挂接。" if po_id else "无采购订单时仅关联应付单。")
                )
            ),
            "supplier_id": payable.supplier_id,
            "supplier_name": payable.supplier_name,
            "payable_id": payable.id,
            "payable_code": code,
            "purchase_order_id": po_id,
            "purchase_order_code": po_code,
            # 同时付款上限：应付剩余可付金额（与开票可开票金额独立）
            "remaining_settle_amount": float(
                Decimal(str(getattr(payable, "remaining_amount", 0) or 0))
            ),
            "max_push_total": pushable,
            "ledger_posting_mode": await resolve_purchase_invoice_pull_ledger_posting_mode(
                tenant_id, payable=payable
            ),
        }

    async def record_multi_payable_invoice_side_effects(
        self,
        tenant_id: int,
        payable_ids: Sequence[int],
        invoice_id: int,
        total_amount: Decimal,
        *,
        pull_receipt_lines: Optional[Sequence[Any]] = None,
        invoice_number: Optional[str] = None,
        created_by: int,
    ) -> None:
        from apps.kuaicaiwu.models.payable import Payable as PayableModel
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            build_invoice_detail_lines_from_payable,
        )
        from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
            record_purchase_receipt_invoice_from_payable,
        )

        ids = self._normalize_source_ids(payable_ids)
        if pull_receipt_lines:
            by_payable: Dict[int, List[Any]] = {}
            item_to_payable_cap: Dict[int, int] = {}
            for pid in ids:
                _, detail = await build_invoice_detail_lines_from_payable(tenant_id, pid)
                for d in detail:
                    item_to_payable_cap[int(d["purchase_receipt_item_id"])] = pid

            for raw in pull_receipt_lines:
                item_id = int(
                    raw.purchase_receipt_item_id
                    if hasattr(raw, "purchase_receipt_item_id")
                    else raw["purchase_receipt_item_id"]
                )
                pid = item_to_payable_cap.get(item_id)
                if pid is None:
                    raise BusinessLogicError(f"入库明细 {item_id} 不在所选应付单可开票范围内")
                by_payable.setdefault(pid, []).append(raw)
            for pid, selections in by_payable.items():
                part = sum(
                    Decimal(
                        str(
                            s.amount
                            if hasattr(s, "amount")
                            else s.get("amount", 0)
                        )
                    )
                    for s in selections
                )
                await record_purchase_receipt_invoice_from_payable(
                    tenant_id,
                    int(pid),
                    int(invoice_id),
                    part,
                    line_selections=selections,
                    created_by=created_by,
                )
                payable_update: dict = {"invoice_received": True, "updated_by": created_by}
                if invoice_number:
                    payable_update["invoice_number"] = invoice_number
                await PayableModel.filter(tenant_id=tenant_id, id=int(pid)).update(**payable_update)
            return

        remaining = Decimal(total_amount)
        for pid in ids:
            if remaining <= 0:
                break
            fragment = await self.preview_pull_from_payable(tenant_id, int(pid))
            cap = Decimal(str(fragment.get("max_push_total") or 0))
            if cap <= 0 and fragment.get("items"):
                cap = Decimal(str(fragment["items"][0].get("max_push_quantity") or 0))
            take = min(cap, remaining)
            if take <= 0:
                continue
            await record_purchase_receipt_invoice_from_payable(
                tenant_id,
                int(pid),
                int(invoice_id),
                take,
                line_selections=None,
                created_by=created_by,
            )
            payable_update = {"invoice_received": True, "updated_by": created_by}
            if invoice_number:
                payable_update["invoice_number"] = invoice_number
            await PayableModel.filter(tenant_id=tenant_id, id=int(pid)).update(**payable_update)
            remaining -= take

    async def list_purchase_order_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        query = PurchaseOrder.filter(
            tenant_id=tenant_id,
            status__in=list(self._PO_ELIGIBLE_STATUSES),
            deleted_at__isnull=True,
        )
        query = apply_pull_query_document_date_filter(
            query,
            field="order_date",
            kind="date",
            date_from=date_from,
            date_to=date_to,
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(Q(order_code__icontains=kw) | Q(supplier_name__icontains=kw))
        total = await query.count()
        orders = await query.offset(skip).limit(limit).order_by("-created_at")
        order_ids = [int(o.id) for o in orders]
        if not order_ids:
            return {"data": [], "total": total, "success": True}

        code_by_id = {int(o.id): str(o.order_code or o.id) for o in orders}
        pushed_map = await self._sum_pushed_totals_by_source(
            tenant_id, "purchase_order", order_ids, code_by_id
        )
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            batch_purchase_order_invoice_line_stats,
        )

        line_stats = await batch_purchase_order_invoice_line_stats(
            tenant_id, orders, pushed_map
        )

        rows: List[Dict[str, Any]] = []
        for order in orders:
            oid = int(order.id)
            preview_items = await self._build_preview_items_for_purchase_order(
                tenant_id,
                order,
                pushed=pushed_map.get(oid, Decimal("0")),
            )
            from apps.kuaicaiwu.services.purchase_settlement import (
                purchase_order_settlement_gross,
            )

            order_gross = purchase_order_settlement_gross(order)
            status_ok = str(getattr(order, "status", "") or "").strip() in self._PO_ELIGIBLE_STATUSES
            allowed, reason = self._derive_pull_capability(
                source_allowed=status_ok and order_gross > 0,
                preview_items=preview_items,
                not_allowed_reason="purchase_invoice.pull_from_purchase_order.not_allowed",
                no_lines_reason="purchase_invoice.pull_from_purchase_order.no_lines",
                already_pulled_reason="purchase_invoice.pull_from_purchase_order.already_pulled",
            )
            code = str(order.order_code or oid)
            name = str(getattr(order, "supplier_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            stats = line_stats.get(oid, {})
            rows.append(
                {
                    "id": oid,
                    "code": label,
                    "order_code": code,
                    "supplier_id": int(order.supplier_id or 0) or None,
                    "supplier_name": order.supplier_name,
                    "source_status": order.status,
                    "source_date": str(getattr(order, "order_date", "") or ""),
                    "amount": float(order_gross),
                    "detail_line_count": int(stats.get("detail_line_count") or 0),
                    "invoiced_line_count": int(stats.get("invoiced_line_count") or 0),
                    "capabilities": {
                        "pull_purchase_invoice": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def list_purchase_receipt_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        query = PurchaseReceipt.filter(
            tenant_id=tenant_id,
            status__in=list(self._PR_ELIGIBLE_STATUSES),
            deleted_at__isnull=True,
        )
        query = apply_pull_query_document_date_filter(
            query,
            field="receipt_time",
            kind="datetime",
            date_from=date_from,
            date_to=date_to,
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(
                Q(receipt_code__icontains=kw) | Q(supplier_name__icontains=kw)
            )
        total = await query.count()
        receipts = await query.offset(skip).limit(limit).order_by("-created_at")
        receipt_ids = [int(r.id) for r in receipts]
        if not receipt_ids:
            return {"data": [], "total": total, "success": True}

        code_by_id = {int(r.id): str(r.receipt_code or r.id) for r in receipts}
        pushed_map = await self._sum_pushed_totals_by_source(
            tenant_id, "purchase_receipt", receipt_ids, code_by_id
        )

        from apps.kuaicaiwu.services.purchase_settlement import (
            batch_purchase_receipt_settlement_gross,
        )

        gross_map = await batch_purchase_receipt_settlement_gross(tenant_id, receipts)

        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            batch_purchase_receipt_invoice_line_stats,
        )

        line_stats = await batch_purchase_receipt_invoice_line_stats(tenant_id, receipts)

        rows: List[Dict[str, Any]] = []
        for receipt in receipts:
            rid = int(receipt.id)
            receipt_gross = gross_map.get(rid, Decimal("0"))
            preview_items = await self._build_preview_items_for_purchase_receipt(
                tenant_id,
                receipt,
                pushed=pushed_map.get(rid, Decimal("0")),
                settlement_gross=receipt_gross,
            )
            from apps.kuaizhizao.services.document_recognition import (
                purchase_receipt_direct_invoice_pull_block_reason,
            )

            ledger_block = purchase_receipt_direct_invoice_pull_block_reason(receipt)
            if ledger_block:
                allowed, reason = False, ledger_block
            else:
                allowed, reason = self._derive_pull_capability(
                    source_allowed=receipt_gross > 0,
                    preview_items=preview_items,
                    not_allowed_reason="purchase_invoice.pull_from_purchase_receipt.not_allowed",
                    no_lines_reason="purchase_invoice.pull_from_purchase_receipt.no_lines",
                    already_pulled_reason="purchase_invoice.pull_from_purchase_receipt.already_pulled",
                )
            code = str(receipt.receipt_code or rid)
            name = str(getattr(receipt, "supplier_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            amount = float(receipt_gross)
            invoiced_amount = float(pushed_map.get(rid, Decimal("0")))
            invoiceable_amount = max(0.0, amount - invoiced_amount)
            stats = line_stats.get(rid, {})
            rows.append(
                {
                    "id": rid,
                    "code": label,
                    "doc_code": code,
                    "receipt_code": code,
                    "supplier_id": int(receipt.supplier_id or 0) or None,
                    "supplier_name": receipt.supplier_name,
                    "source_status": receipt.status,
                    "source_date": str(
                        getattr(receipt, "receipt_time", "") or getattr(receipt, "created_at", "") or ""
                    ),
                    "amount": amount,
                    "invoiceable_amount": invoiceable_amount,
                    "invoiced_amount": invoiced_amount,
                    "detail_line_count": int(stats.get("detail_line_count") or 0),
                    "invoiced_line_count": int(stats.get("invoiced_line_count") or 0),
                    "capabilities": {
                        "pull_purchase_invoice": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def list_payable_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        from apps.kuaicaiwu.constants.finance_source_types import PAYABLE_SOURCE_PARTNER_STATEMENT

        query = (
            Payable.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                total_amount__gt=0,
            )
            .exclude(source_type="采购退货")
            .exclude(source_type=PAYABLE_SOURCE_PARTNER_STATEMENT)
            .exclude(status="已冲减")
        )
        query = apply_pull_query_document_date_filter(
            query,
            field="due_date",
            kind="date",
            date_from=date_from,
            date_to=date_to,
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(
                Q(payable_code__icontains=kw) | Q(supplier_name__icontains=kw)
            )
        total = await query.count()
        payables = await query.offset(skip).limit(limit).order_by("-created_at")
        payable_ids = [int(p.id) for p in payables]
        if not payable_ids:
            return {"data": [], "total": total, "success": True}

        code_by_id = {int(p.id): str(p.payable_code or p.id) for p in payables}
        pushed_map = await self._sum_pushed_totals_by_payable(
            tenant_id, payable_ids, code_by_id
        )
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            batch_payable_invoice_line_stats,
        )

        line_stats = await batch_payable_invoice_line_stats(tenant_id, payables)

        rows: List[Dict[str, Any]] = []
        for payable in payables:
            pid = int(payable.id)
            preview_items = await self._build_preview_items_for_payable(
                tenant_id,
                payable,
                pushed=pushed_map.get(pid, Decimal("0")),
            )
            allowed, reason = self._derive_pull_capability(
                source_allowed=self._payable_source_allowed(payable),
                preview_items=preview_items,
                not_allowed_reason="purchase_invoice.pull_from_payable.not_allowed",
                no_lines_reason="purchase_invoice.pull_from_payable.no_lines",
                already_pulled_reason="purchase_invoice.pull_from_payable.already_pulled",
                source_type=str(getattr(payable, "source_type", "") or ""),
                status=str(getattr(payable, "status", "") or ""),
            )
            code = str(payable.payable_code or pid)
            name = str(getattr(payable, "supplier_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            amount = float(payable.total_amount or 0)
            invoiced_amount = float(pushed_map.get(pid, Decimal("0")))
            invoiceable_amount = max(0.0, amount - invoiced_amount)
            stats = line_stats.get(pid, {})
            rows.append(
                {
                    "id": pid,
                    "code": label,
                    "doc_code": code,
                    "payable_code": code,
                    "supplier_id": int(payable.supplier_id or 0) or None,
                    "supplier_name": payable.supplier_name,
                    "source_status": payable.status,
                    "review_status": payable.review_status,
                    "source_date": str(getattr(payable, "business_date", "") or ""),
                    "amount": amount,
                    "invoiceable_amount": invoiceable_amount,
                    "invoiced_amount": invoiced_amount,
                    "detail_line_count": int(stats.get("detail_line_count") or 0),
                    "invoiced_line_count": int(stats.get("invoiced_line_count") or 0),
                    "capabilities": {
                        "pull_purchase_invoice": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def list_partner_statement_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        """供应商往来对账单 → 采购发票头表取单候选。"""
        from apps.kuaicaiwu.models.partner_statement import PartnerStatement
        from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
            compute_statement_invoice_pull_metrics,
            resolve_statement_amount_basis,
            resolve_statement_invoice_source_ids,
            snapshot_ids_for_api,
            sum_statement_invoice_period_amount,
            sum_supplier_by_invoice_statement_period,
        )

        query = PartnerStatement.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            partner_type="Supplier",
            status__in=["Confirmed", "Sent", "LedgerPosted"],
            review_status__in=["已审核", "approved", "APPROVED"],
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(
                Q(statement_code__icontains=kw) | Q(partner_name__icontains=kw)
            )
        total = await query.count()
        statements = await query.offset(skip).limit(limit).order_by("-end_date", "-id")
        if not statements:
            return {"data": [], "total": total, "success": True}

        rows: List[Dict[str, Any]] = []
        for stmt in statements:
            sid = int(stmt.id)
            snapshot = resolve_statement_invoice_source_ids(
                partner_type=stmt.partner_type,
                ledger_posting_mode=stmt.ledger_posting_mode,
                transaction_details=stmt.transaction_details,
            )
            if (
                snapshot.ledger_posting_mode == "by_invoice"
                and (snapshot.purchase_receipt_ids or snapshot.outsource_order_receipt_ids)
            ):
                period_amt = sum_supplier_by_invoice_statement_period(
                    stmt.transaction_details
                )
            else:
                period_amt = sum_statement_invoice_period_amount(
                    stmt.transaction_details, snapshot.doc_type
                )
            invoiced, remaining, allowed, reason = await compute_statement_invoice_pull_metrics(
                tenant_id,
                side="purchase",
                source_ids=snapshot.source_ids,
                source_type=snapshot.source_type,
                statement_period_amount=period_amt,
                snapshot=snapshot,
            )
            code = str(stmt.statement_code or sid)
            name = str(stmt.partner_name or "").strip()
            label = f"{code} - {name}" if name else code
            period = float(period_amt)
            id_fields = snapshot_ids_for_api(snapshot)
            rows.append(
                {
                    "id": sid,
                    "code": label,
                    "doc_code": code,
                    "statement_code": code,
                    "supplier_id": int(stmt.partner_id or 0) or None,
                    "supplier_name": stmt.partner_name,
                    "source_status": stmt.status,
                    "source_date": str(stmt.end_date or ""),
                    # amount / period_amount：本期对账（勿用期末余额，期末含期初会虚高）
                    "amount": period,
                    "period_amount": period,
                    "closing_balance": float(stmt.closing_balance or 0),
                    "invoiceable_amount": max(0.0, remaining),
                    "invoiced_amount": invoiced,
                    "amount_basis": resolve_statement_amount_basis(stmt.transaction_details),
                    "ledger_posting_mode": snapshot.ledger_posting_mode,
                    **id_fields,
                    "capabilities": {
                        "pull_purchase_invoice": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def preview_pull(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_ids: Sequence[int],
        partner_statement_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        """采购发票取单预览唯一分发（汇总/明细开票共用）。"""
        st = str(source_type or "").strip()
        ids = self._normalize_source_ids(source_ids)
        if not ids:
            raise BusinessLogicError("须指定源单")
        if st == "purchase_order":
            preview = (
                await self.preview_pull_from_purchase_orders(tenant_id, ids)
                if len(ids) > 1
                else await self.preview_pull_from_purchase_order(tenant_id, ids[0])
            )
        elif st == "purchase_receipt":
            if partner_statement_ids:
                from apps.kuaicaiwu.models.partner_statement import PartnerStatement
                from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
                    resolve_statement_invoice_source_ids,
                )

                stmt_ids = [int(x) for x in partner_statement_ids if int(x) > 0]
                stmts = await PartnerStatement.filter(
                    tenant_id=tenant_id,
                    id__in=stmt_ids,
                    deleted_at__isnull=True,
                ).all()
                outsource_id_set: set[int] = set()
                for stmt in stmts:
                    snapshot = resolve_statement_invoice_source_ids(
                        partner_type=str(stmt.partner_type or ""),
                        ledger_posting_mode=stmt.ledger_posting_mode,
                        transaction_details=stmt.transaction_details,
                    )
                    outsource_id_set.update(
                        int(x) for x in snapshot.outsource_order_receipt_ids if int(x) > 0
                    )
                outsource_ids = [i for i in ids if i in outsource_id_set]
                if outsource_ids:
                    receipt_ids = [i for i in ids if i not in set(outsource_ids)]
                    preview = await self.preview_pull_from_partner_statement_supplier_sources(
                        tenant_id,
                        receipt_ids=receipt_ids,
                        outsource_order_receipt_ids=outsource_ids,
                        partner_statement_ids=partner_statement_ids,
                    )
                elif len(ids) > 1:
                    preview = await self.preview_pull_from_purchase_receipts(
                        tenant_id,
                        ids,
                        partner_statement_ids=partner_statement_ids,
                    )
                else:
                    preview = await self.preview_pull_from_purchase_receipt(
                        tenant_id,
                        ids[0],
                        partner_statement_ids=partner_statement_ids,
                    )
            elif len(ids) > 1:
                preview = await self.preview_pull_from_purchase_receipts(
                    tenant_id,
                    ids,
                    partner_statement_ids=partner_statement_ids,
                )
            else:
                preview = await self.preview_pull_from_purchase_receipt(
                    tenant_id,
                    ids[0],
                    partner_statement_ids=partner_statement_ids,
                )
        elif st == "payable":
            preview = (
                await self.preview_pull_from_payables(tenant_id, ids)
                if len(ids) > 1
                else await self.preview_pull_from_payable(tenant_id, ids[0])
            )
        elif st == "outsource_order_receipt":
            preview = (
                await self.preview_pull_from_outsource_order_receipts(
                    tenant_id,
                    ids,
                    partner_statement_ids=partner_statement_ids,
                )
                if len(ids) > 1
                else await self.preview_pull_from_outsource_order_receipt(
                    tenant_id,
                    ids[0],
                    partner_statement_ids=partner_statement_ids,
                )
            )
        else:
            raise BusinessLogicError(f"不支持的加载源单类型: {st}")
        return preview

    async def assert_pull_create_allowed(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        total_amount: Decimal,
        pull_receipt_lines: Optional[List[Any]] = None,
        source_ids: Optional[Sequence[int]] = None,
        partner_statement_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        preview = await self.preview_pull(
            tenant_id,
            source_type=source_type,
            source_ids=source_ids if source_ids else [source_id],
            partner_statement_ids=partner_statement_ids,
        )
        if preview.get("has_blocking_issues"):
            reason = preview.get("blocking_reason") or "当前不可加载采购发票"
            raise BusinessLogicError(reason)
        items = preview.get("items") or []
        if not items:
            raise BusinessLogicError("无可开票金额")
        from apps.kuaicaiwu.services.partner_statement_invoice_pull import (
            enforce_partner_statement_invoice_total,
            resolve_pull_preview_invoice_cap,
            statement_scaled_receipt_line_caps,
        )

        ids_for_budget = (
            self._normalize_source_ids(source_ids or [source_id]) if partner_statement_ids else []
        )
        if partner_statement_ids and source_type in (
            "purchase_receipt",
            "payable",
            "outsource_order_receipt",
        ):
            await enforce_partner_statement_invoice_total(
                tenant_id,
                partner_statement_ids,
                side="purchase",
                restrict_source_ids=ids_for_budget,
                total_amount=total_amount,
            )
        else:
            max_push = resolve_pull_preview_invoice_cap(preview)
            if money_exceeds_max(total_amount, max_push):
                raise BusinessLogicError(f"价税合计 {total_amount} 超过可开票金额 {max_push}")
        if pull_receipt_lines:
            from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
                build_invoice_detail_lines_from_payable,
                build_slices_from_pull_receipt_line_selections,
                resolve_purchase_receipt_id_from_payable,
            )
            from apps.kuaicaiwu.models.payable import Payable

            if source_type == "purchase_receipt":
                receipt_ids = self._normalize_source_ids(source_ids or [source_id])
                if len(receipt_ids) > 1:
                    await self._validate_pull_receipt_lines_for_receipts(
                        tenant_id,
                        receipt_ids,
                        pull_receipt_lines,
                        total_amount,
                        partner_statement_ids=partner_statement_ids,
                    )
                else:
                    max_by = None
                    if partner_statement_ids:
                        max_by = await statement_scaled_receipt_line_caps(
                            tenant_id,
                            int(receipt_ids[0]),
                            header_amount=total_amount,
                        )
                    await build_slices_from_pull_receipt_line_selections(
                        tenant_id,
                        receipt_ids[0],
                        "invoice",
                        pull_receipt_lines,
                        header_amount=total_amount,
                        max_push_by_item=max_by,
                    )
            elif source_type == "payable":
                payable = await Payable.get_or_none(
                    tenant_id=tenant_id, id=int(source_id), deleted_at__isnull=True
                )
                if not payable:
                    raise BusinessLogicError("应付单不存在")
                receipt_id = resolve_purchase_receipt_id_from_payable(
                    str(getattr(payable, "source_type", "") or ""),
                    getattr(payable, "source_id", None),
                )
                if not receipt_id:
                    raise BusinessLogicError("该应付单未关联采购入库，无法按行收票")
                _, detail = await build_invoice_detail_lines_from_payable(tenant_id, int(source_id))
                max_by = {
                    int(d["purchase_receipt_item_id"]): Decimal(str(d["max_push_amount"]))
                    for d in detail
                }
                if partner_statement_ids:
                    max_by = await statement_scaled_receipt_line_caps(
                        tenant_id,
                        int(receipt_id),
                        header_amount=total_amount,
                    )
                allowed_ids = set(max_by.keys())
                for raw in pull_receipt_lines:
                    item_id = int(
                        raw.purchase_receipt_item_id
                        if hasattr(raw, "purchase_receipt_item_id")
                        else raw["purchase_receipt_item_id"]
                    )
                    if item_id not in allowed_ids:
                        raise BusinessLogicError("所选入库行不在该应付单的应付占用范围内")
                await build_slices_from_pull_receipt_line_selections(
                    tenant_id,
                    int(receipt_id),
                    "invoice",
                    pull_receipt_lines,
                    header_amount=total_amount,
                    max_push_by_item=max_by,
                )
        return preview

    async def create_pull_relation(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        source_code: str,
        invoice_id: int,
        invoice_code: str,
        created_by: int,
        allocated_amount: Optional[Decimal] = None,
    ) -> None:
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
        from apps.kuaicaiwu.services.invoice_source_allocation import encode_relation_allocated_amount

        notes = (
            encode_relation_allocated_amount(allocated_amount)
            if allocated_amount is not None
            else None
        )
        rel_svc = DocumentRelationNewService()
        await rel_svc.create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type=source_type,
                source_id=source_id,
                source_code=source_code,
                source_name=None,
                target_type="purchase_invoice",
                target_id=invoice_id,
                target_code=invoice_code,
                target_name=None,
                relation_type="source",
                relation_mode="pull",
                relation_desc="加载创建采购发票",
                notes=notes,
            ),
            created_by=created_by,
        )
