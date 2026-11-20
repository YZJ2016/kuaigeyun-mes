from __future__ import annotations

import hashlib
import hmac
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from loguru import logger
from tortoise import Tortoise

from core.services.system.data_backup_service import DataBackupService
from core.schemas.data_backup import DataBackupCreate
from core.utils.timezone_utils import resolve_business_datetime


class ResetDataService:
    """
    主数据应用重置服务（按侧栏模块细分）。
    """

    MOD_FACTORY = "factory"
    MOD_WAREHOUSE = "warehouse"
    MOD_MATERIALS = "materials"
    MOD_PROCESS = "process"
    MOD_SUPPLY_CHAIN = "supply_chain"
    MOD_WORKFORCE = "workforce"
    MOD_SHARED = "shared"

    LEGACY_BUSINESS = "business"
    LEGACY_MASTER = "master"
    GROUP_BUSINESS = "business"
    GROUP_MASTER = "master"

    MODULE_CATALOG: Tuple[Dict[str, str], ...] = (
        # 删除顺序：先流水/工艺，再物料与其它台账（避免 BOM/路线外键挡住物料删除）
        {"code": MOD_WORKFORCE, "group": GROUP_BUSINESS},
        {"code": MOD_PROCESS, "group": GROUP_MASTER},
        {"code": MOD_MATERIALS, "group": GROUP_MASTER},
        {"code": MOD_FACTORY, "group": GROUP_MASTER},
        {"code": MOD_WAREHOUSE, "group": GROUP_MASTER},
        {"code": MOD_SUPPLY_CHAIN, "group": GROUP_MASTER},
        {"code": MOD_SHARED, "group": GROUP_MASTER},
    )

    # 清物料前须清工艺（BOM/路线引用物料）
    MASTER_IMPLIES_BUSINESS: Dict[str, Tuple[str, ...]] = {
        MOD_MATERIALS: (MOD_PROCESS,),
    }

    MODULE_TABLES: Dict[str, List[str]] = {
        MOD_WORKFORCE: [
            "apps_master_data_roster_time_adjustments",
            "apps_master_data_shift_assignments",
            "apps_master_data_shift_rosters",
            "apps_master_data_overtime_plans",
            "apps_master_data_station_unavailable_windows",
            "apps_master_data_employee_kpi_scores",
            "apps_master_data_performance_summaries",
            "apps_master_data_employee_performance_configs",
            "apps_master_data_kpi_definitions",
            "apps_master_data_piece_rates",
            "apps_master_data_hourly_rates",
            "apps_master_data_skills",
            "apps_master_data_shifts",
            "apps_master_data_holidays",
            "apps_master_data_work_calendar_configs",
        ],
        MOD_FACTORY: [
            "apps_master_data_work_group_members",
            "apps_master_data_work_groups",
            "apps_master_data_workstations",
            "apps_master_data_work_centers",
            "apps_master_data_production_lines",
            "apps_master_data_workshops",
            "apps_master_data_plants",
        ],
        MOD_WAREHOUSE: [
            "apps_master_data_storage_locations",
            "apps_master_data_storage_areas",
            "apps_master_data_warehouses",
        ],
        MOD_MATERIALS: [
            "apps_master_data_material_serials",
            "apps_master_data_material_batches",
            "apps_master_data_material_market_prices",
            "apps_master_data_material_code_aliases",
            "apps_master_data_material_code_mappings",
            "apps_master_data_material_product_process",
            "apps_master_data_unit_conversions",
            "apps_master_data_products",
            "apps_master_data_materials",
            "apps_master_data_material_groups",
            "apps_master_data_units",
        ],
        MOD_PROCESS: [
            "apps_master_data_sop_executions",
            "apps_master_data_sop_controlled_copies",
            "apps_master_data_sop_revisions",
            "apps_master_data_sop",
            "apps_master_data_drawing_loan_lines",
            "apps_master_data_drawing_loans",
            "apps_master_data_drawing_distribution_lines",
            "apps_master_data_drawing_distributions",
            "apps_master_data_drawing_distribution_policies",
            "apps_master_data_drawing_user_clearances",
            "apps_master_data_drawing_watermark_policies",
            "apps_master_data_drawing_changes",
            "apps_master_data_engineering_drawings",
            "apps_master_data_drawing_folders",
            "apps_master_data_bom_changes",
            "apps_master_data_bom",
            "apps_master_data_process_route_changes",
            "apps_master_data_process_routes",
            "apps_master_data_process_route_templates",
            "apps_master_data_operation_defect_types",
            "apps_master_data_defect_types",
            "apps_master_data_operations",
        ],
        MOD_SUPPLY_CHAIN: [
            "apps_master_data_partner_price_books",
            "apps_master_data_customers",
            "apps_master_data_suppliers",
        ],
        MOD_SHARED: [
            "apps_master_data_customer_sync_binding",
            "apps_master_data_supplier_sync_binding",
            "apps_master_data_warehouse_sync_binding",
            "apps_master_data_storage_location_sync_binding",
            "apps_master_data_material_sync_binding",
            "apps_master_data_material_multi_unit_sync_binding",
            "apps_master_data_material_batch_manage_sync_binding",
            "apps_master_data_material_unit_sync_binding",
            "apps_master_data_material_group_sync_binding",
            "apps_master_data_engineering_bom_sync_binding",
            "apps_master_data_operation_sync_binding",
        ],
    }

    @classmethod
    def allowed_module_codes(cls) -> frozenset[str]:
        return frozenset(m["code"] for m in cls.MODULE_CATALOG)

    @classmethod
    def modules_in_group(cls, group: str) -> List[str]:
        return [m["code"] for m in cls.MODULE_CATALOG if m["group"] == group]

    @classmethod
    def all_module_codes(cls) -> List[str]:
        return [m["code"] for m in cls.MODULE_CATALOG]

    @classmethod
    def list_module_catalog(cls) -> List[dict]:
        return [{"code": m["code"], "group": m["group"]} for m in cls.MODULE_CATALOG]

    @staticmethod
    def _token_secret() -> str:
        try:
            from infra.config.settings import settings

            return str(
                getattr(settings, "JWT_SECRET_KEY", None)
                or getattr(settings, "SECRET_KEY", None)
                or "master-data-reset-data"
            )
        except Exception:
            return "master-data-reset-data"

    @classmethod
    def normalize_scopes(cls, scopes: Optional[Iterable[str]]) -> List[str]:
        allowed = cls.allowed_module_codes()
        raw = [str(s or "").strip().lower() for s in (scopes or [])]
        selected: set[str] = set()
        for s in raw:
            if s == cls.LEGACY_BUSINESS:
                selected.update(cls.modules_in_group(cls.GROUP_BUSINESS))
            elif s == cls.LEGACY_MASTER:
                selected.update(cls.modules_in_group(cls.GROUP_MASTER))
            elif s in allowed:
                selected.add(s)

        if not selected:
            raise ValueError("请至少选择一个要重置的模块")

        for code, implies in cls.MASTER_IMPLIES_BUSINESS.items():
            if code in selected:
                selected.update(implies)

        # 任选非 shared 模块时附带同步绑定表
        if selected - {cls.MOD_SHARED}:
            selected.add(cls.MOD_SHARED)

        order = cls.all_module_codes()
        return [c for c in order if c in selected]

    @classmethod
    def _scopes_token_part(cls, scopes: Sequence[str]) -> str:
        return "+".join(cls.normalize_scopes(scopes))

    @classmethod
    def issue_confirmation_token(
        cls,
        *,
        tenant_id: int,
        operator_id: int,
        scopes: Sequence[str],
        ttl_seconds: int = 300,
    ) -> str:
        issued_at = int(time.time())
        scopes_part = cls._scopes_token_part(scopes)
        payload = f"{tenant_id}:{operator_id}:{issued_at}:{ttl_seconds}:{scopes_part}"
        sig = hmac.new(
            cls._token_secret().encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{payload}.{sig}"

    @classmethod
    def verify_confirmation_token(
        cls,
        *,
        tenant_id: int,
        operator_id: int,
        token: str,
        scopes: Sequence[str],
        ttl_seconds: int = 300,
    ) -> List[str]:
        raw = (token or "").strip()
        if not raw or "." not in raw:
            raise ValueError("二次确认 token 无效")
        payload, sig = raw.rsplit(".", 1)
        parts = payload.split(":")
        if len(parts) != 5:
            raise ValueError("二次确认 token 格式错误")
        try:
            tok_tenant = int(parts[0])
            tok_op = int(parts[1])
            issued_at = int(parts[2])
            tok_ttl = int(parts[3])
            tok_scopes_part = parts[4]
        except ValueError as exc:
            raise ValueError("二次确认 token 内容无效") from exc
        if tok_tenant != int(tenant_id) or tok_op != int(operator_id):
            raise ValueError("二次确认 token 与当前操作人不匹配")
        expected = hmac.new(
            cls._token_secret().encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise ValueError("二次确认 token 校验失败")
        effective_ttl = min(int(ttl_seconds), tok_ttl) if tok_ttl > 0 else int(ttl_seconds)
        if int(time.time()) - issued_at > effective_ttl:
            raise ValueError("二次确认 token 已过期，请重新获取")
        normalized = cls.normalize_scopes(scopes)
        if cls._scopes_token_part(normalized) != tok_scopes_part:
            raise ValueError("二次确认 token 与所选重置范围不一致，请重新获取")
        return normalized

    @classmethod
    def _tables_for_scopes(cls, scopes: Sequence[str]) -> List[str]:
        normalized = cls.normalize_scopes(scopes)
        tables: List[str] = []
        seen = set()
        for code in normalized:
            for t in cls.MODULE_TABLES.get(code, []):
                if t not in seen:
                    tables.append(t)
                    seen.add(t)
        return tables

    @classmethod
    def scope_labels_zh(cls, scopes: Sequence[str]) -> str:
        labels = {
            cls.MOD_WORKFORCE: "排班绩效",
            cls.MOD_FACTORY: "工厂数据",
            cls.MOD_WAREHOUSE: "仓库数据",
            cls.MOD_MATERIALS: "物料数据",
            cls.MOD_PROCESS: "工艺数据",
            cls.MOD_SUPPLY_CHAIN: "客户供应商",
            cls.MOD_SHARED: "同步绑定",
        }
        parts = [labels.get(c, c) for c in scopes if c != cls.MOD_SHARED]
        return "、".join(parts) if parts else "、".join(scopes)

    @classmethod
    async def reset_master_data(
        cls,
        tenant_id: int,
        operator_id: int,
        scopes: Sequence[str],
    ) -> dict:
        normalized = cls.normalize_scopes(scopes)
        scope_label = "+".join(normalized)
        logger.warning(
            f"开始重置租户 {tenant_id} 的主数据，操作人: {operator_id}，模块: {scope_label}"
        )

        try:
            backup_name = (
                f"[AUTO] 重置前自动备份_主数据_{scope_label[:80]}_"
                f"{resolve_business_datetime().strftime('%Y%m%d_%H%M%S')}"
            )
            backup_data = DataBackupCreate(
                name=backup_name,
                backup_type="full",
                backup_scope="all",
                backup_tables=None,
            )
            await DataBackupService.create_backup_task(tenant_id, backup_data)
            logger.info("已触发重置前自动备份任务")
        except Exception as e:
            logger.error(f"重置前自动备份失败: {e}")
            raise ValueError(f"自动备份创建失败，出于安全考虑已中止重置操作: {str(e)}")

        conn = Tortoise.get_connection("default")
        deleted_counts = {}
        error_tables = []
        tables = cls._tables_for_scopes(normalized)

        for table in tables:
            try:
                sql = f"DELETE FROM {table} WHERE tenant_id = $1"
                result = await conn.execute_query(sql, [tenant_id])
                if isinstance(result, int):
                    deleted_counts[table] = result
                elif result and len(result) > 0:
                    deleted_counts[table] = int(result[0]) if result[0] is not None else 0
            except Exception as e:
                logger.warning(f"清理表 {table} 失败: {e}")
                error_tables.append(table)

        total_deleted = sum(deleted_counts.values())
        logger.info(
            f"租户 {tenant_id} 主数据重置完成（{scope_label}）。共清理 {total_deleted} 条记录。"
        )
        scope_text = cls.scope_labels_zh(normalized)

        return {
            "success": True,
            "message": (
                f"重置成功（{scope_text}）。"
                f"共从 {len(deleted_counts)} 张表中清理了 {total_deleted} 条记录。"
            ),
            "details": {
                "scopes": normalized,
                "deleted_counts": deleted_counts,
                "error_tables": error_tables,
            },
        }
