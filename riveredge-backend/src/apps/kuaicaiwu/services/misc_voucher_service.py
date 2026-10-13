"""其他费用收入/支出单据与收支类别服务（收入/支出共享实现）。

边界：不复用 Payment/Receipt，不生成应收/应付，不走 UniPullQuery/核销；
确认过账仅写银行流水（见 misc_voucher_posting_service）。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.common.audit_actor import (
    apply_create_audit,
    apply_update_audit,
    operator_name_from_user,
)
from apps.kuaicaiwu.models.finance_misc_category import (
    MiscExpenseCategory,
    MiscIncomeCategory,
)
from apps.kuaicaiwu.models.other_voucher import (
    OtherExpense,
    OtherExpenseLine,
    OtherIncome,
    OtherIncomeLine,
)
from apps.kuaicaiwu.services.bank_account_service import BankAccountService
from apps.kuaicaiwu.services.finance_voucher_codes import (
    allocate_other_expense_code,
    allocate_other_income_code,
)
from apps.kuaicaiwu.services.misc_voucher_posting_service import (
    MiscVoucherPostingService,
)
from core.services.approval.audit_flow_guard import (
    approval_instance_finished_on_submit,
    assert_pending_approval_instance,
    start_document_approval_or_raise,
)
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User
from infra.services.business_config_service import BusinessConfigService


@dataclass(frozen=True)
class MiscVoucherSpec:
    voucher_type: str
    label: str
    doc_label: str
    code_field: str
    fk_field: str
    node_key: str
    model: Any
    line_model: Any
    category_model: Any
    allocate_code: Any


INCOME_SPEC = MiscVoucherSpec(
    voucher_type="other_income",
    label="其他费用收入单",
    doc_label="其他费用收入",
    code_field="income_code",
    fk_field="other_income_id",
    node_key="other_income",
    model=OtherIncome,
    line_model=OtherIncomeLine,
    category_model=MiscIncomeCategory,
    allocate_code=allocate_other_income_code,
)

EXPENSE_SPEC = MiscVoucherSpec(
    voucher_type="other_expense",
    label="其他费用支出单",
    doc_label="其他费用支出",
    code_field="expense_code",
    fk_field="other_expense_id",
    node_key="other_expense",
    model=OtherExpense,
    line_model=OtherExpenseLine,
    category_model=MiscExpenseCategory,
    allocate_code=allocate_other_expense_code,
)

_EDITABLE = frozenset({"Draft", "Rejected"})
_CANCELABLE = frozenset({"Draft", "Rejected", "Approved", "Confirmed"})
_DELETABLE = frozenset({"Draft", "Rejected", "Cancelled"})
_COUNTERPARTY_KINDS = frozenset({"none", "customer", "supplier", "employee", "other"})


class MiscVoucherService:
    """其他费用收入/支出单据 CRUD 与生命周期。"""

    def __init__(self, spec: MiscVoucherSpec) -> None:
        self.spec = spec

    async def get_or_404(self, tenant_id: int, doc_id: int):
        doc = await self.spec.model.get_or_none(
            tenant_id=tenant_id, id=doc_id, deleted_at__isnull=True
        )
        if not doc:
            raise NotFoundError(f"{self.spec.label}不存在: {doc_id}")
        return doc

    async def audit_required(self, tenant_id: int) -> bool:
        return await BusinessConfigService().check_audit_required(
            tenant_id, self.spec.node_key
        )

    def capabilities(self, doc: Any, *, audit_required: bool) -> Dict[str, Dict[str, bool]]:
        status = str(getattr(doc, "status", "") or "")
        return {
            "update": {"allowed": status in _EDITABLE},
            "submit": {"allowed": status in _EDITABLE},
            "approve": {"allowed": status == "PendingReview"},
            "reject": {"allowed": status == "PendingReview"},
            "confirm": {
                "allowed": status == "Approved"
                or (status == "Draft" and not audit_required)
            },
            "unconfirm": {"allowed": status == "Confirmed"},
            "cancel": {"allowed": status in _CANCELABLE},
            "delete": {"allowed": status in _DELETABLE},
        }

    async def _resolve_lines(self, tenant_id: int, lines_in: List[Any]) -> List[Dict[str, Any]]:
        """校验明细行并回填类别名称；返回落库行 dict 列表。"""
        codes = [
            str(l.category_code or "").strip() for l in lines_in
        ]
        if not codes or any(not c for c in codes):
            raise ValidationError("明细行必须选择收支类别")
        cats = await self.spec.category_model.filter(
            tenant_id=tenant_id, code__in=codes, deleted_at__isnull=True
        ).all()
        cat_by_code = {str(c.code): c for c in cats}
        resolved: List[Dict[str, Any]] = []
        for idx, line in enumerate(lines_in, start=1):
            code = str(line.category_code or "").strip()
            cat = cat_by_code.get(code)
            if not cat:
                raise ValidationError(f"收支类别不存在: {code}")
            amount = Decimal(str(line.amount or 0))
            if amount <= 0:
                raise ValidationError("明细行金额必须大于 0")
            resolved.append(
                {
                    "line_no": idx,
                    "category_code": code,
                    "category_name": str(getattr(line, "category_name", None) or cat.name),
                    "amount": amount,
                    "description": getattr(line, "description", None),
                    "gl_account_code": getattr(line, "gl_account_code", None)
                    or cat.default_gl_account_code,
                }
            )
        return resolved

    def _assert_counterparty(self, data: Any) -> None:
        self._assert_counterparty_dict(
            {
                "counterparty_kind": getattr(data, "counterparty_kind", None),
                "counterparty_id": getattr(data, "counterparty_id", None),
                "counterparty_name": getattr(data, "counterparty_name", None),
            }
        )

    @staticmethod
    def _assert_counterparty_dict(data: Dict[str, Any]) -> None:
        kind = str(data.get("counterparty_kind") or "none")
        if kind not in _COUNTERPARTY_KINDS:
            raise ValidationError(f"不支持的往来对象类型: {kind}")
        if kind in ("customer", "supplier", "employee") and not data.get(
            "counterparty_id"
        ):
            raise ValidationError("往来对象类型为客商/员工时须选择往来对象")
        if kind == "other" and not str(data.get("counterparty_name") or "").strip():
            raise ValidationError("往来对象类型为其他时须填写往来对象名称")

    async def _replace_lines(
        self,
        tenant_id: int,
        doc_id: int,
        resolved: List[Dict[str, Any]],
        user: Optional[User],
    ) -> None:
        await self.spec.line_model.filter(
            tenant_id=tenant_id, **{self.spec.fk_field: doc_id}
        ).delete()
        for row in resolved:
            payload = {
                "tenant_id": tenant_id,
                self.spec.fk_field: doc_id,
                **row,
            }
            apply_create_audit(payload, user)
            await self.spec.line_model.create(**payload)

    async def create(self, tenant_id: int, data: Any, user: User):
        self._assert_counterparty(data)
        await BankAccountService().validate_voucher_account(
            tenant_id,
            payment_method=data.payment_method,
            bank_account_id=data.bank_account_id,
        )
        resolved = await self._resolve_lines(tenant_id, data.lines)
        total = sum((r["amount"] for r in resolved), Decimal("0"))
        code = await self.spec.allocate_code(tenant_id)
        payload = {
            "tenant_id": tenant_id,
            self.spec.code_field: code,
            "business_date": data.business_date,
            "counterparty_kind": data.counterparty_kind or "none",
            "counterparty_id": data.counterparty_id,
            "counterparty_name": data.counterparty_name,
            "total_amount": total,
            "payment_method": data.payment_method,
            "bank_account_id": data.bank_account_id,
            "bank_account": data.bank_account,
            "status": "Draft",
            "department_id": data.department_id,
            "department_name": data.department_name,
            "project_id": data.project_id,
            "project_name": data.project_name,
            "notes": data.notes,
            "attachments": data.attachments,
        }
        apply_create_audit(payload, user)
        doc = await self.spec.model.create(**payload)
        for row in resolved:
            line_payload = {
                "tenant_id": tenant_id,
                self.spec.fk_field: int(doc.id),
                **row,
            }
            apply_create_audit(line_payload, user)
            await self.spec.line_model.create(**line_payload)
        return doc

    async def update(self, tenant_id: int, doc_id: int, data: Any, user: User):
        doc = await self.get_or_404(tenant_id, doc_id)
        if str(doc.status) not in _EDITABLE:
            raise BusinessLogicError(
                f"仅草稿/已驳回状态可修改{self.spec.label}，当前状态: {doc.status}"
            )
        update_data = data.model_dump(exclude_unset=True)
        update_data.pop("lines", None)
        merged = {**doc.__dict__, **update_data}
        self._assert_counterparty_dict(merged)
        method = update_data.get("payment_method", doc.payment_method)
        account_id = update_data.get("bank_account_id", doc.bank_account_id)
        await BankAccountService().validate_voucher_account(
            tenant_id, payment_method=method, bank_account_id=account_id
        )
        if data.lines is not None:
            resolved = await self._resolve_lines(tenant_id, data.lines)
            update_data["total_amount"] = sum(
                (r["amount"] for r in resolved), Decimal("0")
            )
            await self._replace_lines(tenant_id, doc_id, resolved, user)
        apply_update_audit(update_data, user)
        await self.spec.model.filter(id=doc_id).update(**update_data)
        return await self.get_or_404(tenant_id, doc_id)

    def _reviewer_patch(self, user: User, remarks: Optional[str]) -> Dict[str, Any]:
        return {
            "reviewer_id": user.id,
            "reviewer_name": operator_name_from_user(user),
            "review_time": resolve_business_datetime(),
            "review_remarks": remarks,
        }

    async def submit(self, tenant_id: int, doc_id: int, user: User):
        doc = await self.get_or_404(tenant_id, doc_id)
        status = str(doc.status)
        audit_required = await self.audit_required(tenant_id)
        if status == "PendingReview" and audit_required:
            raise BusinessLogicError(
                f"{self.spec.label}已提交待审核，无需重复提交"
            )
        if status not in _EDITABLE and status != "PendingReview":
            raise BusinessLogicError(
                f"当前状态不可提交审核，当前状态: {doc.status}"
            )
        if not audit_required:
            patch = {"status": "Approved", **self._reviewer_patch(user, "自动审核")}
            apply_update_audit(patch, user)
            await self.spec.model.filter(id=doc_id).update(**patch)
            return await self.get_or_404(tenant_id, doc_id)

        doc_code = str(getattr(doc, self.spec.code_field, None) or doc_id)
        partner = str(getattr(doc, "counterparty_name", None) or "").strip()
        content = f"{self.spec.doc_label} {doc_code}"
        if partner:
            content = f"{content}, 往来单位: {partner}"
        content = f"{content}, 金额: {doc.total_amount}"
        instance = await start_document_approval_or_raise(
            tenant_id=tenant_id,
            user_id=user.id,
            node_key=self.spec.node_key,
            entity_type=self.spec.voucher_type,
            entity_id=int(doc.id),
            entity_uuid=str(doc.uuid),
            title=f"{self.spec.doc_label}审核: {doc_code}",
            content=content,
            doc_label=self.spec.doc_label,
        )
        patch: Dict[str, Any] = {"status": "PendingReview"}
        apply_update_audit(patch, user)
        await self.spec.model.filter(id=doc_id).update(**patch)
        if approval_instance_finished_on_submit(instance):
            patch = {"status": "Approved", **self._reviewer_patch(user, "自动审核")}
            apply_update_audit(patch, user)
            await self.spec.model.filter(id=doc_id).update(**patch)
        return await self.get_or_404(tenant_id, doc_id)

    async def _review(
        self,
        tenant_id: int,
        doc_id: int,
        user: User,
        *,
        approve: bool,
        remarks: Optional[str],
    ):
        doc = await self.get_or_404(tenant_id, doc_id)
        if str(doc.status) != "PendingReview":
            raise BusinessLogicError(
                f"仅待审核状态可审核/驳回，当前状态: {doc.status}"
            )
        audit_required = await self.audit_required(tenant_id)
        await assert_pending_approval_instance(
            tenant_id=tenant_id,
            entity_type=self.spec.voucher_type,
            entity_id=doc_id,
            audit_required=audit_required,
            doc_label=self.spec.doc_label,
            verb="审核" if approve else "驳回",
        )
        patch = {
            "status": "Approved" if approve else "Rejected",
            **self._reviewer_patch(user, remarks),
        }
        apply_update_audit(patch, user)
        await self.spec.model.filter(id=doc_id).update(**patch)
        return await self.get_or_404(tenant_id, doc_id)

    async def approve(
        self, tenant_id: int, doc_id: int, user: User, remarks: Optional[str] = None
    ):
        return await self._review(
            tenant_id, doc_id, user, approve=True, remarks=remarks
        )

    async def reject(
        self, tenant_id: int, doc_id: int, user: User, remarks: Optional[str] = None
    ):
        return await self._review(
            tenant_id, doc_id, user, approve=False, remarks=remarks
        )

    async def confirm(self, tenant_id: int, doc_id: int, user: User):
        doc = await self.get_or_404(tenant_id, doc_id)
        audit_required = await self.audit_required(tenant_id)
        if str(doc.status) == "Draft" and not audit_required:
            patch = {"status": "Approved", **self._reviewer_patch(user, "自动审核")}
            apply_update_audit(patch, user)
            await self.spec.model.filter(id=doc_id).update(**patch)
        elif str(doc.status) == "PendingReview" and audit_required:
            raise BusinessLogicError(f"{self.spec.label}待审核中，请先完成审核")
        elif str(doc.status) not in ("Approved", "Draft"):
            raise BusinessLogicError(
                f"当前状态不可确认，当前状态: {doc.status}"
            )
        return await MiscVoucherPostingService().post(
            tenant_id,
            voucher_type=self.spec.voucher_type,
            voucher_id=doc_id,
            operator=user,
        )

    async def unconfirm(self, tenant_id: int, doc_id: int, user: User):
        return await MiscVoucherPostingService().unpost(
            tenant_id,
            voucher_type=self.spec.voucher_type,
            voucher_id=doc_id,
            operator=user,
        )

    async def cancel(self, tenant_id: int, doc_id: int, user: User):
        doc = await self.get_or_404(tenant_id, doc_id)
        status = str(doc.status)
        if status == "Cancelled":
            raise BusinessLogicError(f"{self.spec.label}已作废")
        if status == "PendingReview":
            raise BusinessLogicError(f"{self.spec.label}待审核中，请先驳回或完成审核")
        if status not in _CANCELABLE:
            raise BusinessLogicError(f"当前状态不可作废，当前状态: {status}")
        if status == "Confirmed":
            await MiscVoucherPostingService().unpost(
                tenant_id,
                voucher_type=self.spec.voucher_type,
                voucher_id=doc_id,
                operator=user,
            )
        patch: Dict[str, Any] = {"status": "Cancelled"}
        apply_update_audit(patch, user)
        await self.spec.model.filter(id=doc_id).update(**patch)
        return await self.get_or_404(tenant_id, doc_id)

    async def delete(self, tenant_id: int, doc_id: int) -> None:
        doc = await self.get_or_404(tenant_id, doc_id)
        if str(doc.status) not in _DELETABLE:
            raise BusinessLogicError(
                f"仅草稿/已驳回/已作废状态可删除，当前状态: {doc.status}"
            )
        await self.spec.model.filter(id=doc_id).delete()


_DEFAULT_INCOME_CATEGORIES = (
    ("OI-INT", "利息收入"),
    ("OI-INV", "投资收益"),
    ("OI-FX", "汇兑收益"),
    ("OI-OV", "盘盈收入"),
    ("OI-OTH", "其他收入"),
)

_DEFAULT_EXPENSE_CATEGORIES = (
    ("OE-FEE", "银行手续费"),
    ("OE-FINE", "罚款及滞纳金"),
    ("OE-DON", "捐赠支出"),
    ("OE-LOSS", "盘亏损失"),
    ("OE-OTH", "其他支出"),
)


class MiscCategoryService:
    """其他收支类别维护（收入/支出分表）。"""

    @staticmethod
    def _model(kind: str):
        if kind == "income":
            return MiscIncomeCategory
        if kind == "expense":
            return MiscExpenseCategory
        raise ValidationError(f"不支持的类别类型: {kind}")

    async def _ensure_defaults(self, tenant_id: int, kind: str) -> None:
        model = self._model(kind)
        exists = await model.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).exists()
        if exists:
            return
        presets = (
            _DEFAULT_INCOME_CATEGORIES if kind == "income" else _DEFAULT_EXPENSE_CATEGORIES
        )
        for idx, (code, name) in enumerate(presets, start=1):
            await model.create(
                tenant_id=tenant_id,
                code=code,
                name=name,
                is_active=True,
                sort_order=idx,
            )

    async def list(
        self,
        tenant_id: int,
        kind: str,
        *,
        keyword: Optional[str] = None,
        is_active: Optional[bool] = None,
        ensure_defaults: bool = False,
    ) -> List[Any]:
        model = self._model(kind)
        if ensure_defaults:
            await self._ensure_defaults(tenant_id, kind)
        query = model.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if keyword:
            query = query.filter(name__icontains=keyword)
        if is_active is not None:
            query = query.filter(is_active=bool(is_active))
        return await query.order_by("sort_order", "id").all()

    async def _next_code(self, tenant_id: int, kind: str) -> str:
        model = self._model(kind)
        prefix = "OI" if kind == "income" else "OE"
        rows = await model.filter(
            tenant_id=tenant_id, code__startswith=f"{prefix}-", deleted_at__isnull=True
        ).all()
        max_no = 0
        for row in rows:
            try:
                max_no = max(max_no, int(str(row.code).split("-", 1)[1]))
            except (ValueError, IndexError):
                continue
        return f"{prefix}-{max_no + 1:03d}"

    async def create(self, tenant_id: int, kind: str, data: Any, user: User):
        model = self._model(kind)
        code = str(getattr(data, "code", None) or "").strip() or await self._next_code(
            tenant_id, kind
        )
        dup = await model.filter(
            tenant_id=tenant_id, code=code, deleted_at__isnull=True
        ).exists()
        if dup:
            raise BusinessLogicError(f"类别编码已存在: {code}")
        payload = {
            "tenant_id": tenant_id,
            "code": code,
            "name": str(data.name).strip(),
            "is_active": bool(getattr(data, "is_active", True)),
            "default_gl_account_code": getattr(data, "default_gl_account_code", None),
            "sort_order": int(getattr(data, "sort_order", 0) or 0),
        }
        apply_create_audit(payload, user)
        return await model.create(**payload)

    async def update(self, tenant_id: int, kind: str, cat_id: int, data: Any, user: User):
        model = self._model(kind)
        cat = await model.get_or_none(
            tenant_id=tenant_id, id=cat_id, deleted_at__isnull=True
        )
        if not cat:
            raise NotFoundError(f"收支类别不存在: {cat_id}")
        update_data = data.model_dump(exclude_unset=True)
        new_code = str(update_data.get("code") or "").strip()
        if new_code and new_code != cat.code:
            dup = await model.filter(
                tenant_id=tenant_id, code=new_code, deleted_at__isnull=True
            ).exists()
            if dup:
                raise BusinessLogicError(f"类别编码已存在: {new_code}")
            update_data["code"] = new_code
        elif "code" in update_data:
            update_data.pop("code")
        if "name" in update_data and update_data["name"] is not None:
            update_data["name"] = str(update_data["name"]).strip()
        apply_update_audit(update_data, user)
        await model.filter(id=cat_id).update(**update_data)
        return await model.get_or_none(
            tenant_id=tenant_id, id=cat_id, deleted_at__isnull=True
        )

    async def delete(self, tenant_id: int, kind: str, cat_id: int) -> None:
        model = self._model(kind)
        cat = await model.get_or_none(
            tenant_id=tenant_id, id=cat_id, deleted_at__isnull=True
        )
        if not cat:
            raise NotFoundError(f"收支类别不存在: {cat_id}")
        in_use = await OtherIncomeLine.filter(
            tenant_id=tenant_id, category_code=cat.code
        ).exists() if kind == "income" else await OtherExpenseLine.filter(
            tenant_id=tenant_id, category_code=cat.code
        ).exists()
        if in_use:
            raise BusinessLogicError(f"类别已被单据引用，不可删除: {cat.code}")
        await model.filter(id=cat_id).delete()
