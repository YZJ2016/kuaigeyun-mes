"""业财宿主：读账套本位币（真源在轻财务 Pro 总账设置）。"""

from __future__ import annotations

from typing import Any

from apps.common.optional_pro import import_pro_attr, pro_app_available, try_import_pro_module
from infra.exceptions.exceptions import BusinessLogicError


def _model_bound(model: Any) -> bool:
    meta = getattr(model, "_meta", None)
    return bool(meta is not None and getattr(meta, "default_connection", None) is not None)


async def read_tenant_base_currency(tenant_id: int, *, default: str = "CNY") -> str:
    """无 Pro 总账时返回 default。"""
    if not pro_app_available("kuaicaiwu"):
        return default
    try:
        GlSettingsService = import_pro_attr(
            "apps.kuaicaiwu.services.gl.settings_service", "GlSettingsService"
        )
    except BusinessLogicError:
        return default
    try:
        ProGl = import_pro_attr("apps.kuaicaiwu.models.gl_book_settings", "GlBookSettings")
    except BusinessLogicError:
        return default
    if not _model_bound(ProGl):
        return default
    row = await GlSettingsService().get_or_create(tenant_id)
    code = (getattr(row, "base_currency", None) or "").strip()
    return code or default


async def try_gl_settings_service():
    """汇率等只读：Pro 未就绪时 None。"""
    mod = try_import_pro_module("apps.kuaicaiwu.services.gl.settings_service")
    if mod is None:
        return None
    return getattr(mod, "GlSettingsService", None)
