"""自制报表三步向导的保存、字段检测和样本预览。

保存体与开源报表一致：code、name、description、category、classify、report_config、status。
report_config 记录平台数据集、图表字段、参数和下钻，不写星报表数据源 uuid。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from tortoise.exceptions import IntegrityError

from apps.kuaireport.models.report import KuaireportReport
from apps.kuaireport.services.execute_service import (
    _execute_platform_dataset,
    _reject_sql_keys,
    load_dataset,
)
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from core.services.authorization.user_permission_service import UserPermissionService
from infra.api.deps.deps import get_current_user
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id
from infra.exceptions.exceptions import AuthorizationError, NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(prefix="/reports", tags=["kuaireport-wizard"])

CHART_TYPES = frozenset({"table", "line", "bar", "column", "pie", "area", "scatter", "card"})
PARAM_CONTROLS = frozenset({"text", "number", "date", "dateRange", "select"})
CLASSIFIES = frozenset(
    {"销售", "采购", "生产", "质量", "仓库", "设备", "财务", "综合", "库存", "物料", "未分类"}
)
PREVIEW_ROW_CAP = 50


class WizardSaveBody(BaseModel):
    code: str
    name: str
    description: str | None = None
    category: str
    classify: str | None = None
    report_config: dict[str, Any] = Field(default_factory=dict)
    status: str


class PreviewBody(BaseModel):
    dataset_uuid: str | None = None
    dataset_code: str | None = None
    fields: list[Any] = Field(default_factory=list)
    chart_type: str = "table"
    page_size: int = PREVIEW_ROW_CAP
    parameters: dict[str, Any] = Field(default_factory=dict)


def _tenant_id() -> int:
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise TenantContextError("无租户上下文，不读取报表表")
    return int(tenant_id)


def _user_name(user: User) -> str | None:
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    if name is None:
        return None
    text = str(name).strip()
    return text or None


def _clean_text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label}不能为空")
    text = value.strip()
    if len(text) > limit:
        raise ValidationError(f"{label}过长")
    return text


def _clean_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("报表配置无效")
    _reject_sql_keys(raw)
    chart_type = raw.get("chart_type") or "table"
    if chart_type not in CHART_TYPES:
        raise ValidationError("图表类型无效")
    dataset_uuid = raw.get("dataset_uuid")
    if not isinstance(dataset_uuid, str) or not dataset_uuid.strip():
        raise ValidationError("请选择数据集")
    try:
        UUID(dataset_uuid.strip())
    except ValueError as exc:
        raise ValidationError("数据集无效") from exc
    dataset_code = raw.get("dataset_code")
    if dataset_code is not None and not isinstance(dataset_code, str):
        raise ValidationError("数据集编码无效")
    fields = _clean_fields(raw.get("fields"))
    parameters = _clean_parameters(raw.get("parameters"))
    interaction = _clean_interaction(raw.get("interaction"), fields)
    page_size = raw.get("page_size") or PREVIEW_ROW_CAP
    try:
        page_size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise ValidationError("分页参数无效") from exc
    if page_size < 1 or page_size > 10000:
        raise ValidationError("分页参数无效")
    config: dict[str, Any] = {
        "chart_type": chart_type,
        "dataset_uuid": dataset_uuid.strip(),
        "fields": fields,
        "parameters": parameters,
        "interaction": interaction,
        "page_size": page_size,
    }
    if isinstance(dataset_code, str) and dataset_code.strip():
        config["dataset_code"] = dataset_code.strip()
    return config


def _clean_fields(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("字段配置无效")
    fields: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValidationError("字段配置无效")
        field = item.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValidationError("字段名不能为空")
        label = item.get("label") if isinstance(item.get("label"), str) else field
        fields.append(
            {
                "field": field.strip(),
                "label": label.strip() or field.strip(),
                "visible": item.get("visible", True) is not False,
                "x_axis": bool(item.get("x_axis")),
                "y_axis": bool(item.get("y_axis")),
            }
        )
    return fields


def _clean_parameters(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("参数配置无效")
    parameters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValidationError("参数配置无效")
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ValidationError("参数名不能为空")
        key = key.strip()
        if key in seen:
            raise ValidationError("参数名重复")
        seen.add(key)
        control = item.get("control") or "text"
        if control not in PARAM_CONTROLS:
            raise ValidationError("参数类型无效")
        label = item.get("label") if isinstance(item.get("label"), str) else key
        row: dict[str, Any] = {
            "key": key,
            "label": label.strip() or key,
            "control": control,
            "required": bool(item.get("required")),
        }
        options = item.get("options")
        if control == "select" and isinstance(options, list):
            cleaned = []
            for option in options:
                if isinstance(option, dict) and option.get("value") is not None:
                    cleaned.append(
                        {
                            "label": str(option.get("label") or option.get("value")),
                            "value": option.get("value"),
                        }
                    )
            if cleaned:
                row["options"] = cleaned
        parameters.append(row)
    return parameters


def _clean_interaction(raw: Any, fields: list[dict[str, Any]]) -> dict[str, Any]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValidationError("下钻配置无效")
    drill = raw.get("drilldown") if isinstance(raw.get("drilldown"), dict) else {}
    enabled = bool(drill.get("enabled"))
    dimension = next((item["field"] for item in fields if item.get("x_axis")), None)
    if isinstance(drill.get("dimension_field"), str) and drill.get("dimension_field").strip():
        dimension = drill["dimension_field"].strip()
    keys = raw.get("global_filter_keys")
    if not isinstance(keys, list):
        keys = []
    return {
        "drilldown": {
            "enabled": enabled,
            "dimension_field": dimension,
            "detail_chart_type": "table",
            "title": "明细下钻",
        },
        "global_filter_keys": [key for key in keys if isinstance(key, str) and key],
    }


def _public(row: KuaireportReport) -> dict[str, Any]:
    updated = row.updated_at
    text = updated.strftime("%Y-%m-%d %H:%M:%S") if updated is not None else None
    config = row.report_config if isinstance(row.report_config, dict) else {}
    return {
        "id": row.id,
        "uuid": row.uuid,
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "category": row.category,
        "classify": row.classify,
        "is_system": bool(row.is_system),
        "status": row.status,
        "is_shared": bool(row.is_shared),
        "updated_at": text,
        "report_config": config,
    }


async def _require_dataset(tenant_id: int, dataset_uuid: str):
    dataset = await load_dataset(dataset_uuid)
    if dataset is None or getattr(dataset, "tenant_id", tenant_id) != tenant_id:
        raise NotFoundError("数据集", dataset_uuid)
    if dataset.query_type not in ("sql", "api"):
        raise ValidationError("报表只绑定 sql 或 api 数据集")
    return dataset


async def save_wizard_report(
    body: WizardSaveBody,
    *,
    report_id: int | None,
    user: User,
    is_admin: bool,
) -> dict[str, Any]:
    tenant_id = _tenant_id()
    code = _clean_text(body.code, "报表编号", 50)
    name = _clean_text(body.name, "报表名称", 100)
    if body.category not in ("custom", "system"):
        raise ValidationError("报表归属无效")
    if body.status not in ("DRAFT", "PUBLISHED"):
        raise ValidationError("状态无效")
    classify = (body.classify or "").strip() or "未分类"
    if classify not in CLASSIFIES:
        raise ValidationError("分类无效")
    if body.category == "system" and not is_admin:
        raise AuthorizationError("系统报表需要管理员权限")
    description = body.description.strip() if isinstance(body.description, str) else None
    if description == "":
        description = None
    config = _clean_config(body.report_config)
    is_system = body.category == "system"
    existing = None
    if report_id is not None:
        existing = await KuaireportReport.get_or_none(tenant_id=tenant_id, id=report_id)
        if existing is None:
            raise NotFoundError("报表", str(report_id))
        if existing.is_system:
            raise AuthorizationError("系统报表不允许修改")
    await _require_dataset(tenant_id, config["dataset_uuid"])
    try:
        if existing is None:
            row = await KuaireportReport.create(
                tenant_id=tenant_id,
                code=code,
                name=name,
                description=description,
                category=body.category,
                classify=classify,
                is_system=is_system,
                owner_id=None if is_system else user.id,
                status=body.status,
                report_config=config,
                current_version=1,
                created_by=user.id,
                created_by_name=_user_name(user),
            )
        else:
            row = existing
            row.code = code
            row.name = name
            row.description = description
            row.category = body.category
            row.classify = classify
            row.is_system = is_system
            row.status = body.status
            row.report_config = config
            await row.save()
    except IntegrityError as exc:
        raise ValidationError("报表编码已存在") from exc
    return _public(row)


def _columns_from_dataset(dataset: Any) -> list[dict[str, Any]]:
    display = getattr(dataset, "display_config", None) or {}
    raw_cols = display.get("columns") if isinstance(display, dict) else None
    columns: list[dict[str, Any]] = []
    if not isinstance(raw_cols, list):
        return columns
    for col in raw_cols:
        if isinstance(col, dict) and col.get("field"):
            columns.append(
                {
                    "field": col["field"],
                    "label": col.get("label") or col["field"],
                    "visible": col.get("visible", True) is not False,
                }
            )
        elif isinstance(col, str) and col:
            columns.append({"field": col, "label": col, "visible": True})
    return columns


async def detect_dataset_fields(
    *,
    dataset_uuid: str | None,
    dataset_code: str | None,
) -> dict[str, Any]:
    tenant_id = _tenant_id()
    if dataset_uuid:
        dataset = await _require_dataset(tenant_id, dataset_uuid.strip())
        columns = _columns_from_dataset(dataset)
        if columns:
            return {"fields": columns, "success": True}
        rows, _total, _paged = await _execute_platform_dataset(
            tenant_id,
            dataset_uuid.strip(),
            {"limit": 1, "offset": 0},
            {"page_size": 1},
        )
    elif dataset_code:
        raise ValidationError("请选择数据集")
    else:
        return {"fields": [], "success": True}
    if not rows:
        return {"fields": [], "success": True}
    return {
        "fields": [{"field": key, "label": key, "visible": True} for key in rows[0].keys()],
        "success": True,
    }


async def preview_dataset(body: PreviewBody) -> dict[str, Any]:
    tenant_id = _tenant_id()
    if not body.dataset_uuid:
        raise ValidationError("请选择数据集")
    dataset_uuid = body.dataset_uuid.strip()
    await _require_dataset(tenant_id, dataset_uuid)
    try:
        page_size = int(body.page_size)
    except (TypeError, ValueError) as exc:
        raise ValidationError("分页参数无效") from exc
    page_size = min(max(page_size, 1), PREVIEW_ROW_CAP)
    filters = dict(body.parameters or {})
    filters["limit"] = page_size
    filters["offset"] = 0
    rows, total, _paged = await _execute_platform_dataset(
        tenant_id,
        dataset_uuid,
        filters,
        {"page_size": page_size, "parameters": []},
    )
    return {"data": rows, "total": total if total is not None else len(rows), "success": True}


async def _admin(user: User, tenant_id: int) -> bool:
    return await UserPermissionService.is_admin_bypass(user, tenant_id)


@router.post(
    "",
    dependencies=[Depends(require_permission_codes("kuaireport:report:design"))],
)
async def create_wizard_report_api(
    body: WizardSaveBody,
    tenant_id: int = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await save_wizard_report(
        body, report_id=None, user=user, is_admin=await _admin(user, tenant_id)
    )


@router.put(
    "/{report_id:int}",
    dependencies=[Depends(require_permission_codes("kuaireport:report:design"))],
)
async def update_wizard_report_api(
    report_id: int,
    body: WizardSaveBody,
    tenant_id: int = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await save_wizard_report(
        body, report_id=report_id, user=user, is_admin=await _admin(user, tenant_id)
    )


@router.get(
    "/datasets/fields",
    dependencies=[Depends(require_permission_codes("kuaireport:report:design"))],
)
async def dataset_fields_api(
    dataset_uuid: str | None = None,
    dataset_code: str | None = None,
    tenant_id: int = Depends(get_current_tenant),
) -> dict[str, Any]:
    return await detect_dataset_fields(dataset_uuid=dataset_uuid, dataset_code=dataset_code)


@router.post(
    "/preview",
    dependencies=[Depends(require_permission_codes("kuaireport:report:design"))],
)
async def preview_dataset_api(
    body: PreviewBody,
    tenant_id: int = Depends(get_current_tenant),
) -> dict[str, Any]:
    return await preview_dataset(body)
