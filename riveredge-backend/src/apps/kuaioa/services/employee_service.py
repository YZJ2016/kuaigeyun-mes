"""员工档案服务。"""

from __future__ import annotations

import calendar
import re
import secrets
from datetime import date
from typing import Any, Optional

from pydantic import ValidationError as PydanticValidationError

from apps.kuaioa.models.employee import KuaioaEmployeeProfile
from apps.common.bulk_import import BulkCreateResponse, run_bulk_create
from apps.kuaioa.schemas.employee import (
    EmployeeAccountQuickCreateRequest,
    EmployeeProfileCreate,
    EmployeeProfileUpdate,
)
from apps.kuaioa.services.kuaioa_list_core import (
    apply_create_audit_by_user_id,
    build_keyword_q,
    generate_daily_code,
    model_to_dict,
    parse_optional_date,
    touch_updated,
)
from core.schemas.user import UserCreate
from core.services.user.user_service import UserService
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import (
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)
from infra.domain.security.reserved_username import (
    assert_tenant_user_username_allowed,
)
from infra.models.user import User

_ALLOWED_EMPLOYMENT = frozenset({"formal", "temp", "labor"})
_ALLOWED_PAY = frozenset({"piece", "time", "line", "month"})
_ALLOWED_STATUS = frozenset({"active", "left"})


def _username_base_from_name(full_name: str) -> str:
    """由姓名生成登录账号前缀（拼音小写），无法生成时回退随机段。"""
    base = ""
    try:
        from pypinyin import lazy_pinyin

        base = "".join(lazy_pinyin(full_name)).lower()
    except Exception:
        base = ""
    base = re.sub(r"[^a-z0-9_]+", "", base)
    if len(base) < 2:
        base = f"yg{secrets.token_hex(3)}"
    return base[:40]


def _resolve_status(*, leave_date, status: Optional[str]) -> str:
    if leave_date is not None:
        return "left"
    if status in _ALLOWED_STATUS:
        return status
    return "active"


