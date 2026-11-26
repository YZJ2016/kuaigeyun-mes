"""
租户备份恢复后配置愈合。

租户级备份跳过 ``infra_*``（含 ``infra_tenants.settings``），但会替换
``core_message_templates`` / ``core_approval_processes`` 等业务表。
结果：消息提醒规则里的 ``template_uuid`` 仍指向恢复前（或源库）模板，
整表显示「模板不存在」；COPY 显式 id 后若序列未对齐，新建审批流程会撞主键
并被误报成「代码已存在」。

恢复成功后须调用本模块：对齐序列 → 按 template_code 重绑规则 → ensure 审核绑定。
"""

from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger
from tortoise import Tortoise


async def realign_id_sequences_after_restore(
    *,
    table_names: List[str] | None = None,
) -> int:
    """将 ``{table}_id_seq`` / owned serial 对齐到 ``MAX(id)``。

    覆盖 ``pg_get_serial_sequence`` 为 NULL 但 default 仍是 nextval 的历史表。
    """
    conn = Tortoise.get_connection("default")
    if table_names is None:
        rows = await conn.execute_query_dict(
            """
            SELECT c.table_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.column_name = 'id'
              AND c.column_default LIKE 'nextval(%'
            ORDER BY c.table_name
            """
        )
        table_names = [
            str(r["table_name"])
            for r in (rows or [])
            if r.get("table_name") and str(r["table_name"]).replace("_", "").isalnum()
        ]

    fixed = 0
    for table in table_names:
        if not table.replace("_", "").isalnum():
            continue
        await conn.execute_query(
            f"""
            DO $$
            DECLARE seq regclass;
            BEGIN
              seq := pg_get_serial_sequence('{table}', 'id');
              IF seq IS NULL THEN
                BEGIN
                  seq := to_regclass('public.{table}_id_seq');
                EXCEPTION WHEN OTHERS THEN
                  seq := NULL;
                END;
              END IF;
              IF seq IS NOT NULL THEN
                PERFORM setval(
                  seq,
                  GREATEST(COALESCE((SELECT MAX(id) FROM "{table}"), 1), 1),
                  true
                );
              END IF;
            END $$;
            """
        )
        fixed += 1
    logger.info("恢复后序列对齐完成 tables={}", fixed)
    return fixed


async def heal_tenant_config_after_restore(
    tenant_id: int,
    *,
    realign_sequences: bool = True,
) -> Dict[str, Any]:
    """恢复后愈合：可选序列对齐 + 审核绑定/流程 + 消息模板与提醒规则重绑。"""
    from core.services.approval.audit_binding_service import AuditBindingService
    from core.services.tenant.tenant_init_data_service import TenantInitDataService
    from infra.models.tenant import Tenant

    tenant = await Tenant.get_or_none(id=int(tenant_id))
    if not tenant:
        logger.warning("恢复后愈合跳过：组织不存在 tenant_id={}", tenant_id)
        return {"skipped": True, "reason": "tenant_missing"}

    tid = int(tenant_id)
    result: Dict[str, Any] = {"tenant_id": tid, "skipped": False}

    if realign_sequences:
        try:
            result["sequences_realigned"] = await realign_id_sequences_after_restore()
        except Exception as exc:
            logger.exception("恢复后序列对齐失败 tenant={}: {}", tid, exc)
            result["sequence_error"] = str(exc)

    try:
        bindings_created = await AuditBindingService.ensure_binding_rows(tid)
        result["audit_bindings_created"] = int(bindings_created or 0)
    except Exception as exc:
        logger.exception("恢复后愈合审核绑定失败 tenant={}: {}", tid, exc)
        result["audit_error"] = str(exc)

    try:
        # 含消息模板预设 + 各已装应用通知规则预设（按 template_code 修复无效 UUID）
        templates_touched = await TenantInitDataService.run_single(
            tid, "message_template_preset"
        )
        result["message_template_preset"] = int(templates_touched or 0)
    except Exception as exc:
        logger.exception("恢复后愈合消息模板/提醒规则失败 tenant={}: {}", tid, exc)
        result["notification_error"] = str(exc)

    try:
        processes_touched = await TenantInitDataService.run_single(
            tid, "approval_process_preset"
        )
        result["approval_process_preset"] = int(processes_touched or 0)
    except Exception as exc:
        logger.exception("恢复后愈合审批流程预设失败 tenant={}: {}", tid, exc)
        result["approval_error"] = str(exc)

    logger.info("租户恢复后配置愈合完成: {}", result)
    return result
