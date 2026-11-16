"""
付款单加载门控：应付单候选列表、预览、已付款/待占用金额汇总。
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

from tortoise.queryset import Q

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.payment import Payment
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaizhizao.models.document_relation import DocumentRelation
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError


class PaymentPullService(AppBaseService[Payment]):
    """付款单加载门控服务"""

    _EXCLUDED_PAYMENT_STATUSES = frozenset({"Cancelled"})
    # 仅已确认付款单占用应付可加载额度；草稿未过账不占额度
    _RESERVED_PAYMENT_STATUSES = frozenset({"Confirmed"})

    _PAYABLE_ELIGIBLE_REVIEW = frozenset({"已审核"})

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

    async def _sum_reserved_unsettled_by_payable(
        self,
        tenant_id: int,
        payable_ids: List[int],
        code_by_id: Dict[int, str],
    ) -> Dict[int, Decimal]:
        result: Dict[int, Decimal] = {pid: Decimal("0") for pid in payable_ids}
        if not payable_ids:
            return result

        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payable",
            source_id__in=payable_ids,
            target_type="payment",
        ).all()
        payment_by_payable: Dict[int, List[int]] = {}
        for rel in relations:
            if rel.source_id and rel.target_id:
                payment_by_payable.setdefault(int(rel.source_id), []).append(int(rel.target_id))

        all_payment_ids = {pid for ids in payment_by_payable.values() for pid in ids}
        payment_map: Dict[int, Payment] = {}
        if all_payment_ids:
            rows = await Payment.filter(
                tenant_id=tenant_id,
                id__in=list(all_payment_ids),
                deleted_at__isnull=True,
                status__in=list(self._RESERVED_PAYMENT_STATUSES),
            ).all()
            payment_map = {int(p.id): p for p in rows}

        for payable_id, payment_ids in payment_by_payable.items():
            reserved = Decimal("0")
            for payment_id in payment_ids:
                payment = payment_map.get(payment_id)
                if payment:
                    reserved += Decimal(str(payment.unsettled_amount or 0))
            result[payable_id] = reserved

        # 占用金额仅认 DocumentRelation；不再全表扫 notes（列表路径性能陷阱）。
        _ = code_by_id
        return result

    def _build_preview_item(
        self,
        *,
        payable: Any,
        reserved_unsettled: Decimal,
    ) -> Dict[str, Any]:
        pid = int(payable.id)
        code = str(payable.payable_code or pid)
        total = Decimal(str(payable.total_amount or 0))
        paid = Decimal(str(payable.paid_amount or 0))
        remaining = Decimal(str(payable.remaining_amount or 0))
        max_push = max(Decimal("0"), remaining - reserved_unsettled)
        return {
            "item_id": pid,
            "source_code": code,
            "supplier_name": str(getattr(payable, "supplier_name", "") or ""),
            "quantity": float(total),
            "pushed_quantity": float(paid),
            "max_push_quantity": float(max_push),
        }

    async def _build_preview_items_for_payable(
        self,
        tenant_id: int,
        payable: Any,
        *,
        reserved_unsettled: Optional[Decimal] = None,
    ) -> List[Dict[str, Any]]:
        total = Decimal(str(payable.total_amount or 0))
        if total <= 0:
            return []
        pid = int(payable.id)
        if reserved_unsettled is None:
            code = str(payable.payable_code or pid)
            reserved_map = await self._sum_reserved_unsettled_by_payable(
                tenant_id, [pid], {pid: code}
            )
            reserved_unsettled = reserved_map.get(pid, Decimal("0"))
        return [
            self._build_preview_item(
                payable=payable,
                reserved_unsettled=reserved_unsettled,
            )
        ]

    def _payable_source_allowed(self, payable: Any) -> bool:
        from apps.kuaicaiwu.constants.finance_source_types import is_purchase_return_offset_payable

        source_type = (
            payable.get("source_type")
            if isinstance(payable, dict)
            else getattr(payable, "source_type", None)
        )
        if is_purchase_return_offset_payable(source_type):
            return False
        status = str(getattr(payable, "status", "") or "").strip()
        review = str(getattr(payable, "review_status", "") or "").strip()
        remaining = Decimal(str(payable.remaining_amount or 0))
        total = Decimal(str(payable.total_amount or 0))
        if status in ("已结清", "已冲减") or remaining <= 0 or total <= 0:
            return False
        return review in self._PAYABLE_ELIGIBLE_REVIEW

    async def preview_pull_from_payable(
        self,
        tenant_id: int,
        payable_id: int,
        *,
        operator_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from apps.kuaicaiwu.services.return_open_balance_offset_service import (
            ReturnOpenBalanceOffsetService,
        )

        await ReturnOpenBalanceOffsetService().ensure_offsets_for_payable(
            tenant_id,
            payable_id,
            operator_id=int(operator_id or 0) or 0,
        )

        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=payable_id, deleted_at__isnull=True
        )
        if not payable:
            raise NotFoundError(f"应付单不存在: {payable_id}")

        source_allowed = self._payable_source_allowed(payable)
        preview_items = await self._build_preview_items_for_payable(tenant_id, payable)
        allowed, reason = self._derive_pull_capability(
            source_allowed=source_allowed,
            preview_items=preview_items,
            not_allowed_reason="payment.pull_from_payable.not_allowed",
            no_lines_reason="payment.pull_from_payable.no_lines",
            already_pulled_reason="payment.pull_from_payable.already_pulled",
        )
        code = str(payable.payable_code or payable_id)
        pushable = float(preview_items[0]["max_push_quantity"]) if preview_items else 0.0
        return {
            "target_type": "payment",
            "source_type": "payable",
            "source_id": payable_id,
            "source_code": code,
            "summary": (
                f"将从应付单 {code} 创建付款单（可付款 ¥{pushable:,.2f}）"
                if preview_items and allowed
                else f"应付单 {code} 当前不可加载付款单"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": reason,
            "tip": "付款金额不可超过可付款金额；作废未核销付款单后，可付款金额自动回退。",
            "supplier_id": payable.supplier_id,
            "supplier_name": payable.supplier_name,
            "payable_id": payable.id,
            "payable_code": code,
            "max_push_total": pushable,
        }

    @staticmethod
    def _normalize_source_ids(payable_ids: Sequence[int]) -> List[int]:
        ordered: List[int] = []
        seen: set[int] = set()
        for raw in payable_ids:
            pid = int(raw)
            if pid <= 0 or pid in seen:
                continue
            seen.add(pid)
            ordered.append(pid)
        if not ordered:
            raise BusinessLogicError("请至少选择一张源单")
        return ordered

    async def preview_pull_from_payables(
        self,
        tenant_id: int,
        payable_ids: Sequence[int],
        *,
        operator_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        ids = self._normalize_source_ids(payable_ids)
        if len(ids) == 1:
            return await self.preview_pull_from_payable(
                tenant_id, ids[0], operator_id=operator_id
            )

        merged_items: List[Dict[str, Any]] = []
        blocking_reasons: List[str] = []
        supplier_id: Optional[int] = None
        supplier_name: Optional[str] = None
        codes: List[str] = []

        for pid in ids:
            fragment = await self.preview_pull_from_payable(
                tenant_id, pid, operator_id=operator_id
            )
            frag_supplier = int(fragment.get("supplier_id") or 0)
            if supplier_id is None:
                supplier_id = frag_supplier
                supplier_name = str(fragment.get("supplier_name") or "")
            elif frag_supplier != int(supplier_id or 0):
                raise BusinessLogicError("多笔一起加载须为同一供应商")

            codes.append(str(fragment.get("source_code") or pid))
            if fragment.get("has_blocking_issues"):
                reason = str(fragment.get("blocking_reason") or "")
                if reason:
                    blocking_reasons.append(reason)
            for item in fragment.get("items") or []:
                row = dict(item)
                row["payable_id"] = pid
                merged_items.append(row)

        max_push_total = sum(
            Decimal(str(item.get("max_push_quantity") or 0)) for item in merged_items
        )
        allowed = not blocking_reasons and max_push_total > 0
        joined_codes = "、".join(codes)
        return {
            "target_type": "payment",
            "source_type": "payable",
            "source_id": ids[0],
            "source_ids": ids,
            "source_code": joined_codes,
            "summary": (
                f"将从 {len(ids)} 张应付单创建付款单（可付款合计 ¥{float(max_push_total):,.2f}）"
                if allowed
                else "所选应付单当前不可一起加载付款单"
            ),
            "items": merged_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
            "tip": "付款金额不可超过可付款合计；作废未核销付款单后，可付款金额自动回退。",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "max_push_total": float(max_push_total),
            "payable_id": ids[0],
            "payable_code": codes[0] if codes else None,
        }

    async def list_payable_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        supplier_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = Payable.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            remaining_amount__gt=0,
        ).exclude(status="已结清").exclude(status="已冲减").exclude(source_type="采购退货")
        if supplier_id:
            query = query.filter(supplier_id=int(supplier_id))
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
        reserved_map = await self._sum_reserved_unsettled_by_payable(
            tenant_id, payable_ids, code_by_id
        )

        rows: List[Dict[str, Any]] = []
        for payable in payables:
            pid = int(payable.id)
            preview_items = await self._build_preview_items_for_payable(
                tenant_id,
                payable,
                reserved_unsettled=reserved_map.get(pid, Decimal("0")),
            )
            allowed, reason = self._derive_pull_capability(
                source_allowed=self._payable_source_allowed(payable),
                preview_items=preview_items,
                not_allowed_reason="payment.pull_from_payable.not_allowed",
                no_lines_reason="payment.pull_from_payable.no_lines",
                already_pulled_reason="payment.pull_from_payable.already_pulled",
            )
            code = str(payable.payable_code or pid)
            name = str(getattr(payable, "supplier_name", "") or "").strip()
            label = f"{code} - {name}" if name else code
            rows.append(
                {
                    "id": pid,
                    "code": label,
                    "payable_code": code,
                    "supplier_id": int(payable.supplier_id or 0) or None,
                    "supplier_name": payable.supplier_name,
                    "source_status": payable.status,
                    "review_status": payable.review_status,
                    "source_date": str(getattr(payable, "due_date", "") or ""),
                    "amount": float(payable.total_amount or 0),
                    "remaining_amount": float(payable.remaining_amount or 0),
                    "capabilities": {
                        "pull_payment": {
                            "allowed": allowed,
                            "reason": reason,
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def list_payment_application_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        supplier_id: Optional[int] = None,
        application_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.services.payment_application_pull_service import (
            PaymentApplicationPullService,
        )

        return await PaymentApplicationPullService().list_for_payment_pull(
            tenant_id,
            skip=skip,
            limit=limit,
            keyword=keyword,
            supplier_id=supplier_id,
            application_kind=application_kind,
        )

    async def preview_pull_from_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
        *,
        amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.services.payment_application_pull_service import (
            PaymentApplicationPullService,
        )

        preview = await PaymentApplicationPullService().preview_from_purchase_order(
            tenant_id,
            purchase_order_id,
            amount=amount,
        )
        code = str(preview.get("source_code") or preview.get("order_code") or purchase_order_id)
        max_push = float(preview.get("max_push_quantity") or 0)
        allowed = not preview.get("has_blocking_issues")
        preview["target_type"] = "payment"
        preview["max_push_total"] = max_push
        preview["summary"] = (
            f"将从采购订单 {code} 加载预付付款明细（可预付 ¥{max_push:,.2f}）"
            if allowed and max_push > 0
            else f"采购订单 {code} 当前不可加载预付付款明细"
        )
        preview["tip"] = "预付款类型须与采购订单预付额度一致；确认过账后关联采购订单。"
        return preview

    async def preview_pull_from_payment_application(
        self,
        tenant_id: int,
        application_id: int,
    ) -> Dict[str, Any]:
        from apps.kuaizhizao.services.payment_application_pull_service import (
            PaymentApplicationPullService,
        )

        return await PaymentApplicationPullService().preview_pull_for_payment(
            tenant_id, application_id
        )

    async def assert_pull_create_allowed(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        total_amount: Decimal,
    ) -> Dict[str, Any]:
        normalized = str(source_type or "").strip()
        if normalized == "payment_application":
            preview = await self.preview_pull_from_payment_application(tenant_id, source_id)
            if preview.get("has_blocking_issues"):
                reason = preview.get("blocking_reason") or "当前不可加载付款单"
                raise BusinessLogicError(reason)
            max_push = Decimal(str(preview.get("max_push_total") or 0))
            if max_push <= 0:
                items = preview.get("items") or []
                if items:
                    max_push = Decimal(str(items[0].get("max_push_quantity") or 0))
            if max_push <= 0:
                raise BusinessLogicError("无可付款金额")
            if total_amount > max_push:
                raise BusinessLogicError(f"付款金额 {total_amount} 超过可付款金额 {max_push}")
            return preview
        if normalized == "purchase_order":
            preview = await self.preview_pull_from_purchase_order(
                tenant_id, source_id, amount=total_amount
            )
            if preview.get("has_blocking_issues"):
                reason = preview.get("blocking_reason") or "当前不可加载预付付款明细"
                raise BusinessLogicError(reason)
            max_push = Decimal(str(preview.get("max_push_quantity") or preview.get("max_push_total") or 0))
            if max_push <= 0:
                raise BusinessLogicError("无可预付金额")
            if total_amount > max_push:
                raise BusinessLogicError(f"付款金额 {total_amount} 超过可预付金额 {max_push}")
            return preview
        if normalized != "payable":
            raise BusinessLogicError(f"不支持的加载源单类型: {source_type}")
        preview = await self.preview_pull_from_payable(tenant_id, source_id)
        if preview.get("has_blocking_issues"):
            reason = preview.get("blocking_reason") or "当前不可加载付款单"
            raise BusinessLogicError(reason)
        items = preview.get("items") or []
        if not items:
            raise BusinessLogicError("无可付款金额")
        max_push = Decimal(str(items[0].get("max_push_quantity") or 0))
        if total_amount > max_push:
            raise BusinessLogicError(f"付款金额 {total_amount} 超过可付款金额 {max_push}")
        return preview

    async def create_pull_relation(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
        source_code: str,
        payment_id: int,
        payment_code: str,
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
                target_type="payment",
                target_id=payment_id,
                target_code=payment_code,
                target_name=None,
                relation_type="source",
                relation_mode="pull",
                relation_desc="加载创建付款单",
            ),
            created_by=created_by,
        )

    async def settle_pull_created_payment(
        self,
        tenant_id: int,
        *,
        payable_id: int,
        payment_id: int,
        amount: Decimal,
        operator_id: int,
    ) -> None:
        """从应付单加载创建付款单后，立即核销至源应付（与 record_payment 一致）。"""
        from apps.kuaicaiwu.services.finance_service import AccountSettlementService

        settlement_service = AccountSettlementService()
        await settlement_service.settle_payable(
            tenant_id=tenant_id,
            payable_id=payable_id,
            payment_id=payment_id,
            amount=Decimal(amount),
            operator_id=operator_id,
        )

    @staticmethod
    def allocate_draft_claims_to_remaining(
        remaining: Decimal,
        claims: List[tuple[int, Decimal]],
    ) -> List[tuple[int, Decimal]]:
        """按创建先后把草稿占额压进应付剩余。先创建的草稿优先保留，超出部分从后创建的草稿扣减。

        claims 须已按付款单 id 升序。返回需要改写的 (payment_id, 新待核销)。
        """
        left = Decimal(str(remaining or 0)).quantize(Decimal("0.01"))
        if left < 0:
            left = Decimal("0.00")
        changed: List[tuple[int, Decimal]] = []
        for payment_id, claim in claims:
            amount = Decimal(str(claim or 0)).quantize(Decimal("0.01"))
            if amount < 0:
                amount = Decimal("0.00")
            allowed = min(amount, left) if left > 0 else Decimal("0.00")
            left -= allowed
            if allowed != amount:
                changed.append((int(payment_id), allowed))
        return changed

    async def align_draft_payments_to_payable_remaining(
        self,
        tenant_id: int,
        payable_id: int,
    ) -> None:
        """应付剩余变化后，把仍挂在该应付上的草稿货款付款单总额/待核销下调到不超过剩余。

        已确认付款单不改。预付、退款单不参与占额。
        """
        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
        )
        if not payable:
            return
        # DocumentRelation 无 soft-delete 字段，禁止 deleted_at__isnull
        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payable",
            source_id=int(payable_id),
            target_type="payment",
        ).all()
        payment_ids = [int(rel.target_id) for rel in relations if rel.target_id]
        if not payment_ids:
            return
        drafts = await Payment.filter(
            tenant_id=tenant_id,
            id__in=payment_ids,
            status="Draft",
            deleted_at__isnull=True,
        ).order_by("id").all()
        claims: List[tuple[int, Decimal]] = []
        for draft in drafts:
            kind = str(getattr(draft, "settlement_type", "normal") or "normal")
            if kind in ("prepayment", "refund"):
                continue
            claims.append((int(draft.id), Decimal(str(draft.unsettled_amount or 0))))
        updates = self.allocate_draft_claims_to_remaining(
            Decimal(str(payable.remaining_amount or 0)),
            claims,
        )
        for payment_id, allowed in updates:
            await Payment.filter(tenant_id=tenant_id, id=payment_id, status="Draft").update(
                total_amount=allowed,
                settled_amount=Decimal("0.00"),
                unsettled_amount=allowed,
            )

    async def prepare_linked_draft_before_confirm(
        self,
        tenant_id: int,
        payment_id: int,
    ) -> Payment:
        """确认前按应付剩余回写来源草稿，使银行出账与随后核销使用同一金额。"""
        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
        )
        if not payment or payment.status != "Draft":
            if not payment:
                raise NotFoundError(f"付款单不存在: {payment_id}")
            return payment
        if str(getattr(payment, "settlement_type", "normal") or "normal") in ("prepayment", "refund"):
            return payment
        rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payable",
            target_type="payment",
            target_id=payment_id,
        ).first()
        if not rel or not rel.source_id:
            return payment
        await self.align_draft_payments_to_payable_remaining(tenant_id, int(rel.source_id))
        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
        )
        if not payment:
            raise NotFoundError(f"付款单不存在: {payment_id}")
        unsettled = Decimal(str(payment.unsettled_amount or 0))
        if unsettled <= 0:
            raise ValidationError("应付已由其他付款核销，本单已无待付金额")
        return payment

    @staticmethod
    def normal_payment_requires_settlement_source_before_confirm(payment: Payment) -> bool:
        """货款类草稿确认前是否必须已指定清账来源（预付/退款、合并已核销除外）。"""
        kind = str(getattr(payment, "settlement_type", "normal") or "normal")
        if kind in ("prepayment", "refund"):
            return False
        unsettled = Decimal(str(getattr(payment, "unsettled_amount", 0) or 0))
        settled = Decimal(str(getattr(payment, "settled_amount", 0) or 0))
        if unsettled <= 0 and settled > 0:
            return False
        return True

    async def assert_normal_payment_has_settlement_source(
        self,
        tenant_id: int,
        payment_id: int,
        *,
        payment: Optional[Payment] = None,
    ) -> None:
        """货款付款单确认前须已加载应付/付款申请或存在应付关联（合并付款等）。"""
        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

        row = payment
        if row is None:
            row = await Payment.get_or_none(
                tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
            )
        if not row:
            raise NotFoundError(f"付款单不存在: {payment_id}")
        if not self.normal_payment_requires_settlement_source_before_confirm(row):
            return

        has_pull = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
            source_type__in=["payable", "payment_application"],
        ).exists()
        if has_pull:
            return

        has_payable_rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payable",
            target_type="payment",
            target_id=payment_id,
        ).exists()
        if has_payable_rel:
            return

        has_app_rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payment_application",
            target_type="payment",
            target_id=payment_id,
        ).exists()
        if has_app_rel:
            return

        raise ValidationError(
            "货款付款单须指定清账来源（加载应付或付款申请）后再确认"
        )

    async def assert_normal_payment_fully_settled_after_confirm(
        self,
        tenant_id: int,
        payment_id: int,
        *,
        payment: Optional[Payment] = None,
    ) -> None:
        """货款确认后待核销应为 0（预付/退款、合并先核销除外）。"""
        row = payment
        if row is None:
            row = await Payment.get_or_none(
                tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
            )
        if not row:
            raise NotFoundError(f"付款单不存在: {payment_id}")
        if not self.normal_payment_requires_settlement_source_before_confirm(row):
            return
        unsettled = Decimal(str(getattr(row, "unsettled_amount", 0) or 0))
        if unsettled > 0:
            raise ValidationError(
                "确认后仍有待核销金额，请检查付款单加载明细与付款总额是否一致"
            )

    async def repair_confirmed_payment_settlement(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        operator_id: int,
    ) -> None:
        """已确认付款单按已记录的加载明细/关联补核销（不再选手工匹配）。"""
        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
        )
        if not payment:
            raise NotFoundError(f"付款单不存在: {payment_id}")
        if str(getattr(payment, "status", "") or "") != "Confirmed":
            raise ValidationError("仅已确认且有待核销的付款单可执行补核销")
        unsettled = Decimal(str(getattr(payment, "unsettled_amount", 0) or 0))
        if unsettled <= 0:
            raise ValidationError("该付款单已无待核销金额")
        await self.assert_normal_payment_has_settlement_source(
            tenant_id, payment_id, payment=payment
        )
        settled = await self.settle_draft_payment_if_linked(
            tenant_id=tenant_id,
            payment_id=payment_id,
            operator_id=operator_id,
        )
        if not settled:
            raise ValidationError(
                "未能按已加载明细完成核销：请确认付款申请行已关联应付且应付仍有可核销剩余，"
                "或应付剩余是否小于本单待核销金额"
            )
        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
        )
        if payment:
            await self.assert_normal_payment_fully_settled_after_confirm(
                tenant_id, payment_id, payment=payment
            )

    async def validate_pull_lines_for_create(
        self,
        tenant_id: int,
        *,
        pull_lines: Sequence[Any],
        total_amount: Decimal,
        settlement_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """校验加载明细并返回付款申请预览（若有）。"""
        if not pull_lines:
            raise BusinessLogicError("加载明细不能为空")
        source_types = {str(getattr(line, "source_type", "") or "").strip() for line in pull_lines}
        source_types.discard("")
        if len(source_types) != 1:
            raise BusinessLogicError("同一付款单不可混选不同来源类型")
        normalized_type = source_types.pop()
        if normalized_type not in ("payable", "payment_application", "purchase_order"):
            raise BusinessLogicError(f"不支持的加载源单类型: {normalized_type}")
        if normalized_type == "payment_application" and len(pull_lines) > 1:
            raise BusinessLogicError("付款申请须单独加载，不可与其它来源合并")
        settlement = str(settlement_type or "normal").strip() or "normal"
        if normalized_type == "purchase_order" and settlement != "prepayment":
            raise BusinessLogicError("采购订单加载明细仅用于预付款付款单")
        if normalized_type == "payable" and settlement == "prepayment":
            raise BusinessLogicError("预付款类型不可从应付单加载明细")

        line_total = Decimal("0")
        first_preview: Optional[Dict[str, Any]] = None
        if normalized_type == "purchase_order":
            by_po: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
            for line in pull_lines:
                amount = Decimal(str(getattr(line, "amount", 0) or 0))
                if amount <= 0:
                    raise BusinessLogicError("明细付款金额须大于 0")
                line_total += amount
                source_id = int(getattr(line, "source_id", 0) or 0)
                if source_id <= 0:
                    raise BusinessLogicError("采购订单加载明细缺少来源单")
                by_po[source_id] += amount
            for po_id, po_total in by_po.items():
                preview = await self.assert_pull_create_allowed(
                    tenant_id=tenant_id,
                    source_type=normalized_type,
                    source_id=po_id,
                    total_amount=po_total,
                )
                if first_preview is None:
                    first_preview = preview
        else:
            for line in pull_lines:
                amount = Decimal(str(getattr(line, "amount", 0) or 0))
                if amount <= 0:
                    raise BusinessLogicError("明细付款金额须大于 0")
                line_total += amount
                source_id = int(getattr(line, "source_id", 0) or 0)
                preview = await self.assert_pull_create_allowed(
                    tenant_id=tenant_id,
                    source_type=normalized_type,
                    source_id=source_id,
                    total_amount=amount,
                )
                if first_preview is None:
                    first_preview = preview

        expected = Decimal(str(total_amount or 0)).quantize(Decimal("0.01"))
        if line_total.quantize(Decimal("0.01")) != expected:
            raise BusinessLogicError("付款总额须与明细合计一致")
        return first_preview or {}

    async def persist_pull_lines(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        payment_code: str,
        pull_lines: Sequence[Any],
        created_by: int,
    ) -> None:
        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

        relation_seen: set[tuple[str, int]] = set()
        for index, line in enumerate(pull_lines, start=1):
            source_type = str(getattr(line, "source_type", "") or "").strip()
            source_id = int(getattr(line, "source_id", 0) or 0)
            source_code = str(getattr(line, "source_code", "") or "").strip() or str(source_id)
            amount = Decimal(str(getattr(line, "amount", 0) or 0))
            await PaymentPullLine.create(
                tenant_id=tenant_id,
                payment_id=payment_id,
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
                payment_id=payment_id,
                payment_code=payment_code,
                created_by=created_by,
            )

    async def clear_payment_pull_sources(
        self,
        tenant_id: int,
        payment_id: int,
    ) -> None:
        from core.utils.timezone_utils import resolve_business_datetime

        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

        now = resolve_business_datetime()
        await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
        ).update(deleted_at=now)
        await DocumentRelation.filter(
            tenant_id=tenant_id,
            target_type="payment",
            target_id=payment_id,
            relation_mode="pull",
            source_type__in=["payable", "payment_application", "purchase_order"],
        ).delete()

    async def replace_payment_pull_lines(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        payment_code: str,
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
        )
        await self.clear_payment_pull_sources(tenant_id, payment_id)
        await self.persist_pull_lines(
            tenant_id,
            payment_id=payment_id,
            payment_code=payment_code,
            pull_lines=pull_lines,
            created_by=operator_id,
        )

    async def list_pull_lines_for_payment(
        self,
        tenant_id: int,
        payment_id: int,
        *,
        enrich_max: bool = False,
    ) -> List[Dict[str, Any]]:
        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

        rows = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
        ).order_by("line_no")
        result: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {
                "line_no": int(row.line_no),
                "source_type": str(row.source_type),
                "source_id": int(row.source_id),
                "source_code": row.source_code,
                "amount": Decimal(str(row.amount or 0)),
                "max_amount": None,
            }
            if enrich_max:
                if item["source_type"] == "payable":
                    preview = await self.preview_pull_from_payable(
                        tenant_id, int(item["source_id"])
                    )
                    items = preview.get("items") or []
                    if items:
                        item["max_amount"] = Decimal(str(items[0].get("max_push_quantity") or 0))
                elif item["source_type"] == "payment_application":
                    preview = await self.preview_pull_from_payment_application(
                        tenant_id, int(item["source_id"])
                    )
                    item["max_amount"] = Decimal(str(preview.get("max_push_total") or 0))
            result.append(item)
        return result

    async def _resolve_payable_settlement_amounts_from_application(
        self,
        tenant_id: int,
        *,
        lines: Sequence[Any],
        pay_basis: Decimal,
        payment: Payment,
    ) -> Dict[int, Decimal]:
        """按付款申请行汇总应付核销额；申请行已记已付但应付未核销时用待核销+应付剩余补算。"""
        from apps.kuaizhizao.services.payment_application_push_service import (
            PaymentApplicationPushService,
        )

        push_svc = PaymentApplicationPushService()
        settlement_type = str(getattr(payment, "settlement_type", "normal") or "normal")
        line_payments = push_svc._allocate_payment_amount_to_lines(
            list(lines),
            pay_basis,
            settlement_type=settlement_type,
        )
        line_by_id = {int(line.id): line for line in lines}
        by_payable: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        for line_id, amt in line_payments:
            line = line_by_id.get(int(line_id))
            if not line or not line.payable_id:
                continue
            by_payable[int(line.payable_id)] += Decimal(str(amt))

        if by_payable:
            return dict(by_payable)

        budget = Decimal(str(payment.unsettled_amount or 0))
        if budget <= 0:
            return {}

        is_prepay = settlement_type == "prepayment"
        for line in lines:
            if budget <= 0:
                break
            if is_prepay:
                if str(getattr(line, "line_kind", "") or "") != "prepayment":
                    continue
            elif not line.payable_id:
                continue
            pid = int(line.payable_id)
            payable = await Payable.get_or_none(
                tenant_id=tenant_id, id=pid, deleted_at__isnull=True
            )
            if not payable:
                continue
            pay_rem = Decimal(str(payable.remaining_amount or 0))
            if pay_rem <= 0:
                continue
            line_cap = Decimal(str(getattr(line, "request_amount", 0) or 0))
            if line_cap <= 0:
                line_cap = pay_rem
            take = min(budget, pay_rem, line_cap)
            if take <= 0:
                continue
            by_payable[pid] += take
            budget -= take
        return dict(by_payable)

    async def _settle_payment_application_pull_lines(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        operator_id: int,
        app_pull_lines: Sequence[Any],
    ) -> bool:
        """付款单从付款申请加载时，确认后按申请行关联的应付核销（无 payable 加载明细时）。"""
        from apps.kuaizhizao.models.payment_application import PaymentApplicationLine

        settled_any = False
        for pl in app_pull_lines:
            app_id = int(pl.source_id)
            lines = (
                await PaymentApplicationLine.filter(
                    tenant_id=tenant_id,
                    application_id=app_id,
                )
                .order_by("line_no")
                .all()
            )
            if not lines:
                continue
            pay_basis = Decimal(str(pl.amount or 0))
            if pay_basis <= 0:
                payment = await Payment.get_or_none(
                    tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
                )
                if payment:
                    pay_basis = Decimal(str(payment.total_amount or 0))
            if pay_basis <= 0:
                continue
            payment = await Payment.get_or_none(
                tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
            )
            if not payment:
                return settled_any
            by_payable = await self._resolve_payable_settlement_amounts_from_application(
                tenant_id,
                lines=lines,
                pay_basis=pay_basis,
                payment=payment,
            )
            for payable_id, amount in by_payable.items():
                if amount <= 0:
                    continue
                await self.align_draft_payments_to_payable_remaining(tenant_id, payable_id)
                payment = await Payment.get_or_none(
                    tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
                )
                if not payment:
                    return settled_any
                unsettled = Decimal(str(payment.unsettled_amount or 0))
                if unsettled <= 0:
                    raise ValidationError("应付已由其他付款核销，本单已无待付金额")
                settle_amt = min(amount, unsettled)
                await self.settle_pull_created_payment(
                    tenant_id=tenant_id,
                    payable_id=payable_id,
                    payment_id=payment_id,
                    amount=settle_amt,
                    operator_id=operator_id,
                )
                settled_any = True
        return settled_any

    async def settle_draft_prepayment_offset_payment(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        operator_id: int,
    ) -> bool:
        """预付抵扣：用已确认预付付款单余额核销应付，本单不记银行出账。"""
        from apps.kuaicaiwu.constants.payment_method import (
            is_prepayment_offset_payment_method,
        )
        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine
        from apps.kuaicaiwu.services.payable_prepayment_apply_service import (
            PayablePrepaymentApplyService,
        )

        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
        )
        if not payment or not is_prepayment_offset_payment_method(payment.payment_method):
            return False
        if str(getattr(payment, "settlement_type", "normal") or "normal") != "normal":
            raise ValidationError("预付抵扣仅用于普通付款结算类型")

        apply_svc = PayablePrepaymentApplyService()
        pull_lines = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
        ).order_by("line_no")
        if not pull_lines:
            raise ValidationError("预付抵扣须先加载应付或货款类付款申请明细")

        settled_any = False
        payable_lines = [ln for ln in pull_lines if str(ln.source_type) == "payable"]
        app_lines = [ln for ln in pull_lines if str(ln.source_type) == "payment_application"]

        for line in payable_lines:
            amount = Decimal(str(line.amount or 0))
            if amount <= 0:
                continue
            payable_id = int(line.source_id)
            po_id = await apply_svc.resolve_purchase_order_id_for_payable(
                tenant_id, payable_id
            )
            if not po_id:
                raise ValidationError(
                    f"应付单 {getattr(line, 'source_code', None) or payable_id} "
                    "未关联采购订单，无法用预付抵扣"
                )
            applied = await apply_svc.apply_prepayment_to_payable(
                tenant_id,
                payable_id=payable_id,
                purchase_order_id=int(po_id),
                amount=amount,
                operator_id=operator_id,
            )
            if applied.quantize(Decimal("0.01")) < amount.quantize(Decimal("0.01")):
                raise ValidationError(
                    "可用预付余额不足，无法按明细完成抵扣（请核对同采购订单已确认预付付款单）"
                )
            settled_any = True

        for pl in app_lines:
            from apps.kuaizhizao.models.payment_application import PaymentApplicationLine

            app_id = int(pl.source_id)
            lines = (
                await PaymentApplicationLine.filter(
                    tenant_id=tenant_id,
                    application_id=app_id,
                )
                .order_by("line_no")
                .all()
            )
            if not lines:
                continue
            pay_basis = Decimal(str(pl.amount or 0))
            if pay_basis <= 0:
                pay_basis = Decimal(str(payment.total_amount or 0))
            by_payable = await self._resolve_payable_settlement_amounts_from_application(
                tenant_id,
                lines=lines,
                pay_basis=pay_basis,
                payment=payment,
            )
            for payable_id, amount in by_payable.items():
                if amount <= 0:
                    continue
                po_id = await apply_svc.resolve_purchase_order_id_for_payable(
                    tenant_id, int(payable_id)
                )
                if not po_id:
                    raise ValidationError(
                        f"付款申请关联应付 {payable_id} 未关联采购订单，无法用预付抵扣"
                    )
                applied = await apply_svc.apply_prepayment_to_payable(
                    tenant_id,
                    payable_id=int(payable_id),
                    purchase_order_id=int(po_id),
                    amount=amount,
                    operator_id=operator_id,
                )
                if applied.quantize(Decimal("0.01")) < amount.quantize(Decimal("0.01")):
                    raise ValidationError(
                        "可用预付余额不足，无法按付款申请明细完成抵扣"
                    )
                settled_any = True

        if settled_any:
            total = Decimal(str(payment.total_amount or 0)).quantize(Decimal("0.01"))
            await Payment.filter(tenant_id=tenant_id, id=payment_id).update(
                settled_amount=total,
                unsettled_amount=Decimal("0.00"),
            )
        return settled_any

    async def settle_draft_payment_if_linked(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        operator_id: int,
    ) -> bool:
        """确认草稿付款单时：按加载明细核销应付；无明细时回退单源应付关联。"""
        from apps.kuaicaiwu.constants.payment_method import (
            is_prepayment_offset_payment_method,
        )
        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

        payment = await Payment.get_or_none(tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True)
        if not payment:
            return False
        if is_prepayment_offset_payment_method(payment.payment_method):
            return await self.settle_draft_prepayment_offset_payment(
                tenant_id,
                payment_id=payment_id,
                operator_id=operator_id,
            )
        if str(getattr(payment, "settlement_type", "normal") or "normal") == "prepayment":
            return False

        pull_lines = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
            source_type="payable",
        ).order_by("line_no")
        if pull_lines:
            settled_payable_pull = False
            for line in pull_lines:
                await self.align_draft_payments_to_payable_remaining(
                    tenant_id, int(line.source_id)
                )
            payment = await Payment.get_or_none(
                tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
            )
            if not payment:
                return False
            for line in pull_lines:
                amount = Decimal(str(line.amount or 0))
                if amount <= 0:
                    continue
                payment = await Payment.get_or_none(
                    tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
                )
                if not payment:
                    return False
                unsettled = Decimal(str(payment.unsettled_amount or 0))
                if unsettled <= 0:
                    raise ValidationError("应付已由其他付款核销，本单已无待付金额")
                settle_amt = min(amount, unsettled)
                await self.settle_pull_created_payment(
                    tenant_id=tenant_id,
                    payable_id=int(line.source_id),
                    payment_id=payment_id,
                    amount=settle_amt,
                    operator_id=operator_id,
                )
                settled_payable_pull = True
            if settled_payable_pull:
                return True

        app_pull_lines = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
            source_type="payment_application",
        ).order_by("line_no")
        if app_pull_lines:
            return await self._settle_payment_application_pull_lines(
                tenant_id,
                payment_id=payment_id,
                operator_id=operator_id,
                app_pull_lines=app_pull_lines,
            )

        app_rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payment_application",
            target_type="payment",
            target_id=payment_id,
        ).first()
        if app_rel and app_rel.source_id:
            pay_basis = Decimal(str(payment.unsettled_amount or payment.total_amount or 0))
            if pay_basis > 0:
                return await self._settle_payment_application_pull_lines(
                    tenant_id,
                    payment_id=payment_id,
                    operator_id=operator_id,
                    app_pull_lines=[
                        SimpleNamespace(
                            source_id=int(app_rel.source_id),
                            amount=pay_basis,
                        )
                    ],
                )

        rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payable",
            target_type="payment",
            target_id=payment_id,
        ).first()
        if not rel or not rel.source_id:
            return False

        await self.align_draft_payments_to_payable_remaining(tenant_id, int(rel.source_id))
        payment = await Payment.get_or_none(tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True)
        if not payment:
            return False
        unsettled = Decimal(str(payment.unsettled_amount or 0))
        if unsettled <= 0:
            raise ValidationError("应付已由其他付款核销，本单已无待付金额")

        await self.settle_pull_created_payment(
            tenant_id=tenant_id,
            payable_id=int(rel.source_id),
            payment_id=payment_id,
            amount=unsettled,
            operator_id=operator_id,
        )
        return True
