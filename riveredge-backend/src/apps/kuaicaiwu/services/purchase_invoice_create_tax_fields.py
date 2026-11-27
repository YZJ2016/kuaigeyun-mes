"""采购发票创建默认税务字段（宿主业财，读 gl_tax_settings 表）。"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import date
from typing import Any, Dict, Optional

from tortoise.exceptions import IntegrityError

from apps.kuaicaiwu.models.gl_tax_settings import GlTaxSettings
from apps.kuaicaiwu.utils.tax_period import tax_period_from_date

TAXPAYER_SMALL_SCALE = "small_scale"
VERIFICATION_PENDING = "pending"
VERIFICATION_NOT_DEDUCTIBLE = "not_deductible"
TAXPAYER_GENERAL = "general"

_DEFAULT_TAX_RATES = [
    {"rate": 13, "label": "13%", "is_active": True},
    {"rate": 9, "label": "9%", "is_active": True},
    {"rate": 6, "label": "6%", "is_active": True},
    {"rate": 3, "label": "3%", "is_active": True},
    {"rate": 1, "label": "1%", "is_active": True},
    {"rate": 0, "label": "0%", "is_active": True},
    {"rate": -1, "label": "免税", "is_active": True},
]
_DEFAULT_SURCHARGE_RATES = {
    "urban_construction": 7.0,
    "education": 3.0,
    "local_education": 2.0,
}


async def _tax_settings_row(tenant_id: int, created_by: Optional[int] = None) -> GlTaxSettings:
    row = await GlTaxSettings.get_or_none(tenant_id=tenant_id, deleted_at__isnull=True)
    if row:
        return row
    user_name: Optional[str] = None
    if created_by:
        from infra.models.user import User

        user = await User.get_or_none(id=int(created_by))
        user_name = getattr(user, "name", None) or getattr(user, "username", None)
    try:
        return await GlTaxSettings.create(
            tenant_id=tenant_id,
            uuid=str(uuid.uuid4()),
            taxpayer_type=TAXPAYER_GENERAL,
            tax_rates=deepcopy(_DEFAULT_TAX_RATES),
            surcharge_rates=deepcopy(_DEFAULT_SURCHARGE_RATES),
            account_bindings={},
            created_by=created_by,
            created_by_name=user_name,
            updated_by=created_by,
            updated_by_name=user_name,
        )
    except IntegrityError:
        # 并发首建：另一请求已落库，回读其行
        row = await GlTaxSettings.get_or_none(tenant_id=tenant_id, deleted_at__isnull=True)
        if row:
            return row
        raise


async def purchase_invoice_default_tax_fields(
    tenant_id: int,
    invoice_date: date,
    *,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    settings = await _tax_settings_row(tenant_id, created_by=created_by)
    verification = (
        VERIFICATION_NOT_DEDUCTIBLE
        if settings.taxpayer_type == TAXPAYER_SMALL_SCALE
        else VERIFICATION_PENDING
    )
    return {
        "tax_period": tax_period_from_date(invoice_date),
        "verification_status": verification,
    }