"""星报表 P4：大屏四段配置与受控分享（spec 148）。

免登录只走大屏 ``/dashboards/shared``（含 ``file-preview``）和账表 ``/reports/shared``。
口令只经 ``hash_password`` 写入 ``share_password_hash``。访问日志只记原因码。
不写角色授权、订阅。大屏保存成功后调用 149 的版本插入函数，本文件不写版本表 INSERT。
"""

from __future__ import annotations

import ipaddress
import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from infra.api.deps.deps import get_current_user
from infra.domain.security.security import hash_password, verify_password
from infra.utils.client_ip import get_client_ip

WIDGET_TYPES = (
    "metric",
    "table",
    "chart",
    "border",
    "title",
    "carousel",
    "clock",
    "image",
    "video",
    "web",
)
DATA_WIDGET_TYPES = frozenset({"metric", "table", "chart"})
SYSTEM_REPORT_CODES = frozenset(
    {
        "inv_ledger",
        "wo_tracking",
        "qc_pass_rate",
        "perf_stats",
        "node_timeliness",
        "process_efficiency",
        "sales_trace",
        "purchase_trace",
        "material_trace",
        "biz_overview",
    }
)

PASSWORD_HEADER = "X-Share-Password"
UNLOCK_COOKIE = "kuaireport_share_unlock"
UNLOCK_PURPOSE = "kuaireport_share_unlock"
UNLOCK_TTL = timedelta(hours=8)

DETAIL_OK = "ok"
DETAIL_NOT_SHARED = "not_shared"
DETAIL_MISSING_HASH = "missing_password_hash"
DETAIL_MISSING_EXPIRY = "missing_expiry"
DETAIL_EXPIRED = "expired"
DETAIL_PASSWORD = "password_mismatch"
DETAIL_IP = "ip_denied"
DETAIL_DATA = "data_unavailable"
ALLOWED_DETAILS = frozenset(
    {
        DETAIL_OK,
        DETAIL_NOT_SHARED,
        DETAIL_MISSING_HASH,
        DETAIL_MISSING_EXPIRY,
        DETAIL_EXPIRED,
        DETAIL_PASSWORD,
        DETAIL_IP,
        DETAIL_DATA,
    }
)

SECRET_KEYS = frozenset(
    {"password", "share_password", "share_password_hash", "password_hash"}
)

SYSTEM_SHARE_FLAG_SQL = """
SELECT code, is_shared
FROM apps_kuaireport_reports
WHERE tenant_id = $1 AND code = ANY($2::varchar[])
"""


