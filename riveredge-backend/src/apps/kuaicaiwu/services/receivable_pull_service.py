"""
应收单加载门控：销售订单/销售出库候选列表、预览、已应收金额汇总；列表下推收款 capability。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from tortoise.queryset import Q

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.receivable import Receivable
from apps.kuaicaiwu.services.finance_service import derive_invoice_amount_status
from apps.kuaizhizao.models.document_relation import DocumentRelation
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

logger = logging.getLogger(__name__)


class ReceivablePullService(AppBaseService[Receivable]):
    """应收单加载门控服务"""

    _SO_ELIGIBLE_STATUSES = frozenset(
        {
            "AUDITED",
            "CONFIRMED",
            "IN_PROGRESS",
            "COMPLETED",
            "已审核",
            "已确认",
            "进行中",
            "已完成",
            "部分出库",
            "已出库",
        }
    )

    _SD_ELIGIBLE_STATUSES = frozenset({"已出库", "已完成", "部分出库", "SHIPPED", "COMPLETED"})

    _SO_LEGACY_SOURCE_TYPES = frozenset({"sales_order", "销售订单"})
    _SD_LEGACY_SOURCE_TYPES = frozenset({"sales_delivery", "销售出库"})

    def _normalize_source_ids(self, source_ids: Sequence[int]) -> List[int]:
        seen: set[int] = set()
        ordered: List[int] = []
        for raw in source_ids:
            sid = int(raw)
            if sid <= 0 or sid in seen:
                continue
            seen.add(sid)
            ordered.append(sid)
        if not ordered:
            raise BusinessLogicError("请至少选择一张源单")
        return ordered

    async def _load_source_document_totals(
        self,
        tenant_id: int,
        source_type: str,
        source_ids: List[int],
    ) -> Dict[int, Decimal]:
        result: Dict[int, Decimal] = {sid: Decimal("0") for sid in source_ids}
        if not source_ids:
            return result
        if source_type == "sales_order":
            from apps.kuaizhizao.models.sales_order import SalesOrder

            rows = await SalesOrder.filter(
                tenant_id=tenant_id, id__in=source_ids, deleted_at__isnull=True
            ).only("id", "total_amount")
            for row in rows:
                result[int(row.id)] = Decimal(str(row.total_amount or 0))
        elif source_type == "sales_delivery":
            from apps.kuaizhizao.models.sales_delivery import SalesDelivery

            rows = await SalesDelivery.filter(
                tenant_id=tenant_id, id__in=source_ids, deleted_at__isnull=True
            ).only("id", "total_amount")
            for row in rows:
                result[int(row.id)] = Decimal(str(row.total_amount or 0))
        return result

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
        if source_type == "sales_order":
            return self._SO_LEGACY_SOURCE_TYPES
        if source_type == "sales_delivery":
            return self._SD_LEGACY_SOURCE_TYPES
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
            target_type="receivable",
        ).all()
        receivable_ids = sorted(
            {int(r.target_id) for r in relations if r.target_id}
        )
        linked_receivable_ids: set[int] = set()

        if receivable_ids:
            all_rels = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type=source_type,
                target_type="receivable",
                target_id__in=receivable_ids,
            ).order_by("id").all()
            sources_by_ar: Dict[int, List[int]] = defaultdict(list)
            for rel in all_rels:
                if rel.target_id and rel.source_id:
                    sources_by_ar[int(rel.target_id)].append(int(rel.source_id))
            sibling_ids = sorted({sid for sids in sources_by_ar.values() for sid in sids})
            doc_totals = await self._load_source_document_totals(
                tenant_id, source_type, sibling_ids
            )
            allocated: Dict[int, Decimal] = {sid: Decimal("0") for sid in sibling_ids}
            receivables = await Receivable.filter(
                tenant_id=tenant_id,
                id__in=receivable_ids,
                deleted_at__isnull=True,
            ).order_by("id")
            for rec in receivables:
                rid = int(rec.id)
                linked_receivable_ids.add(rid)
                amount = Decimal(str(rec.total_amount or 0))
                sids = sources_by_ar.get(rid, [])
                if not sids:
                    continue
                rem = amount
                for sid in sids:
                    if rem <= 0:
                        break
                    room = max(Decimal("0"), doc_totals.get(sid, Decimal("0")) - allocated[sid])
                    take = min(rem, room)
                    if take > 0:
                        allocated[sid] += take
                        rem -= take
                if rem > 0:
                    allocated[sids[-1]] = allocated.get(sids[-1], Decimal("0")) + rem
            for sid in source_ids:
                result[sid] = result.get(sid, Decimal("0")) + allocated.get(sid, Decimal("0"))

        legacy_types = list(self._legacy_source_types(source_type))
        if legacy_types:
            legacy_rows = await Receivable.filter(
                tenant_id=tenant_id,
                source_id__in=source_ids,
                source_type__in=legacy_types,
                deleted_at__isnull=True,
            )
            for rec in legacy_rows:
                if int(rec.id) in linked_receivable_ids:
                    continue
                sid = int(rec.source_id)
                if sid in result:
                    result[sid] = result.get(sid, Decimal("0")) + Decimal(str(rec.total_amount or 0))

        codes = [c for c in code_by_id.values() if c]
        if codes:
            code_to_id = {str(v).strip(): k for k, v in code_by_id.items() if v}
            orphan_rows = await Receivable.filter(
                tenant_id=tenant_id,
                source_code__in=codes,
                deleted_at__isnull=True,
            )
            for rec in orphan_rows:
                if int(rec.id) in linked_receivable_ids:
                    continue
                sid = code_to_id.get(str(rec.source_code or "").strip())
                if sid is not None:
                    result[sid] = result.get(sid, Decimal("0")) + Decimal(str(rec.total_amount or 0))
        return result

    async def _sum_unused_prepayment_for_sales_order(
        self,
        tenant_id: int,
        sales_order_id: Optional[int],
    ) -> Decimal:
        """销售订单关联预收收款单的未核销余额（用于冲减可应收）。"""
        if not sales_order_id:
            return Decimal("0")
        from apps.kuaicaiwu.models.receipt import Receipt

        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="sales_order",
            source_id=int(sales_order_id),
            target_type="receipt",
        ).all()
        receipt_ids = [int(r.target_id) for r in relations if r.target_id]
        if not receipt_ids:
            return Decimal("0")
        receipts = await Receipt.filter(
            tenant_id=tenant_id,
            id__in=receipt_ids,
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount__gt=0,
            deleted_at__isnull=True,
        ).all()
        total = Decimal("0")
        for row in receipts:
            total += Decimal(str(row.unsettled_amount or 0))
        return max(Decimal("0"), total.quantize(Decimal("0.01")))

    def _build_preview_item(
        self,
        *,
        source_id: int,
        source_code: str,
        customer_name: str,
        quantity: Decimal,
        pushed: Decimal,
        prepaid_offset: Decimal = Decimal("0"),
    ) -> Dict[str, Any]:
        qty = float(quantity)
        pushed_f = float(pushed)
        prepaid_f = float(max(Decimal("0"), prepaid_offset))
        max_push = float(max(Decimal("0"), quantity - pushed))
        return {
            "item_id": int(source_id),
            "source_code": source_code,
            "customer_name": customer_name,
            "quantity": qty,
            "pushed_quantity": pushed_f,
            "prepaid_offset": prepaid_f,
            "max_push_quantity": max_push,
        }

    async def _build_preview_items_for_sales_order(
        self,
        tenant_id: int,
        order: Any,
        *,
        pushed: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        oid = int(order.id)
        code = str(order.order_code or oid)
        total = Decimal(str(order.total_amount or 0))
        if total <= 0:
            return []
        if pushed is None:
            pushed_map = await self._sum_pushed_totals_by_source(
                tenant_id, "sales_order", [oid], {oid: code}
            )
            pushed = pushed_map.get(oid, Decimal("0"))
        prepaid = await self._sum_unused_prepayment_for_sales_order(tenant_id, oid)
        return [
            self._build_preview_item(
                source_id=oid,
                source_code=code,
                customer_name=str(getattr(order, "customer_name", "") or ""),
                quantity=total,
                pushed=pushed,
                prepaid_offset=prepaid,
            )
        ]

    async def _build_preview_items_for_sales_delivery(
        self,
        tenant_id: int,
        delivery: Any,
        *,
        pushed: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        did = int(delivery.id)
        code = str(delivery.delivery_code or did)
        total = Decimal(str(delivery.total_amount or 0))
        if total <= 0:
            return []
        if pushed is None:
            pushed_map = await self._sum_pushed_totals_by_source(
                tenant_id, "sales_delivery", [did], {did: code}
            )
            pushed = pushed_map.get(did, Decimal("0"))
        so_id = getattr(delivery, "sales_order_id", None)
        prepaid = await self._sum_unused_prepayment_for_sales_order(
            tenant_id, int(so_id) if so_id else None
        )
        return [
            self._build_preview_item(
                source_id=did,
                source_code=code,
                customer_name=str(getattr(delivery, "customer_name", "") or ""),
                quantity=total,
                pushed=pushed,
                prepaid_offset=prepaid,
            )
        ]

    async def preview_pull_from_sales_order(
        self,
        tenant_id: int,
        order_id: int,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.sales_order import SalesOrder

        order = await SalesOrder.get_or_none(
            tenant_id=tenant_id, id=order_id, deleted_at__isnull=True
        )
        if not order:
            raise NotFoundError(f"销售订单不存在: {order_id}")

        status = str(getattr(order, "status", "") or "").strip()
        source_allowed = status in self._SO_ELIGIBLE_STATUSES and Decimal(str(order.total_amount or 0)) > 0
        preview_items = await self._build_preview_items_for_sales_order(tenant_id, order)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="receivable.pull_from_sales_order.not_allowed",
            no_lines_reason="receivable.pull_from_sales_order.no_lines",
            already_pulled_reason="receivable.pull_from_sales_order.already_pulled",
        )
        code = str(order.order_code or order_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        prepaid = float(preview_items[0].get("prepaid_offset") or 0) if preview_items else 0.0
        prepaid_tip = f"；已扣未核销预收 ¥{prepaid:,.2f}" if prepaid > 0 else ""
        return {
            "target_type": "receivable",
            "source_type": "sales_order",
            "source_id": order_id,
            "source_code": code,
            "summary": (
                f"将从销售订单 {code} 创建应收单（可应收 ¥{pushable:,.2f}{prepaid_tip}）"
                if preview_items and allowed
                else f"销售订单 {code} 当前不可加载应收单"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": (
                "可应收=单据金额−已应收−未核销预收；创建时将自动核销预收。"
                "删除未审核应收单后，可应收金额自动回退。"
            ),
            "customer_id": order.customer_id,
            "customer_name": order.customer_name,
            "sales_order_id": order.id,
            "sales_order_code": code,
        }

    async def preview_pull_from_sales_delivery(
        self,
        tenant_id: int,
        delivery_id: int,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.sales_delivery import SalesDelivery

        delivery = await SalesDelivery.get_or_none(
            tenant_id=tenant_id, id=delivery_id, deleted_at__isnull=True
        )
        if not delivery:
            raise NotFoundError(f"销售出库单不存在: {delivery_id}")

        status = str(getattr(delivery, "status", "") or "").strip()
        source_allowed = status in self._SD_ELIGIBLE_STATUSES and Decimal(
            str(delivery.total_amount or 0)
        ) > 0
        preview_items = await self._build_preview_items_for_sales_delivery(tenant_id, delivery)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="receivable.pull_from_sales_delivery.not_allowed",
            no_lines_reason="receivable.pull_from_sales_delivery.no_lines",
            already_pulled_reason="receivable.pull_from_sales_delivery.already_pulled",
        )
        code = str(delivery.delivery_code or delivery_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        prepaid = float(preview_items[0].get("prepaid_offset") or 0) if preview_items else 0.0
        prepaid_tip = f"；已扣未核销预收 ¥{prepaid:,.2f}" if prepaid > 0 else ""
        return {
            "target_type": "receivable",
            "source_type": "sales_delivery",
            "source_id": delivery_id,
            "source_code": code,
            "summary": (
                f"将从销售出库单 {code} 创建应收单（可应收 ¥{pushable:,.2f}{prepaid_tip}）"
                if preview_items and allowed
                else f"销售出库单 {code} 当前不可加载应收单"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": (
                "可应收=单据金额−已应收−未核销预收；创建时将自动核销预收。"
                "删除未审核应收单后，可应收金额自动回退。"
            ),
            "customer_id": delivery.customer_id,
            "customer_name": delivery.customer_name,
            "sales_order_id": getattr(delivery, "sales_order_id", None),
            "sales_order_code": getattr(delivery, "sales_order_code", None),
            "max_push_total": pushable,
        }

    async def preview_pull_from_sales_deliveries(
        self,
        tenant_id: int,
        delivery_ids: Sequence[int],
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(delivery_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_sales_delivery(tenant_id, ids[0])

        merged_items: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        customer_id: Optional[int] = None
        customer_name: Optional[str] = None
        codes: List[str] = []
        prepaid_by_so: Dict[int, Decimal] = {}
        primary_so_id: Optional[int] = None
        primary_so_code: Optional[str] = None

        for did in ids:
            fragment = await self.preview_pull_from_sales_delivery(tenant_id, did)
            frag_customer = int(fragment.get("customer_id") or 0)
            if customer_id is None:
                customer_id = frag_customer
                customer_name = str(fragment.get("customer_name") or "")
            elif frag_customer != int(customer_id or 0):
                raise BusinessLogicError("多笔一起加载须为同一客户")

            codes.append(str(fragment.get("source_code") or did))
            if fragment.get("has_blocking_issues"):
                reason = str(fragment.get("blocking_reason") or "")
                if reason:
                    blocking_reasons.append(reason)
            merged_items.extend(fragment.get("items") or [])
            so_id_raw = fragment.get("sales_order_id")
            if so_id_raw:
                so_id = int(so_id_raw)
                if primary_so_id is None:
                    primary_so_id = so_id
                    primary_so_code = fragment.get("sales_order_code")
                if so_id not in prepaid_by_so:
                    prepaid_offset = Decimal("0")
                    for item in fragment.get("items") or []:
                        prepaid_offset = max(
                            prepaid_offset,
                            Decimal(str(item.get("prepaid_offset") or 0)),
                        )
                    prepaid_by_so[so_id] = prepaid_offset

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        prepaid_total = sum(prepaid_by_so.values(), Decimal("0"))
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        return {
            "target_type": "receivable",
            "source_type": "sales_delivery",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 张销售出库单创建应收单（可应收合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选出库单当前不可一起加载应收单"
            ),
            "items": merged_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": (
                "可应收=各出库单金额−已应收合计−未核销预收；创建时将自动核销预收。"
                "删除未审核应收单后，可应收金额自动回退。"
            ),
            "customer_id": customer_id,
            "customer_name": customer_name,
            "sales_order_id": primary_so_id,
            "sales_order_code": primary_so_code,
            "max_push_total": float(max_push_total),
            "prepaid_offset_total": float(prepaid_total),
        }

    async def list_sales_order_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.sales_order import SalesOrder

        query = SalesOrder.filter(
            tenant_id=tenant_id,
            status__in=list(self._SO_ELIGIBLE_STATUSES),
            deleted_at__isnull=True,
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(Q(order_code__icontains=kw) | Q(customer_name__icontains=kw))
        total = await query.count()
        orders = await query.offset(skip).limit(limit).order_by("-created_at")
        order_ids = [int(o.id) for o in orders]
        if not order_ids:
            return {"data": [], "total": total, "success": True}

        code_by_id = {int(o.id): str(o.order_code or o.id) for o in orders}
        pushed_map = await self._sum_pushed_totals_by_source(
            tenant_id, "sales_order", order_ids, code_by_id
        )

        rows: List[Dict[str, Any]] = []
        for order in orders:
            oid = int(order.id)
            preview_items = await self._build_preview_items_for_sales_order(
                tenant_id,
                order,
                pushed=pushed_map.get(oid, Decimal("0")),
            )
            allowed, reason = self._derive_pull_capability(
                source_allowed=Decimal(str(order.total_amount or 0)) > 0,
                preview_items=preview_items,
                not_allowed_reason="receivable.pull_from_sales_order.not_allowed",
                no_lines_reason="receivable.pull_from_sales_order.no_lines",
                already_pulled_reason="receivable.pull_from_sales_order.already_pulled",
            )
            code = str(order.order_code or oid)
            name = str(getattr(order, "customer_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            rows.append(
                {
                    "id": oid,
                    "code": label,
                    "order_code": code,
                    "customer_name": order.customer_name,
                    "source_status": order.status,
                    "source_date": str(getattr(order, "order_date", "") or ""),
                    "amount": float(order.total_amount or 0),
                    "capabilities": {
                        "pull_receivable": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def list_sales_delivery_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.sales_delivery import SalesDelivery

        query = SalesDelivery.filter(
            tenant_id=tenant_id,
            status__in=list(self._SD_ELIGIBLE_STATUSES),
            deleted_at__isnull=True,
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(Q(delivery_code__icontains=kw) | Q(customer_name__icontains=kw))
        total = await query.count()
        deliveries = await query.offset(skip).limit(limit).order_by("-created_at")
        delivery_ids = [int(d.id) for d in deliveries]
        if not delivery_ids:
            return {"data": [], "total": total, "success": True}

        code_by_id = {int(d.id): str(d.delivery_code or d.id) for d in deliveries}
        pushed_map = await self._sum_pushed_totals_by_source(
            tenant_id, "sales_delivery", delivery_ids, code_by_id
        )

        rows: List[Dict[str, Any]] = []
        for delivery in deliveries:
            did = int(delivery.id)
            preview_items = await self._build_preview_items_for_sales_delivery(
                tenant_id,
                delivery,
                pushed=pushed_map.get(did, Decimal("0")),
            )
            allowed, reason = self._derive_pull_capability(
                source_allowed=Decimal(str(delivery.total_amount or 0)) > 0,
                preview_items=preview_items,
                not_allowed_reason="receivable.pull_from_sales_delivery.not_allowed",
                no_lines_reason="receivable.pull_from_sales_delivery.no_lines",
                already_pulled_reason="receivable.pull_from_sales_delivery.already_pulled",
            )
            code = str(delivery.delivery_code or did)
            name = str(getattr(delivery, "customer_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            rows.append(
                {
                    "id": did,
                    "code": label,
                    "delivery_code": code,
                    "customer_id": int(delivery.customer_id or 0) or None,
                    "customer_name": delivery.customer_name,
                    "source_status": delivery.status,
                    "source_date": str(
                        getattr(delivery, "delivery_time", "") or getattr(delivery, "created_at", "") or ""
                    ),
                    "amount": float(delivery.total_amount or 0),
                    "capabilities": {
                        "pull_receivable": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def assert_pull_create_allowed(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        total_amount: Decimal,
        pull_source_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        if source_type == "sales_order":
            preview = await self.preview_pull_from_sales_order(tenant_id, source_id)
        elif source_type == "sales_delivery":
            ids = self._normalize_source_ids(pull_source_ids or [source_id])
            preview = (
                await self.preview_pull_from_sales_deliveries(tenant_id, ids)
                if len(ids) > 1
                else await self.preview_pull_from_sales_delivery(tenant_id, ids[0])
            )
        else:
            raise BusinessLogicError(f"不支持的加载源单类型: {source_type}")
        if preview.get("has_blocking_issues"):
            reason = preview.get("blocking_reason") or "当前不可加载应收单"
            raise BusinessLogicError(reason)
        items = preview.get("items") or []
        if not items:
            raise BusinessLogicError("无可应收金额")
        max_push = Decimal(str(preview.get("max_push_total") or 0))
        if max_push <= 0:
            max_push = sum(
                Decimal(str(item.get("max_push_quantity") or 0)) for item in items
            )
        if total_amount > max_push:
            raise BusinessLogicError(f"应收金额 {total_amount} 超过可应收金额 {max_push}")
        return preview

    async def plan_pull_receivable_amounts(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        net_amount: Decimal,
        preview: Optional[Dict[str, Any]] = None,
        recognition_gross: bool = False,
        pull_source_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        """
        计算应收开立金额与应自动核销的预收。

        - recognition_gross=True（出库/入库自动立账）：net_amount=本次立账全额，预收冲 min(全额, 未核销预收)
        - recognition_gross=False（手工拉单）：net_amount=期望待收净额，开立=净额+预收冲销
        """
        preview = preview or await self.assert_pull_create_allowed(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            total_amount=net_amount,
            pull_source_ids=pull_source_ids,
        )
        items = preview.get("items") or []
        if not items:
            raise BusinessLogicError("无可应收金额")
        net = Decimal(str(net_amount)).quantize(Decimal("0.01"))
        remaining_gross = Decimal(str(preview.get("max_push_total") or 0)).quantize(
            Decimal("0.01")
        )
        if remaining_gross <= 0:
            remaining_gross = sum(
                Decimal(str(item.get("max_push_quantity") or 0)) for item in items
            ).quantize(Decimal("0.01"))
        prepaid_avail = Decimal(str(preview.get("prepaid_offset_total") or 0))
        if prepaid_avail <= 0 and len(items) == 1:
            prepaid_avail = Decimal(str(items[0].get("prepaid_offset") or 0))
        prepaid_apply = Decimal("0.00")
        if recognition_gross:
            gross_this = net
            if gross_this > remaining_gross and remaining_gross > 0:
                gross_this = remaining_gross
            prepaid_apply = min(prepaid_avail, gross_this).quantize(Decimal("0.01"))
            ar_total = gross_this.quantize(Decimal("0.01"))
        else:
            prepaid_apply = min(
                prepaid_avail,
                max(Decimal("0"), remaining_gross - net),
            ).quantize(Decimal("0.01"))
            ar_total = (net + prepaid_apply).quantize(Decimal("0.01"))
        so_id = preview.get("sales_order_id")
        return {
            "preview": preview,
            "net_amount": net,
            "ar_total": ar_total,
            "prepaid_apply": prepaid_apply,
            "sales_order_id": int(so_id) if so_id else None,
        }

    async def apply_prepayment_to_receivable(
        self,
        tenant_id: int,
        *,
        receivable_id: int,
        sales_order_id: Optional[int],
        amount: Decimal,
        operator_id: int,
    ) -> Decimal:
        """按 FIFO 将销售订单预收收款单核销到应收单，返回实际核销金额。"""
        apply_total = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
        if apply_total <= 0 or not sales_order_id:
            return Decimal("0.00")

        from apps.kuaicaiwu.models.receipt import Receipt
        from apps.kuaicaiwu.services.prepayment_service import PrepaymentService

        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="sales_order",
            source_id=int(sales_order_id),
            target_type="receipt",
        ).order_by("id").all()
        receipt_ids = [int(r.target_id) for r in relations if r.target_id]
        if not receipt_ids:
            return Decimal("0.00")

        receipts = await Receipt.filter(
            tenant_id=tenant_id,
            id__in=receipt_ids,
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount__gt=0,
            deleted_at__isnull=True,
        ).order_by("id").select_for_update()
        if not receipts and apply_total > 0:
            from infra.exceptions.exceptions import BusinessLogicError

            raise BusinessLogicError(
                f"预收冲应收未找到可核销预收收款单（销售订单 {sales_order_id}）"
            )
        remaining = apply_total
        applied = Decimal("0.00")
        prep_svc = PrepaymentService()
        from infra.domain.tenant_context import get_current_tenant_id, set_current_tenant_id

        prev_tenant = get_current_tenant_id()
        set_current_tenant_id(int(tenant_id))
        try:
            for receipt in receipts:
                if remaining <= 0:
                    break
                receivable = await Receivable.get_or_none(
                    tenant_id=tenant_id, id=int(receivable_id), deleted_at__isnull=True
                )
                if not receivable:
                    break
                rec_remaining = Decimal(str(receivable.remaining_amount or 0)).quantize(
                    Decimal("0.01")
                )
                if rec_remaining <= 0:
                    break
                fresh_receipt = await Receipt.get_or_none(
                    tenant_id=tenant_id, id=int(receipt.id), deleted_at__isnull=True
                )
                if not fresh_receipt:
                    continue
                unsettled = Decimal(str(fresh_receipt.unsettled_amount or 0)).quantize(
                    Decimal("0.01")
                )
                if unsettled <= 0:
                    continue
                chunk = min(remaining, unsettled, rec_remaining).quantize(Decimal("0.01"))
                if chunk <= 0:
                    continue
                await prep_svc.apply_receipt_to_receivable(
                    tenant_id,
                    receipt_id=int(fresh_receipt.id),
                    receivable_id=int(receivable_id),
                    amount=chunk,
                    operator_id=operator_id,
                )
                applied += chunk
                remaining -= chunk
        finally:
            set_current_tenant_id(prev_tenant)
        return applied.quantize(Decimal("0.01"))

    async def list_open_receivable_ids_for_sales_order(
        self,
        tenant_id: int,
        sales_order_id: int,
    ) -> List[int]:
        """同销售订单下仍有待收余额的应收单（出库立账 + 订单直拉），FIFO 按 id。"""
        receivable_ids: set[int] = set()

        from apps.kuaizhizao.models.sales_delivery import SalesDelivery

        delivery_ids = await SalesDelivery.filter(
            tenant_id=tenant_id,
            sales_order_id=int(sales_order_id),
            deleted_at__isnull=True,
        ).values_list("id", flat=True)
        if delivery_ids:
            rows = await Receivable.filter(
                Q(tenant_id=tenant_id)
                & Q(source_id__in=list(delivery_ids))
                & Q(
                    source_type__in=(
                        "sales_delivery",
                        "销售出库",
                        "SalesDelivery",
                    )
                )
                & Q(remaining_amount__gt=0)
                & Q(deleted_at__isnull=True)
            ).order_by("id").all()
            for row in rows:
                receivable_ids.add(int(row.id))

        rel_rows = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="sales_order",
            source_id=int(sales_order_id),
            target_type="receivable",
        ).all()
        rel_ids = [int(r.target_id) for r in rel_rows if r.target_id]
        if rel_ids:
            rows = await Receivable.filter(
                tenant_id=tenant_id,
                id__in=rel_ids,
                remaining_amount__gt=0,
                deleted_at__isnull=True,
            ).all()
            for row in rows:
                receivable_ids.add(int(row.id))

        return sorted(receivable_ids)

    async def auto_apply_after_receivable_created(
        self,
        tenant_id: int,
        *,
        receivable_id: int,
        sales_order_id: Optional[int],
        operator_id: int,
    ) -> Decimal:
        """应收开立后按组织参数自动冲减同销售订单未核销预收。"""
        from apps.common.app_orm import finance_orm_ready

        if not finance_orm_ready():
            logger.warning(
                "auto_apply_after_receivable_created skip: finance_orm not ready "
                "tenant_id=%s receivable_id=%s",
                tenant_id,
                receivable_id,
            )
            return Decimal("0.00")
        if not sales_order_id:
            return Decimal("0.00")

        from infra.services.business_config_service import BusinessConfigService

        enabled = await BusinessConfigService().get_finance_auto_apply_customer_prepayment_to_receivable(
            tenant_id
        )
        if not enabled:
            return Decimal("0.00")

        receivable = await Receivable.get_or_none(
            tenant_id=tenant_id, id=int(receivable_id), deleted_at__isnull=True
        )
        if not receivable:
            raise BusinessLogicError(f"应收单不存在: {receivable_id}")
        remaining = Decimal(str(receivable.remaining_amount or 0)).quantize(Decimal("0.01"))
        if remaining <= 0:
            return Decimal("0.00")

        prepaid_avail = await self._sum_unused_prepayment_for_sales_order(
            tenant_id, int(sales_order_id)
        )
        apply_amount = min(remaining, prepaid_avail)
        if apply_amount <= 0:
            return Decimal("0.00")

        applied = await self.apply_prepayment_to_receivable(
            tenant_id,
            receivable_id=int(receivable_id),
            sales_order_id=int(sales_order_id),
            amount=apply_amount,
            operator_id=operator_id,
        )
        if applied <= 0:
            raise BusinessLogicError(
                f"预收自动冲应收未写入核销：应收单 {receivable_id} 应对冲 {apply_amount}，"
                f"实际核销 0（销售订单 {sales_order_id}）"
            )
        return applied

    async def auto_apply_after_prepayment_confirmed(
        self,
        tenant_id: int,
        *,
        receipt_id: int,
        operator_id: int,
    ) -> Decimal:
        """预收收款单确认后：若同销售订单已有未结清应收，按 FIFO 冲减。"""
        from apps.common.app_orm import finance_orm_ready
        from apps.kuaicaiwu.models.receipt import Receipt

        if not finance_orm_ready():
            return Decimal("0.00")

        from infra.services.business_config_service import BusinessConfigService

        enabled = await BusinessConfigService().get_finance_auto_apply_customer_prepayment_to_receivable(
            tenant_id
        )
        if not enabled:
            return Decimal("0.00")

        receipt = await Receipt.get_or_none(
            tenant_id=tenant_id, id=int(receipt_id), deleted_at__isnull=True
        )
        if not receipt:
            return Decimal("0.00")
        if str(getattr(receipt, "settlement_type", "") or "") != "prepayment":
            return Decimal("0.00")
        if str(getattr(receipt, "status", "") or "") != "Confirmed":
            return Decimal("0.00")
        unsettled = Decimal(str(receipt.unsettled_amount or 0)).quantize(Decimal("0.01"))
        if unsettled <= 0:
            return Decimal("0.00")

        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="sales_order",
            target_type="receipt",
            target_id=int(receipt_id),
        ).all()
        so_ids = sorted({int(r.source_id) for r in relations if r.source_id})
        if not so_ids:
            return Decimal("0.00")

        total_applied = Decimal("0.00")
        for so_id in so_ids:
            receivable_ids = await self.list_open_receivable_ids_for_sales_order(tenant_id, so_id)
            for receivable_id in receivable_ids:
                fresh = await Receipt.get_or_none(
                    tenant_id=tenant_id, id=int(receipt_id), deleted_at__isnull=True
                )
                rcpt_unsettled = Decimal(str(fresh.unsettled_amount if fresh else 0)).quantize(
                    Decimal("0.01")
                )
                if rcpt_unsettled <= 0:
                    break
                receivable = await Receivable.get_or_none(
                    tenant_id=tenant_id, id=int(receivable_id), deleted_at__isnull=True
                )
                if not receivable:
                    continue
                rem = Decimal(str(receivable.remaining_amount or 0)).quantize(Decimal("0.01"))
                if rem <= 0:
                    continue
                chunk = min(rcpt_unsettled, rem)
                applied = await self.apply_prepayment_to_receivable(
                    tenant_id,
                    receivable_id=int(receivable_id),
                    sales_order_id=int(so_id),
                    amount=chunk,
                    operator_id=operator_id,
                )
                total_applied += applied

        had_open_receivable = False
        for so_id in so_ids:
            if await self.list_open_receivable_ids_for_sales_order(tenant_id, so_id):
                had_open_receivable = True
                break
        if had_open_receivable and total_applied <= 0:
            fresh_rcpt = await Receipt.get_or_none(
                tenant_id=tenant_id, id=int(receipt_id), deleted_at__isnull=True
            )
            rcpt_left = Decimal(str(fresh_rcpt.unsettled_amount if fresh_rcpt else 0)).quantize(
                Decimal("0.01")
            )
            if rcpt_left > 0:
                raise BusinessLogicError(
                    f"预收确认后自动冲应收未写入核销：收款单 {receipt_id} 待核销 {rcpt_left}，"
                    "同销售订单仍有未结清应收"
                )
        return total_applied.quantize(Decimal("0.01"))

    async def create_pull_relation(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        source_code: str,
        receivable_id: int,
        receivable_code: str,
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
                target_type="receivable",
                target_id=receivable_id,
                target_code=receivable_code,
                target_name=None,
                relation_type="source",
                relation_mode="pull",
                relation_desc="加载创建应收单",
            ),
            created_by=created_by,
        )

    async def enrich_push_receipt_capabilities(
        self,
        tenant_id: int,
        receivables: List[Any],
    ) -> List[Dict[str, Any]]:
        """为应收单列表补充下推收款 capability（实际创建收款单在收款页加载）。"""
        from apps.kuaicaiwu.services.receipt_pull_service import ReceiptPullService

        if not receivables:
            return []

        receipt_pull = ReceiptPullService()
        receivable_ids = [int(r.id) for r in receivables]
        code_by_id = {int(r.id): str(getattr(r, "receivable_code", None) or r.id) for r in receivables}
        reserved_map = await receipt_pull._sum_reserved_unsettled_by_receivable(
            tenant_id, receivable_ids, code_by_id
        )

        enriched: List[Dict[str, Any]] = []
        for rec in receivables:
            rid = int(rec.id)
            preview_items = await receipt_pull._build_preview_items_for_receivable(
                tenant_id,
                rec,
                reserved_unsettled=reserved_map.get(rid, Decimal("0")),
            )
            allowed, reason = receipt_pull._derive_pull_capability(
                source_allowed=receipt_pull._receivable_source_allowed(rec),
                preview_items=preview_items,
                not_allowed_reason="receipt.pull_from_receivable.not_allowed",
                no_lines_reason="receipt.pull_from_receivable.no_lines",
                already_pulled_reason="receipt.pull_from_receivable.already_pulled",
                source_type=str(getattr(rec, "source_type", "") or ""),
            )
            payload = rec.model_dump() if hasattr(rec, "model_dump") else dict(rec)
            payload["capabilities"] = {
                "push_receipt": {
                    "allowed": allowed,
                    "reason": reason,
                }
            }
            enriched.append(payload)
        return enriched

    async def enrich_push_sales_invoice_capabilities(
        self,
        tenant_id: int,
        receivables: List[Any],
    ) -> List[Dict[str, Any]]:
        """为应收单列表补充下推销项发票 capability（实际创建销项发票在销项发票页加载）。"""
        from apps.kuaicaiwu.services.sales_invoice_service import SalesInvoiceService

        if not receivables:
            return []

        sales_invoice_pull = SalesInvoiceService()
        from apps.kuaicaiwu.constants.finance_source_types import is_sales_return_offset_receivable

        receivable_ids = [
            int(rec["id"] if isinstance(rec, dict) else rec.id) for rec in receivables
        ]
        code_by_id = {
            int(rec["id"] if isinstance(rec, dict) else rec.id): str(
                (rec.get("receivable_code") if isinstance(rec, dict) else getattr(rec, "receivable_code", None))
                or (rec["id"] if isinstance(rec, dict) else rec.id)
            )
            for rec in receivables
        }
        pushed_map = await sales_invoice_pull._sum_pushed_totals_by_receivable(
            tenant_id, receivable_ids, code_by_id
        )
        from apps.kuaicaiwu.services.return_open_balance_offset_service import (
            sum_goods_offset_for_receivable_ids,
        )

        goods_offset_map = await sum_goods_offset_for_receivable_ids(tenant_id, receivable_ids)

        enriched: List[Dict[str, Any]] = []
        for rec in receivables:
            rid = int(rec["id"] if isinstance(rec, dict) else rec.id)
            preview_items = await sales_invoice_pull._build_preview_items_for_receivable(
                tenant_id,
                rec,
                pushed=pushed_map.get(rid, Decimal("0")),
                goods_offset=goods_offset_map.get(rid, Decimal("0")),
            )
            allowed, reason = sales_invoice_pull._derive_pull_capability(
                source_allowed=sales_invoice_pull._receivable_source_allowed(rec),
                preview_items=preview_items,
                not_allowed_reason="sales_invoice.pull_from_receivable.not_allowed",
                no_lines_reason="sales_invoice.pull_from_receivable.no_lines",
                already_pulled_reason="sales_invoice.pull_from_receivable.already_pulled",
                source_type=str(
                    (rec.get("source_type") if isinstance(rec, dict) else getattr(rec, "source_type", ""))
                    or ""
                ),
            )
            payload = dict(rec) if isinstance(rec, dict) else (
                rec.model_dump() if hasattr(rec, "model_dump") else dict(rec)
            )
            existing_caps = dict(payload.get("capabilities") or {})
            existing_caps["push_sales_invoice"] = {
                "allowed": allowed,
                "reason": reason,
            }
            payload["capabilities"] = existing_caps
            source_type = str(
                (rec.get("source_type") if isinstance(rec, dict) else getattr(rec, "source_type", ""))
                or ""
            )
            status = str(
                (rec.get("status") if isinstance(rec, dict) else getattr(rec, "status", "")) or ""
            ).strip()
            if is_sales_return_offset_receivable(source_type) or status == "已冲减":
                payload["invoiced_amount"] = Decimal("0")
                payload["remaining_invoice_amount"] = Decimal("0")
                payload["invoice_status"] = "未开票"
            else:
                total_amount = Decimal(str(payload.get("total_amount") or 0))
                goods_offset = goods_offset_map.get(rid, Decimal("0"))
                effective_invoice_total = max(
                    Decimal("0"),
                    total_amount - max(Decimal("0"), goods_offset),
                )
                invoiced, remaining_inv, inv_status = derive_invoice_amount_status(
                    pushed_map.get(rid, Decimal("0")),
                    effective_invoice_total,
                    status_none="未开票",
                    status_partial="部分开票",
                    status_full="已开票",
                )
                payload["invoiced_amount"] = invoiced
                payload["remaining_invoice_amount"] = remaining_inv
                payload["invoice_status"] = inv_status
            enriched.append(payload)
        return enriched
