"""账表设计器（spec 147）。

新建 category=custom，写入可被 ReportConfigSchema 读取的 report_config，
并在同一事务插入 apps_kuaireport_report_versions。不写大屏版本，不分享，不恢复。

保存校验本租户已登记数据源，并把其 uuid 写入 report_config.extra.data_source_uuid。
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from uuid import uuid4

from asyncpg.exceptions import UniqueViolationError
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from apps.kuaireport.constants import REPORT_DATA_SOURCE_UUID
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(tags=["kuaireport-designer"])

_ALLOWED_SOURCE_TYPES = frozenset({"static", "dataset", "http"})
_ALLOWED_FORMATS = frozenset({"money", "date", "datetime", "percent", "number", "digit"})
# 只拦 SQL 语句形态（select ... from / insert into / drop table 等），
# 字段名或文案里含 select、update、sql 字样不再误伤；键名拦截见 _SECRET_KEYS。
_SQL_RE = re.compile(
    r"(?i)("
    r"\bselect\b[\s\S]*\bfrom\b"
    r"|\binsert\s+into\b"
    r"|\bupdate\b[\s\S]*\bset\b"
    r"|\bdelete\s+from\b"
    r"|\bdrop\s+(?:table|database|view|index)\b"
    r"|\balter\s+(?:table|database|view|index)\b"
    r"|\btruncate\s+table\b"
    r"|\bunion\s+(?:all\s+)?select\b"
    r"|\bexec(?:ute)?\b\s*[(A-Za-z_]"
    r")"
)
_SECRET_KEYS = frozenset(
    {
        "password",
        "secret",
        "cipher",
        "token",
        "jdbc",
        "query_config",
        "sql",
        "share_password",
        "share_password_hash",
    }
)

_CODE_UNIQUE = "uid_apps_kuaireport_reports_tenant_code"
_VERSION_UNIQUE = "uid_kuaireport_report_ver"


class FieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    label: str
    format: Optional[str] = None
    width: Optional[int] = None
    visible: Optional[bool] = None


class FilterOptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str | int | float


class FilterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    label: str
    operator: Optional[str] = None
    default_value: Any = None
    required: Optional[bool] = None
    control: Optional[str] = None
    options: Optional[list[FilterOptionIn]] = None


class DesignerSaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    page_size: int
    data_source_uuid: str
    fields: list[FieldIn] = Field(default_factory=list)
    filters: list[FilterIn] = Field(default_factory=list)
    summary_fields: list[str] = Field(default_factory=list)
    note: Optional[str] = None
    report_id: Optional[int] = None


class DesignerReportOut(BaseModel):
    report_id: int
    category: str
    code: str
    name: str
    current_version: int
    version_no: Optional[int] = None
    report_config: dict[str, Any]
    data_source_uuid: Optional[str] = None


def _require_tenant(tenant_id: Optional[int] = None) -> int:
    current = get_current_tenant_id()
    if current is None:
        raise TenantContextError("无组织上下文，不能读写账表")
    if tenant_id is not None and tenant_id != current:
        raise ValidationError("租户不一致")
    return current


def _reject_sql_text(value: str, label: str) -> None:
    if _SQL_RE.search(value):
        raise ValidationError(f"{label}不能包含 SQL")


def _walk_secret_keys(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in _SECRET_KEYS:
                raise ValidationError("配置不能包含 SQL、连接密文或口令")
            _walk_secret_keys(value)
    elif isinstance(node, list):
        for item in node:
            _walk_secret_keys(item)
    elif isinstance(node, str):
        _reject_sql_text(node, "配置")


def _primitive(value: Any) -> Any:
    if value is None or type(value) in (str, int, float, bool):
        if isinstance(value, str):
            _reject_sql_text(value, "筛选值")
        return value
    if isinstance(value, list):
        return [_primitive(item) for item in value]
    raise ValidationError("筛选默认值只能是文本、数字或列表")


def build_report_config(
    *,
    page_size: int,
    fields: list[dict[str, Any]],
    filters: list[dict[str, Any]],
    summary_fields: list[str],
) -> dict[str, Any]:
    """组装 ReportConfigSchema 已有的 page_size、fields、filters、summaryFields。"""
    if type(page_size) is not int or isinstance(page_size, bool) or page_size <= 0:
        raise ValidationError("page_size 必须是正整数")

    seen: set[str] = set()
    norm_fields: list[dict[str, Any]] = []
    for raw in fields:
        field = str(raw.get("field") or "").strip()
        label = str(raw.get("label") or "").strip()
        if not field or not label:
            raise ValidationError("列需要 field 和 label")
        _reject_sql_text(field, "列")
        _reject_sql_text(label, "列")
        if field in seen:
            raise ValidationError("列字段不能重复")
        seen.add(field)
        item: dict[str, Any] = {"field": field, "label": label}
        fmt = raw.get("format")
        if fmt not in (None, ""):
            fmt_text = str(fmt).strip()
            if fmt_text not in _ALLOWED_FORMATS:
                raise ValidationError("列格式不在账表已有格式中")
            item["format"] = fmt_text
        width = raw.get("width")
        if width is not None:
            if type(width) is not int or isinstance(width, bool) or width <= 0:
                raise ValidationError("列宽必须是正整数")
            item["width"] = width
        if raw.get("visible") is not None:
            item["visible"] = bool(raw["visible"])
        norm_fields.append(item)

    norm_filters: list[dict[str, Any]] = []
    for raw in filters:
        field = str(raw.get("field") or "").strip()
        label = str(raw.get("label") or "").strip()
        if not field or not label:
            raise ValidationError("筛选需要 field 和 label")
        _reject_sql_text(field, "筛选")
        _reject_sql_text(label, "筛选")
        item = {"field": field, "label": label}
        operator = raw.get("operator")
        if operator not in (None, ""):
            op = str(operator).strip()
            _reject_sql_text(op, "筛选")
            item["operator"] = op
        if "default_value" in raw and raw.get("default_value") is not None:
            item["default_value"] = _primitive(raw.get("default_value"))
        if raw.get("required") is not None:
            item["required"] = bool(raw["required"])
        control = raw.get("control")
        if control not in (None, ""):
            control_text = str(control).strip()
            _reject_sql_text(control_text, "筛选")
            item["control"] = control_text
        options = raw.get("options")
        if options is not None:
            norm_options = []
            for opt in options:
                opt_label = str(opt.get("label") or "").strip()
                _reject_sql_text(opt_label, "筛选项")
                opt_value = opt.get("value")
                if isinstance(opt_value, str):
                    _reject_sql_text(opt_value, "筛选项")
                elif type(opt_value) not in (int, float) or isinstance(opt_value, bool):
                    raise ValidationError("筛选项的值只能是文本或数字")
                norm_options.append({"label": opt_label, "value": opt_value})
            item["options"] = norm_options
        norm_filters.append(item)

    norm_summary: list[str] = []
    for name in summary_fields:
        text = str(name).strip()
        if not text:
            raise ValidationError("合计字段不能为空")
        _reject_sql_text(text, "合计")
        norm_summary.append(text)

    config: dict[str, Any] = {
        "page_size": page_size,
        "fields": norm_fields,
        "filters": norm_filters,
        "extra": {"uni_report": {"summaryFields": norm_summary}},
    }
    _walk_secret_keys(config)
    return config


def _clean_identity(code: str, name: str, note: Optional[str]) -> tuple[str, str, Optional[str]]:
    code_text = code.strip()
    name_text = name.strip()
    if not code_text or len(code_text) > 50:
        raise ValidationError("编码必填且不超过 50 字")
    if not name_text or len(name_text) > 100:
        raise ValidationError("名称必填且不超过 100 字")
    _reject_sql_text(code_text, "编码")
    _reject_sql_text(name_text, "名称")
    if note is None or str(note).strip() == "":
        return code_text, name_text, None
    note_text = str(note).strip()
    if len(note_text) > 200:
        raise ValidationError("备注不超过 200 字")
    _reject_sql_text(note_text, "备注")
    return code_text, name_text, note_text


def _constraint_text(exc: BaseException) -> str:
    constraint = getattr(exc, "constraint_name", None)
    if isinstance(constraint, str) and constraint:
        return constraint
    return str(exc)


def _raise_unique(exc: BaseException) -> None:
    text = _constraint_text(exc)
    if _VERSION_UNIQUE in text:
        raise ValidationError("版本号冲突，请重新保存") from exc
    if _CODE_UNIQUE in text or "apps_kuaireport_reports" in text:
        raise ValidationError("同一组织下账表编码已存在") from exc
    raise exc


async def _fetch_source(conn: Any, tenant_id: int, source_uuid: str) -> Optional[dict[str, Any]]:
    rows = await conn.execute_query_dict(
        """
        SELECT id, uuid, type
        FROM apps_kuaireport_data_sources
        WHERE uuid = $1 AND tenant_id = $2
        """,
        [source_uuid, tenant_id],
    )
    return rows[0] if rows else None


def _ensure_source(source: Optional[dict[str, Any]], source_uuid: str) -> None:
    if source is None:
        raise NotFoundError("数据源", source_uuid)
    if source.get("type") not in _ALLOWED_SOURCE_TYPES:
        raise ValidationError("数据源类型必须是 static、dataset 或 http")


def _bind_source(config: dict[str, Any], source_uuid: str) -> dict[str, Any]:
    bound = {key: value for key, value in config.items() if key != "data_source_id"}
    extra = dict(bound.get("extra") or {})
    extra[REPORT_DATA_SOURCE_UUID] = source_uuid
    bound["extra"] = extra
    return bound


async def _insert_report(
    conn: Any,
    *,
    tenant_id: int,
    code: str,
    name: str,
    config: dict[str, Any],
    created_by: Optional[int],
    created_by_name: Optional[str],
) -> dict[str, Any]:
    rows = await conn.execute_query_dict(
        """
        INSERT INTO apps_kuaireport_reports (
            uuid, tenant_id, code, name, category, is_system, status,
            report_config, current_version, created_by, created_by_name
        ) VALUES (
            $1, $2, $3, $4, 'custom', FALSE, 'DRAFT',
            $5::jsonb, 1, $6, $7
        )
        RETURNING id, current_version, category, code, name
        """,
        [str(uuid4()), tenant_id, code, name, json.dumps(config), created_by, created_by_name],
    )
    return rows[0]


async def _lock_report(conn: Any, tenant_id: int, report_id: int) -> Optional[dict[str, Any]]:
    rows = await conn.execute_query_dict(
        """
        SELECT id, category, current_version, code, name
        FROM apps_kuaireport_reports
        WHERE id = $1 AND tenant_id = $2
        FOR UPDATE
        """,
        [report_id, tenant_id],
    )
    return rows[0] if rows else None


async def _update_report(
    conn: Any,
    *,
    tenant_id: int,
    report_id: int,
    name: str,
    config: dict[str, Any],
    version_no: int,
    updated_by: Optional[int],
    updated_by_name: Optional[str],
) -> dict[str, Any]:
    rows = await conn.execute_query_dict(
        """
        UPDATE apps_kuaireport_reports
        SET report_config = $1::jsonb,
            current_version = $2,
            name = $3,
            updated_by = $4,
            updated_by_name = $5,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $6 AND tenant_id = $7 AND category = 'custom'
        RETURNING id, current_version, category, code, name
        """,
        [json.dumps(config), version_no, name, updated_by, updated_by_name, report_id, tenant_id],
    )
    if not rows:
        raise ValidationError("系统报表只能查看，不能在设计器里保存")
    return rows[0]


async def _insert_version(
    conn: Any,
    *,
    tenant_id: int,
    report_id: int,
    version_no: int,
    config: dict[str, Any],
    note: Optional[str],
    created_by_user_id: Optional[int],
) -> None:
    await conn.execute_query_dict(
        """
        INSERT INTO apps_kuaireport_report_versions (
            uuid, tenant_id, report_id, version_no, snapshot, note, created_by_user_id, created_by
        ) VALUES (
            $1, $2, $3, $4, $5::jsonb, $6, $7, $8
        )
        """,
        [
            str(uuid4()),
            tenant_id,
            report_id,
            version_no,
            json.dumps(config),
            note,
            created_by_user_id,
            created_by_user_id,
        ],
    )


async def save_custom_report(
    *,
    code: str,
    name: str,
    page_size: int,
    data_source_uuid: str,
    fields: list[dict[str, Any]],
    filters: list[dict[str, Any]],
    summary_fields: list[str],
    note: Optional[str] = None,
    report_id: Optional[int] = None,
    created_by: Optional[int] = None,
    created_by_name: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
) -> dict[str, Any]:
    current_tenant = _require_tenant(tenant_id)
    source_uuid = str(data_source_uuid or "").strip()
    if not source_uuid or len(source_uuid) > 36:
        raise ValidationError("必须指定一个数据源")
    code_text, name_text, note_text = _clean_identity(code, name, note)
    config = _bind_source(
        build_report_config(
            page_size=page_size,
            fields=fields,
            filters=filters,
            summary_fields=summary_fields,
        ),
        source_uuid,
    )
    user_id = created_by_user_id if created_by_user_id is not None else created_by
    try:
        async with in_transaction() as conn:
            source = await _fetch_source(conn, current_tenant, source_uuid)
            _ensure_source(source, source_uuid)
            if report_id is None:
                row = await _insert_report(
                    conn,
                    tenant_id=current_tenant,
                    code=code_text,
                    name=name_text,
                    config=config,
                    created_by=created_by,
                    created_by_name=created_by_name,
                )
                version_no = int(row["current_version"])
            else:
                locked = await _lock_report(conn, current_tenant, report_id)
                if locked is None:
                    raise NotFoundError("账表", str(report_id))
                if locked.get("category") != "custom":
                    raise ValidationError("系统报表只能查看，不能在设计器里保存")
                if str(locked.get("code") or "") != code_text:
                    # code 是租户内唯一键，作为已有列不允许随保存变更
                    raise ValidationError("账表编码创建后不可修改")
                version_no = int(locked.get("current_version") or 0) + 1
                row = await _update_report(
                    conn,
                    tenant_id=current_tenant,
                    report_id=report_id,
                    name=name_text,
                    config=config,
                    version_no=version_no,
                    updated_by=created_by,
                    updated_by_name=created_by_name,
                )
            await _insert_version(
                conn,
                tenant_id=current_tenant,
                report_id=int(row["id"]),
                version_no=version_no,
                config=config,
                note=note_text,
                created_by_user_id=user_id,
            )
    except (UniqueViolationError, IntegrityError) as exc:
        _raise_unique(exc)
    return {
        "report_id": int(row["id"]),
        "category": row["category"],
        "code": row["code"],
        "name": row["name"],
        "current_version": version_no,
        "version_no": version_no,
        "report_config": config,
        "data_source_uuid": source_uuid,
    }


async def load_report_for_view(
    report_id: int,
    *,
    tenant_id: Optional[int] = None,
) -> dict[str, Any]:
    current_tenant = _require_tenant(tenant_id)
    async with in_transaction() as conn:
        rows = await conn.execute_query_dict(
            """
            SELECT id, category, current_version, code, name, report_config
            FROM apps_kuaireport_reports
            WHERE id = $1 AND tenant_id = $2
            """,
            [report_id, current_tenant],
        )
    if not rows:
        raise NotFoundError("账表", str(report_id))
    row = rows[0]
    config = row.get("report_config")
    if isinstance(config, str):
        config = json.loads(config)
    if not isinstance(config, dict):
        config = {}
    return {
        "report_id": int(row["id"]),
        "category": row["category"],
        "code": row["code"],
        "name": row["name"],
        "current_version": int(row.get("current_version") or 0),
        "version_no": None,
        "report_config": config,
        "data_source_uuid": _source_uuid_of(config),
    }


def _source_uuid_of(config: dict[str, Any]) -> Optional[str]:
    extra = config.get("extra")
    if not isinstance(extra, dict):
        return None
    raw = extra.get(REPORT_DATA_SOURCE_UUID)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def _user_name(user: User) -> Optional[str]:
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    if name is None:
        return None
    text = str(name).strip()
    return text or None


@router.post(
    "/designer/reports",
    response_model=DesignerReportOut,
    dependencies=[Depends(require_permission_codes("kuaireport:report:design"))],
)
async def api_save_designer_report(
    body: DesignerSaveBody,
    tenant_id: int = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await save_custom_report(
        code=body.code,
        name=body.name,
        page_size=body.page_size,
        data_source_uuid=body.data_source_uuid,
        fields=[item.model_dump() for item in body.fields],
        filters=[item.model_dump() for item in body.filters],
        summary_fields=list(body.summary_fields),
        note=body.note,
        report_id=body.report_id,
        created_by=user.id,
        created_by_name=_user_name(user),
        created_by_user_id=user.id,
        tenant_id=tenant_id,
    )


async def open_designer_report(
    report_id: int,
    *,
    tenant_id: int,
    user_id: int | None,
    grant_store: Any = None,
) -> dict[str, Any]:
    from apps.kuaireport.slices.s149_distribution import RESOURCE_REPORT, enforce_grant_view

    await enforce_grant_view(
        tenant_id, user_id, RESOURCE_REPORT, report_id, store=grant_store
    )
    return await load_report_for_view(report_id, tenant_id=tenant_id)


@router.get(
    "/designer/reports/{report_id}",
    response_model=DesignerReportOut,
    dependencies=[Depends(require_permission_codes("kuaireport:report:design"))],
)
async def api_view_designer_report(
    report_id: int,
    tenant_id: int = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await open_designer_report(
        report_id, tenant_id=tenant_id, user_id=user.id
    )
