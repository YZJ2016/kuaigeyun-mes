"""星报表分发余项：角色授权、订阅登记、版本回看与恢复。

路由对象 `router` 留给应用入口 include。本文件不挂免登录分享，不写访问日志。
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pydantic import ValidationError as ModelValidationError

from apps.kuaireport.services.subscription_service import TASK_TYPE, public_error
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant, get_current_user
from core.schemas.scheduled_task import ScheduledTaskCreate
from core.services.scheduling.scheduled_task_service import ScheduledTaskService
from infra.exceptions.exceptions import RiverEdgeException
from infra.models.user import User

RESOURCE_REPORT = "report"
RESOURCE_DASHBOARD = "dashboard"
RESOURCE_TYPES = (RESOURCE_REPORT, RESOURCE_DASHBOARD)
DASHBOARD_CONFIG_KEYS = (
    "layout_config",
    "widgets_config",
    "theme_config",
    "tv_config",
)
DEFAULT_CRON = "0 8 * * 1-5"
DEFAULT_PERMISSION = "view"
ALLOWED_PERMISSIONS = frozenset({DEFAULT_PERMISSION})

router = APIRouter(prefix="/distribution", tags=["kuaireport-distribution"])


class DistributionError(Exception):
    status_code = 422

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class DistributionNotFoundError(DistributionError):
    """资源不存在：经 _raise_http 映射为 404。"""

    status_code = 404


def _load_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _report_config_from_snapshot(snapshot: Any) -> dict[str, Any]:
    """账表快照就是当时的 report_config，不包 report_config 键。"""
    data = _load_json(snapshot)
    if not isinstance(data, dict):
        raise DistributionError("版本快照不是账表配置")
    return {key: value for key, value in data.items() if key != "data_source_id"}


def _dashboard_configs_from_snapshot(snapshot: Any) -> dict[str, Any]:
    data = _load_json(snapshot)
    if not isinstance(data, dict) or any(key not in data for key in DASHBOARD_CONFIG_KEYS):
        raise DistributionError("版本快照缺少大屏配置")
    return {key: data[key] for key in DASHBOARD_CONFIG_KEYS}


def _dashboard_snapshot(configs: dict[str, Any]) -> dict[str, Any]:
    return {key: configs.get(key) for key in DASHBOARD_CONFIG_KEYS}


class TortoiseDistributionStore:
    """直接读写迁移 92 / 563 已有表，不另注册一套模型。"""

    def __init__(self, conn: Any = None) -> None:
        self.conn = conn

    async def _connection(self) -> Any:
        if self.conn is not None:
            return self.conn
        from tortoise import Tortoise

        return Tortoise.get_connection("default")

    @asynccontextmanager
    async def transaction(self):
        if self.conn is not None:
            yield self
            return
        from tortoise.transactions import in_transaction

        async with in_transaction() as conn:
            yield TortoiseDistributionStore(conn)

    async def _select(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        conn = await self._connection()
        rows = await conn.execute_query_dict(sql, params)
        return list(rows or [])

    async def _execute(self, sql: str, params: list[Any]) -> None:
        conn = await self._connection()
        await conn.execute_query(sql, params)

    def _lock(self, sql: str) -> str:
        if self.conn is None:
            return sql
        return sql + " FOR UPDATE"

    async def get_report(self, tenant_id: int, report_id: int) -> dict[str, Any] | None:
        sql = self._lock(
            """
            SELECT id, tenant_id, report_config, current_version
            FROM apps_kuaireport_reports
            WHERE id = $1 AND tenant_id = $2
            """
        )
        rows = await self._select(sql, [report_id, tenant_id])
        return rows[0] if rows else None

    async def get_dashboard(self, tenant_id: int, dashboard_id: int) -> dict[str, Any] | None:
        sql = self._lock(
            """
            SELECT id, tenant_id, layout_config, widgets_config, theme_config,
                   tv_config, current_version
            FROM apps_kuaireport_dashboards
            WHERE id = $1 AND tenant_id = $2
            """
        )
        rows = await self._select(sql, [dashboard_id, tenant_id])
        return rows[0] if rows else None

    async def role_in_tenant(self, tenant_id: int, role_id: int) -> bool:
        rows = await self._select(
            """
            SELECT id FROM core_roles
            WHERE id = $1 AND tenant_id = $2 AND deleted_at IS NULL
            """,
            [role_id, tenant_id],
        )
        return bool(rows)

    async def insert_grant(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        role_id: int,
        permission: str,
        created_by: int | None,
    ) -> dict[str, Any]:
        try:
            rows = await self._select(
                """
                INSERT INTO apps_kuaireport_share_grants
                    (uuid, tenant_id, resource_type, resource_id, role_id, permission, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, uuid, tenant_id, resource_type, resource_id, role_id, permission
                """,
                [
                    str(uuid.uuid4()),
                    tenant_id,
                    resource_type,
                    resource_id,
                    role_id,
                    permission,
                    created_by,
                ],
            )
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505" or "unique" in str(exc).lower():
                raise DistributionError("授权已存在") from None
            raise
        return rows[0]

    async def list_grants(
        self, tenant_id: int, resource_type: str, resource_id: int
    ) -> list[dict[str, Any]]:
        return await self._select(
            """
            SELECT id, resource_type, resource_id, role_id, permission
            FROM apps_kuaireport_share_grants
            WHERE tenant_id = $1 AND resource_type = $2 AND resource_id = $3
            ORDER BY id
            """,
            [tenant_id, resource_type, resource_id],
        )

    async def user_role_ids(self, tenant_id: int, user_id: int) -> list[int]:
        rows = await self._select(
            """
            SELECT ur.role_id
            FROM core_user_roles ur
            JOIN core_users u ON u.id = ur.user_id
            JOIN core_roles r ON r.id = ur.role_id
            WHERE u.id = $1 AND u.tenant_id = $2 AND u.deleted_at IS NULL
              AND r.tenant_id = $2 AND r.deleted_at IS NULL
            """,
            [user_id, tenant_id],
        )
        return [int(row["role_id"]) for row in rows]

    async def has_grant(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        role_ids: list[int],
        permission: str,
    ) -> bool:
        if not role_ids:
            return False
        placeholders = ", ".join(f"${index}" for index in range(5, 5 + len(role_ids)))
        rows = await self._select(
            f"""
            SELECT id FROM apps_kuaireport_share_grants
            WHERE tenant_id = $1 AND resource_type = $2 AND resource_id = $3
              AND permission = $4 AND role_id IN ({placeholders})
            LIMIT 1
            """,
            [tenant_id, resource_type, resource_id, permission, *role_ids],
        )
        return bool(rows)

    async def users_in_tenant(self, tenant_id: int, user_ids: list[int]) -> set[int]:
        if not user_ids:
            return set()
        placeholders = ", ".join(f"${index}" for index in range(2, 2 + len(user_ids)))
        rows = await self._select(
            f"""
            SELECT id FROM core_users
            WHERE tenant_id = $1 AND deleted_at IS NULL AND id IN ({placeholders})
            """,
            [tenant_id, *user_ids],
        )
        return {int(row["id"]) for row in rows}

    async def insert_subscription(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self._select(
            """
            INSERT INTO apps_kuaireport_report_subscriptions (
                uuid, tenant_id, report_id, name, cron, channel,
                recipient_user_ids, recipient_emails, filters, attach_excel,
                is_active, scheduled_task_uuid
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7::jsonb, '[]'::jsonb, $8::jsonb, $9,
                $10, NULL
            )
            RETURNING id, name, channel, report_id, scheduled_task_uuid, attach_excel
            """,
            [
                str(uuid.uuid4()),
                row["tenant_id"],
                row["report_id"],
                row["name"],
                row["cron"],
                row["channel"],
                _dump_json(row["recipient_user_ids"]),
                _dump_json(row.get("filters")),
                bool(row["attach_excel"]),
                bool(row["is_active"]),
            ],
        )
        return rows[0]

    async def set_subscription_task_uuid(
        self, tenant_id: int, subscription_id: int, task_uuid: str
    ) -> None:
        await self._execute(
            """
            UPDATE apps_kuaireport_report_subscriptions
            SET scheduled_task_uuid = $3, updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = $1 AND id = $2
            """,
            [tenant_id, subscription_id, task_uuid],
        )

    async def get_subscription(self, tenant_id: int, subscription_id: int) -> dict[str, Any] | None:
        rows = await self._select(
            """
            SELECT id, tenant_id, report_id, name, cron, channel, recipient_user_ids,
                   filters, attach_excel, is_active, scheduled_task_uuid,
                   last_run_at, last_run_status, last_run_error
            FROM apps_kuaireport_report_subscriptions
            WHERE tenant_id = $1 AND id = $2
            """,
            [tenant_id, subscription_id],
        )
        return rows[0] if rows else None

    async def mark_run(
        self, tenant_id: int, subscription_id: int, status: str, error: str | None
    ) -> None:
        await self._execute(
            """
            UPDATE apps_kuaireport_report_subscriptions
            SET last_run_at = CURRENT_TIMESTAMP,
                last_run_status = $3,
                last_run_error = $4,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = $1 AND id = $2
            """,
            [tenant_id, subscription_id, status, error],
        )

    async def list_report_versions(self, tenant_id: int, report_id: int) -> list[dict[str, Any]]:
        return await self._select(
            """
            SELECT id, version_no, snapshot, note, created_at
            FROM apps_kuaireport_report_versions
            WHERE tenant_id = $1 AND report_id = $2
            ORDER BY version_no DESC
            """,
            [tenant_id, report_id],
        )

    async def get_report_version(
        self, tenant_id: int, report_id: int, version_no: int
    ) -> dict[str, Any] | None:
        rows = await self._select(
            """
            SELECT id, version_no, snapshot, note
            FROM apps_kuaireport_report_versions
            WHERE tenant_id = $1 AND report_id = $2 AND version_no = $3
            """,
            [tenant_id, report_id, version_no],
        )
        return rows[0] if rows else None

    async def update_report_restored(
        self, tenant_id: int, report_id: int, report_config: Any, current_version: int
    ) -> None:
        await self._execute(
            """
            UPDATE apps_kuaireport_reports
            SET report_config = $3::jsonb, current_version = $4, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND tenant_id = $2
            """,
            [report_id, tenant_id, _dump_json(report_config), current_version],
        )

    async def insert_report_version(
        self,
        tenant_id: int,
        report_id: int,
        version_no: int,
        snapshot: dict[str, Any],
        note: str | None,
        user_id: int | None,
    ) -> dict[str, Any]:
        rows = await self._select(
            """
            INSERT INTO apps_kuaireport_report_versions
                (uuid, tenant_id, report_id, version_no, snapshot, note, created_by_user_id)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            RETURNING id, version_no, snapshot, note
            """,
            [
                str(uuid.uuid4()),
                tenant_id,
                report_id,
                version_no,
                _dump_json(snapshot),
                note,
                user_id,
            ],
        )
        return rows[0]

    async def list_dashboards_without_versions(self, tenant_id: int) -> list[dict[str, Any]]:
        return await self._select(
            """
            SELECT d.id, d.tenant_id, d.layout_config, d.widgets_config,
                   d.theme_config, d.tv_config, d.current_version
            FROM apps_kuaireport_dashboards d
            WHERE d.tenant_id = $1
              AND NOT EXISTS (
                SELECT 1 FROM apps_kuaireport_dashboard_versions v
                WHERE v.tenant_id = d.tenant_id AND v.dashboard_id = d.id
              )
            ORDER BY d.id
            """,
            [tenant_id],
        )

    async def dashboard_version_count(self, tenant_id: int, dashboard_id: int) -> int:
        rows = await self._select(
            """
            SELECT COUNT(*) AS total
            FROM apps_kuaireport_dashboard_versions
            WHERE tenant_id = $1 AND dashboard_id = $2
            """,
            [tenant_id, dashboard_id],
        )
        return int(rows[0]["total"]) if rows else 0

    async def update_dashboard_saved(
        self,
        tenant_id: int,
        dashboard_id: int,
        configs: dict[str, Any],
        current_version: int,
    ) -> None:
        await self._execute(
            """
            UPDATE apps_kuaireport_dashboards
            SET layout_config = $3::jsonb,
                widgets_config = $4::jsonb,
                theme_config = $5::jsonb,
                tv_config = $6::jsonb,
                current_version = $7,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND tenant_id = $2
            """,
            [
                dashboard_id,
                tenant_id,
                _dump_json(configs.get("layout_config")),
                _dump_json(configs.get("widgets_config")),
                _dump_json(configs.get("theme_config")),
                _dump_json(configs.get("tv_config")),
                current_version,
            ],
        )

    async def insert_dashboard_version(
        self,
        tenant_id: int,
        dashboard_id: int,
        version_no: int,
        snapshot: dict[str, Any],
        note: str | None,
        user_id: int | None,
    ) -> dict[str, Any]:
        rows = await self._select(
            """
            INSERT INTO apps_kuaireport_dashboard_versions
                (uuid, tenant_id, dashboard_id, version_no, snapshot, note, created_by_user_id)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            RETURNING id, version_no, snapshot, note
            """,
            [
                str(uuid.uuid4()),
                tenant_id,
                dashboard_id,
                version_no,
                _dump_json(snapshot),
                note,
                user_id,
            ],
        )
        return rows[0]

    async def registered_data_source(self, tenant_id: int, source_uuid: str) -> bool:
        rows = await self._select(
            """
            SELECT uuid FROM apps_kuaireport_data_sources
            WHERE tenant_id = $1 AND uuid = $2
            """,
            [tenant_id, source_uuid],
        )
        return bool(rows)

    async def list_dashboard_versions(
        self, tenant_id: int, dashboard_id: int
    ) -> list[dict[str, Any]]:
        return await self._select(
            """
            SELECT id, version_no, snapshot, note, created_at
            FROM apps_kuaireport_dashboard_versions
            WHERE tenant_id = $1 AND dashboard_id = $2
            ORDER BY version_no DESC
            """,
            [tenant_id, dashboard_id],
        )

    async def get_dashboard_version(
        self, tenant_id: int, dashboard_id: int, version_no: int
    ) -> dict[str, Any] | None:
        rows = await self._select(
            """
            SELECT id, version_no, snapshot, note
            FROM apps_kuaireport_dashboard_versions
            WHERE tenant_id = $1 AND dashboard_id = $2 AND version_no = $3
            """,
            [tenant_id, dashboard_id, version_no],
        )
        return rows[0] if rows else None


async def _require_bound_source(store: Any, tenant_id: int, config: dict[str, Any]) -> None:
    extra = config.get("extra")
    if not isinstance(extra, dict) or "data_source_uuid" not in extra:
        return
    raw = extra.get("data_source_uuid")
    if raw is None:
        return
    if not isinstance(raw, str) or not raw.strip():
        raise DistributionError("报表未绑定数据源")
    if not await store.registered_data_source(tenant_id, raw.strip()):
        raise DistributionNotFoundError("数据源不存在")


async def append_dashboard_version(
    store: Any,
    tenant_id: int,
    dashboard_id: int,
    configs: dict[str, Any],
    version_no: int,
    user_id: int | None = None,
    note: str = "save",
) -> dict[str, Any]:
    """新插入一条大屏版本，不更新已有行。"""
    return await store.insert_dashboard_version(
        tenant_id,
        int(dashboard_id),
        int(version_no),
        _dashboard_snapshot(configs),
        note,
        user_id,
    )


def _store(store: Any) -> Any:
    return store if store is not None else TortoiseDistributionStore()


def _require_resource_type(resource_type: str) -> str:
    value = str(resource_type or "").strip()
    if value not in RESOURCE_TYPES:
        raise DistributionError("资源类型无法识别")
    return value


async def _require_resource(store: Any, tenant_id: int, resource_type: str, resource_id: int) -> dict:
    if resource_type == RESOURCE_REPORT:
        row = await store.get_report(tenant_id, resource_id)
    else:
        row = await store.get_dashboard(tenant_id, resource_id)
    if row is None:
        raise DistributionNotFoundError("资源不存在")
    return row


async def grant_share(
    tenant_id: int,
    resource_type: str,
    resource_id: int,
    role_id: int,
    permission: str = DEFAULT_PERMISSION,
    created_by: int | None = None,
    store: Any = None,
) -> dict[str, Any]:
    store = _store(store)
    kind = _require_resource_type(resource_type)
    await _require_resource(store, tenant_id, kind, int(resource_id))
    if not await store.role_in_tenant(tenant_id, int(role_id)):
        raise DistributionNotFoundError("角色不存在")
    perm = (permission or DEFAULT_PERMISSION).strip() or DEFAULT_PERMISSION
    if perm not in ALLOWED_PERMISSIONS:
        raise DistributionError("权限只允许 view")
    if len(perm) > 20:
        raise DistributionError("权限名过长")
    return await store.insert_grant(
        tenant_id, kind, int(resource_id), int(role_id), perm, created_by
    )


async def can_view_by_grant(
    tenant_id: int,
    user_id: int,
    resource_type: str,
    resource_id: int,
    store: Any = None,
) -> bool:
    """只看 share_grants 与用户角色。不读分享口令、过期、白名单或访问日志。"""
    store = _store(store)
    kind = _require_resource_type(resource_type)
    if await store.get_report(tenant_id, int(resource_id)) is None and kind == RESOURCE_REPORT:
        return False
    if kind == RESOURCE_DASHBOARD and await store.get_dashboard(tenant_id, int(resource_id)) is None:
        return False
    role_ids = await store.user_role_ids(tenant_id, int(user_id))
    return await store.has_grant(
        tenant_id, kind, int(resource_id), role_ids, DEFAULT_PERMISSION
    )


async def list_grants(
    tenant_id: int, resource_type: str, resource_id: int, store: Any = None
) -> list[dict[str, Any]]:
    store = _store(store)
    kind = _require_resource_type(resource_type)
    await _require_resource(store, tenant_id, kind, int(resource_id))
    return await store.list_grants(tenant_id, kind, int(resource_id))


async def _default_create_task(
    tenant_id: int, fields: dict[str, Any], using_db: Any = None
) -> Any:
    data = ScheduledTaskCreate(**fields)
    return await ScheduledTaskService.create_scheduled_task(
        tenant_id, data, using_db=using_db
    )


async def create_subscription(
    tenant_id: int,
    report_id: int,
    name: str,
    recipient_user_ids: list[int],
    cron: str = DEFAULT_CRON,
    channel: str = "inbox",
    filters: dict[str, Any] | None = None,
    attach_excel: bool = True,
    is_active: bool = True,
    store: Any = None,
    create_task: Any = None,
) -> dict[str, Any]:
    title = str(name or "").strip()
    if not title:
        raise DistributionError("订阅名称不能为空")
    if len(title) > 100:
        raise DistributionError("订阅名称超过 100 字")
    if str(channel or "inbox") != "inbox":
        raise DistributionError("本切片只发送站内信")
    cron_text = str(cron or DEFAULT_CRON).strip() or DEFAULT_CRON
    if len(cron_text) > 64:
        raise DistributionError("cron 过长")
    user_ids = [int(item) for item in recipient_user_ids]
    if not user_ids:
        raise DistributionError("没有接收人")

    store = _store(store)
    async with store.transaction() as tx:
        report = await tx.get_report(tenant_id, int(report_id))
        if report is None:
            raise DistributionNotFoundError("报表不存在")
        found = await tx.users_in_tenant(tenant_id, user_ids)
        if set(user_ids) != set(found):
            raise DistributionError("接收人不是本组织用户")
        created = await tx.insert_subscription(
            {
                "tenant_id": tenant_id,
                "report_id": int(report_id),
                "name": title,
                "cron": cron_text,
                "channel": "inbox",
                "recipient_user_ids": user_ids,
                "filters": filters,
                "attach_excel": bool(attach_excel),
                "is_active": bool(is_active),
            }
        )
        subscription_id = int(created["id"])
        task_fields = {
            "name": title[:100],
            "code": f"krps{subscription_id}"[:50],
            "type": TASK_TYPE,
            "trigger_type": "cron",
            "trigger_config": {"cron": cron_text},
            "task_config": {"subscription_id": subscription_id},
            "is_active": bool(is_active),
        }
        if create_task is not None:
            task = await create_task(tenant_id, task_fields)
        else:
            # 定时任务与订阅行同一事务：回写失败时任务一并回滚，不留孤儿任务
            task = await _default_create_task(
                tenant_id, task_fields, using_db=getattr(tx, "conn", None)
            )
        task_uuid = str(getattr(task, "uuid", "") or "")
        if not task_uuid:
            raise DistributionError("定时任务未生成", status_code=500)
        await tx.set_subscription_task_uuid(tenant_id, subscription_id, task_uuid)
        saved = await tx.get_subscription(tenant_id, subscription_id)
    if saved is None or not saved.get("scheduled_task_uuid") or not saved.get("name"):
        raise DistributionError("订阅未写入", status_code=500)
    return saved


async def list_report_versions(
    tenant_id: int, report_id: int, store: Any = None
) -> list[dict[str, Any]]:
    store = _store(store)
    if await store.get_report(tenant_id, int(report_id)) is None:
        raise DistributionNotFoundError("报表不存在")
    return await store.list_report_versions(tenant_id, int(report_id))


async def restore_report_version(
    tenant_id: int,
    report_id: int,
    version_no: int,
    user_id: int | None = None,
    store: Any = None,
) -> dict[str, Any]:
    store = _store(store)
    async with store.transaction() as tx:
        report = await tx.get_report(tenant_id, int(report_id))
        if report is None:
            raise DistributionNotFoundError("报表不存在")
        version = await tx.get_report_version(tenant_id, int(report_id), int(version_no))
        if version is None:
            raise DistributionNotFoundError("版本不存在")
        config = _report_config_from_snapshot(version["snapshot"])
        await _require_bound_source(tx, tenant_id, config)
        new_no = int(report.get("current_version") or 0) + 1
        await tx.update_report_restored(tenant_id, int(report_id), config, new_no)
        await tx.insert_report_version(
            tenant_id,
            int(report_id),
            new_no,
            config,
            "restore",
            user_id,
        )
        restored = await tx.get_report(tenant_id, int(report_id))
    return {
        "report_id": int(report_id),
        "report_config": _load_json(restored["report_config"]) if restored else config,
        "current_version": new_no,
        "restored_from": int(version_no),
    }


async def backfill_dashboard_versions(
    tenant_id: int, user_id: int | None = None, store: Any = None
) -> dict[str, Any]:
    """只为还没有快照的大屏补一条。已有快照的不覆盖。"""
    store = _store(store)
    pending = await store.list_dashboards_without_versions(tenant_id)
    created: list[int] = []
    for row in pending:
        dashboard_id = int(row["id"])
        async with store.transaction() as tx:
            if await tx.dashboard_version_count(tenant_id, dashboard_id) > 0:
                continue
            current = int(row.get("current_version") or 0)
            version_no = current if current > 0 else 1
            configs = _dashboard_snapshot(row)
            await tx.insert_dashboard_version(
                tenant_id,
                dashboard_id,
                version_no,
                configs,
                "backfill",
                user_id,
            )
            if current < version_no:
                await tx.update_dashboard_saved(tenant_id, dashboard_id, configs, version_no)
            created.append(dashboard_id)
    return {"dashboard_ids": created}


async def save_dashboard(
    tenant_id: int,
    dashboard_id: int,
    configs: dict[str, Any],
    user_id: int | None = None,
    store: Any = None,
) -> dict[str, Any]:
    """本切片的大屏保存：更新四段配置，并新插入一条快照。"""
    store = _store(store)
    snapshot = _dashboard_snapshot(configs)
    async with store.transaction() as tx:
        row = await tx.get_dashboard(tenant_id, int(dashboard_id))
        if row is None:
            raise DistributionNotFoundError("大屏不存在")
        new_no = int(row.get("current_version") or 0) + 1
        await tx.update_dashboard_saved(tenant_id, int(dashboard_id), snapshot, new_no)
        await tx.insert_dashboard_version(
            tenant_id, int(dashboard_id), new_no, snapshot, "save", user_id
        )
    return {"dashboard_id": int(dashboard_id), "current_version": new_no, "snapshot": snapshot}


async def list_dashboard_versions(
    tenant_id: int, dashboard_id: int, store: Any = None
) -> list[dict[str, Any]]:
    store = _store(store)
    if await store.get_dashboard(tenant_id, int(dashboard_id)) is None:
        raise DistributionNotFoundError("大屏不存在")
    return await store.list_dashboard_versions(tenant_id, int(dashboard_id))


async def restore_dashboard_version(
    tenant_id: int,
    dashboard_id: int,
    version_no: int,
    user_id: int | None = None,
    store: Any = None,
) -> dict[str, Any]:
    store = _store(store)
    async with store.transaction() as tx:
        row = await tx.get_dashboard(tenant_id, int(dashboard_id))
        if row is None:
            raise DistributionNotFoundError("大屏不存在")
        version = await tx.get_dashboard_version(tenant_id, int(dashboard_id), int(version_no))
        if version is None:
            raise DistributionNotFoundError("版本不存在")
        configs = _dashboard_configs_from_snapshot(version["snapshot"])
        new_no = int(row.get("current_version") or 0) + 1
        await tx.update_dashboard_saved(tenant_id, int(dashboard_id), configs, new_no)
        await tx.insert_dashboard_version(
            tenant_id,
            int(dashboard_id),
            new_no,
            configs,
            "restore",
            user_id,
        )
        current = await tx.get_dashboard(tenant_id, int(dashboard_id))
    return {
        "dashboard_id": int(dashboard_id),
        "current_version": new_no,
        "restored_from": int(version_no),
        "configs": _dashboard_snapshot(current or configs),
    }


class GrantIn(BaseModel):
    resource_type: str
    resource_id: int
    role_id: int
    permission: str = DEFAULT_PERMISSION


class SubscriptionIn(BaseModel):
    report_id: int
    name: str = Field(..., max_length=100)
    recipient_user_ids: list[int]
    cron: str = DEFAULT_CRON
    channel: str = "inbox"
    filters: dict[str, Any] | None = None
    attach_excel: bool = True
    is_active: bool = True


class DashboardSaveIn(BaseModel):
    layout_config: Any = None
    widgets_config: Any = None
    theme_config: Any = None
    tv_config: Any = None


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc from None
    if isinstance(exc, DistributionError):
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    if isinstance(exc, RiverEdgeException):
        # NotFoundError→404、AuthorizationError→403、ValidationError/TenantError→422/400 等
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    if isinstance(exc, ModelValidationError):
        raise HTTPException(status_code=422, detail=public_error(str(exc))) from None
    raise HTTPException(status_code=500, detail="操作失败") from None


@router.post(
    "/grants",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:manage"))],
)
async def post_grant(
    body: GrantIn,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await grant_share(
            tenant_id,
            body.resource_type,
            body.resource_id,
            body.role_id,
            body.permission,
            created_by=current_user.id,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get(
    "/grants",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:display"))],
)
async def get_grants(
    resource_type: str,
    resource_id: int,
    tenant_id: int = Depends(get_current_tenant),
    _: User = Depends(get_current_user),
):
    try:
        return await list_grants(tenant_id, resource_type, resource_id)
    except Exception as exc:
        _raise_http(exc)


@router.get(
    "/grants/can-view",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:display"))],
)
async def get_can_view(
    resource_type: str,
    resource_id: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        allowed = await can_view_by_grant(
            tenant_id, current_user.id, resource_type, resource_id
        )
    except Exception as exc:
        _raise_http(exc)
    return {"allowed": allowed}


@router.post(
    "/subscriptions",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:manage"))],
)
async def post_subscription(
    body: SubscriptionIn,
    tenant_id: int = Depends(get_current_tenant),
    _: User = Depends(get_current_user),
):
    try:
        return await create_subscription(
            tenant_id,
            body.report_id,
            body.name,
            body.recipient_user_ids,
            cron=body.cron,
            channel=body.channel,
            filters=body.filters,
            attach_excel=body.attach_excel,
            is_active=body.is_active,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get(
    "/reports/{report_id}/versions",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:display"))],
)
async def get_report_versions(
    report_id: int,
    tenant_id: int = Depends(get_current_tenant),
    _: User = Depends(get_current_user),
):
    try:
        return await list_report_versions(tenant_id, report_id)
    except Exception as exc:
        _raise_http(exc)


@router.post(
    "/reports/{report_id}/versions/{version_no}/restore",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:manage"))],
)
async def post_restore_report(
    report_id: int,
    version_no: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await restore_report_version(
            tenant_id, report_id, version_no, user_id=current_user.id
        )
    except Exception as exc:
        _raise_http(exc)


@router.post(
    "/dashboards/backfill-versions",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:manage"))],
)
async def post_backfill(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await backfill_dashboard_versions(tenant_id, user_id=current_user.id)
    except Exception as exc:
        _raise_http(exc)


@router.post(
    "/dashboards/{dashboard_id}/save",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:manage"))],
)
async def post_save_dashboard(
    dashboard_id: int,
    body: DashboardSaveIn,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await save_dashboard(
            tenant_id,
            dashboard_id,
            body.model_dump(),
            user_id=current_user.id,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get(
    "/dashboards/{dashboard_id}/versions",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:display"))],
)
async def get_dashboard_versions(
    dashboard_id: int,
    tenant_id: int = Depends(get_current_tenant),
    _: User = Depends(get_current_user),
):
    try:
        return await list_dashboard_versions(tenant_id, dashboard_id)
    except Exception as exc:
        _raise_http(exc)


@router.post(
    "/dashboards/{dashboard_id}/versions/{version_no}/restore",
    dependencies=[Depends(require_permission_codes("kuaireport:distribution:manage"))],
)
async def post_restore_dashboard(
    dashboard_id: int,
    version_no: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await restore_dashboard_version(
            tenant_id, dashboard_id, version_no, user_id=current_user.id
        )
    except Exception as exc:
        _raise_http(exc)
