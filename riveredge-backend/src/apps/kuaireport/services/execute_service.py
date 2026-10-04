"""报表执行。三种数据源共用这一次取数、筛选、分页、合计。"""

from __future__ import annotations

import ipaddress
import math
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse
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


def _bound_source_uuid(report_config: dict[str, Any]) -> str | None:
    """已登记数据源 uuid。自制报表只写 dataset_uuid 时这里返回 None。"""
    extra = report_config.get("extra")
    raw = extra.get(REPORT_DATA_SOURCE_UUID) if isinstance(extra, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return None
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
    """filters 与 parameters 声明的数据集参数键。

    between / dateRange 写成 ``字段_start`` / ``字段_end``；其余用字段名本身。
    下钻维度一并放行，查询时按该字段收窄。
    """
    allowed: set[str] = set()
    specs = report_config.get("filters")
    if isinstance(specs, list):
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
    parameters = report_config.get("parameters")
    if isinstance(parameters, list):
        for spec in parameters:
            if not isinstance(spec, dict):
                continue
            key = spec.get("key")
            if not isinstance(key, str) or not key:
                continue
            if spec.get("control") == "dateRange":
                allowed.add(f"{key}_start")
                allowed.add(f"{key}_end")
            else:
                allowed.add(key)
    interaction = report_config.get("interaction")
    drill = interaction.get("drilldown") if isinstance(interaction, dict) else None
    dimension = drill.get("dimension_field") if isinstance(drill, dict) else None
    if isinstance(dimension, str) and dimension:
        allowed.add(dimension)
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


async def _http_get(url: str, headers: Optional[dict[str, str]] = None) -> Any:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError:
        raise ValidationError("HTTP 数据源执行失败") from None
    if response.status_code != 200:
        raise ValidationError("HTTP 数据源执行失败")
    try:
        return response.json()
    except ValueError:
        raise ValidationError("HTTP 数据源执行失败") from None


async def default_http_get(url: str) -> Any:
    return await _http_get(url)


_FORWARDED_HEADER_NAMES = ("authorization", "x-tenant-id")
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


def _is_self_hosted(url: str) -> bool:
    """目标主机与本服务 BASE_URL 主机一致，或是回环地址时才算同源。"""
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        return False
    if host in _LOOPBACK_HOSTNAMES or host.endswith(".localhost"):
        return True
    try:
        if ipaddress.ip_address(host).is_loopback:
            return True
    except ValueError:
        pass
    from infra.config.infra_config import infra_settings

    raw = (infra_settings.BASE_URL or "").strip()
    if not raw:
        return False
    base_host = (
        urlparse(raw if "://" in raw else f"//{raw}").hostname or ""
    ).strip().lower()
    return bool(base_host) and host == base_host


def forward_auth_http_get(request: Any) -> HttpGet:
    """同源（本服务主机/回环）地址转发当前请求的 Authorization 与租户头。

    馈送类地址要求 ``Authorization`` + 租户上下文，裸 GET 必 401；其它主机保持裸 GET。
    """
    forwarded = {
        name: request.headers[name]
        for name in _FORWARDED_HEADER_NAMES
        if request.headers.get(name)
    }

    async def _get(url: str) -> Any:
        if forwarded and _is_self_hosted(url):
            return await _http_get(url, forwarded)
        return await _http_get(url)

    return _get


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


def nested_http_document(payload: Any) -> Optional[dict[str, Any]]:
    """顶层数组和 ``{data: []}`` 仍走 ``_rows_from_http``。其余对象交给组件路径。"""
    if isinstance(payload, list) or not isinstance(payload, dict):
        return None
    if isinstance(payload.get("data"), list):
        return None
    if "data" in payload:
        return None
    return payload


_MISSING = object()


def _walk_path(node: Any, parts: list[str]) -> Any:
    if not parts:
        return node
    key, *rest = parts
    if isinstance(node, dict):
        if key not in node:
            return _MISSING
        return _walk_path(node[key], rest)
    if isinstance(node, list):
        found = False
        values: list[Any] = []
        for item in node:
            if not isinstance(item, dict) or key not in item:
                continue
            found = True
            got = _walk_path(item[key], rest)
            if got is _MISSING:
                continue
            values.append(got)
        if not found:
            return _MISSING
        return values
    return _MISSING


def _widget_field_path(widget: dict[str, Any]) -> str:
    options = widget.get("options")
    if not isinstance(options, dict):
        return ""
    raw = options.get("field")
    if not isinstance(raw, str):
        return ""
    return raw.strip()


def _plain_column(path: str, result: dict[str, Any]) -> bool:
    """无点号、且已经是行上的标量列或合计键时，保留列表源的原结果。"""
    if "." in path:
        return False
    summary = result.get("summary")
    if isinstance(summary, dict) and path in summary:
        return True
    rows = result.get("data")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if isinstance(row, dict) and path in row and not isinstance(row[path], (dict, list)):
            return True
    return False


def _rows_from_walked(path: str, value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        if not value:
            return {"data": [], "total": 0, "summary": {}}
        if all(isinstance(item, dict) for item in value):
            rows = [dict(item) for item in value]
            return {"data": rows, "total": len(rows), "summary": {}}
        leaf = path.rsplit(".", 1)[-1]
        rows = [{leaf: item} for item in value]
        summary = {path: value[0]} if len(value) == 1 else {}
        return {"data": rows, "total": len(rows), "summary": summary}
    if isinstance(value, dict):
        return {"data": [dict(value)], "total": 1, "summary": {}}
    leaf = path.rsplit(".", 1)[-1]
    return {"data": [{leaf: value}], "total": 1, "summary": {path: value}}


def project_widget_field(widget: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """按组件 ``options.field`` 点号取嵌套值。缺层时该组件为空，不抛错。

    路径落到数组（如 ``status_dist``）时，原样返回元素；图表的 ``x_field`` / ``y_field`` 仍是元素上的列。
    """
    path = _widget_field_path(widget)
    if not path or _plain_column(path, result):
        return result
    rows = result.get("data")
    if not isinstance(rows, list):
        return {"data": [], "total": 0, "summary": {}}
    if len(rows) == 1 and isinstance(rows[0], dict):
        root: Any = rows[0]
    else:
        root = rows
    walked = _walk_path(root, [part for part in path.split(".") if part])
    if walked is _MISSING:
        return {"data": [], "total": 0, "summary": {}}
    return _rows_from_walked(path, walked)


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


async def _execute_platform_dataset(
    tenant_id: int,
    dataset_uuid: str,
    filters: dict[str, Any],
    report_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], Optional[int], bool]:
    """直接执行平台数据集。自制报表不经过星报表数据源登记。"""
    dataset = await load_dataset(dataset_uuid)
    if dataset is None:
        raise NotFoundError("数据集", dataset_uuid)
    if getattr(dataset, "tenant_id", tenant_id) != tenant_id:
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
        return await _execute_platform_dataset(
            tenant_id, dataset_uuid, filters, report_config
        )
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
    platform_uuid = report_config.get(DATASET_UUID_KEY)
    if source_uuid:
        source = await KuaireportDataSource.get_or_none(uuid=source_uuid, tenant_id=tid)
        if source is None:
            raise NotFoundError("数据源", source_uuid)
        rows, remote_total, paged = await _load_rows(
            source, tid, incoming, report_config, http_get
        )
    elif isinstance(platform_uuid, str) and platform_uuid.strip():
        rows, remote_total, paged = await _execute_platform_dataset(
            tid, platform_uuid.strip(), incoming, report_config
        )
    else:
        raise ValidationError("报表未绑定数据源")
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