class EmployeeProfileService:
    async def list_profiles(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        employment_type: Optional[str] = None,
        workshop_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        q = KuaioaEmployeeProfile.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            q = q.filter(status=status)
        if employment_type:
            q = q.filter(employment_type=employment_type)
        if workshop_name:
            q = q.filter(workshop_name=workshop_name)
        if keyword:
            q = q.filter(
                build_keyword_q(
                    keyword,
                    "employee_code",
                    "full_name",
                    "phone",
                    "workshop_name",
                    "bank_account",
                )
            )
        rows = await q.order_by("-updated_at")
        return await self._attach_user_display(
            tenant_id, [model_to_dict(row) for row in rows]
        )

    async def get_profile(self, tenant_id: int, profile_id: int) -> dict[str, Any]:
        row = await KuaioaEmployeeProfile.get_or_none(
            id=profile_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("员工档案不存在")
        return (await self._attach_user_display(tenant_id, [model_to_dict(row)]))[0]

    async def _attach_user_display(
        self, tenant_id: int, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """补出 user_display（姓名（账号））供列表/详情展示。"""
        user_ids = {row.get("user_id") for row in rows if row.get("user_id")}
        name_map: dict[int, str] = {}
        if user_ids:
            users = await User.filter(
                id__in=list(user_ids), tenant_id=tenant_id
            ).only("id", "username", "full_name")
            name_map = {
                u.id: f"{u.full_name or u.username}（{u.username}）" for u in users
            }
        for row in rows:
            row["user_display"] = name_map.get(row.get("user_id"))
        return rows

    async def _validate_linked_user(
        self,
        tenant_id: int,
        user_id: int,
        *,
        exclude_profile_id: Optional[int] = None,
    ) -> None:
        """校验绑定账号：存在、同租户、启用，且未被其他档案占用。"""
        user = await User.filter(
            id=user_id,
            tenant_id=tenant_id,
            is_active=True,
            deleted_at__isnull=True,
        ).first()
        if user is None:
            raise BusinessLogicError("绑定的登录账号不存在或已停用")
        query = KuaioaEmployeeProfile.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            deleted_at__isnull=True,
        )
        if exclude_profile_id:
            query = query.exclude(id=exclude_profile_id)
        if await query.exists():
            raise BusinessLogicError("该登录账号已绑定其他员工档案")

    async def _suggest_username(self, tenant_id: int, full_name: str) -> str:
        base = _username_base_from_name(full_name)
        candidate = base
        for index in range(2, 50):
            try:
                assert_tenant_user_username_allowed(candidate)
            except ValueError:
                candidate = f"{base}{index}"
                continue
            exists = await User.filter(
                tenant_id=tenant_id, username=candidate, deleted_at__isnull=True
            ).exists()
            if not exists:
                return candidate
            candidate = f"{base}{index}"
        raise BusinessLogicError("无法生成可用登录账号，请手动指定")

    async def create_linked_account(
        self,
        tenant_id: int,
        data: EmployeeAccountQuickCreateRequest,
        *,
        operator_user_id: int,
    ) -> dict[str, Any]:
        """一键创建 PC Web 登录账号（无角色），返回仅本次可见的初始密码。"""
        full_name = (data.full_name or "").strip()
        if not full_name:
            raise BusinessLogicError("姓名不能为空")
        username = (data.username or "").strip() or await self._suggest_username(
            tenant_id, full_name
        )
        password = secrets.token_urlsafe(9)
        phone = (data.phone or "").strip() or None
        try:
            user_create = UserCreate(
                username=username,
                password=password,
                full_name=full_name,
                phone=phone,
                tenant_id=tenant_id,
                is_active=True,
                is_tenant_admin=False,
                source="kuaioa_employee",
            )
        except PydanticValidationError as exc:
            raise BusinessLogicError(str(exc)) from exc
        try:
            user = await UserService.create_user(
                tenant_id=tenant_id,
                data=user_create,
                current_user_id=operator_user_id,
            )
        except ValidationError as exc:
            raise BusinessLogicError(str(exc)) from exc
        return {
            "user_id": int(user.id),
            "username": user.username,
            "initial_password": password,
        }

    async def create_profile(
        self, tenant_id: int, data: EmployeeProfileCreate, user_id: int
    ) -> dict[str, Any]:
        full_name = (data.full_name or "").strip()
        if not full_name:
            raise BusinessLogicError("姓名不能为空")
        employment_type = (data.employment_type or "formal").strip()
        if employment_type not in _ALLOWED_EMPLOYMENT:
            raise BusinessLogicError("用工类型无效")
        pay_method = (data.pay_method or "time").strip()
        if pay_method not in _ALLOWED_PAY:
            raise BusinessLogicError("计薪方式无效")

        try:
            hire_date = parse_optional_date(data.hire_date)
            leave_date = parse_optional_date(data.leave_date)
        except ValueError as exc:
            raise BusinessLogicError(str(exc)) from exc
        status = _resolve_status(leave_date=leave_date, status=data.status)

        linked_user_id = data.user_id or None
        if linked_user_id is not None:
            await self._validate_linked_user(tenant_id, linked_user_id)

        create_payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "full_name": full_name,
            "phone": (data.phone or "").strip() or None,
            "workshop_name": (data.workshop_name or "").strip() or None,
            "production_line_name": (data.production_line_name or "").strip() or None,
            "employment_type": employment_type,
            "pay_method": pay_method,
            "hourly_rate": data.hourly_rate,
            "hire_date": hire_date,
            "leave_date": leave_date,
            "bank_account": (data.bank_account or "").strip() or None,
            "bank_name": (data.bank_name or "").strip() or None,
            "bank_branch": (data.bank_branch or "").strip() or None,
            "living_allowance": data.living_allowance,
            "post_wage": data.post_wage,
            "social_insurance": data.social_insurance,
            "housing_fund": data.housing_fund,
            "rent_utility": data.rent_utility,
            "welfare_dragon_boat": data.welfare_dragon_boat,
            "welfare_mid_autumn": data.welfare_mid_autumn,
            "welfare_spring_festival": data.welfare_spring_festival,
            "user_id": linked_user_id,
            "department_name": (data.department_name or "").strip() or None,
            "status": status,
            "notes": data.notes,
        }
        await apply_create_audit_by_user_id(create_payload, user_id)

        provided_code = (data.employee_code or "").strip()
        if provided_code:
            exists = await KuaioaEmployeeProfile.filter(
                tenant_id=tenant_id,
                employee_code=provided_code,
                deleted_at__isnull=True,
            ).exists()
            if exists:
                raise BusinessLogicError(f"员工编号「{provided_code}」已存在")
            create_payload["employee_code"] = provided_code
            try:
                row = await KuaioaEmployeeProfile.create(**create_payload)
                return model_to_dict(row)
            except Exception as exc:
                if "employee_code" in str(exc).lower() or "unique" in str(exc).lower():
                    raise BusinessLogicError(f"员工编号「{provided_code}」已存在") from exc
                raise

        last_error: Exception | None = None
        for _ in range(8):
            create_payload["employee_code"] = await generate_daily_code(
                KuaioaEmployeeProfile, tenant_id, "EMP", code_field="employee_code"
            )
            try:
                row = await KuaioaEmployeeProfile.create(**create_payload)
                return model_to_dict(row)
            except Exception as exc:
                if "employee_code" in str(exc).lower() or "unique" in str(exc).lower():
                    last_error = exc
                    continue
                raise
        raise BusinessLogicError("员工编号生成冲突，请稍后重试") from last_error

    async def bulk_create_profiles(
        self,
        tenant_id: int,
        items: list[EmployeeProfileCreate],
        user_id: int,
    ) -> BulkCreateResponse:
        """批量创建员工（导入分片）；片内顺序执行，单条失败不中断整批。"""

        async def create_one(item: EmployeeProfileCreate, _index: int) -> dict[str, Any]:
            return await self.create_profile(tenant_id, item, user_id)

        return await run_bulk_create(list(items or []), create_one)

    async def update_profile(
        self, tenant_id: int, profile_id: int, data: EmployeeProfileUpdate, user_id: int
    ) -> dict[str, Any]:
        row = await KuaioaEmployeeProfile.get_or_none(
            id=profile_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("员工档案不存在")
        payload = data.model_dump(exclude_unset=True)
        if "full_name" in payload:
            name = (payload["full_name"] or "").strip()
            if not name:
                raise BusinessLogicError("姓名不能为空")
            payload["full_name"] = name
        if "employment_type" in payload and payload["employment_type"] is not None:
            et = str(payload["employment_type"]).strip()
            if et not in _ALLOWED_EMPLOYMENT:
                raise BusinessLogicError("用工类型无效")
            payload["employment_type"] = et
        if "pay_method" in payload and payload["pay_method"] is not None:
            pm = str(payload["pay_method"]).strip()
            if pm not in _ALLOWED_PAY:
                raise BusinessLogicError("计薪方式无效")
            payload["pay_method"] = pm
        for key in ("hire_date", "leave_date"):
            if key in payload:
                try:
                    payload[key] = parse_optional_date(payload[key])
                except ValueError as exc:
                    raise BusinessLogicError(str(exc)) from exc
        for key in (
            "phone",
            "workshop_name",
            "production_line_name",
            "bank_account",
            "bank_name",
            "bank_branch",
            "department_name",
        ):
            if key in payload and isinstance(payload[key], str):
                payload[key] = payload[key].strip() or None
        if "user_id" in payload:
            linked_user_id = payload["user_id"] or None
            if linked_user_id is not None:
                await self._validate_linked_user(
                    tenant_id, linked_user_id, exclude_profile_id=profile_id
                )
            payload["user_id"] = linked_user_id

        leave_date = payload["leave_date"] if "leave_date" in payload else row.leave_date
        status_in = payload.get("status") if "status" in payload else row.status
        payload["status"] = _resolve_status(leave_date=leave_date, status=status_in)

        for key, value in payload.items():
            setattr(row, key, value)
        await touch_updated(row, user_id)
        await row.save()
        return model_to_dict(row)

    async def list_movements(
        self,
        tenant_id: int,
        year_month: str,
        *,
        workshop_name: Optional[str] = None,
        movement_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        text = (year_month or "").strip()
        if len(text) != 7 or text[4] != "-":
            raise BusinessLogicError("年月格式须为 YYYY-MM")
        year = int(text[:4])
        month = int(text[5:7])
        if month < 1 or month > 12:
            raise BusinessLogicError("月份无效")
        last_day = calendar.monthrange(year, month)[1]
        start = date(year, month, 1)
        end = date(year, month, last_day)

        q = KuaioaEmployeeProfile.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if workshop_name:
            q = q.filter(workshop_name=workshop_name.strip())
        employees = await q.order_by("full_name", "id")

        rows: list[dict[str, Any]] = []
        for emp in employees:
            if movement_type in (None, "hire") and emp.hire_date and start <= emp.hire_date <= end:
                rows.append(
                    {
                        "movement_type": "hire",
                        "employee_id": emp.id,
                        "employee_code": emp.employee_code,
                        "employee_name": emp.full_name,
                        "workshop_name": emp.workshop_name,
                        "movement_date": emp.hire_date.isoformat(),
                        "employment_type": emp.employment_type,
                        "year_month": text,
                    }
                )
            if movement_type in (None, "leave") and emp.leave_date and start <= emp.leave_date <= end:
                rows.append(
                    {
                        "movement_type": "leave",
                        "employee_id": emp.id,
                        "employee_code": emp.employee_code,
                        "employee_name": emp.full_name,
                        "workshop_name": emp.workshop_name,
                        "movement_date": emp.leave_date.isoformat(),
                        "employment_type": emp.employment_type,
                        "year_month": text,
                    }
                )
        rows.sort(key=lambda r: (r.get("movement_date") or "", r.get("employee_name") or ""))
        return rows

    async def delete_profile(self, tenant_id: int, profile_id: int, user_id: int) -> None:
        row = await KuaioaEmployeeProfile.get_or_none(
            id=profile_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("员工档案不存在")
        row.deleted_at = resolve_business_datetime()
        await touch_updated(row, user_id)
        await row.save()
