"""其他收支类别维护服务（收入/支出分表）。"""

from __future__ import annotations

from typing import Any, List, Optional

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.kuaicaiwu.models.finance_misc_category import (
    MiscExpenseCategory,
    MiscIncomeCategory,
)
from apps.kuaicaiwu.models.other_voucher import OtherExpenseLine, OtherIncomeLine
from infra.exceptions.exceptions import (
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)
from infra.models.user import User


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
