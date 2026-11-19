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


def pull_line_field(line: Any, key: str, default: Any = None) -> Any:
    """读取加载明细字段（兼容 Pydantic 模型与 dict，list_pull_lines 返回 dict）。"""
    if isinstance(line, dict):
        return line.get(key, default)
    return getattr(line, key, default)


_OFFSET_MONEY = Decimal("0.01")


def _offset_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(_OFFSET_MONEY)


def prepayment_offset_po_coverage_error(
    *,
    prep_by_po: Dict[int, Decimal],
    unlinked_prep: Decimal,
    payable_by_po: Dict[int, Decimal],
    unlinked_payable: Decimal,
    offset_total: Decimal,
) -> Optional[str]:
    """预付抵扣与应付的采购订单配对。

    两边都能解析到采购订单时须是同一张，且该订单预付合计不少于应付合计。
    应付单没有采购订单时，可用任意剩余预付（含已挂其他订单的余额）。
    预付款单没有采购订单时，不能用来补已挂订单的应付。
    """
    for po_id, pay_amt in payable_by_po.items():
        prep_amt = prep_by_po.get(int(po_id), Decimal("0"))
        if _offset_money(prep_amt) < _offset_money(pay_amt):
            if (
                _offset_money(prep_amt) == 0
                and _offset_money(unlinked_prep) > 0
                and _offset_money(offset_total) == _offset_money(unlinked_prep)
            ):
                return "预付款单未关联采购订单，不能抵扣已关联采购订单的应付单"
            return "各采购订单下预付款抵扣合计须不少于同订单应付抵扣合计"
    linked_payable_total = sum(
        (Decimal(amount) for amount in payable_by_po.values()),
        Decimal("0"),
    )
    leftover = _offset_money(offset_total) - _offset_money(linked_payable_total)
    if _offset_money(unlinked_payable) > leftover:
        return "未关联采购订单的应付抵扣金额超过可用预付余额"
    return None


