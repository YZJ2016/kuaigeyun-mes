"""质量体系标准目录服务"""

from __future__ import annotations

from typing import List, Optional

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.qms_standard import QmsStandard
from apps.kuaizhizao.schemas.quality_qms import (
    QmsStandardCreate,
    QmsStandardListResponse,
    QmsStandardResponse,
    QmsStandardUpdate,
)
from apps.kuaizhizao.services.qms_clause_presets import PRESET_REGISTRY
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError
from infra.models.user import User


class QmsStandardService(AppBaseService[QmsStandard]):
    def __init__(self) -> None:
        super().__init__(QmsStandard)
        self.model = QmsStandard

    async def ensure_preset_standards(self, tenant_id: int, user: Optional[User] = None) -> None:
        for sort_base, (code, preset_meta) in enumerate(PRESET_REGISTRY.items()):
            name, family, _items = preset_meta
            exists = await QmsStandard.filter(
                tenant_id=tenant_id, code=code, deleted_at__isnull=True
            ).exists()
            if exists:
                continue
            row = QmsStandard(
                tenant_id=tenant_id,
                code=code,
                name=name,
                family=family,
                is_preset=True,
                is_active=True,
                sort_order=(sort_base + 1) * 100,
            )
            apply_create_audit(row, user)
            await row.save()

    async def _get_row(self, tenant_id: int, standard_id: int) -> QmsStandard:
        row = await QmsStandard.filter(
            id=standard_id, tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError("标准不存在")
        return row

    async def get_by_code(self, tenant_id: int, code: str) -> QmsStandard:
        row = await QmsStandard.filter(
            tenant_id=tenant_id, code=code.strip(), deleted_at__isnull=True
        ).first()
        if not row:
            raise NotFoundError("标准不存在")
        return row

    async def list_standards(
        self,
        tenant_id: int,
        *,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> QmsStandardListResponse:
        await self.ensure_preset_standards(tenant_id)
        from apps.kuaizhizao.services.qms_iso_clause_service import iso_clause_service

        await iso_clause_service.ensure_all_preset_clauses(tenant_id)
        query = QmsStandard.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if is_active is not None:
            query = query.filter(is_active=is_active)
        total = await query.count()
        rows = await query.order_by("sort_order", "code", "id").offset(skip).limit(limit)
        return QmsStandardListResponse(
            items=[QmsStandardResponse.model_validate(r) for r in rows],
            total=total,
        )

    async def create_standard(
        self, tenant_id: int, payload: QmsStandardCreate, user: Optional[User] = None
    ) -> QmsStandardResponse:
        code = payload.code.strip()
        clash = await QmsStandard.filter(
            tenant_id=tenant_id, code=code, deleted_at__isnull=True
        ).exists()
        if clash:
            raise BusinessLogicError("标准代号已存在")
        row = QmsStandard(
            tenant_id=tenant_id,
            code=code,
            name=payload.name.strip(),
            family=payload.family or "custom",
            is_preset=False,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        apply_create_audit(row, user)
        await row.save()
        return QmsStandardResponse.model_validate(row)

    async def update_standard(
        self,
        tenant_id: int,
        standard_id: int,
        payload: QmsStandardUpdate,
        user: Optional[User] = None,
    ) -> QmsStandardResponse:
        row = await self._get_row(tenant_id, standard_id)
        data = payload.model_dump(exclude_unset=True)
        if "code" in data and data["code"]:
            new_code = data["code"].strip()
            clash = (
                await QmsStandard.filter(tenant_id=tenant_id, code=new_code, deleted_at__isnull=True)
                .exclude(id=standard_id)
                .exists()
            )
            if clash:
                raise BusinessLogicError("标准代号已存在")
        for key, value in data.items():
            if isinstance(value, str):
                setattr(row, key, value.strip())
            else:
                setattr(row, key, value)
        apply_update_audit(row, user)
        await row.save()
        return QmsStandardResponse.model_validate(row)

    async def delete_standard(self, tenant_id: int, standard_id: int) -> None:
        row = await self._get_row(tenant_id, standard_id)
        if row.is_preset:
            raise BusinessLogicError("预置标准不可删除")
        from apps.kuaizhizao.models.qms_iso_clause import QmsIsoClause

        linked = await QmsIsoClause.filter(
            tenant_id=tenant_id, standard_id=standard_id, deleted_at__isnull=True
        ).exists()
        if linked:
            raise BusinessLogicError("标准下仍有条款，无法删除")
        row.deleted_at = resolve_business_datetime()
        await row.save()


qms_standard_service = QmsStandardService()
