"""数据源登记。类型只允许 static / dataset / http，配置不存放 SQL。"""

from __future__ import annotations

import ipaddress
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

from apps.kuaireport.constants import (
    DATASET_CONFIG_KEYS,
    DATASET_DISPLAY_NAME_KEY,
    DATASET_UUID_KEY,
    DATA_SOURCE_TYPES,
    FORBIDDEN_CONFIG_KEYS,
    HTTP_CONFIG_KEYS,
    HTTP_URL_KEY,
    STATIC_CONFIG_KEYS,
    STATIC_ROWS_KEY,
    REPORT_DATA_SOURCE_UUID,
)
from apps.kuaireport.models.data_source import KuaireportDataSource
from apps.kuaireport.models.report import KuaireportReport
from apps.kuaireport.schemas.data_source import DataSourceCreate, DataSourceUpdate
from infra.domain.tenant_context import require_tenant_context
from infra.exceptions.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
    tenant_context_missing,
)

_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})
_LOCAL_TEST_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _reject_sql_keys(payload: dict[str, Any]) -> None:
    for key in payload:
        if key in FORBIDDEN_CONFIG_KEYS:
            raise ValidationError("配置不能存放 SQL")


def _reject_internal_http_address(url: str) -> None:
    """拒绝明显内网/环回/链路本地地址。localhost 与 127.0.0.1 留给本地测试。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("http 地址无效")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValidationError("http 地址无效")
    if host in _LOCAL_TEST_HOSTS:
        return
    if host in _LOCAL_HOSTNAMES or host.endswith(".localhost"):
        raise ValidationError("http 地址不允许指向本机或内网")
    ip = None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # 十进制整数写法（如 2130706433 = 127.0.0.1）也按 IPv4 解释
        if host.isdigit():
            try:
                ip = ipaddress.ip_address(int(host))
            except ValueError:
                ip = None
    if ip is not None and (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_reserved
        or ip.is_multicast
    ):
        raise ValidationError("http 地址不允许指向本机或内网")


def validate_data_source_config(source_type: str, config: Optional[dict[str, Any]]) -> dict[str, Any]:
    """按类型收紧 config。dataset 只留数据集 uuid 与可选显示名。"""
    if source_type not in DATA_SOURCE_TYPES:
        raise ValidationError("数据源类型仅允许 static、dataset、http")
    body = dict(config or {})
    _reject_sql_keys(body)
    if source_type == "static":
        unknown = set(body) - STATIC_CONFIG_KEYS
        if unknown:
            raise ValidationError("static 配置只存放 rows")
        rows = body.get(STATIC_ROWS_KEY, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValidationError("static 配置的 rows 必须是对象数组")
        return {STATIC_ROWS_KEY: rows}
    if source_type == "dataset":
        unknown = set(body) - DATASET_CONFIG_KEYS
        if unknown:
            raise ValidationError("dataset 配置只存放数据集 uuid 与显示名")
        raw_uuid = body.get(DATASET_UUID_KEY)
        if not isinstance(raw_uuid, str) or not raw_uuid.strip():
            raise ValidationError("dataset 配置必须包含数据集 uuid")
        try:
            normalized = str(UUID(raw_uuid.strip()))
        except ValueError as exc:
            raise ValidationError("数据集 uuid 无效") from exc
        cleaned: dict[str, Any] = {DATASET_UUID_KEY: normalized}
        display_name = body.get(DATASET_DISPLAY_NAME_KEY)
        if display_name is not None:
            if not isinstance(display_name, str):
                raise ValidationError("数据集显示名必须是字符串")
            cleaned[DATASET_DISPLAY_NAME_KEY] = display_name
        return cleaned
    url = body.get(HTTP_URL_KEY)
    unknown = set(body) - HTTP_CONFIG_KEYS
    if unknown:
        raise ValidationError("http 配置只存放已登记地址")
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("http 配置必须包含地址")
    cleaned_url = url.strip()
    _reject_internal_http_address(cleaned_url)
    return {HTTP_URL_KEY: cleaned_url}


async def _tenant_id(explicit: int) -> int:
    try:
        current = await require_tenant_context()
    except ValueError:
        raise tenant_context_missing() from None
    if current != explicit:
        raise ValidationError("租户上下文不匹配")
    return current


async def create_data_source(
    tenant_id: int,
    payload: DataSourceCreate,
    *,
    user_id: Optional[int] = None,
) -> KuaireportDataSource:
    tid = await _tenant_id(tenant_id)
    config = validate_data_source_config(payload.type, payload.config)
    return await KuaireportDataSource.create(
        tenant_id=tid,
        name=payload.name.strip(),
        type=payload.type,
        config=config,
        description=payload.description,
        is_default=payload.is_default,
        created_by=user_id,
        updated_by=user_id,
    )


async def list_data_sources(tenant_id: int) -> list[KuaireportDataSource]:
    await _tenant_id(tenant_id)
    return await KuaireportDataSource.all().order_by("id")


async def get_data_source(tenant_id: int, source_id: int) -> KuaireportDataSource:
    await _tenant_id(tenant_id)
    row = await KuaireportDataSource.get_or_none(id=source_id)
    if row is None:
        raise NotFoundError("数据源", str(source_id))
    return row


async def update_data_source(
    tenant_id: int,
    source_id: int,
    payload: DataSourceUpdate,
    *,
    user_id: Optional[int] = None,
) -> KuaireportDataSource:
    row = await get_data_source(tenant_id, source_id)
    data = payload.model_dump(exclude_unset=True)
    source_type = data.get("type", row.type)
    config = data.get("config", row.config)
    row.type = source_type
    row.config = validate_data_source_config(source_type, config)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "description" in data:
        row.description = data["description"]
    if "is_default" in data and data["is_default"] is not None:
        row.is_default = data["is_default"]
    row.updated_by = user_id
    await row.save()
    return row


def _report_binds_source(report_config: Any, source_uuid: str) -> bool:
    if not isinstance(report_config, dict):
        return False
    extra = report_config.get("extra")
    if not isinstance(extra, dict):
        return False
    bound = extra.get(REPORT_DATA_SOURCE_UUID)
    return isinstance(bound, str) and bound == source_uuid


async def delete_data_source(tenant_id: int, source_id: int) -> None:
    row = await get_data_source(tenant_id, source_id)
    reports = await KuaireportReport.filter(tenant_id=row.tenant_id).all()
    if any(_report_binds_source(report.report_config, row.uuid) for report in reports):
        raise ConflictError("数据源仍被报表引用，不能删除")
    await row.delete()