def coerce_pull_lines_for_validate(pull_lines: Sequence[Any]) -> List[Any]:
    """丢弃无来源类型/来源 id/金额的脏行，避免误判为混选来源。"""
    kept: List[Any] = []
    for line in pull_lines:
        source_type = str(pull_line_field(line, "source_type", "") or "").strip()
        source_id = int(pull_line_field(line, "source_id", 0) or 0)
        amount = Decimal(str(pull_line_field(line, "amount", 0) or 0))
        if not source_type or source_id <= 0 or amount <= 0:
            continue
        kept.append(line)
    return kept


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
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder
        from apps.kuaizhizao.services.document_action_policy.enricher import (
            _order_prepayment_linked_by_ids,
        )
        from apps.kuaizhizao.services.document_action_policy.purchase_order import (
            derive_purchase_order_capabilities,
        )
        from apps.kuaizhizao.services.payment_application_line_materials import (
            lines_from_purchase_order_items,
        )
        from apps.kuaizhizao.services.payment_application_pull_service import (
            PaymentApplicationPullService,
            compute_prepayment_application_remaining,
        )
        from infra.services.business_config_service import BusinessConfigService

        order = await PurchaseOrder.get_or_none(tenant_id=tenant_id, id=purchase_order_id)
        if not order:
            raise NotFoundError(f"采购订单不存在: {purchase_order_id}")

        prepay_map = await _order_prepayment_linked_by_ids(
            tenant_id,
            [purchase_order_id],
            source_type="purchase_order",
            target_type="payment",
        )
        pull_svc = PaymentApplicationPullService()
        prepay_app_map = await pull_svc.has_prepayment_application_by_order_ids(
            tenant_id, [purchase_order_id]
        )
        require_app = await BusinessConfigService().get_finance_require_payment_application(
            tenant_id
        )
        reserved = (
            await pull_svc.prepayment_reserved_by_order_ids(
                tenant_id, [purchase_order_id]
            )
        ).get(purchase_order_id, Decimal("0"))
        payment_occ = (
            await pull_svc.prepayment_payment_occupied_by_order_ids(
                tenant_id, [purchase_order_id]
            )
        ).get(purchase_order_id, Decimal("0"))
        max_push = compute_prepayment_application_remaining(
            order, reserved + payment_occ
        )
        caps = derive_purchase_order_capabilities(
            order,
            has_prepayment_payment=prepay_map.get(purchase_order_id, False),
            has_prepayment_application=prepay_app_map.get(purchase_order_id, False),
            require_payment_application=require_app,
            prepayment_application_remaining=max_push,
        )
        prepay_cap = caps.push_prepayment
        allowed = bool(prepay_cap.allowed) and max_push > 0
        preview_items: List[Dict[str, Any]] = []
        if allowed:
            req_amt = Decimal(str(amount)) if amount is not None else max_push
            if req_amt > max_push:
                raise ValidationError(f"付款金额超过可预付额度 {max_push}")
            if req_amt <= 0:
                raise ValidationError("付款金额必须大于 0")
            line_models = await lines_from_purchase_order_items(
                tenant_id=tenant_id,
                order=order,
                request_amount=req_amt,
                line_kind="prepayment",
            )
            preview_items = [
                ln.model_dump(by_alias=True, mode="json") for ln in line_models
            ]
        code = str(order.order_code or purchase_order_id)
        max_push_f = float(max_push)
        blocking_reason = prepay_cap.reason if not prepay_cap.allowed else (
            "purchase_order.push_prepayment.no_amount" if max_push <= 0 else None
        )
        return {
            "target_type": "payment",
            "source_type": "purchase_order",
            "source_id": purchase_order_id,
            "source_code": code,
            "order_code": code,
            "max_push_quantity": max_push_f,
            "max_push_total": max_push_f,
            "source_order_amount": max_push_f,
            "summary": (
                f"将从采购订单 {code} 加载预付付款明细（可预付 ¥{max_push_f:,.2f}）"
                if allowed
                else f"采购订单 {code} 当前不可加载预付付款明细"
            ),
            "items": preview_items,
            "has_blocking_issues": not allowed,
            "blocking_reason": blocking_reason,
            "tip": "预付款付款单须对应尚未关联预付付款单的采购订单；确认过账后关联采购订单。",
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier_name,
        }

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
        from apps.kuaicaiwu.constants.payment_method import (
            is_prepayment_offset_payment_method,
        )

        if is_prepayment_offset_payment_method(payment.payment_method):
            raise ValidationError("预付抵扣付款单不支持补核销，请撤回确认后重新保存并核销")
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
        payment_method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """校验加载明细并返回付款申请预览（若有）。"""
        from apps.kuaicaiwu.constants.payment_method import (
            is_prepayment_offset_payment_method,
        )

        pull_lines = coerce_pull_lines_for_validate(pull_lines)
        if not pull_lines:
            raise BusinessLogicError("加载明细不能为空")
        source_types = {
            str(pull_line_field(line, "source_type", "") or "").strip()
            for line in pull_lines
        }
        source_types.discard("")
        if len(source_types) == 0:
            raise BusinessLogicError("加载明细不能为空")
        if len(source_types) > 1:
            raise BusinessLogicError("同一付款单不可混选不同来源类型")
        normalized_type = next(iter(source_types))
        if is_prepayment_offset_payment_method(payment_method):
            if normalized_type != "payable":
                raise BusinessLogicError("预付抵扣仅可加载应付明细")
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
        if normalized_type == "payment_application":
            from apps.kuaizhizao.models.payment_application import PaymentApplication

            app_id = int(pull_line_field(pull_lines[0], "source_id", 0) or 0)
            app = await PaymentApplication.get_or_none(
                tenant_id=tenant_id, id=app_id, deleted_at__isnull=True
            )
            if not app:
                raise BusinessLogicError("付款申请单不存在")
            app_kind = str(app.application_kind or "goods").strip()
            if settlement == "prepayment" and app_kind != "prepayment":
                raise BusinessLogicError("预付款付款单仅可加载预付款类付款申请")
            if settlement == "normal" and app_kind == "prepayment":
                raise BusinessLogicError("普通付款单不可加载预付款类付款申请")
        if normalized_type == "purchase_order":
            by_po: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
            for line in pull_lines:
                amount = Decimal(str(pull_line_field(line, "amount", 0) or 0))
                if amount <= 0:
                    raise BusinessLogicError("明细付款金额须大于 0")
                line_total += amount
                source_id = int(pull_line_field(line, "source_id", 0) or 0)
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
                amount = Decimal(str(pull_line_field(line, "amount", 0) or 0))
                if amount <= 0:
                    raise BusinessLogicError("明细付款金额须大于 0")
                line_total += amount
                source_id = int(pull_line_field(line, "source_id", 0) or 0)
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
            source_type = str(pull_line_field(line, "source_type", "") or "").strip()
            source_id = int(pull_line_field(line, "source_id", 0) or 0)
            source_code = str(pull_line_field(line, "source_code", "") or "").strip() or str(
                source_id
            )
            amount = Decimal(str(pull_line_field(line, "amount", 0) or 0))
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
        payment_method: Optional[str] = None,
    ) -> None:
        await self.validate_pull_lines_for_create(
            tenant_id,
            pull_lines=pull_lines,
            total_amount=total_amount,
            settlement_type=settlement_type,
            payment_method=payment_method,
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

    async def _resolve_purchase_order_id_from_payment_application(
        self,
        tenant_id: int,
        application_id: int,
    ) -> Optional[int]:
        from apps.kuaizhizao.models.payment_application import PaymentApplicationLine
        from apps.kuaicaiwu.services.payable_prepayment_apply_service import (
            PayablePrepaymentApplyService,
        )

        lines = await PaymentApplicationLine.filter(
            tenant_id=tenant_id,
            application_id=int(application_id),
        ).order_by("line_no")
        apply_svc = PayablePrepaymentApplyService()
        for line in lines:
            source_type = str(line.source_type or "").strip()
            source_id = getattr(line, "source_id", None)
            if source_type == "purchase_order" and source_id:
                return int(source_id)
        for line in lines:
            if line.payable_id:
                po_id = await apply_svc.resolve_purchase_order_id_for_payable(
                    tenant_id, int(line.payable_id)
                )
                if po_id:
                    return int(po_id)
        return None

    async def resolve_purchase_order_id_for_prepayment_payment(
        self,
        tenant_id: int,
        prepayment_payment_id: int,
    ) -> Optional[int]:
        pid = int(prepayment_payment_id)
        rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            target_type="payment",
            target_id=pid,
        ).first()
        if rel and rel.source_id:
            return int(rel.source_id)

        from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine

        po_pull = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=pid,
            source_type="purchase_order",
            deleted_at__isnull=True,
        ).order_by("line_no").first()
        if po_pull and po_pull.source_id:
            return int(po_pull.source_id)

        app_pull = await PaymentPullLine.filter(
            tenant_id=tenant_id,
            payment_id=pid,
            source_type="payment_application",
            deleted_at__isnull=True,
        ).order_by("line_no").first()
        if app_pull and app_pull.source_id:
            po_id = await self._resolve_purchase_order_id_from_payment_application(
                tenant_id, int(app_pull.source_id)
            )
            if po_id:
                return po_id

        app_rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="payment_application",
            target_type="payment",
            target_id=pid,
        ).first()
        if app_rel and app_rel.source_id:
            po_id = await self._resolve_purchase_order_id_from_payment_application(
                tenant_id, int(app_rel.source_id)
            )
            if po_id:
                return po_id
        return None

    async def list_prepayment_payment_pull_candidates(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        supplier_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not supplier_id:
            raise BusinessLogicError("须指定供应商后再选择预付款单")
        query = Payment.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            supplier_id=int(supplier_id),
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount__gt=0,
        )
        kw = str(keyword or "").strip()
        if kw:
            query = query.filter(
                Q(payment_code__icontains=kw) | Q(supplier_name__icontains=kw)
            )
        total = await query.count()
        payments = await query.offset(skip).limit(limit).order_by("-payment_date", "-id")
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        rows: List[Dict[str, Any]] = []
        for payment in payments:
            pid = int(payment.id)
            po_id = await self.resolve_purchase_order_id_for_prepayment_payment(
                tenant_id, pid
            )
            po_code: Optional[str] = None
            if po_id:
                order = await PurchaseOrder.get_or_none(
                    tenant_id=tenant_id, id=int(po_id)
                )
                if order:
                    po_code = str(getattr(order, "order_code", None) or po_id)
            code = str(payment.payment_code or pid)
            unsettled = Decimal(str(payment.unsettled_amount or 0))
            total_amt = Decimal(str(payment.total_amount or 0))
            settled = Decimal(str(payment.settled_amount or 0))
            rows.append(
                {
                    "id": pid,
                    "prepayment_payment_id": pid,
                    "code": code,
                    "payment_code": code,
                    "supplier_id": int(payment.supplier_id or 0) or None,
                    "supplier_name": payment.supplier_name,
                    "source_date": str(getattr(payment, "payment_date", "") or ""),
                    "source_status": str(getattr(payment, "status", "") or ""),
                    "status": str(getattr(payment, "status", "") or ""),
                    "payment_method": str(getattr(payment, "payment_method", "") or ""),
                    "total_amount": float(total_amt),
                    "settled_amount": float(settled),
                    "unsettled_amount": float(unsettled),
                    "remaining_amount": float(unsettled),
                    "purchase_order_id": po_id,
                    "purchase_order_code": po_code,
                    "capabilities": {
                        "pull_payment": {
                            "allowed": bool(unsettled > 0),
                            "reason": None
                            if unsettled > 0
                            else "payment.offset_prepayment.no_balance",
                        }
                    },
                }
            )
        return {"data": rows, "total": total, "success": True}

    async def validate_offset_prepayment_lines_for_create(
        self,
        tenant_id: int,
        *,
        offset_prepayment_lines: Sequence[Any],
        pull_lines: Sequence[Any],
        total_amount: Decimal,
    ) -> None:
        from apps.kuaicaiwu.services.payable_prepayment_apply_service import (
            PayablePrepaymentApplyService,
        )

        if not offset_prepayment_lines:
            raise BusinessLogicError("预付抵扣须选择预付款明细")
        apply_svc = PayablePrepaymentApplyService()
        offset_total = Decimal("0")
        prep_by_po: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        unlinked_prep = Decimal("0")
        seen_prep: set[int] = set()
        for line in offset_prepayment_lines:
            if isinstance(line, dict):
                prep_id = int(
                    line.get("prepayment_payment_id") or line.get("source_id") or 0
                )
                amount = Decimal(str(line.get("amount") or 0))
            else:
                prep_id = int(
                    getattr(line, "prepayment_payment_id", None)
                    or getattr(line, "source_id", 0)
                    or 0
                )
                amount = Decimal(str(getattr(line, "amount", 0) or 0))
            if prep_id <= 0:
                raise BusinessLogicError("预付款明细缺少预付款单")
            if prep_id in seen_prep:
                raise BusinessLogicError("同一预付款单不可重复选择")
            seen_prep.add(prep_id)
            if amount <= 0:
                raise BusinessLogicError("预付款抵扣金额须大于 0")
            prep = await Payment.get_or_none(
                tenant_id=tenant_id,
                id=prep_id,
                deleted_at__isnull=True,
            )
            if not prep:
                raise BusinessLogicError(f"预付款单不存在: {prep_id}")
            if str(getattr(prep, "settlement_type", "") or "") != "prepayment":
                raise BusinessLogicError("仅可选择预付款类付款单")
            if str(getattr(prep, "status", "") or "") != "Confirmed":
                raise BusinessLogicError("仅可选择已确认的预付款单")
            unsettled = Decimal(str(prep.unsettled_amount or 0)).quantize(
                Decimal("0.01")
            )
            if amount.quantize(Decimal("0.01")) > unsettled:
                raise BusinessLogicError(
                    f"预付款单 {prep.payment_code or prep_id} 抵扣金额超过未核销余额"
                )
            po_id = await self.resolve_purchase_order_id_for_prepayment_payment(
                tenant_id, prep_id
            )
            offset_total += amount
            if po_id:
                prep_by_po[int(po_id)] += amount
            else:
                unlinked_prep += amount

        expected = Decimal(str(total_amount or 0)).quantize(Decimal("0.01"))
        if offset_total.quantize(Decimal("0.01")) != expected:
            raise BusinessLogicError("预付款抵扣合计须与付款总额一致")

        payable_by_po: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        unlinked_payable = Decimal("0")
        for line in pull_lines or []:
            if isinstance(line, dict):
                source_type = str(line.get("source_type") or "").strip()
                source_id = int(line.get("source_id") or 0)
                amount = Decimal(str(line.get("amount") or 0))
            else:
                source_type = str(getattr(line, "source_type", "") or "").strip()
                source_id = int(getattr(line, "source_id", 0) or 0)
                amount = Decimal(str(getattr(line, "amount", 0) or 0))
            if source_type != "payable" or source_id <= 0 or amount <= 0:
                continue
            po_id = await apply_svc.resolve_purchase_order_id_for_payable(
                tenant_id, source_id
            )
            if po_id:
                payable_by_po[int(po_id)] += amount
            else:
                unlinked_payable += amount

        coverage_error = prepayment_offset_po_coverage_error(
            prep_by_po=prep_by_po,
            unlinked_prep=unlinked_prep,
            payable_by_po=payable_by_po,
            unlinked_payable=unlinked_payable,
            offset_total=offset_total,
        )
        if coverage_error:
            raise BusinessLogicError(coverage_error)

    async def persist_offset_prepayment_lines(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        offset_prepayment_lines: Sequence[Any],
        created_by: int,
    ) -> None:
        from apps.kuaicaiwu.models.payment_offset_prepayment_line import (
            PaymentOffsetPrepaymentLine,
        )

        for index, line in enumerate(offset_prepayment_lines, start=1):
            if isinstance(line, dict):
                prep_id = int(
                    line.get("prepayment_payment_id") or line.get("source_id") or 0
                )
                source_code = line.get("source_code")
                amount = Decimal(str(line.get("amount") or 0))
            else:
                prep_id = int(
                    getattr(line, "prepayment_payment_id", None)
                    or getattr(line, "source_id", 0)
                    or 0
                )
                source_code = getattr(line, "source_code", None)
                amount = Decimal(str(getattr(line, "amount", 0) or 0))
            await PaymentOffsetPrepaymentLine.create(
                tenant_id=tenant_id,
                payment_id=payment_id,
                line_no=index,
                prepayment_payment_id=prep_id,
                source_code=str(source_code or "").strip() or None,
                amount=amount,
                created_by=created_by,
            )

    async def clear_offset_prepayment_lines(
        self,
        tenant_id: int,
        payment_id: int,
    ) -> None:
        from core.utils.timezone_utils import resolve_business_datetime

        from apps.kuaicaiwu.models.payment_offset_prepayment_line import (
            PaymentOffsetPrepaymentLine,
        )

        now = resolve_business_datetime()
        await PaymentOffsetPrepaymentLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
        ).update(deleted_at=now)

    async def replace_payment_offset_prepayment_lines(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        offset_prepayment_lines: Sequence[Any],
        pull_lines: Sequence[Any],
        total_amount: Decimal,
        operator_id: int,
    ) -> None:
        await self.validate_offset_prepayment_lines_for_create(
            tenant_id,
            offset_prepayment_lines=offset_prepayment_lines,
            pull_lines=pull_lines,
            total_amount=total_amount,
        )
        await self.clear_offset_prepayment_lines(tenant_id, payment_id)
        await self.persist_offset_prepayment_lines(
            tenant_id,
            payment_id=payment_id,
            offset_prepayment_lines=offset_prepayment_lines,
            created_by=operator_id,
        )

    async def list_offset_prepayment_lines_for_payment(
        self,
        tenant_id: int,
        payment_id: int,
        *,
        enrich: bool = False,
    ) -> List[Dict[str, Any]]:
        from apps.kuaicaiwu.models.payment_offset_prepayment_line import (
            PaymentOffsetPrepaymentLine,
        )
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        rows = await PaymentOffsetPrepaymentLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
        ).order_by("line_no")
        result: List[Dict[str, Any]] = []
        for row in rows:
            prep_id = int(row.prepayment_payment_id)
            po_id = await self.resolve_purchase_order_id_for_prepayment_payment(
                tenant_id, prep_id
            )
            po_code: Optional[str] = None
            unsettled: Optional[Decimal] = None
            if enrich:
                prep = await Payment.get_or_none(
                    tenant_id=tenant_id, id=prep_id, deleted_at__isnull=True
                )
                if prep:
                    unsettled = Decimal(str(prep.unsettled_amount or 0))
                if po_id:
                    order = await PurchaseOrder.get_or_none(
                        tenant_id=tenant_id, id=int(po_id)
                    )
                    if order:
                        po_code = str(getattr(order, "order_code", None) or po_id)
            result.append(
                {
                    "line_no": int(row.line_no),
                    "prepayment_payment_id": prep_id,
                    "source_code": row.source_code,
                    "amount": Decimal(str(row.amount or 0)),
                    "purchase_order_id": po_id,
                    "purchase_order_code": po_code,
                    "unsettled_amount": unsettled,
                }
            )
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
        """预付抵扣：按用户指定的预付款单及金额核销应付，本单不记银行出账。"""
        from apps.kuaicaiwu.constants.payment_method import (
            is_prepayment_offset_payment_method,
        )
        from apps.kuaicaiwu.models.payment_offset_prepayment_line import (
            PaymentOffsetPrepaymentLine,
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
        offset_lines = await PaymentOffsetPrepaymentLine.filter(
            tenant_id=tenant_id,
            payment_id=payment_id,
            deleted_at__isnull=True,
        ).order_by("line_no")
        if not pull_lines:
            raise ValidationError("预付抵扣须先加载待抵扣应付明细")
        if not offset_lines:
            raise ValidationError("预付抵扣须选择预付款明细")

        pool: List[Dict[str, Any]] = []
        prep_by_po: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        unlinked_prep = Decimal("0")
        offset_total = Decimal("0")
        for row in offset_lines:
            prep_id = int(row.prepayment_payment_id)
            amount = Decimal(str(row.amount or 0))
            po_id = await self.resolve_purchase_order_id_for_prepayment_payment(
                tenant_id, prep_id
            )
            offset_total += amount
            if po_id:
                prep_by_po[int(po_id)] += amount
            else:
                unlinked_prep += amount
            pool.append(
                {
                    "payment_id": prep_id,
                    "po_id": int(po_id) if po_id else None,
                    "remaining": amount,
                }
            )

        settled_any = False
        payable_lines = [ln for ln in pull_lines if str(ln.source_type) == "payable"]
        linked_payables: List[tuple[Any, int]] = []
        unlinked_payables: List[Any] = []
        payable_by_po: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        unlinked_payable = Decimal("0")
        for line in payable_lines:
            need = Decimal(str(line.amount or 0))
            if need <= 0:
                continue
            payable_id = int(line.source_id)
            po_id = await apply_svc.resolve_purchase_order_id_for_payable(
                tenant_id, payable_id
            )
            if po_id:
                payable_by_po[int(po_id)] += need
                linked_payables.append((line, int(po_id)))
            else:
                unlinked_payable += need
                unlinked_payables.append(line)
        coverage_error = prepayment_offset_po_coverage_error(
            prep_by_po=prep_by_po,
            unlinked_prep=unlinked_prep,
            payable_by_po=payable_by_po,
            unlinked_payable=unlinked_payable,
            offset_total=offset_total,
        )
        if coverage_error:
            raise ValidationError(coverage_error)

        async def _apply_line(
            line: Any, allocations: List[tuple[int, Decimal]]
        ) -> None:
            nonlocal settled_any
            applied = await apply_svc.apply_selected_prepayments_to_payable(
                tenant_id,
                payable_id=int(line.source_id),
                amount=Decimal(str(line.amount or 0)),
                operator_id=operator_id,
                allocations=allocations,
                offset_payment_id=int(payment_id),
            )
            target = Decimal(str(line.amount or 0)).quantize(Decimal("0.01"))
            if applied.quantize(Decimal("0.01")) < target:
                raise ValidationError("预付款抵扣执行失败，请核对可用余额")
            settled_any = True

        def _take(
            need: Decimal, po_id: Optional[int]
        ) -> tuple[List[tuple[int, Decimal]], Decimal]:
            allocations: List[tuple[int, Decimal]] = []
            for entry in pool:
                entry_po = entry["po_id"]
                if po_id is not None and entry_po != int(po_id):
                    continue
                rem = Decimal(str(entry["remaining"] or 0))
                if rem <= 0:
                    continue
                take = min(need, rem)
                if take <= 0:
                    continue
                allocations.append((int(entry["payment_id"]), take))
                entry["remaining"] = rem - take
                need -= take
                if need <= 0:
                    break
            return allocations, need

        for line, po_id in linked_payables:
            need = Decimal(str(line.amount or 0))
            allocations, left = _take(need, po_id)
            if left.quantize(Decimal("0.01")) > 0:
                raise ValidationError(
                    "所选预付款明细不足以按采购订单完成应付抵扣，请核对明细"
                )
            await _apply_line(line, allocations)
        for line in unlinked_payables:
            need = Decimal(str(line.amount or 0))
            allocations, left = _take(need, None)
            if left.quantize(Decimal("0.01")) > 0:
                raise ValidationError("未关联采购订单的应付抵扣金额超过可用预付余额")
            await _apply_line(line, allocations)

        if settled_any:
            applied_total = Decimal("0")
            for line in payable_lines:
                applied_total += Decimal(str(line.amount or 0))
            applied_total = applied_total.quantize(Decimal("0.01"))
            await Payment.filter(tenant_id=tenant_id, id=payment_id).update(
                total_amount=applied_total,
                settled_amount=applied_total,
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
