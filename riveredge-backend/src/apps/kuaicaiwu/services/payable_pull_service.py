"""
应付单加载门控：采购订单/采购入库候选列表、预览、已应付金额汇总；列表下推付款 capability。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from tortoise.queryset import Q

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.constants.finance_source_types import (
    is_outsource_return_offset_payable,
    is_purchase_return_offset_payable,
)
from apps.kuaicaiwu.services.finance_service import derive_invoice_amount_status
from apps.kuaicaiwu.services.purchase_settlement import (
    purchase_order_settlement_gross,
    purchase_receipt_settlement_gross_async,
)
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaizhizao.models.document_relation import DocumentRelation
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError


class PayablePullService(AppBaseService[Payable]):
    """应付单加载门控服务"""

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

    _PO_LEGACY_SOURCE_TYPES = frozenset({"purchase_order", "采购订单"})
    _PR_LEGACY_SOURCE_TYPES = frozenset({"purchase_receipt", "采购入库"})

    def _derive_pull_capability(
        self,
        *,
        source_allowed: bool,
        preview_items: List[Dict[str, Any]],
        not_allowed_reason: str,
        no_lines_reason: str,
        already_pulled_reason: str,
    ) -> tuple[bool, Optional[str]]:
        if not source_allowed:
            return False, not_allowed_reason
        if not preview_items:
            return False, no_lines_reason
        pushable = any(float(row.get("max_push_quantity") or 0) > 0 for row in preview_items)
        if not pushable:
            return False, already_pulled_reason
        return True, None

    def _legacy_source_types(self, source_type: str) -> frozenset[str]:
        if source_type == "purchase_order":
            return self._PO_LEGACY_SOURCE_TYPES
        if source_type == "purchase_receipt":
            return self._PR_LEGACY_SOURCE_TYPES
        return frozenset()

    async def _sum_pushed_totals_by_source(
        self,
        tenant_id: int,
        source_type: str,
        source_ids: List[int],
        code_by_id: Dict[int, str],
    ) -> Dict[int, Decimal]:
        result: Dict[int, Decimal] = {sid: Decimal("0") for sid in source_ids}
        if not source_ids:
            return result

        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id__in=source_ids,
            target_type="payable",
        ).all()
        relation_by_payable: Dict[int, int] = {
            int(r.target_id): int(r.source_id) for r in relations if r.target_id and r.source_id
        }
        payable_ids = list(relation_by_payable.keys())
        linked_payable_ids: set[int] = set()

        if payable_ids:
            payables = await Payable.filter(
                tenant_id=tenant_id,
                id__in=payable_ids,
                deleted_at__isnull=True,
            )
            for row in payables:
                pid = int(row.id)
                linked_payable_ids.add(pid)
                sid = relation_by_payable.get(pid)
                if sid is not None:
                    result[sid] = result.get(sid, Decimal("0")) + Decimal(str(row.total_amount or 0))

        legacy_types = list(self._legacy_source_types(source_type))
        if legacy_types:
            legacy_rows = await Payable.filter(
                tenant_id=tenant_id,
                source_id__in=source_ids,
                source_type__in=legacy_types,
                deleted_at__isnull=True,
            )
            for row in legacy_rows:
                if int(row.id) in linked_payable_ids:
                    continue
                sid = int(row.source_id)
                if sid in result:
                    result[sid] = result.get(sid, Decimal("0")) + Decimal(str(row.total_amount or 0))

        codes = [c for c in code_by_id.values() if c]
        if codes:
            code_to_id = {str(v).strip(): k for k, v in code_by_id.items() if v}
            orphan_rows = await Payable.filter(
                tenant_id=tenant_id,
                source_code__in=codes,
                deleted_at__isnull=True,
            )
            for row in orphan_rows:
                if int(row.id) in linked_payable_ids:
                    continue
                sid = code_to_id.get(str(row.source_code or "").strip())
                if sid is not None:
                    result[sid] = result.get(sid, Decimal("0")) + Decimal(str(row.total_amount or 0))
        return result

    def _build_preview_item(
        self,
        *,
        source_id: int,
        source_code: str,
        supplier_name: str,
        quantity: Decimal,
        pushed: Decimal,
    ) -> Dict[str, Any]:
        qty = float(quantity)
        pushed_f = float(pushed)
        max_push = float(max(Decimal("0"), quantity - pushed))
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
        total = purchase_order_settlement_gross(order)
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
        source_allowed = (
            status in self._PO_ELIGIBLE_STATUSES
            and purchase_order_settlement_gross(order) > 0
        )
        preview_items = await self._build_preview_items_for_purchase_order(tenant_id, order)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="payable.pull_from_purchase_order.not_allowed",
            no_lines_reason="payable.pull_from_purchase_order.no_lines",
            already_pulled_reason="payable.pull_from_purchase_order.already_pulled",
        )
        code = str(order.order_code or order_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        return {
            "target_type": "payable",
            "source_type": "purchase_order",
            "source_id": order_id,
            "source_code": code,
            "summary": (
                f"将从采购订单 {code} 创建应付单（可应付 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"采购订单 {code} 当前不可加载应付单"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": "应付金额不可超过可应付金额；删除未审核应付单后，可应付金额自动回退。",
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier_name,
            "purchase_order_id": order.id,
            "purchase_order_code": code,
        }

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
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(receipt_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_purchase_receipt(tenant_id, ids[0])

        merged_items: List[Dict[str, Any]] = []
        merged_detail_lines: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        codes: List[str] = []

        for rid in ids:
            fragment = await self.preview_pull_from_purchase_receipt(tenant_id, rid)
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

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        return {
            "target_type": "payable",
            "source_type": "purchase_receipt",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 张采购入库单创建应付单（可应付合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选入库单当前不可一起加载应付单"
            ),
            "items": merged_items,
            "detail_lines": merged_detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": "应付金额须与所选入库行合计一致；未勾选行时按各入库单可应付余量依次占用。",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "max_push_total": float(max_push_total),
        }

    async def preview_pull_from_purchase_receipt(
        self,
        tenant_id: int,
        receipt_id: int,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"采购入库单不存在: {receipt_id}")

        status = str(getattr(receipt, "status", "") or "").strip()
        receipt_gross = await purchase_receipt_settlement_gross_async(tenant_id, receipt)
        source_allowed = status in self._PR_ELIGIBLE_STATUSES and receipt_gross > 0
        preview_items = await self._build_preview_items_for_purchase_receipt(tenant_id, receipt)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="payable.pull_from_purchase_receipt.not_allowed",
            no_lines_reason="payable.pull_from_purchase_receipt.no_lines",
            already_pulled_reason="payable.pull_from_purchase_receipt.already_pulled",
        )
        code = str(receipt.receipt_code or receipt_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            build_purchase_receipt_finance_detail_lines,
        )

        detail_lines = await build_purchase_receipt_finance_detail_lines(
            tenant_id, receipt_id, "payable"
        )
        return {
            "target_type": "payable",
            "source_type": "purchase_receipt",
            "source_id": receipt_id,
            "source_code": code,
            "summary": (
                f"将从采购入库单 {code} 创建应付单（可应付 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"采购入库单 {code} 当前不可加载应付单"
            ),
            "items": preview_items,
            "detail_lines": detail_lines,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": "应付金额须与所选入库行合计一致；未勾选行时按入库行顺序自动分摊。",
            "supplier_id": receipt.supplier_id,
            "supplier_name": receipt.supplier_name,
            "purchase_order_id": receipt.purchase_order_id,
            "purchase_order_code": receipt.purchase_order_code,
            "max_push_total": pushable,
        }

    async def list_purchase_order_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        query = PurchaseOrder.filter(
            tenant_id=tenant_id,
            status__in=list(self._PO_ELIGIBLE_STATUSES),
            deleted_at__isnull=True,
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

        rows: List[Dict[str, Any]] = []
        for order in orders:
            oid = int(order.id)
            preview_items = await self._build_preview_items_for_purchase_order(
                tenant_id,
                order,
                pushed=pushed_map.get(oid, Decimal("0")),
            )
            gross = purchase_order_settlement_gross(order)
            allowed, reason = self._derive_pull_capability(
                source_allowed=gross > 0,
                preview_items=preview_items,
                not_allowed_reason="payable.pull_from_purchase_order.not_allowed",
                no_lines_reason="payable.pull_from_purchase_order.no_lines",
                already_pulled_reason="payable.pull_from_purchase_order.already_pulled",
            )
            code = str(order.order_code or oid)
            name = str(getattr(order, "supplier_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            rows.append(
                {
                    "id": oid,
                    "code": label,
                    "order_code": code,
                    "supplier_name": order.supplier_name,
                    "source_status": order.status,
                    "source_date": str(getattr(order, "order_date", "") or ""),
                    "amount": float(gross),
                    "capabilities": {
                        "pull_payable": {
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
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        query = PurchaseReceipt.filter(
            tenant_id=tenant_id,
            status__in=list(self._PR_ELIGIBLE_STATUSES),
            deleted_at__isnull=True,
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(Q(receipt_code__icontains=kw) | Q(supplier_name__icontains=kw))
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
            allowed, reason = self._derive_pull_capability(
                source_allowed=receipt_gross > 0,
                preview_items=preview_items,
                not_allowed_reason="payable.pull_from_purchase_receipt.not_allowed",
                no_lines_reason="payable.pull_from_purchase_receipt.no_lines",
                already_pulled_reason="payable.pull_from_purchase_receipt.already_pulled",
            )
            code = str(receipt.receipt_code or rid)
            name = str(getattr(receipt, "supplier_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            rows.append(
                {
                    "id": rid,
                    "code": label,
                    "receipt_code": code,
                    "supplier_id": int(receipt.supplier_id or 0) or None,
                    "supplier_name": receipt.supplier_name,
                    "source_status": receipt.status,
                    "source_date": str(
                        getattr(receipt, "receipt_time", "") or getattr(receipt, "created_at", "") or ""
                    ),
                    "amount": float(receipt_gross),
                    "capabilities": {
                        "pull_payable": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def _validate_pull_receipt_lines_for_receipts(
        self,
        tenant_id: int,
        receipt_ids: Sequence[int],
        pull_receipt_lines: Sequence[Any],
        total_amount: Decimal,
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
            await build_slices_from_pull_receipt_line_selections(
                tenant_id,
                int(rid),
                "payable",
                selections,
                header_amount=part,
            )
        if abs(subtotal - Decimal(total_amount)) > Decimal("0.01"):
            raise BusinessLogicError(
                f"所选入库行金额合计 {subtotal} 与单据金额 {total_amount} 不一致"
            )

    async def record_multi_receipt_payable_occupancy(
        self,
        tenant_id: int,
        receipt_ids: Sequence[int],
        payable_id: int,
        total_amount: Decimal,
        *,
        pull_receipt_lines: Optional[Sequence[Any]] = None,
        created_by: int,
    ) -> None:
        from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
            record_purchase_receipt_payable_occupancy,
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
                await record_purchase_receipt_payable_occupancy(
                    tenant_id,
                    int(rid),
                    int(payable_id),
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
            await record_purchase_receipt_payable_occupancy(
                tenant_id,
                int(rid),
                int(payable_id),
                take,
                line_selections=None,
                created_by=created_by,
            )
            remaining -= take

    async def assert_pull_create_allowed(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        total_amount: Decimal,
        pull_receipt_lines: Optional[List[Any]] = None,
        pull_source_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        if source_type == "purchase_order":
            preview = await self.preview_pull_from_purchase_order(tenant_id, source_id)
        elif source_type == "purchase_receipt":
            ids = self._normalize_source_ids(pull_source_ids or [source_id])
            preview = (
                await self.preview_pull_from_purchase_receipts(tenant_id, ids)
                if len(ids) > 1
                else await self.preview_pull_from_purchase_receipt(tenant_id, ids[0])
            )
        else:
            raise BusinessLogicError(f"不支持的加载源单类型: {source_type}")
        if preview.get("has_blocking_issues"):
            reason = preview.get("blocking_reason") or "当前不可加载应付单"
            raise BusinessLogicError(reason)
        items = preview.get("items") or []
        if not items:
            raise BusinessLogicError("无可应付金额")
        max_push = Decimal(str(preview.get("max_push_total") or 0))
        if max_push <= 0:
            max_push = sum(
                Decimal(str(item.get("max_push_quantity") or 0)) for item in items
            )
        if total_amount > max_push:
            raise BusinessLogicError(f"应付金额 {total_amount} 超过可应付金额 {max_push}")
        if source_type == "purchase_receipt" and pull_receipt_lines:
            ids = self._normalize_source_ids(pull_source_ids or [source_id])
            if len(ids) > 1:
                await self._validate_pull_receipt_lines_for_receipts(
                    tenant_id, ids, pull_receipt_lines, total_amount
                )
            else:
                from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
                    build_slices_from_pull_receipt_line_selections,
                )

                await build_slices_from_pull_receipt_line_selections(
                    tenant_id,
                    ids[0],
                    "payable",
                    pull_receipt_lines,
                    header_amount=total_amount,
                )
        return preview

    async def create_pull_relation(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        source_code: str,
        payable_id: int,
        payable_code: str,
        created_by: int,
    ) -> None:
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate

        rel_svc = DocumentRelationNewService()
        await rel_svc.create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type=source_type,
                source_id=source_id,
                source_code=source_code,
                source_name=None,
                target_type="payable",
                target_id=payable_id,
                target_code=payable_code,
                target_name=None,
                relation_type="source",
                relation_mode="pull",
                relation_desc="加载创建应付单",
            ),
            created_by=created_by,
        )

    async def enrich_push_payment_capabilities(
        self,
        tenant_id: int,
        payables: List[Any],
    ) -> List[Dict[str, Any]]:
        """为应付单列表补充下推付款 capability（实际创建付款单在付款页加载）。"""
        from apps.kuaicaiwu.services.payment_pull_service import PaymentPullService

        if not payables:
            return []

        payment_pull = PaymentPullService()
        payable_ids = [int(p.id) for p in payables]
        code_by_id = {int(p.id): str(getattr(p, "payable_code", None) or p.id) for p in payables}
        reserved_map = await payment_pull._sum_reserved_unsettled_by_payable(
            tenant_id, payable_ids, code_by_id
        )

        enriched: List[Dict[str, Any]] = []
        for row in payables:
            pid = int(row.id)
            preview_items = await payment_pull._build_preview_items_for_payable(
                tenant_id,
                row,
                reserved_unsettled=reserved_map.get(pid, Decimal("0")),
            )
            allowed, reason = payment_pull._derive_pull_capability(
                source_allowed=payment_pull._payable_source_allowed(row),
                preview_items=preview_items,
                not_allowed_reason="payment.pull_from_payable.not_allowed",
                no_lines_reason="payment.pull_from_payable.no_lines",
                already_pulled_reason="payment.pull_from_payable.already_pulled",
            )
            payload = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            existing_caps = dict(payload.get("capabilities") or {})
            existing_caps["push_payment"] = {
                "allowed": allowed,
                "reason": reason,
            }
            payload["capabilities"] = existing_caps
            enriched.append(payload)
        return enriched

    async def enrich_push_purchase_invoice_capabilities(
        self,
        tenant_id: int,
        payables: List[Any],
    ) -> List[Dict[str, Any]]:
        """为应付单列表补充下推进项发票 capability（实际创建进项发票在进项发票页加载）。"""
        from apps.kuaicaiwu.services.purchase_invoice_pull_service import PurchaseInvoicePullService

        if not payables:
            return []

        purchase_invoice_pull = PurchaseInvoicePullService()
        payable_ids = [int(p.id) for p in payables]
        code_by_id = {int(p.id): str(getattr(p, "payable_code", None) or p.id) for p in payables}
        pushed_map = await purchase_invoice_pull._sum_pushed_totals_by_payable(
            tenant_id, payable_ids, code_by_id
        )

        enriched: List[Dict[str, Any]] = []
        for row in payables:
            pid = int(row.id)
            preview_items = await purchase_invoice_pull._build_preview_items_for_payable(
                tenant_id,
                row,
                pushed=pushed_map.get(pid, Decimal("0")),
            )
            source_allowed = purchase_invoice_pull._payable_source_allowed(row)
            # 有 PO 时预览会带上订单；无 PO（委外/手工等）仍允许开进项，挂应付即可
            allowed, reason = purchase_invoice_pull._derive_pull_capability(
                source_allowed=source_allowed,
                preview_items=preview_items,
                not_allowed_reason="purchase_invoice.pull_from_payable.not_allowed",
                no_lines_reason="purchase_invoice.pull_from_payable.no_lines",
                already_pulled_reason="purchase_invoice.pull_from_payable.already_pulled",
                source_type=str(getattr(row, "source_type", "") or ""),
                status=str(getattr(row, "status", "") or ""),
            )
            payload = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            existing_caps = dict(payload.get("capabilities") or {})
            existing_caps["push_purchase_invoice"] = {
                "allowed": allowed,
                "reason": reason,
            }
            payload["capabilities"] = existing_caps
            if (
                is_purchase_return_offset_payable(getattr(row, "source_type", None))
                or is_outsource_return_offset_payable(getattr(row, "source_type", None))
                or str(getattr(row, "status", "") or "").strip() == "已冲减"
            ):
                payload["invoiced_amount"] = Decimal("0")
                payload["remaining_invoice_amount"] = Decimal("0")
                payload["invoice_status"] = "未收票"
            else:
                invoiced, remaining_inv, inv_status = derive_invoice_amount_status(
                    pushed_map.get(pid, Decimal("0")),
                    Decimal(str(payload.get("total_amount") or 0)),
                    status_none="未收票",
                    status_partial="部分收票",
                    status_full="已收票",
                )
                payload["invoiced_amount"] = invoiced
                payload["remaining_invoice_amount"] = remaining_inv
                payload["invoice_status"] = inv_status
            enriched.append(payload)
        return enriched

    async def enrich_push_capabilities(
        self,
        tenant_id: int,
        payables: List[Any],
    ) -> List[Dict[str, Any]]:
        """合并下推付款与下推进项发票 capability。"""
        payment_enriched = await self.enrich_push_payment_capabilities(tenant_id, payables)
        invoice_enriched = await self.enrich_push_purchase_invoice_capabilities(tenant_id, payables)
        merged: List[Dict[str, Any]] = []
        for pay_row, inv_row in zip(payment_enriched, invoice_enriched):
            caps = dict(pay_row.get("capabilities") or {})
            inv_caps = (inv_row.get("capabilities") or {}).get("push_purchase_invoice")
            if inv_caps is not None:
                caps["push_purchase_invoice"] = inv_caps
            merged.append(
                {
                    **pay_row,
                    "capabilities": caps,
                    "invoiced_amount": inv_row.get("invoiced_amount"),
                    "remaining_invoice_amount": inv_row.get("remaining_invoice_amount"),
                    "invoice_status": inv_row.get("invoice_status"),
                }
            )
        return merged