class ShareLogError(RuntimeError):
    """访问日志没写上。此时不能把大屏或账表数据返回。"""


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def allowlist_is_empty(value: Any) -> bool:
    """空名单不做 IP 匹配。非空才逐条比对。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return len(value) == 0
    if isinstance(value, (list, tuple)):
        return not any(str(item).strip() for item in value)
    return False


def ip_allowed(client_ip: Optional[str], allow: Any) -> bool:
    if allowlist_is_empty(allow):
        return True
    entries = allow if isinstance(allow, (list, tuple)) else [allow]
    text_ip = (client_ip or "").strip()
    try:
        ip = ipaddress.ip_address(text_ip)
    except ValueError:
        return False
    for entry in entries:
        raw = str(entry).strip()
        if not raw:
            continue
        try:
            if "/" in raw:
                if ip in ipaddress.ip_network(raw, strict=False):
                    return True
            elif ip == ipaddress.ip_address(raw):
                return True
        except ValueError:
            continue
    return False


def evaluate_share(
    *,
    is_shared: bool,
    share_expires_at: Optional[datetime],
    share_password_hash: Optional[str],
    share_allow_ip_cidrs: Any,
    password: Optional[str],
    client_ip: Optional[str],
    now: datetime,
    unlock_ok: bool,
) -> tuple[bool, str]:
    """顺序：已分享、哈希已存在、未过期、口令匹配、白名单（非空才查）。"""
    if not is_shared:
        return False, DETAIL_NOT_SHARED
    if not (share_password_hash or "").strip():
        return False, DETAIL_MISSING_HASH
    if share_expires_at is None:
        return False, DETAIL_MISSING_EXPIRY
    if as_utc(now) >= as_utc(share_expires_at):
        return False, DETAIL_EXPIRED
    if password:
        try:
            matched = verify_password(password, share_password_hash or "")
        except Exception:
            matched = False
        if not matched:
            return False, DETAIL_PASSWORD
    elif not unlock_ok:
        return False, DETAIL_PASSWORD
    if not ip_allowed(client_ip, share_allow_ip_cidrs):
        return False, DETAIL_IP
    return True, DETAIL_OK


def _as_object(value: Any, name: str) -> Optional[dict]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def validate_widgets(widgets: Any) -> list[dict]:
    """每个组件恰好一个 data_source_id，并带 refresh_seconds。"""
    if widgets is None:
        return []
    if not isinstance(widgets, list):
        raise ValueError("widgets_config must be a list")
    cleaned: list[dict] = []
    for index, widget in enumerate(widgets):
        if not isinstance(widget, dict):
            raise ValueError("widget must be an object")
        extra_sources = [
            key
            for key in ("data_source_ids", "data_sources", "source_ids")
            if key in widget
        ]
        if extra_sources:
            raise ValueError("widget binds exactly one data source")
        widget_type = widget.get("type")
        if widget_type not in WIDGET_TYPES:
            raise ValueError("unknown widget type")
        if "data_source_id" not in widget:
            raise ValueError("widget requires one data source")
        source_id = widget["data_source_id"]
        if isinstance(source_id, bool) or not isinstance(source_id, int):
            raise ValueError("data_source_id must be an integer")
        refresh = widget.get("refresh_seconds")
        if isinstance(refresh, bool) or not isinstance(refresh, int) or refresh < 1:
            raise ValueError("refresh_seconds must be a positive integer")
        item = {
            "id": str(widget.get("id") or f"w{index + 1}"),
            "type": widget_type,
            "data_source_id": source_id,
            "refresh_seconds": refresh,
        }
        if isinstance(widget.get("title"), str):
            item["title"] = widget["title"]
        if isinstance(widget.get("options"), dict):
            item["options"] = widget["options"]
        if isinstance(widget.get("layout"), dict):
            item["layout"] = widget["layout"]
        cleaned.append(item)
    return cleaned


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: scrub(item)
            for key, item in value.items()
            if key not in SECRET_KEYS
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def issue_unlock(share_token: str, secret: str, now: datetime) -> str:
    payload = {
        "purpose": UNLOCK_PURPOSE,
        "stk": share_token,
        "exp": as_utc(now) + UNLOCK_TTL,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def unlock_matches(token: Optional[str], share_token: str, secret: str) -> bool:
    if not token or not share_token:
        return False
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError:
        return False
    return payload.get("purpose") == UNLOCK_PURPOSE and payload.get("stk") == share_token


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


@dataclass
class DashboardRecord:
    id: int
    uuid: str
    tenant_id: int
    code: str
    name: str
    layout_config: Optional[dict] = None
    widgets_config: list = field(default_factory=list)
    theme_config: Optional[dict] = None
    tv_config: Optional[dict] = None
    status: str = "DRAFT"
    is_shared: bool = False
    share_token: Optional[str] = None
    share_expires_at: Optional[datetime] = None
    share_password_hash: Optional[str] = None
    share_allow_ip_cidrs: Any = None
    current_version: int = 0


@dataclass
class ReportRecord:
    id: int
    uuid: str
    tenant_id: int
    code: str
    name: str
    report_config: Optional[dict] = None
    is_system: bool = False
    is_shared: bool = False
    share_token: Optional[str] = None
    share_expires_at: Optional[datetime] = None
    share_password_hash: Optional[str] = None
    share_allow_ip_cidrs: Any = None


@dataclass
class AccessLogRecord:
    tenant_id: int
    resource_type: str
    resource_id: int
    share_token: str
    action: str
    client_ip: Optional[str]
    success: bool
    detail: str
    user_agent: Optional[str] = None


SourceExecutor = Callable[[int, int], Awaitable[dict]]
ReportExecutor = Callable[[int, int, Optional[dict]], Awaitable[dict]]
PreviewBuilder = Callable[[str, int, Optional[int]], Awaitable[str]]


def _empty_result() -> dict:
    return {"data": [], "total": 0, "summary": {}}


def _shape_result(raw: Any) -> dict:
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return _empty_result()
    data = raw.get("data") or []
    summary = raw.get("summary") or {}
    return {
        "data": list(data) if isinstance(data, list) else [],
        "total": int(raw.get("total") or 0),
        "summary": dict(summary) if isinstance(summary, dict) else {},
    }


async def default_execute_source(tenant_id: int, data_source_id: int) -> dict:
    """指标/表格/图表走 145 的取数。分享打开时用大屏所属租户，不读客户端租户。"""
    try:
        from apps.kuaireport.models.data_source import KuaireportDataSource
        from apps.kuaireport.services.execute_service import (
            _filter_rows,
            _load_rows,
            _page,
            default_http_get,
            summarize_rows,
        )
        from infra.domain.tenant_context import with_tenant
    except ImportError:
        return _empty_result()
    report_config = {"data_source_id": data_source_id}
    async with with_tenant(tenant_id):
        source = await KuaireportDataSource.get_or_none(id=data_source_id, tenant_id=tenant_id)
        if source is None:
            return _empty_result()
        rows, remote_total, paged = await _load_rows(
            source, tenant_id, {}, report_config, default_http_get
        )
        if paged:
            data_rows = rows
            total = remote_total if remote_total is not None else len(data_rows)
            summary = summarize_rows(data_rows, report_config)
        else:
            filtered = _filter_rows(rows, report_config, {})
            summary = summarize_rows(filtered, report_config)
            limit, offset = _page({}, report_config)
            data_rows = filtered[offset : offset + limit]
            total = len(filtered)
    return {"data": data_rows, "total": int(total), "summary": summary}


async def default_execute_report(
    tenant_id: int, report_id: int, report_config: Optional[dict]
) -> dict:
    del report_config
    try:
        from apps.kuaireport.services.execute_service import execute_report
        from infra.domain.tenant_context import with_tenant
    except ImportError:
        return _empty_result()
    async with with_tenant(tenant_id):
        result = await execute_report(tenant_id, report_id)
    return _shape_result(result)


async def default_preview_url(file_uuid: str, tenant_id: int, size: Optional[int]) -> str:
    from core.services.file.file_preview_service import FilePreviewService

    return await FilePreviewService.generate_simple_preview_url(
        file_uuid=file_uuid,
        tenant_id=tenant_id,
        size=size,
    )


def _default_secret() -> str:
    from infra.config.infra_config import infra_settings

    return infra_settings.JWT_SECRET_KEY


class MemoryShareStore:
    def __init__(self) -> None:
        self.dashboards: dict[int, DashboardRecord] = {}
        self.reports: dict[int, ReportRecord] = {}
        self.logs: list[AccessLogRecord] = []
        self.fail_logs = False
        self._next_id = 1

    def _alloc(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    async def create_dashboard(
        self,
        *,
        tenant_id: int,
        code: str,
        name: str,
        layout_config: Optional[dict],
        widgets_config: list,
        theme_config: Optional[dict],
        tv_config: Optional[dict],
    ) -> DashboardRecord:
        if any(row.code == code for row in self.dashboards.values()):
            raise ValueError("dashboard code already exists")
        row = DashboardRecord(
            id=self._alloc(),
            uuid=str(uuid.uuid4()),
            tenant_id=tenant_id,
            code=code,
            name=name,
            layout_config=layout_config,
            widgets_config=widgets_config,
            theme_config=theme_config,
            tv_config=tv_config,
        )
        self.dashboards[row.id] = row
        return row

    async def update_dashboard(
        self,
        *,
        tenant_id: int,
        dashboard_id: int,
        name: Optional[str],
        layout_config: Optional[dict],
        widgets_config: list,
        theme_config: Optional[dict],
        tv_config: Optional[dict],
    ) -> Optional[DashboardRecord]:
        row = self.dashboards.get(dashboard_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        if name:
            row.name = name
        row.layout_config = layout_config
        row.widgets_config = widgets_config
        row.theme_config = theme_config
        row.tv_config = tv_config
        return row

    async def get_dashboard(self, tenant_id: int, dashboard_id: int) -> Optional[DashboardRecord]:
        row = self.dashboards.get(dashboard_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def find_dashboard_by_token(self, share_token: str) -> Optional[DashboardRecord]:
        for row in self.dashboards.values():
            if row.share_token == share_token:
                return row
        return None

    async def set_dashboard_share(
        self,
        *,
        tenant_id: int,
        dashboard_id: int,
        share_token: str,
        share_expires_at: datetime,
        share_password_hash: str,
        share_allow_ip_cidrs: Any,
    ) -> Optional[DashboardRecord]:
        row = await self.get_dashboard(tenant_id, dashboard_id)
        if row is None:
            return None
        row.is_shared = True
        row.share_token = share_token
        row.share_expires_at = share_expires_at
        row.share_password_hash = share_password_hash
        row.share_allow_ip_cidrs = share_allow_ip_cidrs
        return row

    async def add_report(self, row: ReportRecord) -> ReportRecord:
        self.reports[row.id] = row
        return row

    async def get_report(self, tenant_id: int, report_id: int) -> Optional[ReportRecord]:
        row = self.reports.get(report_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def find_report_by_token(self, share_token: str) -> Optional[ReportRecord]:
        for row in self.reports.values():
            if row.share_token == share_token:
                return row
        return None

    async def set_report_share(
        self,
        *,
        tenant_id: int,
        report_id: int,
        share_token: str,
        share_expires_at: datetime,
        share_password_hash: str,
        share_allow_ip_cidrs: Any,
    ) -> Optional[ReportRecord]:
        row = await self.get_report(tenant_id, report_id)
        if row is None:
            return None
        row.is_shared = True
        row.share_token = share_token
        row.share_expires_at = share_expires_at
        row.share_password_hash = share_password_hash
        row.share_allow_ip_cidrs = share_allow_ip_cidrs
        return row

    async def system_share_flags(self, tenant_id: int) -> dict[str, bool]:
        flags = {code: False for code in SYSTEM_REPORT_CODES}
        for row in self.reports.values():
            if row.tenant_id == tenant_id and row.code in flags:
                flags[row.code] = bool(row.is_shared)
        return flags

    async def append_log(self, record: AccessLogRecord) -> None:
        if self.fail_logs:
            raise ShareLogError("access log write failed")
        if record.detail not in ALLOWED_DETAILS:
            raise ShareLogError("access log detail rejected")
        self.logs.append(record)


class SqlShareStore:
    """读写迁移 92 / 563 已有列。按分享 token 找行时不用客户端租户。"""

    def __init__(self) -> None:
        self._conn_override = None

    async def _conn(self):
        if self._conn_override is not None:
            return self._conn_override
        from tortoise import Tortoise

        return Tortoise.get_connection("default")

    async def run_in_transaction(self, work):
        from tortoise.transactions import in_transaction

        async with in_transaction() as conn:
            previous = self._conn_override
            self._conn_override = conn
            try:
                return await work(conn)
            finally:
                self._conn_override = previous

    def _dashboard_from_row(self, row: dict) -> DashboardRecord:
        return DashboardRecord(
            id=int(row["id"]),
            uuid=row["uuid"],
            tenant_id=int(row["tenant_id"]),
            code=row["code"],
            name=row["name"],
            layout_config=_json_load(row.get("layout_config")),
            widgets_config=_json_load(row.get("widgets_config")) or [],
            theme_config=_json_load(row.get("theme_config")),
            tv_config=_json_load(row.get("tv_config")),
            status=row.get("status") or "DRAFT",
            is_shared=bool(row.get("is_shared")),
            share_token=row.get("share_token"),
            share_expires_at=row.get("share_expires_at"),
            share_password_hash=row.get("share_password_hash"),
            share_allow_ip_cidrs=_json_load(row.get("share_allow_ip_cidrs")),
            current_version=int(row.get("current_version") or 0),
        )

    def _report_from_row(self, row: dict) -> ReportRecord:
        return ReportRecord(
            id=int(row["id"]),
            uuid=row["uuid"],
            tenant_id=int(row["tenant_id"]),
            code=row["code"],
            name=row["name"],
            report_config=_json_load(row.get("report_config")),
            is_system=bool(row.get("is_system")),
            is_shared=bool(row.get("is_shared")),
            share_token=row.get("share_token"),
            share_expires_at=row.get("share_expires_at"),
            share_password_hash=row.get("share_password_hash"),
            share_allow_ip_cidrs=_json_load(row.get("share_allow_ip_cidrs")),
        )

    async def create_dashboard(
        self,
        *,
        tenant_id: int,
        code: str,
        name: str,
        layout_config: Optional[dict],
        widgets_config: list,
        theme_config: Optional[dict],
        tv_config: Optional[dict],
    ) -> DashboardRecord:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            INSERT INTO apps_kuaireport_dashboards
                (uuid, tenant_id, code, name, layout_config, widgets_config,
                 theme_config, tv_config, status, is_shared, current_version)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb, 'DRAFT', FALSE, 1)
            RETURNING id, uuid, tenant_id, code, name, layout_config, widgets_config,
                      theme_config, tv_config, status, is_shared, share_token,
                      share_expires_at, share_password_hash, share_allow_ip_cidrs,
                      current_version
            """,
            [
                str(uuid.uuid4()),
                tenant_id,
                code,
                name,
                _json_dumps(layout_config),
                _json_dumps(widgets_config),
                _json_dumps(theme_config),
                _json_dumps(tv_config),
            ],
        )
        return self._dashboard_from_row(rows[0])

    async def update_dashboard(
        self,
        *,
        tenant_id: int,
        dashboard_id: int,
        name: Optional[str],
        layout_config: Optional[dict],
        widgets_config: list,
        theme_config: Optional[dict],
        tv_config: Optional[dict],
    ) -> Optional[DashboardRecord]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            UPDATE apps_kuaireport_dashboards
            SET name = COALESCE($3, name),
                layout_config = $4::jsonb,
                widgets_config = $5::jsonb,
                theme_config = $6::jsonb,
                tv_config = $7::jsonb,
                current_version = current_version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND tenant_id = $2
            RETURNING id, uuid, tenant_id, code, name, layout_config, widgets_config,
                      theme_config, tv_config, status, is_shared, share_token,
                      share_expires_at, share_password_hash, share_allow_ip_cidrs,
                      current_version
            """,
            [
                dashboard_id,
                tenant_id,
                name,
                _json_dumps(layout_config),
                _json_dumps(widgets_config),
                _json_dumps(theme_config),
                _json_dumps(tv_config),
            ],
        )
        if not rows:
            return None
        return self._dashboard_from_row(rows[0])

    async def get_dashboard(self, tenant_id: int, dashboard_id: int) -> Optional[DashboardRecord]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            SELECT id, uuid, tenant_id, code, name, layout_config, widgets_config,
                   theme_config, tv_config, status, is_shared, share_token,
                   share_expires_at, share_password_hash, share_allow_ip_cidrs
            FROM apps_kuaireport_dashboards
            WHERE id = $1 AND tenant_id = $2
            """,
            [dashboard_id, tenant_id],
        )
        if not rows:
            return None
        return self._dashboard_from_row(rows[0])

    async def find_dashboard_by_token(self, share_token: str) -> Optional[DashboardRecord]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            SELECT id, uuid, tenant_id, code, name, layout_config, widgets_config,
                   theme_config, tv_config, status, is_shared, share_token,
                   share_expires_at, share_password_hash, share_allow_ip_cidrs
            FROM apps_kuaireport_dashboards
            WHERE share_token = $1
            """,
            [share_token],
        )
        if not rows:
            return None
        return self._dashboard_from_row(rows[0])

    async def set_dashboard_share(
        self,
        *,
        tenant_id: int,
        dashboard_id: int,
        share_token: str,
        share_expires_at: datetime,
        share_password_hash: str,
        share_allow_ip_cidrs: Any,
    ) -> Optional[DashboardRecord]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            UPDATE apps_kuaireport_dashboards
            SET is_shared = TRUE,
                share_token = $3,
                share_expires_at = $4,
                share_password_hash = $5,
                share_allow_ip_cidrs = $6::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND tenant_id = $2
            RETURNING id
            """,
            [
                dashboard_id,
                tenant_id,
                share_token,
                share_expires_at,
                share_password_hash,
                _json_dumps(share_allow_ip_cidrs),
            ],
        )
        if not rows:
            return None
        return await self.get_dashboard(tenant_id, dashboard_id)

    async def get_report(self, tenant_id: int, report_id: int) -> Optional[ReportRecord]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            SELECT id, uuid, tenant_id, code, name, report_config, is_system,
                   is_shared, share_token, share_expires_at, share_password_hash,
                   share_allow_ip_cidrs
            FROM apps_kuaireport_reports
            WHERE id = $1 AND tenant_id = $2
            """,
            [report_id, tenant_id],
        )
        if not rows:
            return None
        return self._report_from_row(rows[0])

    async def find_report_by_token(self, share_token: str) -> Optional[ReportRecord]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            SELECT id, uuid, tenant_id, code, name, report_config, is_system,
                   is_shared, share_token, share_expires_at, share_password_hash,
                   share_allow_ip_cidrs
            FROM apps_kuaireport_reports
            WHERE share_token = $1
            """,
            [share_token],
        )
        if not rows:
            return None
        return self._report_from_row(rows[0])

    async def set_report_share(
        self,
        *,
        tenant_id: int,
        report_id: int,
        share_token: str,
        share_expires_at: datetime,
        share_password_hash: str,
        share_allow_ip_cidrs: Any,
    ) -> Optional[ReportRecord]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            """
            UPDATE apps_kuaireport_reports
            SET is_shared = TRUE,
                share_token = $3,
                share_expires_at = $4,
                share_password_hash = $5,
                share_allow_ip_cidrs = $6::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND tenant_id = $2
            RETURNING id
            """,
            [
                report_id,
                tenant_id,
                share_token,
                share_expires_at,
                share_password_hash,
                _json_dumps(share_allow_ip_cidrs),
            ],
        )
        if not rows:
            return None
        return await self.get_report(tenant_id, report_id)

    async def system_share_flags(self, tenant_id: int) -> dict[str, bool]:
        conn = await self._conn()
        rows = await conn.execute_query_dict(
            SYSTEM_SHARE_FLAG_SQL,
            [tenant_id, list(SYSTEM_REPORT_CODES)],
        )
        flags = {code: False for code in SYSTEM_REPORT_CODES}
        for row in rows:
            flags[row["code"]] = bool(row["is_shared"])
        return flags

    async def append_log(self, record: AccessLogRecord) -> None:
        if record.detail not in ALLOWED_DETAILS:
            raise ShareLogError("access log detail rejected")
        conn = await self._conn()
        await conn.execute_query(
            """
            INSERT INTO apps_kuaireport_share_access_logs
                (uuid, tenant_id, resource_type, resource_id, share_token,
                 action, client_ip, user_agent, success, detail)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            [
                str(uuid.uuid4()),
                record.tenant_id,
                record.resource_type,
                record.resource_id,
                record.share_token,
                record.action or "view",
                record.client_ip,
                (record.user_agent or "")[:255] or None,
                record.success,
                record.detail,
            ],
        )


class ShareService:
    def __init__(
        self,
        store: Any,
        *,
        secret: Optional[str] = None,
        execute_source: SourceExecutor = default_execute_source,
        execute_report: ReportExecutor = default_execute_report,
        preview_url: PreviewBuilder = default_preview_url,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.store = store
        self._secret = secret
        self.execute_source = execute_source
        self.execute_report = execute_report
        self.preview_url = preview_url
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def now(self) -> datetime:
        return as_utc(self.clock())

    def secret(self) -> str:
        if self._secret:
            return self._secret
        return _default_secret()

    def _hash_password(self, password: str) -> str:
        hashed = hash_password(password)
        if not hashed.startswith("$pbkdf2-sha256$") or hashed == password:
            raise ValueError("password hash rejected")
        if len(hashed) > 128:
            raise ValueError("password hash exceeds column")
        return hashed

    def _new_token(self) -> str:
        return secrets.token_urlsafe(32)[:64]

    async def save_dashboard(
        self,
        *,
        tenant_id: int,
        dashboard_id: Optional[int],
        code: Optional[str],
        name: str,
        layout_config: Any,
        widgets_config: Any,
        theme_config: Any,
        tv_config: Any,
    ) -> dict:
        if tenant_id is None:
            raise ValueError("tenant required")
        layout = _as_object(layout_config, "layout_config")
        theme = _as_object(theme_config, "theme_config")
        tv = _as_object(tv_config, "tv_config")
        widgets = validate_widgets(widgets_config)
        configs = {
            "layout_config": layout,
            "widgets_config": widgets,
            "theme_config": theme,
            "tv_config": tv,
        }

        async def _persist(conn=None):
            if dashboard_id is None:
                if not code or not str(code).strip():
                    raise ValueError("code required")
                saved = await self.store.create_dashboard(
                    tenant_id=tenant_id,
                    code=str(code).strip(),
                    name=name,
                    layout_config=layout,
                    widgets_config=widgets,
                    theme_config=theme,
                    tv_config=tv,
                )
            else:
                saved = await self.store.update_dashboard(
                    tenant_id=tenant_id,
                    dashboard_id=dashboard_id,
                    name=name,
                    layout_config=layout,
                    widgets_config=widgets,
                    theme_config=theme,
                    tv_config=tv,
                )
                if saved is None:
                    raise LookupError("dashboard not found")
            version_no = int(getattr(saved, "current_version", 0) or 0)
            if conn is not None and version_no >= 1:
                from apps.kuaireport.slices.s149_distribution import (
                    TortoiseDistributionStore,
                    append_dashboard_version,
                )

                await append_dashboard_version(
                    TortoiseDistributionStore(conn),
                    tenant_id,
                    int(saved.id),
                    configs,
                    version_no=version_no,
                )
            return saved

        runner = getattr(self.store, "run_in_transaction", None)
        if runner is not None:
            row = await runner(_persist)
        else:
            row = await _persist(None)
        return self._dashboard_public(row)

    async def preview_dashboard(self, *, tenant_id: int, dashboard_id: int) -> dict:
        row = await self.store.get_dashboard(tenant_id, dashboard_id)
        if row is None:
            raise LookupError("dashboard not found")
        body = await self._dashboard_payload(row)
        body["id"] = row.id
        body["code"] = row.code
        body["status"] = row.status
        return scrub(body)

    async def enable_dashboard_share(
        self,
        *,
        tenant_id: int,
        dashboard_id: int,
        expires_at: datetime,
        password: str,
        allow_ip_cidrs: Any,
    ) -> dict:
        hashed = self._hash_password(password)
        token = self._new_token()
        row = await self.store.set_dashboard_share(
            tenant_id=tenant_id,
            dashboard_id=dashboard_id,
            share_token=token,
            share_expires_at=as_utc(expires_at),
            share_password_hash=hashed,
            share_allow_ip_cidrs=allow_ip_cidrs,
        )
        if row is None:
            raise LookupError("dashboard not found")
        return {
            "is_shared": True,
            "share_path": f"/apps/kuaireport/dashboards/shared?token={token}",
            "expires_at": as_utc(expires_at).isoformat(),
        }

    async def enable_report_share(
        self,
        *,
        tenant_id: int,
        report_id: int,
        expires_at: datetime,
        password: str,
        allow_ip_cidrs: Any,
    ) -> dict:
        hashed = self._hash_password(password)
        token = self._new_token()
        row = await self.store.set_report_share(
            tenant_id=tenant_id,
            report_id=report_id,
            share_token=token,
            share_expires_at=as_utc(expires_at),
            share_password_hash=hashed,
            share_allow_ip_cidrs=allow_ip_cidrs,
        )
        if row is None:
            raise LookupError("report not found")
        return {
            "is_shared": True,
            "share_path": f"/apps/kuaireport/reports/shared?token={token}",
            "expires_at": as_utc(expires_at).isoformat(),
        }

    async def system_share_flags(self, tenant_id: int) -> dict[str, bool]:
        return await self.store.system_share_flags(tenant_id)

    async def open_dashboard(
        self,
        *,
        share_token: str,
        password: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
        unlock_cookie: Optional[str],
    ) -> tuple[str, Optional[dict], Optional[str]]:
        row = await self.store.find_dashboard_by_token(share_token)
        if row is None:
            return "missing", None, None
        return await self._open_resource(
            resource_type="dashboard",
            resource_id=row.id,
            tenant_id=row.tenant_id,
            share_token=share_token,
            is_shared=row.is_shared,
            share_expires_at=row.share_expires_at,
            share_password_hash=row.share_password_hash,
            share_allow_ip_cidrs=row.share_allow_ip_cidrs,
            password=password,
            client_ip=client_ip,
            user_agent=user_agent,
            unlock_cookie=unlock_cookie,
            build=lambda: self._dashboard_payload(row),
        )

    async def open_report(
        self,
        *,
        share_token: str,
        password: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
        unlock_cookie: Optional[str],
    ) -> tuple[str, Optional[dict], Optional[str]]:
        row = await self.store.find_report_by_token(share_token)
        if row is None:
            return "missing", None, None
        return await self._open_resource(
            resource_type="report",
            resource_id=row.id,
            tenant_id=row.tenant_id,
            share_token=share_token,
            is_shared=row.is_shared,
            share_expires_at=row.share_expires_at,
            share_password_hash=row.share_password_hash,
            share_allow_ip_cidrs=row.share_allow_ip_cidrs,
            password=password,
            client_ip=client_ip,
            user_agent=user_agent,
            unlock_cookie=unlock_cookie,
            build=lambda: self._report_payload(row),
        )

    async def open_file_preview(
        self,
        *,
        share_token: str,
        file_uuid: str,
        size: Optional[int],
        password: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
        unlock_cookie: Optional[str],
    ) -> tuple[str, dict, Optional[str]]:
        row = await self.store.find_dashboard_by_token(share_token)
        if row is None:
            return "missing", {"success": False, "message": "missing"}, None

        async def build() -> dict:
            preview = await self.preview_url(file_uuid, row.tenant_id, size)
            if not preview:
                raise RuntimeError("preview unavailable")
            return {"success": True, "preview_url": preview}

        status, payload, cookie = await self._open_resource(
            resource_type="dashboard",
            resource_id=row.id,
            tenant_id=row.tenant_id,
            share_token=share_token,
            is_shared=row.is_shared,
            share_expires_at=row.share_expires_at,
            share_password_hash=row.share_password_hash,
            share_allow_ip_cidrs=row.share_allow_ip_cidrs,
            password=password,
            client_ip=client_ip,
            user_agent=user_agent,
            unlock_cookie=unlock_cookie,
            build=build,
        )
        if status != "ok":
            reason = status if status in ALLOWED_DETAILS else DETAIL_PASSWORD
            return status, {"success": False, "message": reason}, None
        return status, payload or {"success": False, "message": DETAIL_DATA}, cookie

    async def _open_resource(
        self,
        *,
        resource_type: str,
        resource_id: int,
        tenant_id: int,
        share_token: str,
        is_shared: bool,
        share_expires_at: Optional[datetime],
        share_password_hash: Optional[str],
        share_allow_ip_cidrs: Any,
        password: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
        unlock_cookie: Optional[str],
        build: Callable[[], Awaitable[dict]],
    ) -> tuple[str, Optional[dict], Optional[str]]:
        supplied = (password or "").strip()
        unlock_ok = False if supplied else unlock_matches(
            unlock_cookie, share_token, self.secret()
        )
        ok, reason = evaluate_share(
            is_shared=is_shared,
            share_expires_at=share_expires_at,
            share_password_hash=share_password_hash,
            share_allow_ip_cidrs=share_allow_ip_cidrs,
            password=supplied or None,
            client_ip=client_ip,
            now=self.now(),
            unlock_ok=unlock_ok,
        )
        payload = None
        if ok:
            try:
                payload = scrub(await build())
            except Exception:
                ok = False
                reason = DETAIL_DATA
                payload = None
        if reason not in ALLOWED_DETAILS:
            reason = DETAIL_DATA if not ok else DETAIL_OK
        await self._write_log(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            share_token=share_token,
            client_ip=client_ip,
            user_agent=user_agent,
            success=ok,
            detail=reason,
        )
        cookie = None
        if ok and supplied:
            cookie = issue_unlock(share_token, self.secret(), self.now())
        if not ok:
            return reason, None, None
        return "ok", payload, cookie

    async def _write_log(
        self,
        *,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        share_token: str,
        client_ip: Optional[str],
        user_agent: Optional[str],
        success: bool,
        detail: str,
    ) -> None:
        if detail not in ALLOWED_DETAILS:
            detail = DETAIL_DATA
        record = AccessLogRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            share_token=share_token,
            action="view",
            client_ip=client_ip,
            success=success,
            detail=detail,
            user_agent=(user_agent or "")[:255] or None,
        )
        try:
            await self.store.append_log(record)
        except ShareLogError:
            raise
        except Exception as exc:
            raise ShareLogError("access log write failed") from exc

    async def _dashboard_payload(self, row: DashboardRecord) -> dict:
        rendered = []
        for widget in row.widgets_config or []:
            item = dict(widget)
            if widget.get("type") in DATA_WIDGET_TYPES:
                raw = await self.execute_source(row.tenant_id, int(widget["data_source_id"]))
                item["result"] = _shape_result(raw)
            rendered.append(item)
        return {
            "name": row.name,
            "layout_config": row.layout_config,
            "widgets_config": rendered,
            "theme_config": row.theme_config,
            "tv_config": row.tv_config,
        }

    async def _report_payload(self, row: ReportRecord) -> dict:
        result = _shape_result(
            await self.execute_report(row.tenant_id, row.id, row.report_config)
        )
        return {
            "name": row.name,
            "code": row.code,
            "data": result["data"],
            "total": result["total"],
            "summary": result["summary"],
        }

    def _dashboard_public(self, row: DashboardRecord) -> dict:
        return scrub(
            {
                "id": row.id,
                "uuid": row.uuid,
                "code": row.code,
                "name": row.name,
                "status": row.status,
                "layout_config": row.layout_config,
                "widgets_config": row.widgets_config,
                "theme_config": row.theme_config,
                "tv_config": row.tv_config,
                "is_shared": row.is_shared,
            }
        )


def _parse_expires(value: Any) -> datetime:
    if isinstance(value, datetime):
        return as_utc(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expires_at required")
    text = value.strip().replace("Z", "+00:00")
    return as_utc(datetime.fromisoformat(text))


def _share_body(body: Any) -> tuple[datetime, str, Any]:
    if not isinstance(body, dict):
        raise ValueError("invalid body")
    password = body.get("password")
    if not isinstance(password, str) or not password:
        raise ValueError("password required")
    expires_at = _parse_expires(body.get("expires_at"))
    allow = body.get("allow_ip_cidrs")
    if allow is not None and not isinstance(allow, list):
        raise ValueError("allow_ip_cidrs must be a list")
    return expires_at, password, allow


def _dashboard_body(body: Any) -> dict:
    if not isinstance(body, dict):
        raise ValueError("invalid body")
    return {key: value for key, value in body.items() if key not in SECRET_KEYS}


def _set_unlock_cookie(response: Response, token: Optional[str], request: Request) -> None:
    if not token:
        return
    response.set_cookie(
        UNLOCK_COOKIE,
        token,
        max_age=int(UNLOCK_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/api/v1/apps/kuaireport",
    )


def _log_unavailable() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "access log unavailable"})


def create_router(service: ShareService) -> APIRouter:
    router = APIRouter(tags=["kuaireport-148"])

    def _tenant_of(user: Any) -> int:
        tenant_id = getattr(user, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=403, detail="tenant required")
        return int(tenant_id)

    @router.post("/dashboards")
    async def create_dashboard(
        request: Request,
        user: Any = Depends(get_current_user),
    ):
        body = _dashboard_body(await _read_json(request))
        try:
            return await service.save_dashboard(
                tenant_id=_tenant_of(user),
                dashboard_id=None,
                code=body.get("code"),
                name=str(body.get("name") or ""),
                layout_config=body.get("layout_config"),
                widgets_config=body.get("widgets_config"),
                theme_config=body.get("theme_config"),
                tv_config=body.get("tv_config"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/dashboards/{dashboard_id}")
    async def update_dashboard(
        dashboard_id: int,
        request: Request,
        user: Any = Depends(get_current_user),
    ):
        body = _dashboard_body(await _read_json(request))
        try:
            return await service.save_dashboard(
                tenant_id=_tenant_of(user),
                dashboard_id=dashboard_id,
                code=None,
                name=str(body.get("name") or ""),
                layout_config=body.get("layout_config"),
                widgets_config=body.get("widgets_config"),
                theme_config=body.get("theme_config"),
                tv_config=body.get("tv_config"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="dashboard not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/dashboards/{dashboard_id}/preview")
    async def preview_dashboard(
        dashboard_id: int,
        user: Any = Depends(get_current_user),
    ):
        try:
            return await service.preview_dashboard(
                tenant_id=_tenant_of(user),
                dashboard_id=dashboard_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="dashboard not found") from exc

    @router.post("/dashboards/{dashboard_id}/share")
    async def share_dashboard(
        dashboard_id: int,
        request: Request,
        user: Any = Depends(get_current_user),
    ):
        try:
            expires_at, password, allow = _share_body(await _read_json(request))
            return await service.enable_dashboard_share(
                tenant_id=_tenant_of(user),
                dashboard_id=dashboard_id,
                expires_at=expires_at,
                password=password,
                allow_ip_cidrs=allow,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="dashboard not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/reports/{report_id}/share")
    async def share_report(
        report_id: int,
        request: Request,
        user: Any = Depends(get_current_user),
    ):
        try:
            expires_at, password, allow = _share_body(await _read_json(request))
            return await service.enable_report_share(
                tenant_id=_tenant_of(user),
                report_id=report_id,
                expires_at=expires_at,
                password=password,
                allow_ip_cidrs=allow,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="report not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/dashboards/shared")
    async def open_shared_dashboard(
        request: Request,
        response: Response,
        token: str = Query(...),
        share_password: Optional[str] = Header(default=None, alias=PASSWORD_HEADER),
        unlock_cookie: Optional[str] = Cookie(default=None, alias=UNLOCK_COOKIE),
    ):
        try:
            opened = await service.open_dashboard(
                share_token=token,
                password=share_password,
                client_ip=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                unlock_cookie=unlock_cookie,
            )
        except ShareLogError:
            return _log_unavailable()
        return _finish_open(request, response, opened)

    @router.get("/dashboards/shared/file-preview")
    async def shared_file_preview(
        request: Request,
        response: Response,
        token: str = Query(...),
        uuid: str = Query(...),
        size: Optional[int] = Query(default=None),
        share_password: Optional[str] = Header(default=None, alias=PASSWORD_HEADER),
        unlock_cookie: Optional[str] = Cookie(default=None, alias=UNLOCK_COOKIE),
    ):
        try:
            status, payload, cookie = await service.open_file_preview(
                share_token=token,
                file_uuid=uuid,
                size=size,
                password=share_password,
                client_ip=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                unlock_cookie=unlock_cookie,
            )
        except ShareLogError:
            return _log_unavailable()
        if status == "missing":
            return {"success": False, "message": "missing"}
        if isinstance(payload, dict) and payload.get("success") and cookie:
            _set_unlock_cookie(response, cookie, request)
        return payload

    @router.get("/reports/shared")
    async def open_shared_report(
        request: Request,
        response: Response,
        token: str = Query(...),
        share_password: Optional[str] = Header(default=None, alias=PASSWORD_HEADER),
        unlock_cookie: Optional[str] = Cookie(default=None, alias=UNLOCK_COOKIE),
    ):
        try:
            opened = await service.open_report(
                share_token=token,
                password=share_password,
                client_ip=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                unlock_cookie=unlock_cookie,
            )
        except ShareLogError:
            return _log_unavailable()
        return _finish_open(request, response, opened)

    return router


async def _read_json(request: Request) -> Any:
    try:
        return await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc


def _finish_open(request: Request, response: Response, result: tuple[str, Optional[dict], Optional[str]]):
    status, payload, cookie = result
    if status == "missing":
        raise HTTPException(status_code=404, detail="share not found")
    if status != "ok":
        denied = status if status in ALLOWED_DETAILS else DETAIL_PASSWORD
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SHARE_ACCESS_DENIED",
                "reason": denied,
                "requires_password": denied == DETAIL_PASSWORD,
            },
        )
    _set_unlock_cookie(response, cookie, request)
    return payload or {}


router = create_router(ShareService(SqlShareStore()))
