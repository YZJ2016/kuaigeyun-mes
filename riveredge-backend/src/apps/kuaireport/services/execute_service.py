"""报表执行。三种数据源共用这一次取数、筛选、分页、合计。"""

from __future__ import annotations

import math
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from apps.kuaireport.constants import (
    DATASET_UUID_KEY,
    FORBIDDEN_CONFIG_KEYS,
    HTTP_ADDRESS_OVERRIDE_KEYS,
    HTTP_URL_KEY,
    PAGINATION_KEYS,
    REPORT_DATA_SOURCE_UUID,
    STATIC_ROWS_KEY,
)
from apps.kuaireport.models.data_source import KuaireportDataSource
from apps.kuaireport.models.report import KuaireportReport
from apps.kuaireport.schemas.execute import ExecuteReportResult
from apps.kuaireport.services.data_source_service import _tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError

HttpGet = Callable[[str], Awaitable[Any]]


def _reject_sql_keys(node: Any) -> None:
    """递归扫 report_config 全部嵌套层，任何深度出现禁用键即拒绝。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORBIDDEN_CONFIG_KEYS:
                raise ValidationError("报表配置不能存放 SQL")
            _reject_sql_keys(value)
    elif isinstance(node, list):
        for item in node:
            _reject_sql_keys(item)


def _report_lookup(report_id: str | int) -> dict[str, Any]:
    if isinstance(report_id, int) and not isinstance(report_id, bool):
        return {"id": report_id}
    ref = str(report_id or "").strip()
    if not ref:
        raise ValidationError("报表不存在")
    if ref.isdigit():
        return {"id": int(ref)}
    return {"uuid": ref}


def _bound_source_uuid(report_config: dict[str, Any]) -> str:
    extra = report_config.get("extra")
    raw = extra.get(REPORT_DATA_SOURCE_UUID) if isinstance(extra, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("报表未绑定数据源")
    return raw.strip()


def _page(filters: dict[str, Any], report_config: dict[str, Any]) -> tuple[int, int]:
    raw_limit = filters.get("limit")
    if raw_limit is None:
        raw_limit = report_config.get("page_size") or 20
    raw_offset = filters.get("offset", 0)
    if raw_offset is None:
        raw_offset = 0
    try:
        limit = int(raw_limit)
        offset = int(raw_offset)
    except (TypeError, ValueError) as exc:
        raise ValidationError("分页参数无效") from exc
    if limit < 1 or limit > 10000 or offset < 0:
        raise ValidationError("分页参数无效")
    return limit, offset


def _as_order(value: Any) -> tuple[int, float | str]:
    if isinstance(value, bool) or value is None:
        return (1, "" if value is None else str(value))
    if isinstance(value, (int, float)):
        return (0, float(value))
    text = str(value)
    try:
        return (0, float(text))
    except ValueError:
        return (1, text)


def _equals(left: Any, right: Any) -> bool:
    if left == right:
        return True
    return str(left) == str(right)


def _filter_rows(
    rows: list[dict[str, Any]],
    report_config: dict[str, Any],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    specs = report_config.get("filters") or []
    if not isinstance(specs, list):
        return rows
    matched = rows
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        field = spec.get("field")
        if not isinstance(field, str) or not field:
            continue
        operator = spec.get("operator")
        if operator == "between":
            start = filters.get(f"{field}_start")
            end = filters.get(f"{field}_end")
            if start is None and end is None:
                continue

            def _keep(row: dict[str, Any], start=start, end=end, field=field) -> bool:
                value = row.get(field)
                if value is None:
                    return False
                current = _as_order(value)
                if start is not None and current < _as_order(start):
                    return False
                if end is not None and current > _as_order(end):
                    return False
                return True

            matched = [row for row in matched if _keep(row)]
            continue
        if field not in filters or filters[field] is None:
            continue
        expected = filters[field]
        matched = [row for row in matched if _equals(row.get(field), expected)]
    return matched


def _summary_field_names(report_config: dict[str, Any]) -> list[str]:
    extra = report_config.get("extra") if isinstance(report_config.get("extra"), dict) else {}
    uni = extra.get("uni_report") if isinstance(extra, dict) else None
    if isinstance(uni, dict):
        names = uni.get("summaryFields")
        if isinstance(names, list) and names:
            return [name for name in names if isinstance(name, str) and name]
    fields = report_config.get("fields") or []
    if not isinstance(fields, list):
        return []
    picked: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = field.get("field")
        if not isinstance(name, str) or not name:
            continue
        if field.get("aggregate") == "sum" or field.get("format") in ("money", "number"):
            picked.append(name)
    return picked


def _number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value))
        except (TypeError, ValueError):
            return 0.0
    if not math.isfinite(number):
        return 0.0
    return number


def summarize_rows(rows: list[dict[str, Any]], report_config: dict[str, Any]) -> dict[str, float | int]:
    """报表层合计。数据集响应没有 summary，这里按 report_config 的合计字段求和。"""
    summary: dict[str, float | int] = {}
    for field in _summary_field_names(report_config):
        total = sum(_number(row.get(field)) for row in rows)
        summary[field] = int(total) if total.is_integer() else total
    return summary


def _project(rows: list[dict[str, Any]], report_config: dict[str, Any]) -> list[dict[str, Any]]:
    fields = report_config.get("fields") or []
    if not isinstance(fields, list) or not fields:
        return [dict(row) for row in rows]
    names = [field.get("field") for field in fields if isinstance(field, dict)]
    names = [name for name in names if isinstance(name, str) and name]
    if not names:
        return [dict(row) for row in rows]
    return [{name: row.get(name) for name in names} for row in rows]


def _declared_parameter_keys(report_config: dict[str, Any]) -> set[str]:
    """report_config.filters 声明的字段收敛出的数据集参数键。

    between 写成 ``字段_start`` / ``字段_end``；其余操作符用字段名本身。
    """
    allowed: set[str] = set()
    specs = report_config.get("filters")
    if not isinstance(specs, list):
        return allowed
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        field = spec.get("field")
        if not isinstance(field, str) or not field:
            continue
        if spec.get("operator") == "between":
            allowed.add(f"{field}_start")
            allowed.add(f"{field}_end")
        else:
            allowed.add(field)
    return allowed


def _parameters(
    filters: dict[str, Any], report_config: dict[str, Any]
) -> Optional[dict[str, Any]]:
    skipped = PAGINATION_KEYS | HTTP_ADDRESS_OVERRIDE_KEYS
    allowed = _declared_parameter_keys(report_config)
    params = {
        key: value
        for key, value in filters.items()
        if key not in skipped and key in allowed
    }
    return params or None


async def load_dataset(dataset_uuid: str):
    """读取本租户数据集。测试可替换此函数，避免在执行器之外再写查询。"""
    from core.models.dataset import Dataset

    return await Dataset.get_or_none(uuid=dataset_uuid)


async def run_dataset_query(tenant_id: int, dataset_uuid: str, request):
    """调用已有数据集执行器。请求体只有 parameters、limit、offset。"""
    from core.services.data.dataset_service import DatasetService

    return await DatasetService().execute_query(
        tenant_id=tenant_id,
        dataset_uuid=UUID(dataset_uuid),
        execute_request=request,
    )


async def default_http_get(url: str) -> Any:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        raise ValidationError("HTTP 数据源执行失败") from None
    if response.status_code != 200:
        raise ValidationError("HTTP 数据源执行失败")
    try:
        return response.json()
    except ValueError:
        raise ValidationError("HTTP 数据源执行失败") from None


def _rows_from_http(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = payload["data"]
    else:
        raise ValidationError("HTTP 数据源执行失败")
    if any(not isinstance(row, dict) for row in rows):
        raise ValidationError("HTTP 数据源执行失败")
    return rows


async def _assert_registered_http_url(url: str, tenant_id: int) -> None:
    rows = await KuaireportDataSource.filter(type="http", tenant_id=tenant_id).all()
    for row in rows:
        config = row.config if isinstance(row.config, dict) else {}
        if config.get(HTTP_URL_KEY) == url:
            return
    raise ValidationError("HTTP 地址未登记")


def _reject_address_override(filters: dict[str, Any], registered_url: str) -> None:
    for key in HTTP_ADDRESS_OVERRIDE_KEYS:
        if key in filters and filters[key] != registered_url:
            raise ValidationError("HTTP 地址未登记")


async def _load_rows(
    source: KuaireportDataSource,
    tenant_id: int,
    filters: dict[str, Any],
    report_config: dict[str, Any],
    http_get: HttpGet,
) -> tuple[list[dict[str, Any]], Optional[int], bool]:
    """返回 (行, 数据集给出的 total, 是否已由数据集按 limit/offset 分页)。"""
    config = source.config if isinstance(source.config, dict) else {}
    if source.type == "static":
        rows = config.get(STATIC_ROWS_KEY) or []
        if not isinstance(rows, list):
            raise ValidationError("static 配置的 rows 必须是对象数组")
        return [row for row in rows if isinstance(row, dict)], None, False
    if source.type == "dataset":
        dataset_uuid = config.get(DATASET_UUID_KEY)
        if not isinstance(dataset_uuid, str) or not dataset_uuid:
            raise ValidationError("dataset 配置必须包含数据集 uuid")
        dataset = await load_dataset(dataset_uuid)
        if dataset is None:
            raise NotFoundError("数据集", dataset_uuid)
        if dataset.query_type not in ("sql", "api"):
            raise ValidationError("报表只绑定 sql 或 api 数据集")
        from core.schemas.dataset import ExecuteQueryRequest

        limit, offset = _page(filters, report_config)
        request = ExecuteQueryRequest(
            parameters=_parameters(filters, report_config),
            limit=limit,
            offset=offset,
        )
        result = await run_dataset_query(tenant_id, dataset_uuid, request)
        if not result.success:
            raise ValidationError("数据集执行失败")
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        return rows, result.total, True
    if source.type == "http":
        url = config.get(HTTP_URL_KEY)
        if not isinstance(url, str) or not url:
            raise ValidationError("http 配置必须包含地址")
        _reject_address_override(filters, url)
        await _assert_registered_http_url(url, tenant_id)
        payload = await http_get(url)
        return _rows_from_http(payload), None, False
    raise ValidationError("数据源类型仅允许 static、dataset、http")


async def execute_report(
    tenant_id: int,
    report_id: str | int,
    filters: Optional[dict[str, Any]] = None,
    *,
    http_get: HttpGet = default_http_get,
) -> ExecuteReportResult:
    """按 report_config 执行一张报表。无租户上下文时不读报表表。"""
    tid = await _tenant_id(tenant_id)
    incoming = dict(filters or {})
    report = await KuaireportReport.get_or_none(**_report_lookup(report_id))
    if report is None:
        raise NotFoundError("报表", str(report_id))
    report_config = report.report_config if isinstance(report.report_config, dict) else {}
    _reject_sql_keys(report_config)
    source_uuid = _bound_source_uuid(report_config)
    source = await KuaireportDataSource.get_or_none(uuid=source_uuid, tenant_id=tid)
    if source is None:
        raise NotFoundError("数据源", source_uuid)
    rows, remote_total, paged = await _load_rows(source, tid, incoming, report_config, http_get)
    if paged:
        data_rows = rows
        summary = summarize_rows(data_rows, report_config)
        total = remote_total if remote_total is not None else len(data_rows)
    else:
        filtered = _filter_rows(rows, report_config, incoming)
        summary = summarize_rows(filtered, report_config)
        limit, offset = _page(incoming, report_config)
        data_rows = filtered[offset : offset + limit]
        total = len(filtered)
    return ExecuteReportResult(
        data=_project(data_rows, report_config),
        total=int(total),
        success=True,
        summary=summary,
    )
