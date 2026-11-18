"""
收/付款单纠错门禁与过账回滚（唯一真源）。

无退款的已确认单：可作废 / 撤回确认 / 删除；须先冲回往来核销与银行流水。
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, Literal, Optional

from infra.exceptions.exceptions import BusinessLogicError, ValidationError
from core.utils.timezone_utils import now_utc

VoucherKind = Literal["receipt", "payment"]


def quantize_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def assert_voucher_correction_allowed(voucher: Any, *, action: str) -> None:
    """
    action: cancel | unconfirm | delete | update
    """
    status = str(getattr(voucher, "status", "") or "").strip()
    settlement_type = str(getattr(voucher, "settlement_type", "") or "normal").strip() or "normal"
    refunded = quantize_money(getattr(voucher, "refunded_amount", 0))
    refund_exec = str(getattr(voucher, "refund_execution_status", "") or "").strip()

    if settlement_type == "refund":
        if action == "update" and status == "Draft":
            return
        if action == "delete" and status in ("Draft", "Cancelled"):
            return
        raise BusinessLogicError("退款单请在收款退款/付款退款菜单处理，不可按普通收付款纠错")

    if refunded > 0 or refund_exec in ("部分退款", "全部退款"):
        raise BusinessLogicError("已有退款记录，不可直接纠错；请先处理退款单据")

    if action == "update":
        if status != "Draft":
            raise BusinessLogicError("仅草稿状态可修改；已确认请先撤回确认")
        return

    if action == "unconfirm":
        if status != "Confirmed":
            raise BusinessLogicError("仅已确认单据可撤回确认")
        return

    if action == "cancel":
        if status == "Cancelled":
            raise BusinessLogicError("单据已作废")
        if status not in ("Draft", "Confirmed"):
            raise BusinessLogicError("当前状态不可作废")
        return

    if action == "delete":
        if status in ("Draft", "Cancelled", "Confirmed"):
            return
        raise BusinessLogicError("当前状态不可删除")

    raise ValueError(f"unknown voucher correction action: {action}")


def _settlement_notes_payload(notes: Optional[str]) -> Dict[str, Any]:
    if not notes or not str(notes).strip():
        return {}
    try:
        parsed = json.loads(str(notes))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _reverse_one_payable_payment_settlement(
    tenant_id: int,
    settlement: Any,
    *,
    operator_id: Optional[int],
    user_name: str,
) -> None:
    """冲销一条应付←付款核销，并回写应付与贷方付款单余额。"""
    from apps.kuaicaiwu.models.payment import Payment
    from apps.kuaicaiwu.models.payable import Payable
    from apps.kuaicaiwu.services.finance_refund_utils import (
        compute_open_balance_after_refund,
        resolve_ap_status_after_amounts,
    )
    from apps.kuaicaiwu.services.return_open_balance_offset_service import (
        sum_goods_offset_for_payable,
    )

    amount = quantize_money(settlement.amount)
    if amount <= 0:
        return
    if str(settlement.debit_doc_type or "") != "Payable":
        raise BusinessLogicError(
            f"付款单存在非应付核销记录（{settlement.debit_doc_type}），无法自动纠错"
        )
    payable = await Payable.get_or_none(
        tenant_id=tenant_id, id=int(settlement.debit_doc_id)
    )
    if not payable:
        raise BusinessLogicError(f"核销关联应付单不存在: {settlement.debit_doc_id}")
    new_paid = quantize_money(payable.paid_amount) - amount
    if new_paid < 0:
        new_paid = Decimal("0.00")
    refunded = quantize_money(getattr(payable, "refunded_amount", 0) or 0)
    goods_offset = await sum_goods_offset_for_payable(tenant_id, int(payable.id))
    new_remaining = compute_open_balance_after_refund(
        payable.total_amount,
        new_paid,
        refunded,
        goods_offset,
    )
    net_paid = quantize_money(new_paid - refunded)
    if net_paid < Decimal("0.00"):
        net_paid = Decimal("0.00")
    ap_status = resolve_ap_status_after_amounts(
        total_amount=payable.total_amount,
        paid_amount=net_paid,
        remaining_amount=new_remaining,
    )
    await Payable.filter(tenant_id=tenant_id, id=payable.id).update(
        paid_amount=new_paid,
        remaining_amount=new_remaining,
        status=ap_status,
        updated_by=operator_id,
        updated_by_name=user_name or None,
    )

    credit_payment = await Payment.get_or_none(
        tenant_id=tenant_id,
        id=int(settlement.credit_doc_id),
        deleted_at__isnull=True,
    )
    if credit_payment:
        new_settled = quantize_money(credit_payment.settled_amount) - amount
        if new_settled < 0:
            new_settled = Decimal("0.00")
        new_unsettled = quantize_money(credit_payment.total_amount) - new_settled
        if new_unsettled < 0:
            new_unsettled = Decimal("0.00")
        await Payment.filter(tenant_id=tenant_id, id=int(credit_payment.id)).update(
            settled_amount=new_settled,
            unsettled_amount=new_unsettled,
            updated_by=operator_id,
            updated_by_name=user_name or None,
        )

    settlement.is_active = False
    settlement.deleted_at = now_utc()
    await settlement.save()


async def _unwind_prepayment_offset_payment_settlements(
    tenant_id: int,
    offset_payment: Any,
    *,
    operator_id: Optional[int],
    user_name: str,
) -> None:
    """预付抵扣单撤回：冲销本单触发的预付款→应付核销（贷方为预付款单，非抵扣单本身）。"""
    from apps.kuaicaiwu.models.payment_offset_prepayment_line import (
        PaymentOffsetPrepaymentLine,
    )
    from apps.kuaicaiwu.models.payment_pull_line import PaymentPullLine
    from apps.kuaicaiwu.models.settlement import SettlementRecord

    offset_id = int(offset_payment.id)
    pull_lines = await PaymentPullLine.filter(
        tenant_id=tenant_id,
        payment_id=offset_id,
        deleted_at__isnull=True,
        source_type="payable",
    ).all()
    offset_lines = await PaymentOffsetPrepaymentLine.filter(
        tenant_id=tenant_id,
        payment_id=offset_id,
        deleted_at__isnull=True,
    ).all()
    if not pull_lines or not offset_lines:
        raise BusinessLogicError(
            "预付抵扣单缺少应付或预付款明细，无法自动冲回核销，请核对单据数据"
        )

    payable_caps: Dict[int, Decimal] = {}
    for line in pull_lines:
        pid = int(line.source_id or 0)
        if pid <= 0:
            continue
        payable_caps[pid] = payable_caps.get(pid, Decimal("0.00")) + quantize_money(
            line.amount
        )
    prep_ids = {
        int(row.prepayment_payment_id)
        for row in offset_lines
        if int(getattr(row, "prepayment_payment_id", 0) or 0) > 0
    }
    if not payable_caps or not prep_ids:
        raise BusinessLogicError("预付抵扣明细无效，无法冲回核销")

    settlements = (
        await SettlementRecord.filter(
            tenant_id=tenant_id,
            credit_doc_type="Payment",
            credit_doc_id__in=list(prep_ids),
            debit_doc_type="Payable",
            debit_doc_id__in=list(payable_caps.keys()),
            is_active=True,
            deleted_at__isnull=True,
        )
        .order_by("-id")
        .all()
    )

    remaining = dict(payable_caps)
    reversed_any = False
    for settlement in settlements:
        payable_id = int(settlement.debit_doc_id)
        cap_left = remaining.get(payable_id, Decimal("0.00"))
        if cap_left <= 0:
            continue
        meta = _settlement_notes_payload(getattr(settlement, "notes", None))
        tagged_offset = meta.get("offset_payment_id")
        if tagged_offset is not None and int(tagged_offset) != offset_id:
            continue
        amount = quantize_money(settlement.amount)
        if amount <= 0 or amount > cap_left + Decimal("0.009"):
            if tagged_offset is not None:
                continue
            if amount > cap_left + Decimal("0.009"):
                continue
        await _reverse_one_payable_payment_settlement(
            tenant_id,
            settlement,
            operator_id=operator_id,
            user_name=user_name,
        )
        remaining[payable_id] = quantize_money(cap_left - amount)
        reversed_any = True

    if not reversed_any:
        raise BusinessLogicError(
            "未找到可冲回的预付抵扣核销记录，请确认本单已确认过账且预付款核销未被其他单据占用"
        )

    total = quantize_money(offset_payment.total_amount)
    from apps.kuaicaiwu.models.payment import Payment

    await Payment.filter(tenant_id=tenant_id, id=offset_id).update(
        settled_amount=Decimal("0.00"),
        unsettled_amount=total,
        updated_by=operator_id,
        updated_by_name=user_name or None,
    )


async def unwind_voucher_settlements(
    tenant_id: int,
    *,
    voucher_type: VoucherKind,
    voucher_id: int,
    operator_id: Optional[int] = None,
) -> None:
    """冲回收/付款单关联的往来核销，并重置单据已核销/待核销金额。"""
    from apps.kuaicaiwu.models.payment import Payment
    from apps.kuaicaiwu.models.receipt import Receipt
    from apps.kuaicaiwu.models.receivable import Receivable
    from apps.common.audit_actor import operator_name_from_user
    from apps.kuaicaiwu.models.settlement import SettlementRecord
    from infra.models.user import User

    user_name = ""
    if operator_id:
        user = await User.filter(id=operator_id).first()
        if user:
            user_name = operator_name_from_user(user)

    if voucher_type == "receipt":
        voucher = await Receipt.get_or_none(
            tenant_id=tenant_id, id=voucher_id, deleted_at__isnull=True
        )
        if not voucher:
            raise ValidationError(f"收款单不存在: {voucher_id}")
        settlements = await SettlementRecord.filter(
            tenant_id=tenant_id,
            credit_doc_type="Receipt",
            credit_doc_id=voucher_id,
            is_active=True,
            deleted_at__isnull=True,
        ).all()
        for settlement in settlements:
            amount = quantize_money(settlement.amount)
            if amount <= 0:
                continue
            if str(settlement.debit_doc_type or "") != "Receivable":
                raise BusinessLogicError(
                    f"收款单存在非应收核销记录（{settlement.debit_doc_type}），无法自动纠错"
                )
            receivable = await Receivable.get_or_none(
                tenant_id=tenant_id, id=int(settlement.debit_doc_id)
            )
            if not receivable:
                raise BusinessLogicError(f"核销关联应收单不存在: {settlement.debit_doc_id}")
            new_received = quantize_money(receivable.received_amount) - amount
            if new_received < 0:
                new_received = Decimal("0.00")
            from apps.kuaicaiwu.services.finance_refund_utils import (
                compute_open_balance_after_refund,
                resolve_ar_status_after_amounts,
            )

            refunded = quantize_money(getattr(receivable, "refunded_amount", 0) or 0)
            from apps.kuaicaiwu.services.return_open_balance_offset_service import (
                sum_goods_offset_for_receivable,
            )

            goods_offset = await sum_goods_offset_for_receivable(tenant_id, int(receivable.id))
            new_remaining = compute_open_balance_after_refund(
                receivable.total_amount,
                new_received,
                refunded,
                goods_offset,
            )
            net_received = quantize_money(new_received - refunded)
            if net_received < Decimal("0.00"):
                net_received = Decimal("0.00")
            ar_status = resolve_ar_status_after_amounts(
                total_amount=receivable.total_amount,
                received_amount=net_received,
                remaining_amount=new_remaining,
            )
            await Receivable.filter(tenant_id=tenant_id, id=receivable.id).update(
                received_amount=new_received,
                remaining_amount=new_remaining,
                status=ar_status,
                updated_by=operator_id,
                updated_by_name=user_name or None,
            )
            settlement.is_active = False
            settlement.deleted_at = now_utc()
            await settlement.save()

        total = quantize_money(voucher.total_amount)
        await Receipt.filter(tenant_id=tenant_id, id=voucher_id).update(
            settled_amount=Decimal("0.00"),
            unsettled_amount=total,
            updated_by=operator_id,
            updated_by_name=user_name or None,
        )
        return

    voucher = await Payment.get_or_none(
        tenant_id=tenant_id, id=voucher_id, deleted_at__isnull=True
    )
    if not voucher:
        raise ValidationError(f"付款单不存在: {voucher_id}")

    from apps.kuaicaiwu.constants.payment_method import (
        is_prepayment_offset_payment_method,
    )

    if is_prepayment_offset_payment_method(voucher.payment_method):
        await _unwind_prepayment_offset_payment_settlements(
            tenant_id,
            voucher,
            operator_id=operator_id,
            user_name=user_name,
        )
        return

    settlements = await SettlementRecord.filter(
        tenant_id=tenant_id,
        credit_doc_type="Payment",
        credit_doc_id=voucher_id,
        is_active=True,
        deleted_at__isnull=True,
    ).all()
    for settlement in settlements:
        await _reverse_one_payable_payment_settlement(
            tenant_id,
            settlement,
            operator_id=operator_id,
            user_name=user_name,
        )

    total = quantize_money(voucher.total_amount)
    await Payment.filter(tenant_id=tenant_id, id=voucher_id).update(
        settled_amount=Decimal("0.00"),
        unsettled_amount=total,
        updated_by=operator_id,
        updated_by_name=user_name or None,
    )


async def reverse_voucher_bank_if_needed(
    tenant_id: int,
    *,
    voucher_type: VoucherKind,
    voucher_id: int,
    operator_id: Optional[int] = None,
) -> None:
    from apps.kuaicaiwu.services.bank_account_service import BankAccountService

    await BankAccountService().reverse_from_voucher(
        tenant_id,
        voucher_type=voucher_type,
        voucher_id=voucher_id,
        operator_id=operator_id,
    )


async def apply_confirmed_voucher_unpost(
    tenant_id: int,
    *,
    voucher_type: VoucherKind,
    voucher_id: int,
    operator_id: Optional[int] = None,
) -> None:
    """已确认单据纠错前：冲回核销 + 冲回银行流水。"""
    await unwind_voucher_settlements(
        tenant_id,
        voucher_type=voucher_type,
        voucher_id=voucher_id,
        operator_id=operator_id,
    )
    await reverse_voucher_bank_if_needed(
        tenant_id,
        voucher_type=voucher_type,
        voucher_id=voucher_id,
        operator_id=operator_id,
    )
    if voucher_type == "payment":
        from apps.kuaicaiwu.services.payment_advance_service import PaymentAdvanceService
        from apps.kuaizhizao.services.payment_application_push_service import (
            PaymentApplicationPushService,
        )

        await PaymentAdvanceService().void_for_payment(tenant_id, voucher_id)
        # 须在删除 DocumentRelation 之前冲回，否则找不到申请单
        await PaymentApplicationPushService().apply_payment_unconfirmed(
            tenant_id, voucher_id, operator_id or 0
        )
