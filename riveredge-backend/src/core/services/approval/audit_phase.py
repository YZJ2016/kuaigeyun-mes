"""审核相位单一派生。

`record.audit = { entity_type, phase, enabled, mode, allowed_actions }` 是前端 uni-audit 的
**唯一来源**。ApprovalInstance 是运行时唯一写者（完成回调把结果写回单据
status / review_status），因此列表无需逐行查实例——由 status / review_status
确定性派生 phase 即可。

``enabled``（= manual）：是否启用**人工**审批流（绑定流程且开关打开）。
``enabled=False`` 表示 **自动通过审核**（提交即写入已通过态），**不是**跳过审核；
phase 仍由 status / review_status 派生，UI 须展示审核状态列。

phase ∈ ``draft`` | ``pending`` | ``approved`` | ``rejected`` | ``none``

撤销审核落点见 ``audit_transition``：人工审且重开终审节点 → pending；
否则 draft（``resolve_revoke_to_draft_landing_phase`` / ``resolve_revoke_landing_phase``）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_DRAFT = {"draft", "草稿"}
# pendingreview：其他费用收支等 PascalCase PendingReview 经 _norm 后的形态
_PENDING = {
    "pending_review",
    "pendingreview",
    "pending_approval",
    "待审核",
    "已提交",
    "pending",
}
_SENT_AWAITING_REVIEW = {"已发送", "sent"}
_AUDITED_STRICT = {"audited", "已审核", "approved"}
_APPROVED_ONGOING = {
    "confirmed", "已确认", "已生效", "effective",
    "executing", "执行中", "in_progress",
    "completed", "已完成", "closed", "已关闭",
    # 报价单：客户确认 / 已转单后不再展示反审核（与 revoke_review 仅允许「已发送」一致）
    "已接受", "accepted", "已转订单", "converted",
}
# 已通过态仍禁止撤销审核的主状态（终态 / 报价转单后）
_REVOKE_DENIED_STATUSES = frozenset({
    "completed", "已完成",
    "closed", "已关闭",
    "cancelled", "已取消",
    "已接受", "accepted",
    "已转订单", "converted",
})
# 含「驳回」：快财务应收/应付/进项发票等写回 review_status=驳回（非仅「已驳回」）
_REJECTED_STATUS = {"rejected", "已驳回", "审核驳回", "驳回"}
_REVIEW_APPROVED = {"approved", "审核通过", "已通过", "通过", "已审核"}
_REVIEW_REJECTED = {"rejected", "已驳回", "审核驳回", "驳回"}
_REVIEW_PENDING = {"待审核", "pending_review", "pending_approval", "已提交", "pending"}
_REVIEW_DRAFT = {"草稿", "draft", ""}

# 提交后仍保持主状态为草稿、仅 review_status 进入待审的单据
# （采购询价、生产工单、报价单、报工、返工）
_DRAFT_REVIEW_PENDING_ENTITY_TYPES = frozenset({
    "purchase_inquiry",
    "work_order",
    "quotation",
    "reporting_record",
    "rework_order",
})
# 上述单据「已提交待审」的 review 取值（不含建单默认 PENDING，避免草稿同时露出提交+审核）
_DRAFT_ENTITY_SUBMITTED_REVIEW = frozenset({
    "pending_review",
    "pending_approval",
    "待审核",
    "已提交",
})

# 来料/过程/成品/出货检验：须先执行检验，再进入审核（与 quality_inspection_record capabilities 一致）
_QUALITY_INSPECTION_ENTITY_TYPES = frozenset({
    "incoming_inspection",
    "process_inspection",
    "finished_goods_inspection",
    "oqc_inspection",
})
_QUALITY_INSPECTION_PRE_CONDUCT_STATUSES = frozenset({
    "待检验", "pending_inspection",
})
_QUALITY_INSPECTION_PENDING_MAIN_STATUSES = frozenset({
    "已检验", "inspected", "待审核", "pending_review",
})
_QUALITY_INSPECTION_APPROVED_MAIN_STATUSES = frozenset({
    "已审核", "audited", "approved",
})

# 审核已通过、主 status 进入业务履约态（无 review_status 字段的单据）
_ENTITY_APPROVED_BUSINESS_STATUSES: Dict[str, frozenset[str]] = {
    "payment_application": frozenset({"已批准", "部分付款", "approved", "audited"}),
}
# 业务 status 与 review_status 分离（退货、采购入库：主状态是执行态，审核看 review_status）
_RETURN_REVIEW_ENTITY_TYPES = frozenset({
    "sales_return",
    "purchase_return",
    "purchase_receipt",
    "receipt_notice",
    "shipment_notice",
    "sales_delivery",
})
# 财务 AR/AP/进项：主 status 为收付款态，审核看 review_status
_FINANCE_REVIEW_ENTITY_TYPES = frozenset({
    "receivable",
    "payable",
    "purchase_invoice",
    "partner_statement",
    "receipt",
    "receipt_refund",
    "payment",
    "payment_refund",
    "sales_invoice",
    "other_income",
    "other_expense",
    "other_expense_application",
    "notes_receivable",
    "notes_payable",
    "fund_transfer",
})
_ALLOWED_ACTIONS_BY_PHASE: Dict[str, List[str]] = {
    "draft": ["submit"],
    "submitted": ["submit_review", "withdraw"],
    "rejected": ["submit"],
    "pending": ["approve", "reject", "withdraw"],
    "approved": ["revoke"],
    "none": [],
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def derive_audit_phase(
    entity_type: str,
    status: Any,
    review_status: Any = None,
    *,
    enabled: bool,
    review_submitted: Optional[bool] = None,
) -> Dict[str, Any]:
    """由单据状态确定性派生审核相位与允许动作。

    Args:
        entity_type: 实体类型（= manifest.audit.entity_type，也即 ApprovalProcess.code）。
        status: 单据主状态。
        review_status: 单据审核状态（可空）。
        enabled: 该单据类型当前是否开启了人工审核（AuditDocumentBinding.is_enabled + 已绑定流程）。
    """
    raw_status = str(status or "").strip()
    s = _norm(status)
    r = _norm(review_status)

    if s in _REJECTED_STATUS or r in _REVIEW_REJECTED:
        phase = "rejected"
    elif raw_status == "SUBMITTED":
        phase = "submitted"
    elif entity_type in _RETURN_REVIEW_ENTITY_TYPES | _FINANCE_REVIEW_ENTITY_TYPES:
        raw_review = str(review_status or "").strip()
        pending_review = r in _REVIEW_PENDING or raw_review in _REVIEW_PENDING
        if entity_type == "partner_statement":
            biz_n = _norm(status)
            if biz_n in ("draft", "disputed"):
                if pending_review:
                    phase = "pending"
                elif r in _REVIEW_APPROVED or raw_review in _REVIEW_APPROVED:
                    phase = "approved"
                elif r in _REVIEW_REJECTED:
                    phase = "rejected"
                else:
                    phase = "draft"
            elif biz_n == "confirmed":
                if pending_review:
                    phase = "pending"
                elif r in _REVIEW_APPROVED or raw_review in _REVIEW_APPROVED:
                    phase = "approved"
                elif r in _REVIEW_REJECTED:
                    phase = "rejected"
                elif r in _REVIEW_DRAFT or raw_review in ("草稿", "draft", ""):
                    phase = "submitted"
                else:
                    phase = "none"
            elif biz_n in ("sent", "ledgerposted") and (
                r in _REVIEW_APPROVED or raw_review in _REVIEW_APPROVED
            ):
                phase = "approved"
            else:
                phase = "none"
        elif (
            entity_type in (
                "purchase_return",
                "sales_return",
                "purchase_receipt",
                "receipt_notice",
                "shipment_notice",
                "sales_delivery",
                "receivable",
                "payable",
                "purchase_invoice",
                "receipt",
                "receipt_refund",
                "payment",
                "payment_refund",
                "sales_invoice",
                "other_income",
                "other_expense",
                "other_expense_application",
                "notes_receivable",
                "notes_payable",
                "partner_statement",
                "fund_transfer",
            )
            and raw_review == "SUBMITTED"
        ):
            phase = "submitted"
        elif pending_review:
            phase = "draft" if review_submitted is False else "pending"
        elif r in _REVIEW_APPROVED or raw_review in _REVIEW_APPROVED:
            phase = "approved"
        elif r in _REVIEW_DRAFT or s in _DRAFT:
            phase = "draft"
        else:
            phase = "none"
    elif entity_type in _QUALITY_INSPECTION_ENTITY_TYPES:
        # 未检验完成前：忽略预置/残留的 review_status，审核列显示 —
        if s in _QUALITY_INSPECTION_PRE_CONDUCT_STATUSES or not s:
            phase = "none"
        elif r in _REVIEW_PENDING and s in _QUALITY_INSPECTION_PENDING_MAIN_STATUSES:
            phase = "pending"
        elif r in _REVIEW_APPROVED or s in _QUALITY_INSPECTION_APPROVED_MAIN_STATUSES:
            phase = "approved"
        else:
            phase = "none"
    elif s in _DRAFT:
        # 主状态仍为草稿：已通过 / 已提交未送审（采购询价）/ 已提交待审 / 其余草稿
        raw_review = str(review_status or "").strip()
        if r in _REVIEW_APPROVED:
            phase = "approved"
        elif entity_type in _DRAFT_REVIEW_PENDING_ENTITY_TYPES and raw_review == "SUBMITTED":
            phase = "submitted"
        elif (
            entity_type in _DRAFT_REVIEW_PENDING_ENTITY_TYPES
            and r in _DRAFT_ENTITY_SUBMITTED_REVIEW
        ):
            phase = "draft" if review_submitted is False else "pending"
        else:
            phase = "draft"
    elif (s in _PENDING or s in _SENT_AWAITING_REVIEW) and r not in _REVIEW_APPROVED:
        phase = "draft" if review_submitted is False else "pending"
    elif s in _AUDITED_STRICT or s in _APPROVED_ONGOING or r in _REVIEW_APPROVED:
        phase = "approved"
    elif entity_type in _ENTITY_APPROVED_BUSINESS_STATUSES and s in _ENTITY_APPROVED_BUSINESS_STATUSES[entity_type]:
        phase = "approved"
    else:
        phase = "none"

    allowed = list(_ALLOWED_ACTIONS_BY_PHASE[phase])
    # 已通过态默认允许 revoke；终态或报价转单后禁止（业务能力门控见 audit_capability_gate）
    if phase == "approved":
        allow_revoke = s not in _REVOKE_DENIED_STATUSES
        if not allow_revoke:
            allowed = []

    if entity_type in _QUALITY_INSPECTION_ENTITY_TYPES:
        # 无草稿提交/撤回；pending 仅人审/驳，approved 保留 revoke（与 capabilities 对齐）
        if phase == "pending":
            allowed = [a for a in allowed if a in ("approve", "reject")]
        elif phase == "approved":
            allowed = [a for a in allowed if a == "revoke"]
        else:
            allowed = []

    # 审核关闭（自动通过）：不提供人工审/驳回；已通过态仍保留 revoke，便于撤回后再编辑。
    # pending 仍保留 submit：用于误入待审时再次提交即自动通过。
    # 检验单无 submit/withdraw 业务态，关闭审核时 pending 不注入假路径。
    if not enabled:
        if entity_type in _QUALITY_INSPECTION_ENTITY_TYPES:
            if phase == "approved":
                allowed = [a for a in allowed if a == "revoke"]
            else:
                allowed = []
        elif phase == "submitted":
            allowed = ["submit_review", "withdraw"]
        elif phase in ("draft", "rejected"):
            allowed = ["submit"]
        elif phase == "pending":
            allowed = ["submit", "withdraw"]
        elif phase == "approved":
            allowed = [a for a in allowed if a == "revoke"]
        else:
            allowed = []

    if entity_type == "partner_statement":
        biz_n = _norm(status)
        if phase in ("draft", "rejected") and biz_n in ("draft", "disputed", ""):
            allowed = ["submit_review"]
        elif phase == "rejected" and biz_n == "confirmed":
            allowed = ["submit_review"]

    return {
        "entity_type": entity_type,
        "phase": phase,
        "enabled": bool(enabled),
        "mode": "manual" if enabled else "auto",
        "allowed_actions": allowed,
    }
