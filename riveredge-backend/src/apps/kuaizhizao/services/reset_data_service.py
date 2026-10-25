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
    快制造应用数据重置服务（按侧栏模块细分；业务模块 / 基础模块分组）。
    """

    # 业务模块（单据与流水）
    MOD_SALES = "sales"
    MOD_PLAN = "plan"
    MOD_PURCHASE = "purchase"
    MOD_PRODUCTION = "production"
    MOD_OUTSOURCE = "outsource"
    MOD_WAREHOUSE = "warehouse"
    MOD_QUALITY = "quality"
    MOD_EQUIPMENT_OPS = "equipment_ops"
    MOD_SHARED = "shared"

    # 基础模块（台账 / 方案 / 模板 / 规则）
    MOD_MASTER_EQUIPMENT = "master_equipment"
    MOD_MASTER_MOLD = "master_mold"
    MOD_MASTER_TOOL = "master_tool"
    MOD_MASTER_QUALITY = "master_quality"
    MOD_MASTER_TEMPLATES = "master_templates"
    MOD_MASTER_PACKING = "master_packing"
    MOD_MASTER_LOGISTICS = "master_logistics"
    MOD_MASTER_RULES = "master_rules"

    # 兼容上一版粗粒度：展开为组内全部模块（仅 normalize 接受，不再作为独立表名单）
    LEGACY_BUSINESS = "business"
    LEGACY_MASTER = "master"

    GROUP_BUSINESS = "business"
    GROUP_MASTER = "master"

    # 模块目录：顺序即删除与展示顺序（先业务后基础）
    MODULE_CATALOG: Tuple[Dict[str, str], ...] = (
        {"code": MOD_SALES, "group": GROUP_BUSINESS},
        {"code": MOD_PLAN, "group": GROUP_BUSINESS},
        {"code": MOD_PURCHASE, "group": GROUP_BUSINESS},
        {"code": MOD_PRODUCTION, "group": GROUP_BUSINESS},
        {"code": MOD_OUTSOURCE, "group": GROUP_BUSINESS},
        {"code": MOD_WAREHOUSE, "group": GROUP_BUSINESS},
        {"code": MOD_QUALITY, "group": GROUP_BUSINESS},
        {"code": MOD_EQUIPMENT_OPS, "group": GROUP_BUSINESS},
        {"code": MOD_SHARED, "group": GROUP_BUSINESS},
        {"code": MOD_MASTER_EQUIPMENT, "group": GROUP_MASTER},
        {"code": MOD_MASTER_MOLD, "group": GROUP_MASTER},
        {"code": MOD_MASTER_TOOL, "group": GROUP_MASTER},
        {"code": MOD_MASTER_QUALITY, "group": GROUP_MASTER},
        {"code": MOD_MASTER_TEMPLATES, "group": GROUP_MASTER},
        {"code": MOD_MASTER_PACKING, "group": GROUP_MASTER},
        {"code": MOD_MASTER_LOGISTICS, "group": GROUP_MASTER},
        {"code": MOD_MASTER_RULES, "group": GROUP_MASTER},
    )

    # 勾选基础模块时自动带上依赖的业务模块（外键）
    MASTER_IMPLIES_BUSINESS: Dict[str, Tuple[str, ...]] = {
        MOD_MASTER_EQUIPMENT: (MOD_EQUIPMENT_OPS,),
        MOD_MASTER_MOLD: (MOD_EQUIPMENT_OPS,),
        MOD_MASTER_TOOL: (MOD_EQUIPMENT_OPS,),
        MOD_MASTER_QUALITY: (MOD_QUALITY,),
        MOD_MASTER_TEMPLATES: (MOD_PRODUCTION,),
        MOD_MASTER_PACKING: (MOD_PRODUCTION,),
        MOD_MASTER_LOGISTICS: (MOD_WAREHOUSE,),
        MOD_MASTER_RULES: (),
    }

    MODULE_TABLES: Dict[str, List[str]] = {
        MOD_SALES: [
            "apps_kuaizhizao_quotation_items",
            "apps_kuaizhizao_quotations",
            "apps_kuaizhizao_sales_order_items",
            "apps_kuaizhizao_sales_orders",
            "apps_kuaizhizao_sales_order_change_items",
            "apps_kuaizhizao_sales_order_change_orders",
            "apps_kuaizhizao_sales_contract_items",
            "apps_kuaizhizao_sales_contracts",
            "apps_kuaizhizao_sales_forecast_items",
            "apps_kuaizhizao_sales_forecasts",
            "apps_kuaizhizao_shipment_notice_items",
            "apps_kuaizhizao_shipment_notices",
            "apps_kuaizhizao_delivery_notice_items",
            "apps_kuaizhizao_delivery_notices",
            "apps_kuaizhizao_sales_delivery_items",
            "apps_kuaizhizao_sales_deliveries",
            "apps_kuaizhizao_sales_return_items",
            "apps_kuaizhizao_sales_returns",
            "apps_kuaizhizao_customer_material_registration_items",
            "apps_kuaizhizao_customer_material_registrations",
        ],
        MOD_PLAN: [
            "apps_kuaizhizao_demand_items",
            "apps_kuaizhizao_demands",
            "apps_kuaizhizao_demand_snapshots",
            "apps_kuaizhizao_demand_recalc_histories",
            "apps_kuaizhizao_demand_computation_items",
            "apps_kuaizhizao_demand_computations",
            "apps_kuaizhizao_demand_computation_snapshots",
            "apps_kuaizhizao_demand_computation_recalc_histories",
            "apps_kuaizhizao_demand_replan_tasks",
            "apps_kuaizhizao_demand_impact_records",
            "apps_kuaizhizao_demand_change_events",
            "apps_kuaizhizao_production_plan_items",
            "apps_kuaizhizao_production_plans",
            "apps_kuaizhizao_rolling_schedule_plan_lines",
            "apps_kuaizhizao_rolling_schedule_plans",
        ],
        MOD_PURCHASE: [
            "apps_kuaizhizao_purchase_requisition_items",
            "apps_kuaizhizao_purchase_requisitions",
            "apps_kuaizhizao_purchase_inquiry_vendors",
            "apps_kuaizhizao_purchase_inquiry_items",
            "apps_kuaizhizao_purchase_inquiries",
            "apps_kuaizhizao_purchase_supplier_quote_items",
            "apps_kuaizhizao_purchase_supplier_quotes",
            "apps_kuaizhizao_purchase_order_items",
            "apps_kuaizhizao_purchase_orders",
            "apps_kuaizhizao_purchase_order_change_items",
            "apps_kuaizhizao_purchase_order_change_orders",
            "apps_kuaizhizao_purchase_order_changes",
            "apps_kuaizhizao_receipt_notice_items",
            "apps_kuaizhizao_receipt_notices",
            "apps_kuaizhizao_purchase_receipt_item",
            "apps_kuaizhizao_purchase_receipt_items",
            "apps_kuaizhizao_purchase_receipts",
            "apps_kuaizhizao_purchase_return_items",
            "apps_kuaizhizao_purchase_returns",
        ],
        MOD_PRODUCTION: [
            "apps_kuaizhizao_work_order_operations",
            "apps_kuaizhizao_work_orders",
            "apps_kuaizhizao_reporting_records",
            "apps_kuaizhizao_rework_order_operations",
            "apps_kuaizhizao_rework_orders",
            "apps_kuaizhizao_assembly_order_items",
            "apps_kuaizhizao_assembly_orders",
            "apps_kuaizhizao_batching_order_items",
            "apps_kuaizhizao_batching_orders",
            "apps_kuaizhizao_disassembly_order_items",
            "apps_kuaizhizao_disassembly_orders",
            "apps_kuaizhizao_scrap_records",
            "apps_kuaizhizao_defect_records",
            "apps_kuaizhizao_material_bindings",
            "apps_kuaizhizao_assembly_material_bindings",
            "apps_kuaizhizao_packing_bindings",
            "apps_kuaizhizao_production_picking_items",
            "apps_kuaizhizao_production_pickings",
            "apps_kuaizhizao_production_return_items",
            "apps_kuaizhizao_production_returns",
            "apps_kuaizhizao_finished_goods_receipt_items",
            "apps_kuaizhizao_finished_goods_receipts",
            "apps_kuaizhizao_semi_finished_goods_receipt_items",
            "apps_kuaizhizao_semi_finished_goods_receipts",
            "apps_kuaizhizao_backflush_records",
        ],
        MOD_OUTSOURCE: [
            "apps_kuaizhizao_outsource_orders",
            "apps_kuaizhizao_outsource_work_orders",
            "apps_kuaizhizao_outsource_material_issues",
            "apps_kuaizhizao_outsource_material_receipts",
            "apps_kuaizhizao_outsource_material_returns",
            "apps_kuaizhizao_outsource_product_returns",
        ],
        MOD_WAREHOUSE: [
            "apps_kuaizhizao_other_inbound_items",
            "apps_kuaizhizao_other_inbounds",
            "apps_kuaizhizao_other_outbound_items",
            "apps_kuaizhizao_other_outbounds",
            "apps_kuaizhizao_material_borrow_items",
            "apps_kuaizhizao_material_borrows",
            "apps_kuaizhizao_material_return_items",
            "apps_kuaizhizao_material_returns",
            "apps_kuaizhizao_stocktaking_items",
            "apps_kuaizhizao_stocktakings",
            "apps_kuaizhizao_inventory_transfer_items",
            "apps_kuaizhizao_inventory_transfers",
            "apps_kuaizhizao_material_call_request_items",
            "apps_kuaizhizao_material_call_requests",
            "apps_kuaizhizao_replenishment_suggestions",
            "apps_kuaizhizao_wave_pickings",
            "apps_kuaizhizao_inventory_alerts",
        ],
        MOD_QUALITY: [
            "apps_kuaizhizao_incoming_inspections",
            "apps_kuaizhizao_process_inspections",
            "apps_kuaizhizao_finished_goods_inspections",
            "apps_kuaizhizao_oqc_inspections",
            "apps_kuaizhizao_quality_8d_reports",
            "apps_kuaizhizao_quality_exceptions",
            "apps_kuaizhizao_exception_process_records",
            "apps_kuaizhizao_exception_process_histories",
        ],
        MOD_EQUIPMENT_OPS: [
            "apps_kuaizhizao_equipment_faults",
            "apps_kuaizhizao_equipment_repairs",
            "apps_kuaizhizao_equipment_status_histories",
            "apps_kuaizhizao_equipment_status_monitors",
            "apps_kuaizhizao_equipment_calibrations",
            "apps_kuaizhizao_maintenance_executions",
            "apps_kuaizhizao_maintenance_reminders",
            "apps_kuaizhizao_maintenance_plans",
            "apps_kuaizhizao_mold_usages",
            "apps_kuaizhizao_mold_calibrations",
            "apps_kuaizhizao_tool_usages",
            "apps_kuaizhizao_tool_maintenances",
            "apps_kuaizhizao_tool_calibrations",
        ],
        MOD_SHARED: [
            "apps_kuaizhizao_document_relations",
            "apps_kuaizhizao_state_transition_logs",
        ],
        MOD_MASTER_EQUIPMENT: [
            "apps_kuaizhizao_equipment_inspection_scheme_lines",
            "apps_kuaizhizao_equipment_inspection_schemes",
            "apps_kuaizhizao_equipment_maintenance_scheme_lines",
            "apps_kuaizhizao_equipment_maintenance_schemes",
            "apps_kuaizhizao_equipment_scheme_bindings",
            "apps_kuaizhizao_equipment_patrol_route_steps",
            "apps_kuaizhizao_equipment_patrol_routes",
            "apps_kuaizhizao_equipment_inspection_items",
            "apps_kuaizhizao_equipment_maintenance_items",
            "apps_kuaizhizao_equipment",
        ],
        MOD_MASTER_MOLD: [
            "apps_kuaizhizao_mold_maintenance_scheme_lines",
            "apps_kuaizhizao_mold_maintenance_schemes",
            "apps_kuaizhizao_mold_repair_scheme_lines",
            "apps_kuaizhizao_mold_repair_schemes",
            "apps_kuaizhizao_mold_scheme_bindings",
            "apps_kuaizhizao_mold_maintenance_items",
            "apps_kuaizhizao_mold_repair_items",
            "apps_kuaizhizao_molds",
        ],
        MOD_MASTER_TOOL: [
            "apps_kuaizhizao_tool_maintenance_scheme_lines",
            "apps_kuaizhizao_tool_maintenance_schemes",
            "apps_kuaizhizao_tool_repair_scheme_lines",
            "apps_kuaizhizao_tool_repair_schemes",
            "apps_kuaizhizao_tool_scheme_bindings",
            "apps_kuaizhizao_tool_maintenance_items",
            "apps_kuaizhizao_tool_repair_items",
            "apps_kuaizhizao_tools",
        ],
        MOD_MASTER_QUALITY: [
            "apps_kuaizhizao_inspection_plan_steps",
            "apps_kuaizhizao_inspection_plans",
            "apps_kuaizhizao_quality_standards",
            "apps_kuaizhizao_qms_document_clauses",
            "apps_kuaizhizao_qms_iso_clauses",
            "apps_kuaizhizao_qms_review_standards",
            "apps_kuaizhizao_qms_standards",
            "apps_kuaizhizao_supplier_eval_template_clauses",
            "apps_kuaizhizao_supplier_eval_templates",
        ],
        MOD_MASTER_TEMPLATES: [
            "apps_kuaizhizao_assembly_template_items",
            "apps_kuaizhizao_assembly_templates",
            "apps_kuaizhizao_delivery_process_template_node_tasks",
            "apps_kuaizhizao_delivery_process_template_nodes",
            "apps_kuaizhizao_delivery_process_templates",
            "apps_kuaizhizao_rework_position_plan_template_items",
            "apps_kuaizhizao_rework_position_plan_templates",
            "apps_kuaizhizao_production_daily_templates",
        ],
        MOD_MASTER_PACKING: [
            "apps_kuaizhizao_packing_profiles",
            "apps_kuaizhizao_barcode_mapping_rules",
            "apps_kuaizhizao_label_model_configs",
            "apps_kuaizhizao_label_stations",
        ],
        MOD_MASTER_LOGISTICS: [
            "apps_kuaizhizao_logistics_carriers",
            "apps_kuaizhizao_vehicles",
            "apps_kuaizhizao_drivers",
            "apps_kuaizhizao_spare_parts",
            "apps_kuaizhizao_service_assets",
            "apps_kuaizhizao_operator_skill_qualifications",
        ],
        MOD_MASTER_RULES: [
            "apps_kuaizhizao_customer_pool_rules",
            "apps_kuaizhizao_scheduling_configs",
            "apps_kuaizhizao_state_transition_rules",
            "apps_kuaizhizao_inventory_alert_rules",
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
        """供 API / FE 对齐的模块目录（无表名单）。"""
        return [{"code": m["code"], "group": m["group"]} for m in cls.MODULE_CATALOG]

    @staticmethod
    def _token_secret() -> str:
        try:
            from infra.config.settings import settings

            return str(
                getattr(settings, "JWT_SECRET_KEY", None)
                or getattr(settings, "SECRET_KEY", None)
                or "kuaizhizao-reset-data"
            )
        except Exception:
            return "kuaizhizao-reset-data"

    @classmethod
    def normalize_scopes(cls, scopes: Optional[Iterable[str]]) -> List[str]:
        """
        规范化模块 scopes：
        - 展开 legacy business/master 为组内全部模块
        - 勾选基础模块时展开依赖的业务模块
        - 任选业务模块时自动带上 shared（单据关联/状态日志）
        """
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

        # 基础 → 依赖业务
        for master_code, implies in cls.MASTER_IMPLIES_BUSINESS.items():
            if master_code in selected:
                selected.update(implies)

        # 有任一业务模块（不含仅 shared）时带上 shared
        business_mods = set(cls.modules_in_group(cls.GROUP_BUSINESS))
        non_shared_business = (selected & business_mods) - {cls.MOD_SHARED}
        if non_shared_business:
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
        """签发短时二次确认 token：tenant:op:issued:ttl:scopes.signature。"""
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
        """校验 token，并返回规范化后的 scopes（须与签发时一致）。"""
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
            cls.MOD_SALES: "销售管理",
            cls.MOD_PLAN: "计划管理",
            cls.MOD_PURCHASE: "采购管理",
            cls.MOD_PRODUCTION: "生产执行",
            cls.MOD_OUTSOURCE: "委外管理",
            cls.MOD_WAREHOUSE: "仓储管理",
            cls.MOD_QUALITY: "质量管理",
            cls.MOD_EQUIPMENT_OPS: "设备模具工装运维",
            cls.MOD_SHARED: "单据关联",
            cls.MOD_MASTER_EQUIPMENT: "设备台账与方案",
            cls.MOD_MASTER_MOLD: "模具台账与方案",
            cls.MOD_MASTER_TOOL: "工装台账与方案",
            cls.MOD_MASTER_QUALITY: "质检标准与方案",
            cls.MOD_MASTER_TEMPLATES: "装配交付模板",
            cls.MOD_MASTER_PACKING: "包装条码配置",
            cls.MOD_MASTER_LOGISTICS: "物流与服务台账",
            cls.MOD_MASTER_RULES: "规则与排程配置",
        }
        # 摘要不展示 shared（自动附带）
        parts = [labels.get(c, c) for c in scopes if c != cls.MOD_SHARED]
        return "、".join(parts) if parts else "、".join(scopes)

    @classmethod
    async def reset_kuaizhizao_data(
        cls,
        tenant_id: int,
        operator_id: int,
        scopes: Sequence[str],
    ) -> dict:
        """
        按模块 scopes 重置快制造数据：备份 -> 物理删除对应表。
        """
        normalized = cls.normalize_scopes(scopes)
        scope_label = "+".join(normalized)
        logger.warning(
            f"开始重置租户 {tenant_id} 的快制造数据，操作人: {operator_id}，模块: {scope_label}"
        )

        try:
            backup_name = (
                f"[AUTO] 重置前自动备份_快制造_{scope_label[:80]}_"
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
            f"租户 {tenant_id} 数据重置完成（{scope_label}）。共清理 {total_deleted} 条记录。"
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
