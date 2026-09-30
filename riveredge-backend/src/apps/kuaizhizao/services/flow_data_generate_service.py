"""按销售订单生成制造全流程演示数据（运维造数）。"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from core.services.document_time_rewrite_service import (
    DocumentTimeRewriteService,
    WorkScheduleParams,
)
from core.services.logging.operation_log_service import OperationLogService
from core.models.operation_log import OperationLog
from core.utils.timezone_utils import now_utc, resolve_business_datetime, site_timezone_name
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError


STEP_KEYS = (
    "demand_computation",
    "purchase",
    "inventory_topup",
    "production_picking",
    "reporting",
    "finished_goods_inspection",
    "finished_goods_receipt",
    "shipment_delivery",
)

# 各步骤默认从这些预设角色码中随机取激活用户（按序尝试）
STEP_DEFAULT_ROLE_CODES: dict[str, tuple[str, ...]] = {
    "demand_computation": ("PRODUCTION_MANAGER", "PRODUCTION_CLERK", "SALES_MANAGER"),
    "purchase": ("PURCHASE_PERSON", "PURCHASE_OPERATOR", "PURCHASE_MANAGER"),
    "inventory_topup": ("WAREHOUSE_OPERATOR",),
    "production_picking": ("WAREHOUSE_OPERATOR",),
    "reporting": ("PRODUCTION_STAFF", "PRODUCTION_TEAM_LEADER", "PRODUCTION_CLERK"),
    "finished_goods_inspection": ("QUALITY_OPERATOR", "QUALITY_MANAGER"),
    "finished_goods_receipt": ("WAREHOUSE_OPERATOR",),
    "shipment_delivery": ("WAREHOUSE_OPERATOR", "SALES_OPERATOR", "SALES_PERSON"),
}

DEFAULT_INTERVAL_MIN = 300
DEFAULT_INTERVAL_MAX = 1800
DEFAULT_REPORTING_BATCHES_MIN = 2
DEFAULT_REPORTING_BATCHES_MAX = 5


@dataclass
class IntervalConfig:
    min_seconds: int = DEFAULT_INTERVAL_MIN
    max_seconds: int = DEFAULT_INTERVAL_MAX

    def clamp(self) -> "IntervalConfig":
        lo = max(1, int(self.min_seconds))
        hi = max(lo, int(self.max_seconds))
        return IntervalConfig(min_seconds=lo, max_seconds=hi)


@dataclass
class ReportingBatchConfig:
    """工序报工分批：数量拆多批、每批独立时间与操作人。"""

    min_batches: int = DEFAULT_REPORTING_BATCHES_MIN
    max_batches: int = DEFAULT_REPORTING_BATCHES_MAX

    def clamp(self) -> "ReportingBatchConfig":
        lo = max(1, min(20, int(self.min_batches)))
        hi = max(lo, min(20, int(self.max_batches)))
        return ReportingBatchConfig(min_batches=lo, max_batches=hi)

    def pick_batch_count(self, qty: Decimal) -> int:
        cfg = self.clamp()
        n = random.randint(cfg.min_batches, cfg.max_batches)
        if qty == qty.to_integral_value() and qty >= 1:
            n = min(n, int(qty))
        return max(1, n)


@dataclass
class StepOperatorConfig:
    """单据步骤操作用户配置。

    mode:
      - fixed: 使用 user_id
      - random_role: 从 role_code（或步骤默认角色）下激活用户随机
      - current: 使用当前登录用户（fallback）
    """

    mode: str = "random_role"
    user_id: Optional[int] = None
    role_code: Optional[str] = None

    def normalized_mode(self) -> str:
        raw = (self.mode or "random_role").strip().lower()
        if raw in ("fixed", "user", "指定", "指定人员"):
            return "fixed"
        if raw in ("current", "self", "当前"):
            return "current"
        return "random_role"


@dataclass
class TimelineEntry:
    step_key: str
    doc_type: str
    doc_id: int
    doc_code: str
    issued_at: datetime
    label: str = ""
    operation_log_id: Optional[int] = None
    note: Optional[str] = None


@dataclass
class FlowGenerateRequest:
    source_type: str = "sales_order"  # sales_order | sales_forecast
    sales_order_id: Optional[int] = None
    sales_forecast_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    anchor_at: Optional[datetime] = None
    intervals: dict[str, IntervalConfig] = field(default_factory=dict)
    default_interval: IntervalConfig = field(
        default_factory=lambda: IntervalConfig(DEFAULT_INTERVAL_MIN, DEFAULT_INTERVAL_MAX)
    )
    steps: dict[str, bool] = field(default_factory=dict)
    step_operators: dict[str, StepOperatorConfig] = field(default_factory=dict)
    reporting_batches: ReportingBatchConfig = field(
        default_factory=lambda: ReportingBatchConfig(
            DEFAULT_REPORTING_BATCHES_MIN, DEFAULT_REPORTING_BATCHES_MAX
        )
    )
    work_schedule: Optional[WorkScheduleParams] = None
    use_work_schedule: bool = False

    def normalized_source(self) -> str:
        raw = (self.source_type or "sales_order").strip().lower()
        if raw in ("sales_forecast", "forecast"):
            return "sales_forecast"
        return "sales_order"


class TimelinePlanner:
    """按间隔随机生成严格递增的业务时刻（含分秒）。"""

    def __init__(
        self,
        *,
        anchor: datetime,
        default_interval: IntervalConfig,
        intervals: dict[str, IntervalConfig],
        work_schedule: Optional[WorkScheduleParams] = None,
        use_work_schedule: bool = False,
    ) -> None:
        self._cursor = resolve_business_datetime(anchor).replace(microsecond=0)
        self._default = default_interval.clamp()
        self._intervals = {k: v.clamp() for k, v in intervals.items()}
        self._schedule = work_schedule
        self._use_schedule = bool(use_work_schedule and work_schedule)
        self._tz = ZoneInfo(site_timezone_name())

    def next(self, step_key: str) -> datetime:
        cfg = self._intervals.get(step_key, self._default)
        gap = random.uniform(float(cfg.min_seconds), float(cfg.max_seconds))
        # 额外扰动分秒：在秒级 gap 上再叠 0–59 秒的碎秒感（若 gap 已含秒则仍保证随机）
        gap += random.uniform(0.0, 59.0) * 0.01
        nxt = self._cursor + timedelta(seconds=gap)
        nxt = nxt.replace(microsecond=0)
        if nxt <= self._cursor:
            nxt = self._cursor + timedelta(seconds=1)
        if self._use_schedule and self._schedule is not None:
            site = nxt.astimezone(self._tz)
            site = self._clamp_forward(site)
            nxt = site.astimezone(timezone.utc).replace(microsecond=0)
            if nxt <= self._cursor:
                nxt = self._cursor + timedelta(seconds=1)
        self._cursor = nxt
        return nxt

    def _clamp_forward(self, when_site: datetime) -> datetime:
        """保证落在工作时段内；过晚则推到下一工作日上班时刻。"""
        assert self._schedule is not None
        cur = when_site.replace(microsecond=0)
        day = cur.date()
        for _ in range(400):
            window = self._schedule.window_on(day, self._tz)
            if window is None:
                day += timedelta(days=1)
                continue
            start, end = window
            last = end - timedelta(seconds=1)
            if last < start:
                last = start
            if cur.date() < day:
                return start
            if cur < start:
                return start
            if cur > last:
                day += timedelta(days=1)
                cur = datetime(day.year, day.month, day.day, tzinfo=self._tz)
                continue
            return cur
        return when_site


class FlowDataGenerateService:
    """销售订单 → 制造/采购/质检/出库 全流程造数编排。"""

    async def list_eligible_orders(
        self,
        tenant_id: int,
        *,
        keyword: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        from tortoise.expressions import Q

        from apps.kuaizhizao.constants import LEGACY_AUDITED_VALUES, ORDER_PUSHABLE_STATUSES
        from apps.kuaizhizao.models.sales_order import SalesOrder

        qs = SalesOrder.filter(tenant_id=tenant_id, deleted_at__isnull=True).filter(
            Q(status__in=tuple(ORDER_PUSHABLE_STATUSES))
            | Q(status__in=tuple(LEGACY_AUDITED_VALUES))
        )
        kw = (keyword or "").strip()
        if kw:
            qs = qs.filter(
                Q(order_code__icontains=kw)
                | Q(customer_name__icontains=kw)
                | Q(order_name__icontains=kw)
            )
        rows = await qs.order_by("-id").limit(max(1, min(int(limit), 200))).all()
        items: list[dict[str, Any]] = []
        for row in rows:
            pushed = bool(getattr(row, "planning_pushed_to_computation", False))
            items.append(
                {
                    "id": int(row.id),
                    "order_code": row.order_code,
                    "order_name": getattr(row, "order_name", None),
                    "customer_name": getattr(row, "customer_name", None),
                    "status": row.status,
                    "order_date": str(row.order_date) if row.order_date else None,
                    "planning_pushed_to_computation": pushed,
                    "eligible": not pushed,
                    "block_reason": (
                        "已下推需求计算，请选择未下推的销售订单" if pushed else None
                    ),
                }
            )
        return {"items": items, "total": len(items)}

    async def list_eligible_forecasts(
        self,
        tenant_id: int,
        *,
        keyword: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        from tortoise.expressions import Q

        from apps.kuaizhizao.constants import LEGACY_AUDITED_VALUES, ORDER_PUSHABLE_STATUSES
        from apps.kuaizhizao.models.sales_forecast import SalesForecast

        qs = SalesForecast.filter(tenant_id=tenant_id, deleted_at__isnull=True).filter(
            Q(status__in=tuple(ORDER_PUSHABLE_STATUSES))
            | Q(status__in=tuple(LEGACY_AUDITED_VALUES))
        )
        kw = (keyword or "").strip()
        if kw:
            qs = qs.filter(
                Q(forecast_code__icontains=kw)
                | Q(forecast_name__icontains=kw)
            )
        rows = await qs.order_by("-id").limit(max(1, min(int(limit), 200))).all()
        items: list[dict[str, Any]] = []
        for row in rows:
            pushed = bool(getattr(row, "planning_pushed_to_computation", False))
            items.append(
                {
                    "id": int(row.id),
                    "forecast_code": row.forecast_code,
                    "forecast_name": getattr(row, "forecast_name", None),
                    "forecast_period": getattr(row, "forecast_period", None),
                    "status": row.status,
                    "start_date": str(row.start_date) if getattr(row, "start_date", None) else None,
                    "end_date": str(row.end_date) if getattr(row, "end_date", None) else None,
                    "planning_pushed_to_computation": pushed,
                    "eligible": not pushed,
                    "block_reason": (
                        "已下推需求计算，请选择未下推的销售预测" if pushed else None
                    ),
                }
            )
        return {"items": items, "total": len(items)}

    async def preview(
        self,
        tenant_id: int,
        req: FlowGenerateRequest,
    ) -> dict[str, Any]:
        source = req.normalized_source()
        if source == "sales_forecast":
            doc = await self._load_and_validate_sales_forecast(tenant_id, int(req.sales_forecast_id or 0))
            doc_id = int(doc.id)
            doc_code = str(doc.forecast_code)
            anchor_src = getattr(doc, "created_at", None)
        else:
            doc = await self._load_and_validate_sales_order(tenant_id, int(req.sales_order_id or 0))
            doc_id = int(doc.id)
            doc_code = str(doc.order_code)
            anchor_src = getattr(doc, "created_at", None)
        warehouse = await self._resolve_warehouse(tenant_id, req.warehouse_id)
        enabled = self._enabled_steps(req.steps)
        planned_steps = self._planned_step_labels(enabled)
        # 销售预测无销售订单发货链时，预览仍保留步骤标签，执行阶段会走预测出库
        anchor = resolve_business_datetime(req.anchor_at or anchor_src)
        planner = TimelinePlanner(
            anchor=anchor,
            default_interval=req.default_interval,
            intervals=req.intervals,
            work_schedule=req.work_schedule,
            use_work_schedule=req.use_work_schedule,
        )
        preview_times: list[dict[str, Any]] = []
        for key, label in planned_steps:
            issued = planner.next(key)
            preview_times.append(
                {
                    "step_key": key,
                    "label": label,
                    "issued_at": issued.isoformat(),
                }
            )
        return {
            "source_type": source,
            "sales_order_id": doc_id if source == "sales_order" else None,
            "sales_forecast_id": doc_id if source == "sales_forecast" else None,
            "order_code": doc_code,
            "warehouse_id": warehouse["id"],
            "warehouse_name": warehouse["name"],
            "anchor_at": anchor.isoformat(),
            "steps": preview_times,
            "warnings": self._preview_warnings(doc, enabled, source_type=source),
        }

    async def execute(
        self,
        tenant_id: int,
        operator_id: int,
        req: FlowGenerateRequest,
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        source = req.normalized_source()
        sales_order = None
        sales_forecast = None
        if source == "sales_forecast":
            sales_forecast = await self._load_and_validate_sales_forecast(
                tenant_id, int(req.sales_forecast_id or 0)
            )
            doc_id = int(sales_forecast.id)
            doc_code = str(sales_forecast.forecast_code)
            anchor_src = getattr(sales_forecast, "created_at", None)
        else:
            sales_order = await self._load_and_validate_sales_order(
                tenant_id, int(req.sales_order_id or 0)
            )
            doc_id = int(sales_order.id)
            doc_code = str(sales_order.order_code)
            anchor_src = getattr(sales_order, "created_at", None)

        warehouse = await self._resolve_warehouse(tenant_id, req.warehouse_id)
        enabled = self._enabled_steps(req.steps)
        anchor = resolve_business_datetime(req.anchor_at or anchor_src)
        planner = TimelinePlanner(
            anchor=anchor,
            default_interval=req.default_interval,
            intervals=req.intervals,
            work_schedule=req.work_schedule,
            use_work_schedule=req.use_work_schedule,
        )

        timeline: list[TimelineEntry] = []
        step_results: list[dict[str, Any]] = []
        errors: list[str] = []
        outsource_notes: list[str] = []
        ops, op_notes = await self._resolve_step_operators(
            tenant_id=tenant_id,
            fallback_user_id=operator_id,
            step_operators=req.step_operators,
            enabled=enabled,
        )
        outsource_notes.extend(op_notes)
        reporting_pool = await self._resolve_operator_pool_for_step(
            tenant_id=tenant_id,
            step_key="reporting",
            cfg=req.step_operators.get("reporting") or StepOperatorConfig(),
            fallback_user_id=ops.get("reporting", operator_id),
        )
        if len(reporting_pool) > 1:
            outsource_notes.append(
                f"reporting: 报工操作人池 {len(reporting_pool)} 人，将按批次轮换"
            )

        try:
            # 1) 需求计算
            if enabled.get("demand_computation", True):
                if source == "sales_forecast":
                    computation_id, demand_id = await self._step_push_and_execute_computation_from_forecast(
                        tenant_id=tenant_id,
                        operator_id=ops["demand_computation"],
                        sales_forecast_id=doc_id,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )
                else:
                    computation_id, demand_id = await self._step_push_and_execute_computation(
                        tenant_id=tenant_id,
                        operator_id=ops["demand_computation"],
                        sales_order_id=doc_id,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )
            else:
                raise BusinessLogicError("需求计算步骤为必选，无法关闭")

            # 2) 一键下推工单 + 采购单
            push_results = await self._step_push_orders(
                tenant_id=tenant_id,
                operator_id=ops["demand_computation"],
                computation_id=computation_id,
                planner=planner,
                timeline=timeline,
                step_results=step_results,
                run_id=run_id,
                enable_purchase=enabled.get("purchase", True),
            )
            work_orders = push_results.get("work_orders") or []
            purchase_orders = push_results.get("purchase_orders") or []
            for owo in push_results.get("outsource_work_orders") or []:
                code = owo.get("code") or owo.get("id")
                outsource_notes.append(f"委外工单 {code} 已生成，本版不自动走委外收发，需人工处理")

            # 3) 采购入库链
            if enabled.get("purchase", True) and purchase_orders:
                await self._step_purchase_inbound(
                    tenant_id=tenant_id,
                    operator_id=ops["purchase"],
                    purchase_orders=purchase_orders,
                    warehouse=warehouse,
                    planner=planner,
                    timeline=timeline,
                    step_results=step_results,
                    run_id=run_id,
                )

            # 4) 生产链（按工单）
            for wo in work_orders:
                wo_id = int(wo.get("id") or 0)
                if wo_id <= 0:
                    continue
                if enabled.get("inventory_topup", True):
                    await self._step_inventory_topup(
                        tenant_id=tenant_id,
                        operator_id=ops["inventory_topup"],
                        work_order_id=wo_id,
                        warehouse=warehouse,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )
                if enabled.get("production_picking", True):
                    await self._step_picking(
                        tenant_id=tenant_id,
                        operator_id=ops["production_picking"],
                        work_order_id=wo_id,
                        warehouse=warehouse,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )
                if enabled.get("reporting", True):
                    await self._step_reporting(
                        tenant_id=tenant_id,
                        operator_id=ops["reporting"],
                        operator_pool=reporting_pool,
                        batch_cfg=req.reporting_batches.clamp(),
                        work_order_id=wo_id,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )
                if enabled.get("finished_goods_inspection", True):
                    await self._step_fqc(
                        tenant_id=tenant_id,
                        operator_id=ops["finished_goods_inspection"],
                        work_order_id=wo_id,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )
                if enabled.get("finished_goods_receipt", True):
                    await self._step_fg_receipt(
                        tenant_id=tenant_id,
                        operator_id=ops["finished_goods_receipt"],
                        work_order_id=wo_id,
                        warehouse=warehouse,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )

            # 5) 发货 / 出库
            if enabled.get("shipment_delivery", True):
                if source == "sales_forecast":
                    await self._step_shipment_delivery_from_forecast(
                        tenant_id=tenant_id,
                        operator_id=ops["shipment_delivery"],
                        sales_forecast_id=doc_id,
                        warehouse=warehouse,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )
                else:
                    await self._step_shipment_delivery(
                        tenant_id=tenant_id,
                        operator_id=ops["shipment_delivery"],
                        sales_order_id=doc_id,
                        warehouse=warehouse,
                        planner=planner,
                        timeline=timeline,
                        step_results=step_results,
                        run_id=run_id,
                    )

            # 改写时间 + 日志回写
            await self._rewrite_timeline(tenant_id, timeline)
            await self._align_operation_logs(timeline)

        except Exception as exc:
            logger.exception("flow-generate failed: {}", exc)
            errors.append(str(exc))
            # 尽力改写已产生单据时间
            try:
                if timeline:
                    await self._rewrite_timeline(tenant_id, timeline)
                    await self._align_operation_logs(timeline)
            except Exception as rewrite_exc:
                errors.append(f"时间改写失败: {rewrite_exc}")

        return {
            "success": len(errors) == 0,
            "run_id": run_id,
            "source_type": source,
            "sales_order_id": doc_id if source == "sales_order" else None,
            "sales_forecast_id": doc_id if source == "sales_forecast" else None,
            "order_code": doc_code,
            "warehouse_id": warehouse["id"],
            "warehouse_name": warehouse["name"],
            "steps": step_results,
            "timeline": [
                {
                    "step_key": t.step_key,
                    "doc_type": t.doc_type,
                    "doc_id": t.doc_id,
                    "doc_code": t.doc_code,
                    "label": t.label,
                    "issued_at": t.issued_at.isoformat(),
                    "operation_log_id": t.operation_log_id,
                    "note": t.note,
                }
                for t in timeline
            ],
            "outsource_notes": outsource_notes,
            "operators": ops,
            "errors": errors,
        }

    # ── helpers ──────────────────────────────────────────────

    def _enabled_steps(self, steps: dict[str, bool]) -> dict[str, bool]:
        enabled = {k: True for k in STEP_KEYS}
        for k, v in (steps or {}).items():
            if k in enabled:
                enabled[k] = bool(v)
        return enabled

    async def _resolve_step_operators(
        self,
        *,
        tenant_id: int,
        fallback_user_id: int,
        step_operators: dict[str, StepOperatorConfig],
        enabled: dict[str, bool],
    ) -> tuple[dict[str, int], list[str]]:
        """解析各步骤操作用户；无可用角色用户时回退当前登录用户。"""
        notes: list[str] = []
        resolved: dict[str, int] = {}
        for key in STEP_KEYS:
            cfg = step_operators.get(key) or StepOperatorConfig()
            user_id, note = await self._pick_operator_for_step(
                tenant_id=tenant_id,
                step_key=key,
                cfg=cfg,
                fallback_user_id=fallback_user_id,
            )
            resolved[key] = user_id
            if note and enabled.get(key, True):
                notes.append(note)
        return resolved, notes

    async def _pick_operator_for_step(
        self,
        *,
        tenant_id: int,
        step_key: str,
        cfg: StepOperatorConfig,
        fallback_user_id: int,
    ) -> tuple[int, Optional[str]]:
        from infra.models.user import User

        mode = cfg.normalized_mode()
        if mode == "current":
            return int(fallback_user_id), None

        if mode == "fixed":
            uid = int(cfg.user_id or 0)
            if uid <= 0:
                return int(fallback_user_id), f"{step_key}: 未指定人员，已使用当前用户"
            user = await User.get_or_none(
                id=uid, tenant_id=tenant_id, deleted_at__isnull=True, is_active=True
            )
            if not user:
                # 平台超管可能无 tenant_id 对齐，再按 id 兜底
                user = await User.get_or_none(id=uid, deleted_at__isnull=True, is_active=True)
            if not user:
                return int(fallback_user_id), f"{step_key}: 指定用户 #{uid} 不可用，已回退当前用户"
            return int(user.id), None

        # random_role
        role_codes: list[str] = []
        if (cfg.role_code or "").strip():
            role_codes.append((cfg.role_code or "").strip())
        role_codes.extend(STEP_DEFAULT_ROLE_CODES.get(step_key, ()))
        # 去重保序
        seen: set[str] = set()
        uniq_codes: list[str] = []
        for code in role_codes:
            key = code.upper()
            if key in seen:
                continue
            seen.add(key)
            uniq_codes.append(code)

        candidates = await self._list_active_user_ids_by_role_codes(tenant_id, uniq_codes)
        if not candidates:
            codes_txt = "/".join(uniq_codes) or "(无角色)"
            return (
                int(fallback_user_id),
                f"{step_key}: 角色 {codes_txt} 下无激活用户，已回退当前用户",
            )
        picked = int(random.choice(candidates))
        return picked, f"{step_key}: 随机选用用户 #{picked}（角色 {', '.join(uniq_codes)}）"

    async def _list_active_user_ids_by_role_codes(
        self, tenant_id: int, role_codes: list[str]
    ) -> list[int]:
        if not role_codes:
            return []
        from core.models.role import Role
        from core.models.user_role import UserRole
        from infra.models.user import User

        upper = [c.upper() for c in role_codes]
        roles = await Role.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            is_active=True,
        ).all()
        role_ids = [
            int(r.id)
            for r in roles
            if (getattr(r, "code", None) or "").strip().upper() in upper
        ]
        if not role_ids:
            # 兼容大小写不敏感 / 中文名：再按 code__in 原值试一次
            role_ids = list(
                await Role.filter(
                    tenant_id=tenant_id,
                    deleted_at__isnull=True,
                    is_active=True,
                    code__in=role_codes,
                ).values_list("id", flat=True)
            )
        if not role_ids:
            return []
        user_ids = await UserRole.filter(role_id__in=role_ids).values_list("user_id", flat=True)
        if not user_ids:
            return []
        active = await User.filter(
            id__in=list({int(x) for x in user_ids if x}),
            deleted_at__isnull=True,
            is_active=True,
        ).values_list("id", flat=True)
        # 租户内用户优先；平台账号也可能挂角色
        tenant_users = await User.filter(
            id__in=list(active),
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            is_active=True,
        ).values_list("id", flat=True)
        pool = [int(x) for x in tenant_users] or [int(x) for x in active]
        return sorted(set(pool))

    async def _resolve_operator_pool_for_step(
        self,
        *,
        tenant_id: int,
        step_key: str,
        cfg: StepOperatorConfig,
        fallback_user_id: int,
    ) -> list[int]:
        """返回步骤可用操作人池；报工多批次从中轮换。"""
        from infra.models.user import User

        mode = cfg.normalized_mode()
        if mode == "current":
            return [int(fallback_user_id)]

        if mode == "fixed":
            uid = int(cfg.user_id or 0)
            if uid <= 0:
                return [int(fallback_user_id)]
            user = await User.get_or_none(
                id=uid, tenant_id=tenant_id, deleted_at__isnull=True, is_active=True
            )
            if not user:
                user = await User.get_or_none(id=uid, deleted_at__isnull=True, is_active=True)
            return [int(user.id)] if user else [int(fallback_user_id)]

        role_codes: list[str] = []
        if (cfg.role_code or "").strip():
            role_codes.append((cfg.role_code or "").strip())
        role_codes.extend(STEP_DEFAULT_ROLE_CODES.get(step_key, ()))
        seen: set[str] = set()
        uniq_codes: list[str] = []
        for code in role_codes:
            key = code.upper()
            if key in seen:
                continue
            seen.add(key)
            uniq_codes.append(code)
        candidates = await self._list_active_user_ids_by_role_codes(tenant_id, uniq_codes)
        if not candidates:
            return [int(fallback_user_id)]
        return candidates

    @staticmethod
    def _split_reporting_quantities(total: Decimal, batches: int) -> list[Decimal]:
        """把报工数量拆成多批正数，合计等于 total。"""
        total = Decimal(str(total))
        if total <= 0:
            return [Decimal("1")]
        n = max(1, int(batches))
        if total == total.to_integral_value() and total >= 1:
            int_total = int(total)
            n = min(n, int_total)
            if n <= 1:
                return [Decimal(int_total)]
            cuts = sorted(random.sample(range(1, int_total), n - 1))
            parts: list[Decimal] = []
            prev = 0
            for c in cuts + [int_total]:
                parts.append(Decimal(c - prev))
                prev = c
            return parts
        n = min(n, 20)
        if n <= 1:
            return [total]
        # 小数数量：大致均分，尾差落到最后一笔
        base = (total / Decimal(n)).quantize(Decimal("0.001"))
        parts = [base for _ in range(n - 1)]
        last = total - sum(parts)
        if last <= 0:
            return [total]
        parts.append(last)
        return parts

    def _planned_step_labels(self, enabled: dict[str, bool]) -> list[tuple[str, str]]:
        labels = [
            ("demand_computation", "需求计算"),
            ("demand_computation", "生产工单"),
            ("purchase", "采购订单/入库"),
            ("inventory_topup", "缺料补库"),
            ("production_picking", "生产领料"),
            ("reporting", "工序报工"),
            ("finished_goods_inspection", "成品检验"),
            ("finished_goods_receipt", "成品入库"),
            ("shipment_delivery", "发货/出库"),
        ]
        out: list[tuple[str, str]] = []
        for key, label in labels:
            if enabled.get(key, True):
                out.append((key, label))
        return out

    def _preview_warnings(
        self, doc: Any, enabled: dict[str, bool], *, source_type: str = "sales_order"
    ) -> list[str]:
        warnings: list[str] = []
        label = "销售预测" if source_type == "sales_forecast" else "销售订单"
        if getattr(doc, "planning_pushed_to_computation", False):
            warnings.append(f"该{label}已下推需求计算，执行将被拒绝")
        if not enabled.get("demand_computation", True):
            warnings.append("需求计算不可关闭")
        if enabled.get("reporting", True):
            warnings.append(
                "工序报工按配置拆成多批次：每批独立业务时间，操作人从角色池随机轮换"
            )
        warnings.append("需组织已开启「自动生成工单」且允许计算直推工单")
        warnings.append("BOM/工艺路线不全会导致工单或报工失败")
        if source_type == "sales_forecast":
            warnings.append("销售预测出库走 MTS 加载销售出库，不经过发货通知")
        return warnings

    async def _load_and_validate_sales_order(self, tenant_id: int, sales_order_id: int):
        from apps.kuaizhizao.models.sales_order import SalesOrder
        from apps.kuaizhizao.services.sales_order_service import SalesOrderService

        if not sales_order_id:
            raise ValidationError("请选择销售订单")
        so = await SalesOrder.get_or_none(
            tenant_id=tenant_id, id=sales_order_id, deleted_at__isnull=True
        )
        if not so:
            raise NotFoundError(f"销售订单不存在: {sales_order_id}")
        svc = SalesOrderService()
        if not svc._is_audited(getattr(so, "status", None)):
            raise BusinessLogicError("销售订单须已审核后方可生成全流程数据")
        if getattr(so, "planning_pushed_to_computation", False):
            raise BusinessLogicError(
                f"销售订单 {so.order_code} 已下推需求计算，请选择未下推的订单以避免脏数据"
            )
        return so

    async def _load_and_validate_sales_forecast(self, tenant_id: int, sales_forecast_id: int):
        from apps.kuaizhizao.constants import LEGACY_AUDITED_VALUES, ORDER_PUSHABLE_STATUSES
        from apps.kuaizhizao.models.sales_forecast import SalesForecast

        if not sales_forecast_id:
            raise ValidationError("请选择销售预测")
        forecast = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=sales_forecast_id, deleted_at__isnull=True
        )
        if not forecast:
            raise NotFoundError(f"销售预测不存在: {sales_forecast_id}")
        status = str(getattr(forecast, "status", "") or "")
        if status not in ORDER_PUSHABLE_STATUSES and status not in LEGACY_AUDITED_VALUES:
            raise BusinessLogicError("销售预测须已审核后方可生成全流程数据")
        if getattr(forecast, "planning_pushed_to_computation", False):
            raise BusinessLogicError(
                f"销售预测 {forecast.forecast_code} 已下推需求计算，请选择未下推的预测以避免脏数据"
            )
        return forecast

    async def _resolve_warehouse(
        self, tenant_id: int, warehouse_id: Optional[int]
    ) -> dict[str, Any]:
        from apps.master_data.models.warehouse import Warehouse

        if warehouse_id:
            wh = await Warehouse.get_or_none(
                tenant_id=tenant_id, id=warehouse_id, deleted_at__isnull=True
            )
            if not wh:
                raise NotFoundError(f"仓库不存在: {warehouse_id}")
            return {"id": int(wh.id), "name": wh.name or wh.code or str(wh.id)}

        wh = await Warehouse.filter(
            tenant_id=tenant_id, deleted_at__isnull=True, is_active=True
        ).order_by("id").first()
        if not wh:
            raise BusinessLogicError("组织下无可用仓库，请先维护仓库主数据")
        return {"id": int(wh.id), "name": wh.name or wh.code or str(wh.id)}

    async def _record_step(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        run_id: str,
        step_key: str,
        doc_type: str,
        doc_id: int,
        doc_code: str,
        label: str,
        issued_at: datetime,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        note: Optional[str] = None,
    ) -> None:
        log = await OperationLogService.create_operation_log(
            tenant_id=tenant_id,
            user_id=operator_id,
            operation_type="flow_generate",
            operation_module="kuaizhizao",
            operation_object_type=doc_type,
            operation_object_id=int(doc_id),
            operation_content=f"[{run_id}] {label}: {doc_code}",
            request_method="POST",
            request_path="/management/flow-generate",
        )
        entry = TimelineEntry(
            step_key=step_key,
            doc_type=doc_type,
            doc_id=int(doc_id),
            doc_code=str(doc_code or doc_id),
            issued_at=issued_at,
            label=label,
            operation_log_id=int(log.id) if log else None,
            note=note,
        )
        timeline.append(entry)
        step_results.append(
            {
                "step_key": step_key,
                "status": "ok",
                "doc_type": doc_type,
                "doc_id": entry.doc_id,
                "doc_code": entry.doc_code,
                "label": label,
                "issued_at": issued_at.isoformat(),
                "operation_log_id": entry.operation_log_id,
                "note": note,
            }
        )

    async def _rewrite_timeline(self, tenant_id: int, timeline: list[TimelineEntry]) -> None:
        by_type: dict[str, list[dict[str, Any]]] = {}
        for t in timeline:
            by_type.setdefault(t.doc_type, []).append(
                {"id": t.doc_id, "issued_at": t.issued_at}
            )
        for doc_type, items in by_type.items():
            try:
                await DocumentTimeRewriteService.rewrite_documents_at_exact_times(
                    tenant_id=tenant_id,
                    doc_type=doc_type,
                    items=items,
                    sync_operator=True,
                    rewrite_code_date=doc_type != "reporting_record",
                    preserve_business_dates=False,
                )
            except Exception as exc:
                logger.warning("rewrite {} failed: {}", doc_type, exc)
                raise

    async def _align_operation_logs(self, timeline: list[TimelineEntry]) -> None:
        for t in timeline:
            if not t.operation_log_id:
                continue
            await OperationLog.filter(id=t.operation_log_id).update(created_at=t.issued_at)

    # ── business steps ───────────────────────────────────────

    async def _step_push_and_execute_computation(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        sales_order_id: int,
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> tuple[int, Optional[int]]:
        from apps.kuaizhizao.services.sales_order_service import SalesOrderService
        from apps.kuaizhizao.services.demand_computation_service import DemandComputationService
        from apps.kuaizhizao.models.demand_computation import DemandComputation
        from apps.kuaizhizao.models.demand import Demand

        push = await SalesOrderService().push_sales_order_to_computation(
            tenant_id=tenant_id,
            sales_order_id=sales_order_id,
            created_by=operator_id,
        )
        computation_id = int(push["computation_id"])
        computation = await DemandComputation.get(id=computation_id)
        demand_id = getattr(computation, "demand_id", None)

        # 执行计算
        await DemandComputationService().execute_computation(
            tenant_id=tenant_id,
            computation_id=computation_id,
            operator_id=operator_id,
        )

        issued = planner.next("demand_computation")
        if demand_id:
            demand = await Demand.get_or_none(tenant_id=tenant_id, id=demand_id)
            if demand:
                await self._record_step(
                    tenant_id=tenant_id,
                    operator_id=operator_id,
                    run_id=run_id,
                    step_key="demand_computation",
                    doc_type="demand",
                    doc_id=int(demand.id),
                    doc_code=str(demand.demand_code),
                    label="需求计划",
                    issued_at=issued,
                    timeline=timeline,
                    step_results=step_results,
                )
                issued = planner.next("demand_computation")

        await self._record_step(
            tenant_id=tenant_id,
            operator_id=operator_id,
            run_id=run_id,
            step_key="demand_computation",
            doc_type="demand_computation",
            doc_id=computation_id,
            doc_code=str(push.get("computation_code") or computation.computation_code),
            label="需求计算",
            issued_at=issued,
            timeline=timeline,
            step_results=step_results,
        )
        return computation_id, int(demand_id) if demand_id else None

    async def _step_push_and_execute_computation_from_forecast(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        sales_forecast_id: int,
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> tuple[int, Optional[int]]:
        from apps.kuaizhizao.services.sales_service import SalesForecastService
        from apps.kuaizhizao.services.demand_computation_service import DemandComputationService
        from apps.kuaizhizao.models.demand_computation import DemandComputation
        from apps.kuaizhizao.models.demand import Demand

        push = await SalesForecastService().push_to_computation(
            tenant_id=tenant_id,
            forecast_id=sales_forecast_id,
            user_id=operator_id,
        )
        computation_id = int(push["computation_id"])
        computation = await DemandComputation.get(id=computation_id)
        demand_id = getattr(computation, "demand_id", None)

        await DemandComputationService().execute_computation(
            tenant_id=tenant_id,
            computation_id=computation_id,
            operator_id=operator_id,
        )

        issued = planner.next("demand_computation")
        if demand_id:
            demand = await Demand.get_or_none(tenant_id=tenant_id, id=demand_id)
            if demand:
                await self._record_step(
                    tenant_id=tenant_id,
                    operator_id=operator_id,
                    run_id=run_id,
                    step_key="demand_computation",
                    doc_type="demand",
                    doc_id=int(demand.id),
                    doc_code=str(demand.demand_code),
                    label="需求计划",
                    issued_at=issued,
                    timeline=timeline,
                    step_results=step_results,
                )
                issued = planner.next("demand_computation")

        await self._record_step(
            tenant_id=tenant_id,
            operator_id=operator_id,
            run_id=run_id,
            step_key="demand_computation",
            doc_type="demand_computation",
            doc_id=computation_id,
            doc_code=str(push.get("computation_code") or computation.computation_code),
            label="需求计算",
            issued_at=issued,
            timeline=timeline,
            step_results=step_results,
        )
        return computation_id, int(demand_id) if demand_id else None

    async def _step_push_orders(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        computation_id: int,
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
        enable_purchase: bool,
    ) -> dict[str, Any]:
        from apps.kuaizhizao.services.demand_computation_service import DemandComputationService

        result = await DemandComputationService().push_all(
            tenant_id=tenant_id,
            computation_id=computation_id,
            created_by=operator_id,
            production="work_order",
            purchase="purchase_order" if enable_purchase else None,
            include_outsource=True,
            push_mode="confirm",
        )
        results = result.get("results") or {}
        for wo in results.get("work_orders") or []:
            wo_id = int(wo.get("id") or 0)
            if wo_id <= 0:
                continue
            issued = planner.next("demand_computation")
            await self._record_step(
                tenant_id=tenant_id,
                operator_id=operator_id,
                run_id=run_id,
                step_key="demand_computation",
                doc_type="work_order",
                doc_id=wo_id,
                doc_code=str(wo.get("code") or wo_id),
                label="生产工单",
                issued_at=issued,
                timeline=timeline,
                step_results=step_results,
            )
        for po in results.get("purchase_orders") or []:
            po_id = int(po.get("id") or 0)
            if po_id <= 0:
                continue
            issued = planner.next("purchase")
            await self._record_step(
                tenant_id=tenant_id,
                operator_id=operator_id,
                run_id=run_id,
                step_key="purchase",
                doc_type="purchase_order",
                doc_id=po_id,
                doc_code=str(po.get("order_code") or po.get("code") or po_id),
                label="采购订单",
                issued_at=issued,
                timeline=timeline,
                step_results=step_results,
            )
        return results

    async def _step_purchase_inbound(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        purchase_orders: list[dict[str, Any]],
        warehouse: dict[str, Any],
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from apps.kuaizhizao.services.purchase_service import PurchaseService
        from apps.kuaizhizao.schemas.purchase import PurchaseOrderApprove
        from apps.kuaizhizao.services.quality_service import IncomingInspectionService
        from apps.kuaizhizao.services.warehouse_service import PurchaseReceiptService

        po_svc = PurchaseService()
        iqc_svc = IncomingInspectionService()
        receipt_svc = PurchaseReceiptService()

        for po in purchase_orders:
            po_id = int(po.get("id") or 0)
            if po_id <= 0:
                continue
            try:
                await po_svc.approve_purchase_order(
                    tenant_id=tenant_id,
                    order_id=po_id,
                    approve_data=PurchaseOrderApprove(approved=True),
                    approved_by=operator_id,
                )
            except Exception as exc:
                logger.info("PO {} approve skipped/failed: {}", po_id, exc)

            receipt_id: Optional[int] = None
            receipt_code: Optional[str] = None
            try:
                inspections = await iqc_svc.create_inspection_from_purchase_order(
                    tenant_id=tenant_id,
                    purchase_order_id=po_id,
                    created_by=operator_id,
                )
                for insp in inspections or []:
                    insp_id = int(getattr(insp, "id", 0) or 0)
                    if insp_id <= 0:
                        continue
                    issued = planner.next("purchase")
                    await self._record_step(
                        tenant_id=tenant_id,
                        operator_id=operator_id,
                        run_id=run_id,
                        step_key="purchase",
                        doc_type="incoming_inspection",
                        doc_id=insp_id,
                        doc_code=str(getattr(insp, "inspection_code", None) or insp_id),
                        label="来料检验",
                        issued_at=issued,
                        timeline=timeline,
                        step_results=step_results,
                    )
                    try:
                        await iqc_svc.approve_inspection(
                            tenant_id=tenant_id,
                            inspection_id=insp_id,
                            approved_by=operator_id,
                            is_auto_approve=True,
                        )
                    except Exception as exc:
                        logger.info("IQC approve {}: {}", insp_id, exc)
                    try:
                        pushed = await iqc_svc.push_to_purchase_receipt(
                            tenant_id=tenant_id,
                            inspection_id=insp_id,
                            created_by=operator_id,
                            warehouse_id=warehouse["id"],
                        )
                        receipt_id = int(pushed.get("receipt_id") or 0) or None
                        receipt_code = pushed.get("receipt_code")
                    except Exception as exc:
                        logger.info("IQC push receipt {}: {}", insp_id, exc)
            except Exception as exc:
                logger.info("IQC from PO {} failed, fallback push_to_receipt: {}", po_id, exc)
                try:
                    pushed = await po_svc.push_to_receipt(
                        tenant_id=tenant_id,
                        order_id=po_id,
                        created_by=operator_id,
                        warehouse_id=warehouse["id"],
                    )
                    receipt_id = int(pushed.get("id") or pushed.get("receipt_id") or 0) or None
                    receipt_code = pushed.get("receipt_code") or pushed.get("code")
                except Exception as exc2:
                    step_results.append(
                        {
                            "step_key": "purchase",
                            "status": "error",
                            "label": f"采购入库(PO {po_id})",
                            "message": str(exc2),
                        }
                    )
                    continue

            if receipt_id:
                try:
                    await receipt_svc.confirm_receipt(
                        tenant_id=tenant_id,
                        receipt_id=receipt_id,
                        confirmed_by=operator_id,
                    )
                except Exception as exc:
                    logger.info("confirm purchase receipt {}: {}", receipt_id, exc)
                issued = planner.next("purchase")
                await self._record_step(
                    tenant_id=tenant_id,
                    operator_id=operator_id,
                    run_id=run_id,
                    step_key="purchase",
                    doc_type="purchase_receipt",
                    doc_id=receipt_id,
                    doc_code=str(receipt_code or receipt_id),
                    label="采购入库",
                    issued_at=issued,
                    timeline=timeline,
                    step_results=step_results,
                )

    async def _step_inventory_topup(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        work_order_id: int,
        warehouse: dict[str, Any],
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from apps.kuaizhizao.services.work_order_service import WorkOrderService
        from apps.kuaizhizao.services.warehouse_service import OtherInboundService
        from apps.kuaizhizao.schemas.warehouse import OtherInboundCreate, OtherInboundItemCreate
        from apps.kuaizhizao.utils.issue_method_resolver import is_pick_list_material

        try:
            kitting = await WorkOrderService().get_work_order_kitting_analysis(
                tenant_id, work_order_id
            )
        except Exception as exc:
            logger.info("kitting analysis skip: {}", exc)
            return

        shortage_items: list[OtherInboundItemCreate] = []
        for item in getattr(kitting, "items", None) or []:
            if not is_pick_list_material(
                getattr(item, "issue_method", None),
                getattr(item, "source_type", None),
            ):
                continue
            need = Decimal(str(getattr(item, "shortage_quantity", 0) or 0))
            if need <= 0:
                # 兜底：需求 − 已领 − 主仓 − 线边
                required = Decimal(str(getattr(item, "required_quantity", 0) or 0))
                picked = Decimal(str(getattr(item, "picked_quantity", 0) or 0))
                main_avail = Decimal(str(getattr(item, "main_warehouse_available", 0) or 0))
                line_avail = Decimal(str(getattr(item, "line_side_available", 0) or 0))
                need = required - picked - main_avail - line_avail
            if need <= 0:
                continue
            mid = int(getattr(item, "material_id", 0) or 0)
            if mid <= 0:
                continue
            shortage_items.append(
                OtherInboundItemCreate(
                    material_id=mid,
                    material_code=str(getattr(item, "material_code", "") or "") or None,
                    material_name=str(getattr(item, "material_name", "") or "") or None,
                    material_unit=str(getattr(item, "material_unit", "") or "个") or "个",
                    inbound_quantity=float(need),
                )
            )
        if not shortage_items:
            return

        inbound = await OtherInboundService().create_other_inbound(
            tenant_id=tenant_id,
            inbound_data=OtherInboundCreate(
                reason_type="其他",
                reason_desc=f"流程造数补库 WO#{work_order_id}",
                warehouse_id=warehouse["id"],
                warehouse_name=warehouse["name"],
                notes="flow_generate inventory topup",
                items=shortage_items,
            ),
            created_by=operator_id,
        )
        inbound_id = int(inbound.id)
        try:
            await OtherInboundService().confirm_inbound(
                tenant_id=tenant_id,
                inbound_id=inbound_id,
                confirmed_by=operator_id,
            )
        except Exception as exc:
            logger.info("confirm other inbound {}: {}", inbound_id, exc)

        issued = planner.next("inventory_topup")
        await self._record_step(
            tenant_id=tenant_id,
            operator_id=operator_id,
            run_id=run_id,
            step_key="inventory_topup",
            doc_type="other_inbound",
            doc_id=inbound_id,
            doc_code=str(getattr(inbound, "inbound_code", None) or inbound_id),
            label="其他入库(补库)",
            issued_at=issued,
            timeline=timeline,
            step_results=step_results,
        )

    async def _step_picking(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        work_order_id: int,
        warehouse: dict[str, Any],
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from apps.kuaizhizao.services.warehouse_service import ProductionPickingService

        svc = ProductionPickingService()
        picking = await svc.quick_pick_from_work_order(
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            created_by=operator_id,
            warehouse_id=warehouse["id"],
            warehouse_name=warehouse["name"],
        )
        picking_id = int(picking.id)
        try:
            await svc.confirm_picking(
                tenant_id=tenant_id,
                picking_id=picking_id,
                confirmed_by=operator_id,
            )
        except Exception as exc:
            logger.info("confirm picking {}: {}", picking_id, exc)

        issued = planner.next("production_picking")
        await self._record_step(
            tenant_id=tenant_id,
            operator_id=operator_id,
            run_id=run_id,
            step_key="production_picking",
            doc_type="production_picking",
            doc_id=picking_id,
            doc_code=str(getattr(picking, "picking_code", None) or picking_id),
            label="生产领料",
            issued_at=issued,
            timeline=timeline,
            step_results=step_results,
        )

    async def _step_reporting(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        operator_pool: Optional[list[int]] = None,
        batch_cfg: Optional[ReportingBatchConfig] = None,
        work_order_id: int,
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from apps.kuaizhizao.models.work_order import WorkOrder
        from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
        from apps.kuaizhizao.services.reporting_service import ReportingService
        from apps.kuaizhizao.schemas.reporting_record import ReportingRecordCreate
        from infra.models.user import User

        wo = await WorkOrder.get_or_none(
            tenant_id=tenant_id, id=work_order_id, deleted_at__isnull=True
        )
        if not wo:
            return
        ops = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            deleted_at__isnull=True,
        ).order_by("sequence").all()
        if not ops:
            step_results.append(
                {
                    "step_key": "reporting",
                    "status": "skipped",
                    "label": f"报工 WO#{work_order_id}",
                    "message": "工单无工序，跳过报工",
                }
            )
            return

        pool = [int(x) for x in (operator_pool or []) if int(x) > 0]
        if not pool:
            pool = [int(operator_id)]
        cfg = (batch_cfg or ReportingBatchConfig()).clamp()
        qty = Decimal(str(wo.quantity or 1))
        if qty <= 0:
            qty = Decimal("1")

        user_cache: dict[int, str] = {}

        async def _worker_name(uid: int) -> str:
            if uid in user_cache:
                return user_cache[uid]
            user = await User.get_or_none(id=uid)
            name = str(uid)
            if user:
                name = (
                    getattr(user, "display_name", None)
                    or getattr(user, "username", None)
                    or str(uid)
                )
            user_cache[uid] = str(name)
            return user_cache[uid]

        svc = ReportingService()
        for op in ops:
            op_id = int(getattr(op, "operation_id", 0) or op.id)
            op_name = str(getattr(op, "operation_name", None) or f"工序{op_id}")
            batch_count = cfg.pick_batch_count(qty)
            parts = self._split_reporting_quantities(qty, batch_count)
            # 打乱操作人顺序，尽量多角色轮换
            rotating = list(pool)
            random.shuffle(rotating)
            for batch_idx, part_qty in enumerate(parts, start=1):
                worker_id = rotating[(batch_idx - 1) % len(rotating)]
                worker_name = await _worker_name(worker_id)
                reported_at = now_utc()
                create_data = ReportingRecordCreate(
                    work_order_id=work_order_id,
                    work_order_code=str(wo.code),
                    work_order_name=str(wo.name or wo.code),
                    operation_id=op_id,
                    operation_code=str(getattr(op, "operation_code", None) or op_id),
                    operation_name=op_name,
                    worker_id=worker_id,
                    worker_name=worker_name,
                    reported_quantity=part_qty,
                    qualified_quantity=part_qty,
                    unqualified_quantity=Decimal("0"),
                    work_hours=Decimal("1"),
                    reported_at=reported_at,
                    remarks=f"flow_generate batch={batch_idx}/{len(parts)}",
                )
                record = await svc.create_reporting_record(
                    tenant_id=tenant_id,
                    reporting_data=create_data,
                    reported_by=worker_id,
                    entry_mode="quick",
                )
                record_id = int(record.id)
                try:
                    await svc.approve_reporting_record(
                        tenant_id=tenant_id,
                        record_id=record_id,
                        approved_by=worker_id,
                        is_auto_approve=True,
                    )
                except Exception as exc:
                    logger.info("approve reporting {}: {}", record_id, exc)

                issued = planner.next("reporting")
                await self._record_step(
                    tenant_id=tenant_id,
                    operator_id=worker_id,
                    run_id=run_id,
                    step_key="reporting",
                    doc_type="reporting_record",
                    doc_id=record_id,
                    doc_code=f"RR-{record_id}",
                    label=f"报工-{op_name}·批{batch_idx}/{len(parts)}·{worker_name}",
                    issued_at=issued,
                    timeline=timeline,
                    step_results=step_results,
                    note=f"qty={part_qty} worker=#{worker_id}",
                )

    async def _step_fqc(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        work_order_id: int,
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from apps.kuaizhizao.services.quality_service import FinishedGoodsInspectionService

        svc = FinishedGoodsInspectionService()
        try:
            insp = await svc.create_inspection_from_work_order(
                tenant_id=tenant_id,
                work_order_id=work_order_id,
                created_by=operator_id,
            )
        except Exception as exc:
            step_results.append(
                {
                    "step_key": "finished_goods_inspection",
                    "status": "skipped",
                    "label": f"成品检验 WO#{work_order_id}",
                    "message": str(exc),
                }
            )
            return

        insp_id = int(insp.id)
        try:
            await svc.approve_inspection(
                tenant_id=tenant_id,
                inspection_id=insp_id,
                approved_by=operator_id,
                is_auto_approve=True,
            )
        except Exception as exc:
            logger.info("approve FQC {}: {}", insp_id, exc)

        issued = planner.next("finished_goods_inspection")
        await self._record_step(
            tenant_id=tenant_id,
            operator_id=operator_id,
            run_id=run_id,
            step_key="finished_goods_inspection",
            doc_type="finished_goods_inspection",
            doc_id=insp_id,
            doc_code=str(getattr(insp, "inspection_code", None) or insp_id),
            label="成品检验",
            issued_at=issued,
            timeline=timeline,
            step_results=step_results,
        )

    async def _step_fg_receipt(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        work_order_id: int,
        warehouse: dict[str, Any],
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from apps.kuaizhizao.services.warehouse_service import FinishedGoodsReceiptService

        svc = FinishedGoodsReceiptService()
        receipt = await svc.quick_receipt_from_work_order(
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            created_by=operator_id,
            warehouse_id=warehouse["id"],
            warehouse_name=warehouse["name"],
        )
        receipt_id = int(receipt.id)
        try:
            await svc.confirm_receipt(
                tenant_id=tenant_id,
                receipt_id=receipt_id,
                confirmed_by=operator_id,
            )
        except Exception as exc:
            logger.info("confirm FG receipt {}: {}", receipt_id, exc)

        issued = planner.next("finished_goods_receipt")
        await self._record_step(
            tenant_id=tenant_id,
            operator_id=operator_id,
            run_id=run_id,
            step_key="finished_goods_receipt",
            doc_type="finished_goods_receipt",
            doc_id=receipt_id,
            doc_code=str(getattr(receipt, "receipt_code", None) or receipt_id),
            label="成品入库",
            issued_at=issued,
            timeline=timeline,
            step_results=step_results,
        )

    async def _step_shipment_delivery(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        sales_order_id: int,
        warehouse: dict[str, Any],
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from infra.services.business_config_service import BusinessConfigService
        from apps.kuaizhizao.services.sales_order_service import SalesOrderService
        from apps.kuaizhizao.services.shipment_notice_service import ShipmentNoticeService
        from apps.kuaizhizao.services.warehouse_service import SalesDeliveryService

        so_svc = SalesOrderService()
        require_notice = await BusinessConfigService().require_shipment_notice_before_delivery(
            tenant_id
        )
        delivery_id: Optional[int] = None
        delivery_code: Optional[str] = None

        if require_notice:
            notice_result = await so_svc.push_sales_order_to_shipment_notice(
                tenant_id=tenant_id,
                sales_order_id=sales_order_id,
                created_by=operator_id,
                warehouse_id=warehouse["id"],
                warehouse_name=warehouse["name"],
            )
            notice_id = int(notice_result.get("notice_id") or 0)
            if notice_id:
                issued = planner.next("shipment_delivery")
                await self._record_step(
                    tenant_id=tenant_id,
                    operator_id=operator_id,
                    run_id=run_id,
                    step_key="shipment_delivery",
                    doc_type="shipment_notice",
                    doc_id=notice_id,
                    doc_code=str(notice_result.get("notice_code") or notice_id),
                    label="发货通知",
                    issued_at=issued,
                    timeline=timeline,
                    step_results=step_results,
                )
                notified = await ShipmentNoticeService().notify_warehouse(
                    tenant_id=tenant_id,
                    notice_id=notice_id,
                    notified_by=operator_id,
                )
                delivery_id = int(
                    getattr(notified, "sales_delivery_id", None)
                    or notice_result.get("sales_delivery_id")
                    or 0
                ) or None
                delivery_code = (
                    getattr(notified, "sales_delivery_code", None)
                    or notice_result.get("sales_delivery_code")
                )
                related = getattr(notified, "related_sales_delivery_ids", None) or []
                if not delivery_id and related:
                    first = related[0] if isinstance(related[0], dict) else {"id": related[0]}
                    delivery_id = int(first.get("id") or 0) or None
                    delivery_code = first.get("code")
        else:
            pushed = await so_svc.push_sales_order_to_delivery(
                tenant_id=tenant_id,
                sales_order_id=sales_order_id,
                created_by=operator_id,
                warehouse_id=warehouse["id"],
                warehouse_name=warehouse["name"],
            )
            delivery_id = int(pushed.get("delivery_id") or 0) or None
            delivery_code = pushed.get("delivery_code")

        if delivery_id:
            try:
                await SalesDeliveryService().confirm_delivery(
                    tenant_id=tenant_id,
                    delivery_id=delivery_id,
                    confirmed_by=operator_id,
                )
            except Exception as exc:
                logger.info("confirm delivery {}: {}", delivery_id, exc)
            issued = planner.next("shipment_delivery")
            await self._record_step(
                tenant_id=tenant_id,
                operator_id=operator_id,
                run_id=run_id,
                step_key="shipment_delivery",
                doc_type="sales_delivery",
                doc_id=delivery_id,
                doc_code=str(delivery_code or delivery_id),
                label="销售出库",
                issued_at=issued,
                timeline=timeline,
                step_results=step_results,
            )
        else:
            step_results.append(
                {
                    "step_key": "shipment_delivery",
                    "status": "error",
                    "label": "销售出库",
                    "message": "未能生成销售出库单",
                }
            )

    async def _step_shipment_delivery_from_forecast(
        self,
        *,
        tenant_id: int,
        operator_id: int,
        sales_forecast_id: int,
        warehouse: dict[str, Any],
        planner: TimelinePlanner,
        timeline: list[TimelineEntry],
        step_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        from apps.kuaizhizao.services.warehouse_service import SalesDeliveryService

        delivery = await SalesDeliveryService().pull_from_sales_forecast(
            tenant_id=tenant_id,
            sales_forecast_id=sales_forecast_id,
            created_by=operator_id,
            warehouse_id=warehouse["id"],
            warehouse_name=warehouse["name"],
        )
        delivery_id = int(getattr(delivery, "id", None) or 0)
        delivery_code = getattr(delivery, "delivery_code", None)
        if delivery_id:
            try:
                await SalesDeliveryService().confirm_delivery(
                    tenant_id=tenant_id,
                    delivery_id=delivery_id,
                    confirmed_by=operator_id,
                )
            except Exception as exc:
                logger.info("confirm forecast delivery {}: {}", delivery_id, exc)
            issued = planner.next("shipment_delivery")
            await self._record_step(
                tenant_id=tenant_id,
                operator_id=operator_id,
                run_id=run_id,
                step_key="shipment_delivery",
                doc_type="sales_delivery",
                doc_id=delivery_id,
                doc_code=str(delivery_code or delivery_id),
                label="销售出库(预测)",
                issued_at=issued,
                timeline=timeline,
                step_results=step_results,
            )
        else:
            step_results.append(
                {
                    "step_key": "shipment_delivery",
                    "status": "error",
                    "label": "销售出库(预测)",
                    "message": "未能从销售预测生成销售出库单",
                }
            )


def parse_intervals(raw: Optional[dict[str, Any]]) -> dict[str, IntervalConfig]:
    out: dict[str, IntervalConfig] = {}
    if not raw:
        return out
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        out[str(key)] = IntervalConfig(
            min_seconds=int(val.get("min_seconds", DEFAULT_INTERVAL_MIN)),
            max_seconds=int(val.get("max_seconds", DEFAULT_INTERVAL_MAX)),
        ).clamp()
    return out


def parse_step_operators(raw: Optional[dict[str, Any]]) -> dict[str, StepOperatorConfig]:
    out: dict[str, StepOperatorConfig] = {}
    if not raw:
        return out
    for key, val in raw.items():
        step_key = str(key)
        if step_key not in STEP_KEYS:
            continue
        if not isinstance(val, dict):
            continue
        user_id = val.get("user_id")
        out[step_key] = StepOperatorConfig(
            mode=str(val.get("mode") or "random_role"),
            user_id=int(user_id) if user_id not in (None, "", 0, "0") else None,
            role_code=(str(val.get("role_code")).strip() if val.get("role_code") else None),
        )
    return out


def parse_reporting_batches(raw: Optional[dict[str, Any]]) -> ReportingBatchConfig:
    if not raw:
        return ReportingBatchConfig(
            DEFAULT_REPORTING_BATCHES_MIN, DEFAULT_REPORTING_BATCHES_MAX
        ).clamp()
    return ReportingBatchConfig(
        min_batches=int(raw.get("min_batches", DEFAULT_REPORTING_BATCHES_MIN)),
        max_batches=int(raw.get("max_batches", DEFAULT_REPORTING_BATCHES_MAX)),
    ).clamp()


def parse_work_schedule(raw: Optional[dict[str, Any]]) -> Optional[WorkScheduleParams]:
    if not raw:
        return None
    schedule = WorkScheduleParams(
        weekdays=list(raw.get("weekdays") or [0, 1, 2, 3, 4]),
        start_time=str(raw.get("start_time") or "09:00"),
        end_time=str(raw.get("end_time") or "18:00"),
        lookback_days=int(raw.get("lookback_days") or 14),
    )
    schedule.validate()
    return schedule
