"""
收款单加载门控：应收单候选列表、预览、已收款/待占用金额汇总。
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from tortoise.queryset import Q

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.receipt import Receipt
from apps.kuaicaiwu.models.receivable import Receivable
from apps.kuaizhizao.models.document_relation import DocumentRelation
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError


class ReceiptPullService(AppBaseService[Receipt]):
    """收款单加载门控服务"""

    _EXCLUDED_RECEIPT_STATUSES = frozenset({"Cancelled"})
    # 仅已确认收款单占用应收可加载额度；草稿未过账不占额度（与 finance_voucher_posting 一致）
    _RESERVED_RECEIPT_STATUSES = frozenset({"Confirmed"})

    _RECEIVABLE_ELIGIBLE_REVIEW = frozenset({"已审核"})

    def _derive_pull_capability(
        self,
        *,
        source_allowed: bool,
        preview_items: List[Dict[str, Any]],
        not_allowed_reason: str,
        no_lines_reason: str,
        already_pulled_reason: str,
        source_type: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        from apps.kuaicaiwu.constants.finance_source_types import is_sales_return_offset_receivable

        if is_sales_return_offset_receivable(source_type):
            return False, "receipt.pull_from_receivable.sales_return_offset"
        if not source_allowed:
            return False, not_allowed_reason
        if not preview_items:
            return False, no_lines_reason
        pushable = any(float(row.get("max_push_quantity") or 0) > 0 for row in preview_items)
        if not pushable:
            return False, already_pulled_reason
        return True, None

    async def _sum_reserved_unsettled_by_receivable(
        self,
        tenant_id: int,
        receivable_ids: List[int],
        code_by_id: Dict[int, str],
    ) -> Dict[int, Decimal]:
        result: Dict[int, Decimal] = {rid: Decimal("0") for rid in receivable_ids}
        if not receivable_ids:
            return result

        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="receivable",
            source_id__in=receivable_ids,
            target_type="receipt",
        ).all()
        receipt_by_receivable: Dict[int, List[int]] = {}
        for rel in relations:
            if rel.source_id and rel.target_id:
                receipt_by_receivable.setdefault(int(rel.source_id), []).append(int(rel.target_id))

        all_receipt_ids = {rid for ids in receipt_by_receivable.values() for rid in ids}
        receipt_map: Dict[int, Receipt] = {}
        if all_receipt_ids:
            rows = await Receipt.filter(
                tenant_id=tenant_id,
                id__in=list(all_receipt_ids),
                deleted_at__isnull=True,
                status__in=list(self._RESERVED_RECEIPT_STATUSES),
            ).all()
            receipt_map = {int(r.id): r for r in rows}

        for receivable_id, receipt_ids in receipt_by_receivable.items():
            reserved = Decimal("0")
            for receipt_id in receipt_ids:
                receipt = receipt_map.get(receipt_id)
                if receipt:
                    reserved += Decimal(str(receipt.unsettled_amount or 0))
            result[receivable_id] = reserved

        # 占用金额仅认 DocumentRelation；不再全表扫 notes（列表路径性能陷阱）。
        _ = code_by_id
        return result

    def _build_preview_item(
        self,
        *,
        receivable: Any,
        reserved_unsettled: Decimal,
    ) -> Dict[str, Any]:
        rid = int(receivable.id)
        code = str(receivable.receivable_code or rid)
        total = Decimal(str(receivable.total_amount or 0))
        received = Decimal(str(receivable.received_amount or 0))
        remaining = Decimal(str(receivable.remaining_amount or 0))
        max_push = max(Decimal("0"), remaining - reserved_unsettled)
        return {
            "item_id": rid,
            "source_code": code,
            "customer_name": str(getattr(receivable, "customer_name", "") or ""),
            "quantity": float(total),
            "pushed_quantity": float(received),
            "max_push_quantity": float(max_push),
        }

    async def _build_preview_items_for_receivable(
        self,
        tenant_id: int,
        receivable: Any,
        *,
        reserved_unsettled: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        total = Decimal(str(receivable.total_amount or 0))
        if total <= 0:
            return []
        rid = int(receivable.id)
        if reserved_unsettled is None:
            code = str(receivable.receivable_code or rid)
            reserved_map = await self._sum_reserved_unsettled_by_receivable(
                tenant_id, [rid], {rid: code}
            )
            reserved_unsettled = reserved_map.get(rid, Decimal("0"))
        return [
            self._build_preview_item(
                receivable=receivable,
                reserved_unsettled=reserved_unsettled,
            )
        ]

    def _receivable_source_allowed(self, receivable: Any) -> bool:
        from apps.kuaicaiwu.constants.finance_source_types import is_sales_return_offset_receivable

        source_type = (
            receivable.get("source_type")
            if isinstance(receivable, dict)
            else getattr(receivable, "source_type", None)
        )
        if is_sales_return_offset_receivable(source_type):
            return False
        status = str(
            (receivable.get("status") if isinstance(receivable, dict) else getattr(receivable, "status", ""))
            or ""
        ).strip()
        review = str(
            (receivable.get("review_status") if isinstance(receivable, dict) else getattr(receivable, "review_status", ""))
            or ""
        ).strip()
        remaining = Decimal(
            str(
                (receivable.get("remaining_amount") if isinstance(receivable, dict) else getattr(receivable, "remaining_amount", 0))
                or 0
            )
        )
        total = Decimal(
            str(
                (receivable.get("total_amount") if isinstance(receivable, dict) else getattr(receivable, "total_amount", 0))
                or 0
            )
        )
        if status in ("已结清", "已冲减") or remaining <= 0 or total <= 0:
            return False
        return review in self._RECEIVABLE_ELIGIBLE_REVIEW

    async def preview_pull_from_receivable(
        self,
        tenant_id: int,
        receivable_id: int,
        *,
        operator_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from apps.kuaicaiwu.services.return_open_balance_offset_service import (
            ReturnOpenBalanceOffsetService,
        )

        await ReturnOpenBalanceOffsetService().ensure_offsets_for_receivable(
            tenant_id,
            receivable_id,
            operator_id=int(operator_id or 0) or 0,
        )

        receivable = await Receivable.get_or_none(
            tenant_id=tenant_id, id=receivable_id, deleted_at__isnull=True
        )
        if not receivable:
            raise NotFoundError(f"应收单不存在: {receivable_id}")

        source_allowed = self._receivable_source_allowed(receivable)
        preview_items = await self._build_preview_items_for_receivable(tenant_id, receivable)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="receipt.pull_from_receivable.not_allowed",
            no_lines_reason="receipt.pull_from_receivable.no_lines",
            already_pulled_reason="receipt.pull_from_receivable.already_pulled",
            source_type=str(getattr(receivable, "source_type", "") or ""),
        )
        code = str(receivable.receivable_code or receivable_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        return {
            "target_type": "receipt",
            "source_type": "receivable",
            "source_id": receivable_id,
            "source_code": code,
            "summary": (
                f"将从应收单 {code} 创建收款单（可收款 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"应收单 {code} 当前不可加载收款单"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": "收款金额不可超过可收款金额；作废未核销收款单后，可收款金额自动回退。",
            "customer_id": receivable.customer_id,
            "customer_name": receivable.customer_name,
            "receivable_id": receivable.id,
            "receivable_code": code,
        }

    async def list_receivable_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = Receivable.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            remaining_amount__gt=0,
        ).exclude(status="已结清").exclude(status="已冲减").exclude(source_type="销售退货")
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(
                Q(receivable_code__icontains=kw) | Q(customer_name__icontains=kw)
            )
        total = await query.count()
        receivables = await query.offset(skip).limit(limit).order_by("-created_at")
        receivable_ids = [int(r.id) for r in receivables]
        if not receivable_ids:
            return {"data": [], "total": total, "success": True}

        code_by_id = {int(r.id): str(r.receivable_code or r.id) for r in receivables}
        reserved_map = await self._sum_reserved_unsettled_by_receivable(
            tenant_id, receivable_ids, code_by_id
        )

        rows: List[Dict[str, Any]] = []
        for receivable in receivables:
            rid = int(receivable.id)
            preview_items = await self._build_preview_items_for_receivable(
                tenant_id,
                receivable,
                reserved_unsettled=reserved_map.get(rid, Decimal("0")),
            )
            allowed, reason = self._derive_pull_capability(
                source_allowed=self._receivable_source_allowed(receivable),
                preview_items=preview_items,
                not_allowed_reason="receipt.pull_from_receivable.not_allowed",
                no_lines_reason="receipt.pull_from_receivable.no_lines",
                already_pulled_reason="receipt.pull_from_receivable.already_pulled",
                source_type=str(getattr(receivable, "source_type", "") or ""),
            )
            code = str(receivable.receivable_code or rid)
            name = str(getattr(receivable, "customer_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            rows.append(
                {
                    "id": rid,
                    "code": label,
                    "receivable_code": code,
                    "customer_id": receivable.customer_id,
                    "customer_name": receivable.customer_name,
                    "source_status": receivable.status,
                    "review_status": receivable.review_status,
                    "source_date": str(getattr(receivable, "due_date", "") or ""),
                    "amount": float(receivable.total_amount or 0),
                    "remaining_amount": float(receivable.remaining_amount or 0),
                    "capabilities": {
                        "pull_receipt": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

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

    async def preview_pull_from_receivables(
        self,
        tenant_id: int,
        receivable_ids: Sequence[int],
        *,
        operator_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(receivable_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_receivable(
                tenant_id, ids[0], operator_id=operator_id
            )

        merged_items: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        customer_id: Optional[int] = None
        customer_name: Optional[str] = None
        codes: List[str] = []

        for rid in ids:
            fragment = await self.preview_pull_from_receivable(
                tenant_id, rid, operator_id=operator_id
            )
            frag_customer = int(fragment.get("customer_id") or 0)
            if customer_id is None:
                customer_id = frag_customer
                customer_name = str(fragment.get("customer_name") or "")
            elif frag_customer != int(customer_id or 0):
                raise BusinessLogicError("多笔一起加载须为同一客户")

            codes.append(str(fragment.get("source_code") or rid))
            if fragment.get("has_blocking_issues"):
                reason = str(fragment.get("blocking_reason") or "")
                if reason:
                    blocking_reasons.append(reason)
            merged_items.extend(fragment.get("items") or [])

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        return {
            "target_type": "receipt",
            "source_type": "receivable",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 张应收单创建收款单（可收款合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选应收单当前不可一起加载收款单"
            ),
            "items": merged_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": "收款金额不可超过可收款合计；作废未核销收款单后，可收款金额自动回退。",
            "customer_id": customer_id,
            "customer_name": customer_name,
            "receivable_id": ids[0],
            "receivable_code": codes[0] if codes else None,
            "max_push_total": float(max_push_total),
        }

    async def list_sales_order_prepayment_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        customer_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """预收收款单：按客户列出可加载预收的销售订单（仅需收款权限，不走销售订单列表数据范围）。"""
        from tortoise.expressions import Q

        from apps.kuaizhizao.constants import DemandStatus
        from apps.kuaizhizao.models.sales_order import SalesOrder
        from apps.kuaizhizao.models.sales_order_milestone import SalesOrderMilestone
        from apps.kuaizhizao.services.document_action_policy.enricher import (
            _order_prepayment_linked_by_ids,
        )
        from apps.kuaizhizao.services.document_action_policy.sales_order import (
            derive_sales_order_capabilities,
        )

        if customer_id is None or int(customer_id) <= 0:
            return {"data": [], "total": 0, "success": True}

        audited_q = (
            Q(status=DemandStatus.AUDITED.value)
            | Q(status=DemandStatus.CONFIRMED.value)
            | Q(status__in=["已审核", "审核通过", "已确认", "AUDITED", "CONFIRMED"])
        )
        query = SalesOrder.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            customer_id=int(customer_id),
        ).filter(audited_q)
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(Q(order_code__icontains=kw) | Q(customer_name__icontains=kw))

        total = await query.count()
        orders = await query.offset(skip).limit(limit).order_by("-created_at")
        order_ids = [int(o.id) for o in orders]
        if not order_ids:
            return {"data": [], "total": total, "success": True}

        prepay_map = await _order_prepayment_linked_by_ids(
            tenant_id,
            order_ids,
            source_type="sales_order",
            target_type="receipt",
        )
        milestone_amounts: Dict[int, Decimal] = {}
        for sid, amt in await SalesOrderMilestone.filter(
            tenant_id=tenant_id,
            sales_order_id__in=order_ids,
            is_prepayment=True,
        ).values_list("sales_order_id", "planned_amount"):
            milestone_amounts[int(sid)] = Decimal(str(amt or 0))

        rows: List[Dict[str, Any]] = []
        for order in orders:
            oid = int(order.id)
            prepay_amt = Decimal(str(order.prepayment_amount or 0))
            if prepay_amt <= 0:
                prepay_amt = milestone_amounts.get(oid, Decimal("0"))
            caps = derive_sales_order_capabilities(
                order,
                has_prepayment_receipt=prepay_map.get(oid, False),
                has_items=True,
            )
            prepay_cap = caps.push_prepayment
            pullable = bool(prepay_cap.allowed) and prepay_amt > 0
            reason = prepay_cap.reason
            if prepay_amt <= 0:
                reason = "sales_order.push_prepayment.no_amount"
            code = str(order.order_code or oid)
            order_date = getattr(order, "order_date", None)
            rows.append(
                {
                    "id": oid,
                    "code": code,
                    "order_code": code,
                    "customer_id": order.customer_id,
                    "customer_name": order.customer_name,
                    "partnerName": order.customer_name,
                    "documentDate": str(order_date) if order_date else None,
                    "source_date": str(order_date) if order_date else "",
                    "amount": float(prepay_amt) if prepay_amt > 0 else None,
                    "status": order.status,
                    "review_status": getattr(order, "review_status", None),
                    "capabilities": {
                        "pull_prepayment": {
                            "allowed": pullable,
                            "reason": reason if not pullable else None,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def preview_pull_from_sales_order(
        self,
        tenant_id: int,
        sales_order_id: int,
        *,
        amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.models.sales_order import SalesOrder
        from apps.kuaizhizao.services.document_action_policy.enricher import (
            _order_prepayment_linked_by_ids,
        )
        from apps.kuaizhizao.services.document_action_policy.sales_order import (
            derive_sales_order_capabilities,
        )
        from apps.kuaizhizao.services.payment_application_line_materials import (
            lines_from_sales_order_items,
        )

        order = await SalesOrder.get_or_none(
            tenant_id=tenant_id, id=sales_order_id, deleted_at__isnull=True
        )
        if not order:
            raise NotFoundError(f"销售订单不存在: {sales_order_id}")

        prepay_map = await _order_prepayment_linked_by_ids(
            tenant_id,
            [sales_order_id],
            source_type="sales_order",
            target_type="receipt",
        )
        has_receipt = prepay_map.get(sales_order_id, False)
        max_push = Decimal(str(order.prepayment_amount or 0))
        caps = derive_sales_order_capabilities(order, has_prepayment_receipt=has_receipt)
        prepay_cap = caps.push_prepayment
        allowed = bool(prepay_cap.allowed) and max_push > 0
        preview_items: List[Dict[str, Any]] = []
        if allowed:
            req_amt = Decimal(str(amount)) if amount is not None else max_push
            if req_amt > max_push:
                raise ValidationError(f"收款金额超过可预收额度 {max_push}")
            if req_amt <= 0:
                raise ValidationError("收款金额必须大于 0")
            line_models = await lines_from_sales_order_items(
                tenant_id=tenant_id,
                order=order,
                request_amount=req_amt,
                line_kind="prepayment",
            )
            preview_items = [
                ln.model_dump(by_alias=True, mode="json") for ln in line_models
            ]
        code = str(order.order_code or sales_order_id)
        max_push_f = float(max_push)
        blocking_reason = prepay_cap.reason if not prepay_cap.allowed else (
            "sales_order.push_prepayment.no_amount" if max_push <= 0 else (
                "sales_order.push_prepayment.already_exists" if has_receipt else None
            )
        )
        return {
            "target_type": "receipt",
            "source_type": "sales_order",
            "source_id": sales_order_id,
            "source_code": code,
            "order_code": code,
            "max_push_quantity": max_push_f,
            "max_push_total": max_push_f,
            "source_order_amount": max_push_f,
            "summary": (
                f"将从销售订单 {code} 加载预收明细（可预收 ¥{max_push_f:,.2f}）"
                if allowed
                else f"销售订单 {code} 当前不可加载预收明细"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reason,
            "tip": "预收收款单须对应尚未关联预收收款单的销售订单；确认过账后关联销售订单。",
            "customer_id": order.customer_id,
            "customer_name": order.customer_name,
        }

    async def assert_pull_create_allowed(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        total_amount: Decimal,
        pull_source_ids: Optional[Sequence[int]] = None,
        operator_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized = str(source_type or "").strip()
        if normalized == "sales_order":
            preview = await self.preview_pull_from_sales_order(
                tenant_id, source_id, amount=total_amount
            )
            if preview.get("has_blocking_issues"):
                reason = preview.get("blocking_reason") or "当前不可加载预收明细"
                raise BusinessLogicError(reason)
            max_push = Decimal(
                str(preview.get("max_push_quantity") or preview.get("max_push_total") or 0)
            )
            if max_push <= 0:
                raise BusinessLogicError("无可预收金额")
            if total_amount > max_push:
                raise BusinessLogicError(f"收款金额 {total_amount} 超过可预收金额 {max_push}")
            return preview
        if normalized != "receivable":
            raise BusinessLogicError(f"不支持的加载源单类型: {source_type}")
        ids = self._normalize_source_ids(pull_source_ids or [source_id])
        preview = (
            await self.preview_pull_from_receivables(
                tenant_id, ids, operator_id=operator_id
            )
            if len(ids) > 1
            else await self.preview_pull_from_receivable(
                tenant_id, ids[0], operator_id=operator_id
            )
        )
        if preview.get("has_blocking_issues"):
            reason = preview.get("blocking_reason") or "当前不可加载收款单"
            raise BusinessLogicError(reason)
        items = preview.get("items") or []
        if not items:
            raise BusinessLogicError("无可收款金额")
        max_push = Decimal(str(preview.get("max_push_total") or 0))
        if max_push <= 0:
            max_push = sum(
                Decimal(str(item.get("max_push_quantity") or 0)) for item in items
            )
        if total_amount > max_push:
            raise BusinessLogicError(f"收款金额 {total_amount} 超过可收款金额 {max_push}")
        return preview

    async def create_pull_relation(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        source_code: str,
        receipt_id: int,
        receipt_code: str,
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
                target_type="receipt",
                target_id=receipt_id,
                target_code=receipt_code,
                target_name=None,
                relation_type="source",
                relation_mode="pull",
                relation_desc="加载创建收款单",
            ),
            created_by=created_by,
        )

    async def settle_pull_created_receipt(
        self,
        tenant_id: int,
        *,
        receivable_id: int,
        receipt_id: int,
        amount: Decimal,
        operator_id: int,
    ) -> None:
        """从应收单加载创建收款单后，立即核销至源应收（与 record_receipt 一致）。"""
        from apps.kuaicaiwu.services.finance_service import AccountSettlementService

        settlement_service = AccountSettlementService()
        await settlement_service.settle_receivable(
            tenant_id=tenant_id,
            receivable_id=receivable_id,
            receipt_id=receipt_id,
            amount=Decimal(amount),
            operator_id=operator_id,
        )

    async def align_draft_receipts_to_receivable_remaining(
        self,
        tenant_id: int,
        receivable_id: int,
    ) -> None:
        """应收剩余变化后，把仍挂在该应收上的草稿货款收款单总额/待核销下调到不超过剩余。

        已确认收款单不改。预收、退款单不参与占额。占额顺序与付款草稿相同。
        """
        receivable = await Receivable.get_or_none(
            tenant_id=tenant_id, id=int(receivable_id), deleted_at__isnull=True
        )
        if not receivable:
            return
        # DocumentRelation 无 soft-delete 字段，禁止 deleted_at__isnull
        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="receivable",
            source_id=int(receivable_id),
            target_type="receipt",
        ).all()
        receipt_ids = [int(rel.target_id) for rel in relations if rel.target_id]
        if not receipt_ids:
            return
        drafts = await Receipt.filter(
            tenant_id=tenant_id,
            id__in=receipt_ids,
            status="Draft",
            deleted_at__isnull=True,
        ).order_by("id").all()
        claims: List[tuple[int, Decimal]] = []
        for draft in drafts:
            kind = str(getattr(draft, "settlement_type", "normal") or "normal")
            if kind in ("prepayment", "refund"):
                continue
            claims.append((int(draft.id), Decimal(str(draft.unsettled_amount or 0))))
        from apps.kuaicaiwu.services.payment_pull_service import PaymentPullService

        updates = PaymentPullService.allocate_draft_claims_to_remaining(
            Decimal(str(receivable.remaining_amount or 0)),
            claims,
        )
        for receipt_id, allowed in updates:
            await Receipt.filter(tenant_id=tenant_id, id=receipt_id, status="Draft").update(
                total_amount=allowed,
                settled_amount=Decimal("0.00"),
                unsettled_amount=allowed,
            )

    async def prepare_linked_draft_before_confirm(
        self,
        tenant_id: int,
        receipt_id: int,
    ) -> Receipt:
        """确认前按应收剩余回写来源草稿，使银行入账与随后核销使用同一金额。"""
        receipt = await Receipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt or receipt.status != "Draft":
            if not receipt:
                raise NotFoundError(f"收款单不存在: {receipt_id}")
            return receipt
        if str(getattr(receipt, "settlement_type", "normal") or "normal") in ("prepayment", "refund"):
            return receipt
        rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="receivable",
            target_type="receipt",
            target_id=receipt_id,
        ).first()
        if not rel or not rel.source_id:
            return receipt
        await self.align_draft_receipts_to_receivable_remaining(tenant_id, int(rel.source_id))
        receipt = await Receipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"收款单不存在: {receipt_id}")
        unsettled = Decimal(str(receipt.unsettled_amount or 0))
        if unsettled <= 0:
            raise ValidationError("应收已由其他收款核销，本单已无待收金额")
        return receipt

    @staticmethod
    def normal_receipt_requires_settlement_source_before_confirm(receipt: Receipt) -> bool:
        kind = str(getattr(receipt, "settlement_type", "normal") or "normal")
        if kind in ("prepayment", "refund"):
            return False
        unsettled = Decimal(str(getattr(receipt, "unsettled_amount", 0) or 0))
        settled = Decimal(str(getattr(receipt, "settled_amount", 0) or 0))
        if unsettled <= 0 and settled > 0:
            return False
        return True

    async def assert_normal_receipt_has_settlement_source(
        self,
        tenant_id: int,
        receipt_id: int,
        *,
        receipt: Optional[Receipt] = None,
    ) -> None:
        row = receipt
        if row is None:
            row = await Receipt.get_or_none(
                tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
            )
        if not row:
            raise NotFoundError(f"收款单不存在: {receipt_id}")
        if not self.normal_receipt_requires_settlement_source_before_confirm(row):
            return

        has_rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="receivable",
            target_type="receipt",
            target_id=receipt_id,
        ).exists()
        if has_rel:
            return

        raise ValidationError(
            "货款收款单须从应收单加载创建并关联应收后再确认"
        )

    async def assert_normal_receipt_fully_settled_after_confirm(
        self,
        tenant_id: int,
        receipt_id: int,
        *,
        receipt: Optional[Receipt] = None,
    ) -> None:
        row = receipt
        if row is None:
            row = await Receipt.get_or_none(
                tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
            )
        if not row:
            raise NotFoundError(f"收款单不存在: {receipt_id}")
        if not self.normal_receipt_requires_settlement_source_before_confirm(row):
            return
        unsettled = Decimal(str(getattr(row, "unsettled_amount", 0) or 0))
        if unsettled > 0:
            raise ValidationError(
                "确认后仍有待核销金额，请检查收款单是否已从应收加载且金额与应收剩余一致"
            )

    async def repair_confirmed_receipt_settlement(
        self,
        tenant_id: int,
        *,
        receipt_id: int,
        operator_id: int,
    ) -> None:
        payment = await Receipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not payment:
            raise NotFoundError(f"收款单不存在: {receipt_id}")
        if str(getattr(payment, "status", "") or "") != "Confirmed":
            raise ValidationError("仅已确认且有待核销的收款单可执行补核销")
        unsettled = Decimal(str(getattr(payment, "unsettled_amount", 0) or 0))
        if unsettled <= 0:
            raise ValidationError("该收款单已无待核销金额")
        await self.assert_normal_receipt_has_settlement_source(
            tenant_id, receipt_id, receipt=payment
        )
        settled = await self.settle_draft_receipt_if_linked(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            operator_id=operator_id,
        )
        if not settled:
            raise ValidationError("未能按已关联应收完成核销，请检查应收剩余")
        payment = await Receipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if payment:
            await self.assert_normal_receipt_fully_settled_after_confirm(
                tenant_id, receipt_id, receipt=payment
            )

    async def settle_draft_receipt_if_linked(
        self,
        tenant_id: int,
        *,
        receipt_id: int,
        operator_id: int,
    ) -> bool:
        """确认草稿收款单时：若由应收单加载创建且尚未核销，补做核销。预收款不自动核销。

        确认前先按应收剩余回写本单及同应收上更晚的草稿，避免先开满额草稿、后核销预收时按旧总额审核失败。
        """
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        from apps.kuaicaiwu.models.receipt_pull_line import ReceiptPullLine

        receipt = await Receipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            return False
        if str(getattr(receipt, "settlement_type", "normal") or "normal") == "prepayment":
            return False

        pull_rows = await ReceiptPullLine.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            deleted_at__isnull=True,
            source_type="receivable",
        ).order_by("line_no")
        if pull_rows:
            settled_any = False
            by_receivable: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
            for pl in pull_rows:
                by_receivable[int(pl.source_id)] += Decimal(str(pl.amount or 0))
            for receivable_id, amount in by_receivable.items():
                if amount <= 0:
                    continue
                await self.align_draft_receipts_to_receivable_remaining(tenant_id, receivable_id)
                receipt = await Receipt.get_or_none(
                    tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
                )
                if not receipt:
                    return settled_any
                unsettled = Decimal(str(receipt.unsettled_amount or 0))
                if unsettled <= 0:
                    raise ValidationError("应收已由其他收款核销，本单已无待收金额")
                settle_amt = min(amount, unsettled)
                await self.settle_pull_created_receipt(
                    tenant_id=tenant_id,
                    receivable_id=receivable_id,
                    receipt_id=receipt_id,
                    amount=settle_amt,
                    operator_id=operator_id,
                )
                settled_any = True
            return settled_any

        rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="receivable",
            target_type="receipt",
            target_id=receipt_id,
        ).first()
        if not rel or not rel.source_id:
            return False

        receipt = await Receipt.get_or_none(tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True)
        if not receipt:
            return False
        if str(getattr(receipt, "settlement_type", "normal") or "normal") == "prepayment":
            # 预收款保留未核销余额，供预收预付余额与「预收转核销」使用，不因来源应收单自动核销。
            return False
        await self.align_draft_receipts_to_receivable_remaining(
            tenant_id, int(rel.source_id)
        )
        receipt = await Receipt.get_or_none(tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True)
        if not receipt:
            return False
        unsettled = Decimal(str(receipt.unsettled_amount or 0))
        if unsettled <= 0:
            raise ValidationError("应收已由其他收款核销，本单已无待收金额")

        await self.settle_pull_created_receipt(
            tenant_id=tenant_id,
            receivable_id=int(rel.source_id),
            receipt_id=receipt_id,
            amount=unsettled,
            operator_id=operator_id,
        )
        return True

    async def validate_pull_lines_for_create(
        self,
        tenant_id: int,
        *,
        pull_lines: Sequence[Any],
        total_amount: Decimal,
        settlement_type: Optional[str] = None,
        operator_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from apps.kuaicaiwu.services.payment_pull_service import (
            coerce_pull_lines_for_validate,
            pull_line_field,
        )

        pull_lines = coerce_pull_lines_for_validate(pull_lines)
        if not pull_lines:
            raise BusinessLogicError("加载明细不能为空")
        source_types = {
            str(pull_line_field(line, "source_type", "") or "").strip() for line in pull_lines
        }
        source_types.discard("")
        if len(source_types) != 1:
            raise BusinessLogicError(
                "同一收款单不可混选不同来源类型" if len(source_types) > 1 else "加载明细不能为空"
            )
        normalized_type = next(iter(source_types))
        if normalized_type not in ("receivable", "sales_order"):
            raise BusinessLogicError(f"不支持的加载源单类型: {normalized_type}")
        settlement = str(settlement_type or "normal").strip() or "normal"
        if normalized_type == "sales_order" and settlement != "prepayment":
            raise BusinessLogicError("销售订单加载明细仅用于预收收款单")
        if normalized_type == "receivable" and settlement == "prepayment":
            raise BusinessLogicError("预收类型不可从应收单加载明细")

        line_total = Decimal("0")
        first_preview: Optional[Dict[str, Any]] = None
        if normalized_type == "sales_order":
            by_so: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
            for line in pull_lines:
                amount = Decimal(str(pull_line_field(line, "amount", 0) or 0))
                if amount <= 0:
                    raise BusinessLogicError("明细收款金额须大于 0")
                line_total += amount
                source_id = int(pull_line_field(line, "source_id", 0) or 0)
                if source_id <= 0:
                    raise BusinessLogicError("销售订单加载明细缺少来源单")
                by_so[source_id] += amount
            for so_id, so_total in by_so.items():
                preview = await self.assert_pull_create_allowed(
                    tenant_id=tenant_id,
                    source_type=normalized_type,
                    source_id=so_id,
                    total_amount=so_total,
                    operator_id=operator_id,
                )
                if first_preview is None:
                    first_preview = preview
        else:
            for line in pull_lines:
                amount = Decimal(str(pull_line_field(line, "amount", 0) or 0))
                if amount <= 0:
                    raise BusinessLogicError("明细收款金额须大于 0")
                line_total += amount
                source_id = int(pull_line_field(line, "source_id", 0) or 0)
                preview = await self.assert_pull_create_allowed(
                    tenant_id=tenant_id,
                    source_type=normalized_type,
                    source_id=source_id,
                    total_amount=amount,
                    operator_id=operator_id,
                )
                if first_preview is None:
                    first_preview = preview

        expected = Decimal(str(total_amount or 0)).quantize(Decimal("0.01"))
        if line_total.quantize(Decimal("0.01")) != expected:
            raise BusinessLogicError("收款总额须与明细合计一致")
        return first_preview or {}

    async def persist_pull_lines(
        self,
        tenant_id: int,
        *,
        receipt_id: int,
        receipt_code: str,
        pull_lines: Sequence[Any],
        created_by: int,
    ) -> None:
        from apps.kuaicaiwu.models.receipt_pull_line import ReceiptPullLine
        from apps.kuaicaiwu.services.payment_pull_service import pull_line_field

        relation_seen: set[tuple[str, int]] = set()
        for index, line in enumerate(pull_lines, start=1):
            source_type = str(pull_line_field(line, "source_type", "") or "").strip()
            source_id = int(pull_line_field(line, "source_id", 0) or 0)
            source_code = str(pull_line_field(line, "source_code", "") or "").strip() or str(
                source_id
            )
            amount = Decimal(str(pull_line_field(line, "amount", 0) or 0))
            await ReceiptPullLine.create(
                tenant_id=tenant_id,
                receipt_id=receipt_id,
                line_no=index,
                source_type=source_type,
                source_id=source_id,
                source_code=source_code,
                amount=amount,
            )
            rel_key = (source_type, source_id)
            if rel_key in relation_seen:
                continue
            relation_seen.add(rel_key)
            await self.create_pull_relation(
                tenant_id=tenant_id,
                source_type=source_type,
                source_id=source_id,
                source_code=source_code,
                receipt_id=receipt_id,
                receipt_code=receipt_code,
                created_by=created_by,
            )

    async def list_pull_lines_for_receipt(
        self,
        tenant_id: int,
        receipt_id: int,
    ) -> List[Dict[str, Any]]:
        from apps.kuaicaiwu.models.receipt_pull_line import ReceiptPullLine

        rows = await ReceiptPullLine.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            deleted_at__isnull=True,
        ).order_by("line_no")
        return [
            {
                "line_no": int(r.line_no),
                "source_type": str(r.source_type),
                "source_id": int(r.source_id),
                "source_code": r.source_code,
                "amount": Decimal(str(r.amount or 0)),
            }
            for r in rows
        ]

    async def clear_receipt_pull_sources(self, tenant_id: int, receipt_id: int) -> None:
        from core.utils.timezone_utils import resolve_business_datetime

        from apps.kuaicaiwu.models.receipt_pull_line import ReceiptPullLine

        now = resolve_business_datetime()
        await ReceiptPullLine.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            deleted_at__isnull=True,
        ).update(deleted_at=now)
        await DocumentRelation.filter(
            tenant_id=tenant_id,
            target_type="receipt",
            target_id=receipt_id,
            relation_mode="pull",
            source_type__in=["receivable", "sales_order"],
        ).delete()

    async def replace_receipt_pull_lines(
        self,
        tenant_id: int,
        *,
        receipt_id: int,
        receipt_code: str,
        pull_lines: Sequence[Any],
        total_amount: Decimal,
        operator_id: int,
        settlement_type: Optional[str] = None,
    ) -> None:
        await self.validate_pull_lines_for_create(
            tenant_id,
            pull_lines=pull_lines,
            total_amount=total_amount,
            settlement_type=settlement_type,
            operator_id=operator_id,
        )
        await self.clear_receipt_pull_sources(tenant_id, receipt_id)
        await self.persist_pull_lines(
            tenant_id,
            receipt_id=receipt_id,
            receipt_code=receipt_code,
            pull_lines=pull_lines,
            created_by=operator_id,
        )
