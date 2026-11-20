"""规则式贪心排产引擎：逾期优先、工位最早可行槽（工作日/工作时段内）。"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from tortoise.timezone import now as tz_now

from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.services.rolling_schedule_service import RollingScheduleService
from apps.kuaizhizao.services.scheduling_engine.base import SchedulingPlanRequest
from apps.kuaizhizao.services.scheduling_engine.strategies import (
    STRATEGY_CHANGEOVER_MIN,
    STRATEGY_LOAD_BALANCE,
    normalize_strategy,
    strategy_label,
)
from apps.kuaizhizao.services.scheduling_freeze import freeze_anchor_datetime
from apps.kuaizhizao.services.visual_scheduling_service import VisualSchedulingService
from apps.kuaizhizao.services.work_order_score_service import WorkOrderScoreService
from apps.kuaizhizao.utils.work_order_operation_scheduling import (
    has_operation_hours,
    operation_total_hours,
)
from apps.kuaizhizao.utils.working_time import (
    add_working_hours,
    find_earliest_working_slot,
    find_latest_working_slot,
    load_scheduling_work_context,
    subtract_working_hours,
)
from apps.kuaizhizao.models.outsource_order import OutsourceOrder
from apps.kuaizhizao.utils.outsource_operation import occupies_factory_capacity
from apps.master_data.models.work_calendar import StationUnavailableWindow
from apps.master_data.models.factory import Workstation
from core.utils.timezone_utils import make_aware, site_timezone_name, to_site_date, to_site_timezone


PRIORITY_WEIGHT = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def _business_tz_name() -> str:
    return site_timezone_name()


def _scheduling_dt(value: datetime) -> datetime:
    """统一为业务时区 aware，便于与 ORM DatetimeField 比较。"""
    return to_site_timezone(value)


def _plan_day_bounds(plan_date: date) -> Tuple[datetime, datetime]:
    tz_name = _business_tz_name()
    start = make_aware(datetime.combine(plan_date, datetime.min.time()), tz_name)
    end = make_aware(datetime.combine(plan_date, datetime.max.time()), tz_name)
    return start, end


def _is_schedulable_status(wo: WorkOrder) -> bool:
    return wo.status in {"released", "in_progress", "draft"}


def _is_overdue(wo: WorkOrder, now: datetime) -> bool:
    if wo.status in {"completed", "cancelled"}:
        return False
    planned_end = _scheduling_dt(wo.planned_end_date) if wo.planned_end_date else None
    return bool(planned_end and planned_end < now)



def _timeline_3(intervals: List[Tuple]) -> List[Tuple[datetime, datetime, int]]:
    """Strip product_id for slot finder."""
    out = []
    for iv in intervals:
        if len(iv) >= 3:
            out.append((iv[0], iv[1], int(iv[2])))
    return out


def _prev_interval(timeline: List[Tuple], before: datetime) -> Optional[Tuple]:
    prev = None
    for iv in timeline:
        if iv[1] <= before and (prev is None or iv[1] > prev[1]):
            prev = iv
    return prev


def _apply_changeover_earliest(
    timeline: List[Tuple],
    earliest: datetime,
    product_id: int,
    changeover_ctx,
    *,
    production_line_id: int,
    holidays,
    work_hours,
    overtime,
) -> Tuple[datetime, Optional[str]]:
    """返回 (earliest, reason_code|None)。禁共线时 reason_code=forbid_same_line。"""
    if product_id <= 0 or not timeline:
        return earliest, None
    prev = _prev_interval(timeline, earliest)
    if prev is None:
        return earliest, None
    prev_pid = int(prev[3]) if len(prev) > 3 else 0
    if prev_pid <= 0 or prev_pid == product_id:
        return earliest, None
    hours, forbid, source = changeover_ctx.lookup(
        prev_pid, product_id, production_line_id=production_line_id or None
    )
    if forbid:
        return earliest, "forbid_same_line"
    if hours <= 0:
        return earliest, None
    ready = add_working_hours(
        prev[1],
        hours,
        holidays=holidays,
        config=work_hours,
        overtime=overtime,
    )
    if ready > earliest:
        return max(earliest, ready), f"changeover:{source}"
    return earliest, None


def _neighbor_changeover_hours(
    changeover_ctx,
    from_pid: int,
    to_pid: int,
    *,
    production_line_id: int,
    fallback_hours: float,
) -> Tuple[float, bool, str]:
    if changeover_ctx is not None:
        return changeover_ctx.lookup(
            from_pid, to_pid, production_line_id=production_line_id or None
        )
    if from_pid <= 0 or to_pid <= 0 or from_pid == to_pid:
        return 0.0, False, "same"
    if fallback_hours > 0:
        return float(fallback_hours), False, "fallback"
    return 0.0, False, "none"


def _timeline_occupied_hours(
    timeline: List[Tuple[datetime, datetime, int, int]],
) -> float:
    total = 0.0
    for iv in timeline:
        start, end = iv[0], iv[1]
        delta = (end - start).total_seconds() / 3600.0
        if delta > 0:
            total += delta
    return total


class GreedyRulesSchedulingEngine:
    async def plan(self, request: SchedulingPlanRequest) -> Dict[str, Any]:
        tenant_id = request.tenant_id
        now = tz_now()
        t0 = time.perf_counter()
        execution_log: List[Dict[str, Any]] = []
        strategy = normalize_strategy(getattr(request, "strategy", None))

        def _log(step: str, message: str, mark: Optional[float] = None) -> float:
            stamp = time.perf_counter()
            elapsed = None if mark is None else round((stamp - mark) * 1000, 1)
            execution_log.append(
                {"step": step, "message": message, "elapsed_ms": elapsed}
            )
            return stamp

        mark = _log(
            "start",
            f"开始排产策略「{strategy_label(strategy)}」（{strategy}）",
        )
        vs = VisualSchedulingService()
        constraints = await vs._load_constraints(tenant_id)
        freeze_days = int(constraints.get("freeze_horizon_days", 0))
        now_business = to_site_timezone(now)
        freeze_anchor = make_aware(
            freeze_anchor_datetime(freeze_days, now=now_business.replace(tzinfo=None)),
            _business_tz_name(),
        ) + timedelta(seconds=1)

        rolling_svc = RollingScheduleService()
        anchor_day = request.plan_date or await rolling_svc.get_next_workday(
            tenant_id, to_site_timezone(now).date()
        )
        span_days = max(120, int(constraints.get("rolling_horizon_days", 14)) * 3)
        holidays, work_hours, overtime = await load_scheduling_work_context(
            tenant_id, around=anchor_day, span_days=span_days
        )
        changeover_hours = float(constraints.get("setup_changeover_hours") or 0.0)
        schedule_mode = str(constraints.get("schedule_mode") or "forward").strip().lower()
        material_hard = bool(constraints.get("material_hard_constraint"))
        resource_mode = str(constraints.get("resource_mode") or "workstation").strip().lower()
        line_exclusive = bool(constraints.get("line_exclusive", True))
        use_line_resource = resource_mode == "production_line"
        station_rows = await Workstation.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).values("id", "max_parallel", "production_line_id")
        station_parallel = {
            int(r["id"]): max(1, int(r.get("max_parallel") or 1)) for r in station_rows
        }
        line_capacity_map = {}
        line_allow_map: Dict[int, Set[int]] = {}
        duration_hours_from_takt = None
        default_line_id = 0
        configured_line_ids: List[int] = []
        if use_line_resource:
            from apps.kuaizhizao.services.line_capacity_lookup import (
                duration_hours_from_takt as _duration_hours_from_takt,
                load_line_capacity_map,
            )
            from apps.kuaizhizao.services.line_product_lookup import (
                eligible_line_ids_for_product,
                line_accepts_product,
                load_line_allowed_product_ids,
            )

            line_capacity_map = await load_line_capacity_map(tenant_id)
            line_allow_map = await load_line_allowed_product_ids(tenant_id)
            duration_hours_from_takt = _duration_hours_from_takt
            if not line_capacity_map:
                _log("abort", "产线节拍未配置", mark)
                return {
                    "summary": "产线节拍未配置",
                    "strategy": strategy,
                    "strategy_name": strategy_label(strategy),
                    "warnings": ["请先在行业包「产线节拍」维护节拍与日产能后再自动重排"],
                    "reasons": [],
                    "execution_log": execution_log,
                    "unfreezed": [],
                    "work_order_adjustments": [],
                    "operation_adjustments": [],
                    "operation_station_adjustments": [],
                    "operation_production_line_adjustments": [],
                }
            # 仅一条已配节拍+日产能的产线时，可默认指派（对齐前端拖入单线自动盖产线）
            configured_line_ids = [
                lid
                for lid, cap in line_capacity_map.items()
                if float(cap.takt_seconds or 0) > 0 and float(cap.daily_capacity_qty or 0) > 0
            ]
            default_line_id = configured_line_ids[0] if len(configured_line_ids) == 1 else 0

        # 锚点为业务墙钟（厂级上班时刻），须按站点时区 make_aware，不可走 to_site_timezone（naive=UTC）
        anchor_start = make_aware(
            datetime.combine(anchor_day, work_hours.start),
            _business_tz_name(),
        )

        candidate_ids = await self._resolve_candidate_ids(
            tenant_id, request, now, use_line_resource=use_line_resource
        )
        mark = _log("load_candidates", f"待排工单 {len(candidate_ids)} 张", mark)
        if not candidate_ids:
            _log("abort", "无可重排工单", mark)
            return {
                "summary": "无可重排工单",
                "strategy": strategy,
                "strategy_name": strategy_label(strategy),
                "warnings": ["未找到符合范围的工单"],
                "reasons": [],
                "execution_log": execution_log,
                "unfreezed": [],
                "work_order_adjustments": [],
                "operation_adjustments": [],
                "operation_station_adjustments": [],
                "operation_production_line_adjustments": [],
            }

        wos = await WorkOrder.filter(
            tenant_id=tenant_id,
            id__in=candidate_ids,
            deleted_at__isnull=True,
        ).all()
        score_map = await WorkOrderScoreService().batch_get_scores(
            tenant_id, [w.id for w in wos], "scheduling"
        )

        # 本地 WorkOrder 无上游 required_date：期望交期走 demand_item → 需求行交期
        demand_ids = {int(w.demand_item_id or 0) for w in wos if int(w.demand_item_id or 0) > 0}
        expected_map: Dict[int, Any] = {}
        if demand_ids:
            from apps.kuaizhizao.models.demand_item import DemandItem

            for di in await DemandItem.filter(tenant_id=tenant_id, id__in=list(demand_ids)).all():
                if di.delivery_date:
                    # DateField → 站点日界 aware datetime
                    expected_map[int(di.id)] = make_aware(
                        datetime.combine(di.delivery_date, datetime.min.time()),
                        _business_tz_name(),
                    )

        def sort_key(wo: WorkOrder) -> Tuple:
            delay = 0
            planned_end = _scheduling_dt(wo.planned_end_date) if wo.planned_end_date else None
            if planned_end and planned_end < now:
                delay = (now - planned_end).days
            due_key = planned_end.timestamp() if planned_end else float("inf")
            req_raw = expected_map.get(int(wo.demand_item_id or 0))
            req = _scheduling_dt(req_raw) if req_raw else None
            expected_key = req.timestamp() if req else due_key
            pri = PRIORITY_WEIGHT.get(str(wo.priority or "normal"), 2)
            cached = score_map.get(wo.id)
            score = float(cached.composite_score) if cached and cached.composite_score is not None else 0.0
            product_id = int(wo.product_id or 0)
            if strategy == STRATEGY_CHANGEOVER_MIN:
                # 同产品簇优先，簇内仍按逾期/期望交期
                return (product_id if product_id > 0 else 10**9, -delay, expected_key, pri, wo.id)
            # due_date / load_balance：交期与逾期优先；负荷在资源指派时处理
            return (-delay, expected_key, pri, -score, wo.id)

        wos.sort(key=sort_key)
        mark = _log(
            "sort",
            f"已按策略「{strategy_label(strategy)}」排序 {len(wos)} 张工单",
            mark,
        )

        if use_line_resource:
            existing_ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                planned_start_date__isnull=False,
                planned_end_date__isnull=False,
                assigned_production_line_id__gt=0,
            ).all()
        else:
            existing_ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                planned_start_date__isnull=False,
                planned_end_date__isnull=False,
                assigned_station_id__gt=0,
            ).all()
        candidate_op_ids = set()
        for wo in wos:
            for op in await WorkOrderOperation.filter(
                tenant_id=tenant_id, work_order_id=wo.id, deleted_at__isnull=True
            ).all():
                if op.status not in {"completed", "cancelled"}:
                    candidate_op_ids.add(int(op.id))

        # (start, end, op_id, product_id)；产线模式下 key 为 production_line_id
        resource_timeline: Dict[int, List[Tuple[datetime, datetime, int, int]]] = defaultdict(list)
        # 日产能：key=(day, line_id) -> {wo_id: qty}
        day_line_qty: Dict[Tuple[date, int], Dict[int, float]] = defaultdict(dict)
        existing_wo_ids = list({int(op.work_order_id) for op in existing_ops if op.work_order_id})
        product_by_wo: Dict[int, int] = {}
        qty_by_wo: Dict[int, float] = {}
        if existing_wo_ids:
            for row in await WorkOrder.filter(tenant_id=tenant_id, id__in=existing_wo_ids).values(
                "id", "product_id", "quantity"
            ):
                product_by_wo[int(row["id"])] = int(row.get("product_id") or 0)
                qty_by_wo[int(row["id"])] = float(row.get("quantity") or 0)
        active_outsource_op_ids: Set[int] = set(
            await OutsourceOrder.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
            )
            .exclude(status="cancelled")
            .values_list("work_order_operation_id", flat=True)
        )

        def _resource_key_from_op(op: WorkOrderOperation) -> int:
            if use_line_resource:
                return int(op.assigned_production_line_id or 0)
            return int(op.assigned_station_id or 0)

        def _resource_capacity(resource_id: int) -> int:
            if use_line_resource and line_exclusive:
                return 1
            return station_parallel.get(resource_id, 1)

        for op in existing_ops:
            rkey = _resource_key_from_op(op)
            if rkey <= 0 or not op.planned_start_date or not op.planned_end_date:
                continue
            if not occupies_factory_capacity(
                op, has_active_outsource_order=int(op.id) in active_outsource_op_ids
            ):
                continue
            # 将被重排的工序从占用时间线中排除，避免自己挡自己
            if int(op.id) in candidate_op_ids:
                continue
            resource_timeline[rkey].append(
                (
                    _scheduling_dt(op.planned_start_date),
                    _scheduling_dt(op.planned_end_date),
                    int(op.id),
                    product_by_wo.get(int(op.work_order_id or 0), 0),
                )
            )
            if use_line_resource:
                day = to_site_date(op.planned_start_date)
                day_line_qty[(day, rkey)][int(op.work_order_id or 0)] = qty_by_wo.get(
                    int(op.work_order_id or 0), 0.0
                )

        if not use_line_resource:
            downtime_rows = await StationUnavailableWindow.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                is_active=True,
            ).all()
            for row in downtime_rows:
                sid = int(row.station_id or 0)
                if sid <= 0 or not row.start_at or not row.end_at:
                    continue
                resource_timeline[sid].append(
                    (
                        _scheduling_dt(row.start_at),
                        _scheduling_dt(row.end_at),
                        0,
                        0,
                    )
                )

        product_ids: Set[int] = set(product_by_wo.values())
        for wo in wos:
            pid = int(wo.product_id or 0)
            if pid > 0:
                product_ids.add(pid)
                product_by_wo[int(wo.id)] = pid
        changeover_ctx = None
        try:
            from apps.ind_relay.services.changeover_lookup import load_changeover_context
        except ImportError:
            load_changeover_context = None  # type: ignore[assignment]
        if load_changeover_context is not None:
            changeover_ctx = await load_changeover_context(
                tenant_id,
                fallback_hours=changeover_hours,
                product_ids=product_ids,
            )

        proposals: Dict[str, Any] = {
            "summary": None,
            "strategy": strategy,
            "strategy_name": strategy_label(strategy),
            "warnings": [],
            "reasons": [],
            "execution_log": execution_log,
            "unfreezed": [],
            "work_order_adjustments": [],
            "operation_adjustments": [],
            "operation_station_adjustments": [],
            "operation_production_line_adjustments": [],
        }
        scheduled_wo = 0
        mark = _log(
            "build_timeline",
            f"已装载资源占用时间线（资源模式={'产线' if use_line_resource else '工位'}）",
            mark,
        )

        def _pick_least_loaded_line(preferred: int = 0, product_id: int = 0) -> int:
            eligible = eligible_line_ids_for_product(
                int(product_id or 0),
                configured_line_ids=set(configured_line_ids),
                allow_map=line_allow_map,
            )
            if preferred > 0 and preferred in eligible:
                return preferred
            best_id = 0
            best_load = float("inf")
            for lid in sorted(eligible):
                load = _timeline_occupied_hours(resource_timeline.get(lid, []))
                if load < best_load:
                    best_load = load
                    best_id = lid
            if best_id > 0:
                return best_id
            # 无兼容线时不回落默认线（默认线可能不接受该产品）
            return preferred if preferred in eligible else 0

        for wo in wos:
            if not _is_schedulable_status(wo):
                proposals["warnings"].append(f"工单 {wo.code} 状态不可排，跳过")
                continue
            if wo.is_frozen:
                if _is_overdue(wo, now) and request.updated_by:
                    wo.is_frozen = False
                    wo.updated_by = int(request.updated_by)
                    await wo.save(update_fields=["is_frozen", "updated_by", "updated_at"])
                    proposals["unfreezed"].append(int(wo.id))
                    proposals["warnings"].append(f"工单 {wo.code} 已逾期，已自动解冻并纳入重排")
                else:
                    proposals["warnings"].append(f"工单 {wo.code} 已冻结，跳过")
                    continue

            ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                work_order_id=wo.id,
                deleted_at__isnull=True,
            ).order_by("sequence").all()
            pending = [op for op in ops if op.status not in {"completed", "cancelled"}]
            if not pending:
                continue

            if material_hard:
                readiness = getattr(wo, "readiness_rate", None)
                if readiness is None:
                    rate = 100.0
                else:
                    try:
                        rate = float(readiness)
                    except (TypeError, ValueError):
                        proposals["warnings"].append(
                            f"工单 {wo.code} 齐套率无法解析（{readiness!r}），硬约束跳过"
                        )
                        continue
                if rate < 100.0:
                    proposals["warnings"].append(
                        f"工单 {wo.code} 物料未齐套（{rate}%），硬约束跳过"
                    )
                    continue

            place_backward = (
                schedule_mode == "backward" and wo.planned_end_date is not None
            )
            if place_backward:
                due = _scheduling_dt(wo.planned_end_date)
                cursor = max(freeze_anchor, due)
            else:
                cursor = max(anchor_start, freeze_anchor)
            wo_op_slots: List[Tuple[WorkOrderOperation, datetime, datetime, int]] = []
            product_id = int(wo.product_id or 0)
            wo_qty = float(wo.quantity or 0)

            # —— 产线模式：整单 qty×takt 一次，全厂内工序共享同一窗口 ——
            if use_line_resource:
                factory_ops = [
                    op
                    for op in pending
                    if occupies_factory_capacity(
                        op, has_active_outsource_order=int(op.id) in active_outsource_op_ids
                    )
                ]
                outsource_ops = [
                    op
                    for op in pending
                    if not occupies_factory_capacity(
                        op, has_active_outsource_order=int(op.id) in active_outsource_op_ids
                    )
                ]
                line_id = 0
                for op in factory_ops:
                    line_id = int(op.assigned_production_line_id or 0)
                    if line_id > 0:
                        break
                # 已指派但不兼容（含无自制件）→ 清空后按 eligible 重选
                if line_id > 0 and not line_accepts_product(
                    line_id, product_id, line_allow_map
                ):
                    line_id = 0
                eligible_for_wo = eligible_line_ids_for_product(
                    product_id,
                    configured_line_ids=set(configured_line_ids),
                    allow_map=line_allow_map,
                )
                if strategy == STRATEGY_LOAD_BALANCE:
                    line_id = _pick_least_loaded_line(line_id, product_id=product_id)
                elif line_id <= 0:
                    if len(eligible_for_wo) == 1:
                        line_id = next(iter(eligible_for_wo))
                    elif default_line_id > 0 and default_line_id in eligible_for_wo:
                        line_id = default_line_id
                if not factory_ops:
                    # 仅委外：按交期/锚点摆 lead days
                    pass
                elif line_id <= 0:
                    proposals["warnings"].append(
                        f"工单 {wo.code} 无兼容产线（须在产线节拍绑定本自制件），跳过"
                    )
                    continue
                else:
                    if not line_accepts_product(line_id, product_id, line_allow_map):
                        proposals["warnings"].append(
                            f"工单 {wo.code} 产线 {line_id} 未绑定本自制件，跳过"
                        )
                        continue
                    cap = line_capacity_map.get(line_id)
                    if cap is None or float(cap.takt_seconds or 0) <= 0:
                        proposals["warnings"].append(
                            f"工单 {wo.code} 产线 {line_id} 未维护节拍，跳过"
                        )
                        continue
                    if float(cap.daily_capacity_qty or 0) <= 0:
                        proposals["warnings"].append(
                            f"工单 {wo.code} 产线 {line_id} 未维护日产能，跳过"
                        )
                        continue
                    duration_hours = duration_hours_from_takt(wo_qty, float(cap.takt_seconds))
                    if duration_hours is None:
                        proposals["warnings"].append(
                            f"工单 {wo.code} 无法按节拍计算时长，跳过"
                        )
                        continue
                    rkey = line_id
                    capacity = _resource_capacity(line_id)
                    timeline = resource_timeline.get(rkey, [])
                    earliest = cursor
                    ref_op = factory_ops[0]
                    try:
                        start = end = None
                        if place_backward:
                            latest = cursor
                            for _attempt in range(40):
                                start, end = find_latest_working_slot(
                                    _timeline_3(timeline),
                                    latest,
                                    duration_hours,
                                    holidays=holidays,
                                    config=work_hours,
                                    overtime=overtime,
                                    exclude_op_id=int(ref_op.id),
                                    max_parallel=capacity,
                                )
                                nxt = None
                                for iv in timeline:
                                    if iv[0] >= end and (nxt is None or iv[0] < nxt[0]):
                                        nxt = iv
                                if nxt and product_id > 0:
                                    nxt_pid = int(nxt[3] if len(nxt) > 3 else 0)
                                    ch_hours, forbid, source = _neighbor_changeover_hours(
                                        changeover_ctx,
                                        product_id,
                                        nxt_pid,
                                        production_line_id=line_id,
                                        fallback_hours=changeover_hours,
                                    )
                                    if forbid:
                                        proposals["warnings"].append(
                                            f"工单 {wo.code} 与后续产品禁共线，跳过"
                                        )
                                        proposals["reasons"].append(
                                            {
                                                "code": "forbid_same_line",
                                                "work_order_id": int(wo.id),
                                                "operation_id": int(ref_op.id),
                                                "message": "料号族禁共线，无法倒排到该资源",
                                            }
                                        )
                                        raise ValueError("禁共线")
                                    if ch_hours > 0 and nxt_pid not in (0, product_id):
                                        ready = add_working_hours(
                                            end,
                                            ch_hours,
                                            holidays=holidays,
                                            config=work_hours,
                                            overtime=overtime,
                                        )
                                        if ready > nxt[0]:
                                            latest = subtract_working_hours(
                                                nxt[0],
                                                ch_hours,
                                                holidays=holidays,
                                                config=work_hours,
                                                overtime=overtime,
                                            )
                                            continue
                                break
                        else:
                            for _attempt in range(40):
                                if changeover_ctx is not None:
                                    earliest, ch_reason = _apply_changeover_earliest(
                                        timeline,
                                        earliest,
                                        product_id,
                                        changeover_ctx,
                                        production_line_id=line_id,
                                        holidays=holidays,
                                        work_hours=work_hours,
                                        overtime=overtime,
                                    )
                                    if ch_reason == "forbid_same_line":
                                        proposals["warnings"].append(
                                            f"工单 {wo.code} 与前序产品禁共线，跳过"
                                        )
                                        proposals["reasons"].append(
                                            {
                                                "code": "forbid_same_line",
                                                "work_order_id": int(wo.id),
                                                "operation_id": int(ref_op.id),
                                                "message": "料号族禁共线，无法排到该资源",
                                            }
                                        )
                                        raise ValueError("禁共线")
                                else:
                                    ch_reason = None
                                    if changeover_hours > 0 and product_id > 0:
                                        prev = _prev_interval(timeline, earliest)
                                        if prev and int(prev[3] if len(prev) > 3 else 0) not in (
                                            0,
                                            product_id,
                                        ):
                                            earliest = add_working_hours(
                                                prev[1],
                                                changeover_hours,
                                                holidays=holidays,
                                                config=work_hours,
                                                overtime=overtime,
                                            )
                                            ch_reason = "changeover:fallback"
                                start, end = find_earliest_working_slot(
                                    _timeline_3(timeline),
                                    earliest,
                                    duration_hours,
                                    holidays=holidays,
                                    config=work_hours,
                                    overtime=overtime,
                                    exclude_op_id=int(ref_op.id),
                                    max_parallel=capacity,
                                )
                                prev = _prev_interval(timeline, start)
                                if prev and product_id > 0:
                                    prev_pid = int(prev[3] if len(prev) > 3 else 0)
                                    ch_hours, forbid, source = _neighbor_changeover_hours(
                                        changeover_ctx,
                                        prev_pid,
                                        product_id,
                                        production_line_id=line_id,
                                        fallback_hours=changeover_hours,
                                    )
                                    if forbid:
                                        proposals["warnings"].append(
                                            f"工单 {wo.code} 与前序产品禁共线，跳过"
                                        )
                                        proposals["reasons"].append(
                                            {
                                                "code": "forbid_same_line",
                                                "work_order_id": int(wo.id),
                                                "operation_id": int(ref_op.id),
                                                "message": "料号族禁共线，无法排到该资源",
                                            }
                                        )
                                        raise ValueError("禁共线")
                                    if ch_hours > 0 and prev_pid not in (0, product_id):
                                        ready = add_working_hours(
                                            prev[1],
                                            ch_hours,
                                            holidays=holidays,
                                            config=work_hours,
                                            overtime=overtime,
                                        )
                                        if start < ready:
                                            earliest = ready
                                            continue
                                        if ch_reason and ch_reason.startswith("changeover:"):
                                            proposals["reasons"].append(
                                                {
                                                    "code": ch_reason,
                                                    "work_order_id": int(wo.id),
                                                    "operation_id": int(ref_op.id),
                                                    "message": (
                                                        f"插入换型 {ch_hours:g}h（来源 {source}）"
                                                    ),
                                                    "changeover_hours": ch_hours,
                                                }
                                            )
                                break
                        if start is None or end is None:
                            raise ValueError("无法找到可行槽位")
                    except ValueError as e:
                        proposals["warnings"].append(
                            f"工单 {wo.code} 无法安排工作时段：{e}"
                        )
                        if str(e) != "禁共线":
                            proposals["reasons"].append(
                                {
                                    "code": "no_slot",
                                    "work_order_id": int(wo.id),
                                    "operation_id": int(ref_op.id),
                                    "message": str(e),
                                }
                            )
                        continue

                    day = to_site_date(start)
                    bucket = day_line_qty[(day, line_id)]
                    projected = dict(bucket)
                    projected[int(wo.id)] = wo_qty
                    if sum(projected.values()) > float(cap.daily_capacity_qty) + 1e-9:
                        proposals["warnings"].append(
                            f"工单 {wo.code} 超出产线 {line_id} 在 {day.isoformat()} 的日产能，跳过"
                        )
                        proposals["reasons"].append(
                            {
                                "code": "daily_capacity_exceeded",
                                "work_order_id": int(wo.id),
                                "operation_id": int(ref_op.id),
                                "message": f"超出产线日产能（{day.isoformat()}）",
                            }
                        )
                        continue
                    bucket[int(wo.id)] = wo_qty

                    # 全厂内工序共享同一整单窗口；时间轴只占用一次
                    for op in factory_ops:
                        wo_op_slots.append((op, start, end, line_id))
                    resource_timeline[rkey].append(
                        (start, end, int(ref_op.id), product_id)
                    )
                    cursor = start if place_backward else end

                for op in outsource_ops:
                    lead_days = int(getattr(op, "outsource_lead_time_days", None) or 1)
                    lead_days = max(0, lead_days)
                    if place_backward:
                        end = cursor
                        start = end - timedelta(days=lead_days if lead_days > 0 else 0)
                        if start < freeze_anchor:
                            start = freeze_anchor
                            end = start + timedelta(days=lead_days if lead_days > 0 else 0)
                        wo_op_slots.insert(0, (op, start, end, 0))
                        cursor = start
                    else:
                        start = cursor
                        end = start + timedelta(days=lead_days if lead_days > 0 else 0)
                        wo_op_slots.append((op, start, end, 0))
                        cursor = end

                if not wo_op_slots:
                    continue
            else:
                op_iter = list(reversed(pending)) if place_backward else pending
                for op in op_iter:
                    is_outsource = not occupies_factory_capacity(
                        op, has_active_outsource_order=int(op.id) in active_outsource_op_ids
                    )
                    if is_outsource:
                        lead_days = int(getattr(op, "outsource_lead_time_days", None) or 1)
                        lead_days = max(0, lead_days)
                        if place_backward:
                            end = cursor
                            start = end - timedelta(days=lead_days if lead_days > 0 else 0)
                            if start < freeze_anchor:
                                start = freeze_anchor
                                end = start + timedelta(days=lead_days if lead_days > 0 else 0)
                            wo_op_slots.insert(0, (op, start, end, 0))
                            cursor = start
                        else:
                            start = cursor
                            end = start + timedelta(days=lead_days if lead_days > 0 else 0)
                            wo_op_slots.append((op, start, end, 0))
                            cursor = end
                        continue

                    if not has_operation_hours(op.setup_time, op.standard_time):
                        proposals["warnings"].append(
                            f"工单 {wo.code} 工序 {op.operation_name or op.operation_code or op.id} "
                            f"缺少工序工时（setup_time/standard_time），请先补齐后重排"
                        )
                        wo_op_slots = []
                        break
                    duration_hours = operation_total_hours(
                        op.setup_time, op.standard_time, wo.quantity
                    )
                    station_id = int(op.assigned_station_id or 0)
                    if station_id <= 0 or strategy == STRATEGY_LOAD_BALANCE:
                        station_id = await self._resolve_default_station_id(
                            tenant_id,
                            op,
                            prefer_least_loaded=strategy == STRATEGY_LOAD_BALANCE,
                            resource_timeline=resource_timeline,
                            current_station_id=station_id,
                        )
                    if station_id <= 0:
                        proposals["warnings"].append(
                            f"工单 {wo.code} 工序 {op.operation_name} 无可用工位，跳过"
                        )
                        wo_op_slots = []
                        break
                    rkey = station_id
                    capacity = _resource_capacity(station_id)
                    timeline = resource_timeline.get(rkey, [])
                    earliest = cursor
                    try:
                        start = end = None
                        if place_backward:
                            latest = cursor
                            for _attempt in range(40):
                                start, end = find_latest_working_slot(
                                    _timeline_3(timeline),
                                    latest,
                                    duration_hours,
                                    holidays=holidays,
                                    config=work_hours,
                                    overtime=overtime,
                                    exclude_op_id=int(op.id),
                                    max_parallel=capacity,
                                )
                                nxt = None
                                for iv in timeline:
                                    if iv[0] >= end and (nxt is None or iv[0] < nxt[0]):
                                        nxt = iv
                                if nxt and product_id > 0:
                                    nxt_pid = int(nxt[3] if len(nxt) > 3 else 0)
                                    ch_hours, forbid, source = _neighbor_changeover_hours(
                                        changeover_ctx,
                                        product_id,
                                        nxt_pid,
                                        production_line_id=rkey,
                                        fallback_hours=changeover_hours,
                                    )
                                    if forbid:
                                        proposals["warnings"].append(
                                            f"工单 {wo.code} 工序 {op.operation_name} 与后续产品禁共线，跳过"
                                        )
                                        proposals["reasons"].append(
                                            {
                                                "code": "forbid_same_line",
                                                "work_order_id": int(wo.id),
                                                "operation_id": int(op.id),
                                                "message": "料号族禁共线，无法倒排到该资源",
                                            }
                                        )
                                        raise ValueError("禁共线")
                                    if ch_hours > 0 and nxt_pid not in (0, product_id):
                                        ready = add_working_hours(
                                            end,
                                            ch_hours,
                                            holidays=holidays,
                                            config=work_hours,
                                            overtime=overtime,
                                        )
                                        if ready > nxt[0]:
                                            latest = subtract_working_hours(
                                                nxt[0],
                                                ch_hours,
                                                holidays=holidays,
                                                config=work_hours,
                                                overtime=overtime,
                                            )
                                            continue
                                break
                        else:
                            for _attempt in range(40):
                                if changeover_ctx is not None:
                                    earliest, ch_reason = _apply_changeover_earliest(
                                        timeline,
                                        earliest,
                                        product_id,
                                        changeover_ctx,
                                        production_line_id=rkey,
                                        holidays=holidays,
                                        work_hours=work_hours,
                                        overtime=overtime,
                                    )
                                    if ch_reason == "forbid_same_line":
                                        proposals["warnings"].append(
                                            f"工单 {wo.code} 工序 {op.operation_name} 与前序产品禁共线，跳过"
                                        )
                                        proposals["reasons"].append(
                                            {
                                                "code": "forbid_same_line",
                                                "work_order_id": int(wo.id),
                                                "operation_id": int(op.id),
                                                "message": "料号族禁共线，无法排到该资源",
                                            }
                                        )
                                        raise ValueError("禁共线")
                                else:
                                    ch_reason = None
                                    if changeover_hours > 0 and product_id > 0:
                                        prev = _prev_interval(timeline, earliest)
                                        if prev and int(prev[3] if len(prev) > 3 else 0) not in (
                                            0,
                                            product_id,
                                        ):
                                            earliest = add_working_hours(
                                                prev[1],
                                                changeover_hours,
                                                holidays=holidays,
                                                config=work_hours,
                                                overtime=overtime,
                                            )
                                            ch_reason = "changeover:fallback"
                                start, end = find_earliest_working_slot(
                                    _timeline_3(timeline),
                                    earliest,
                                    duration_hours,
                                    holidays=holidays,
                                    config=work_hours,
                                    overtime=overtime,
                                    exclude_op_id=int(op.id),
                                    max_parallel=capacity,
                                )
                                prev = _prev_interval(timeline, start)
                                if prev and product_id > 0:
                                    prev_pid = int(prev[3] if len(prev) > 3 else 0)
                                    ch_hours, forbid, source = _neighbor_changeover_hours(
                                        changeover_ctx,
                                        prev_pid,
                                        product_id,
                                        production_line_id=rkey,
                                        fallback_hours=changeover_hours,
                                    )
                                    if forbid:
                                        proposals["warnings"].append(
                                            f"工单 {wo.code} 工序 {op.operation_name} 与前序产品禁共线，跳过"
                                        )
                                        proposals["reasons"].append(
                                            {
                                                "code": "forbid_same_line",
                                                "work_order_id": int(wo.id),
                                                "operation_id": int(op.id),
                                                "message": "料号族禁共线，无法排到该资源",
                                            }
                                        )
                                        raise ValueError("禁共线")
                                    if ch_hours > 0 and prev_pid not in (0, product_id):
                                        ready = add_working_hours(
                                            prev[1],
                                            ch_hours,
                                            holidays=holidays,
                                            config=work_hours,
                                            overtime=overtime,
                                        )
                                        if start < ready:
                                            earliest = ready
                                            continue
                                        if ch_reason and ch_reason.startswith("changeover:"):
                                            proposals["reasons"].append(
                                                {
                                                    "code": ch_reason,
                                                    "work_order_id": int(wo.id),
                                                    "operation_id": int(op.id),
                                                    "message": (
                                                        f"插入换型 {ch_hours:g}h（来源 {source}）"
                                                    ),
                                                    "changeover_hours": ch_hours,
                                                }
                                            )
                                break
                        if start is None or end is None:
                            raise ValueError("无法找到可行槽位")
                    except ValueError as e:
                        proposals["warnings"].append(
                            f"工单 {wo.code} 工序 {op.operation_name} 无法安排工作时段：{e}"
                        )
                        if str(e) != "禁共线":
                            proposals["reasons"].append(
                                {
                                    "code": "no_slot",
                                    "work_order_id": int(wo.id),
                                    "operation_id": int(op.id),
                                    "message": str(e),
                                }
                            )
                        wo_op_slots = []
                        break

                    if place_backward:
                        wo_op_slots.insert(0, (op, start, end, station_id))
                        cursor = start
                    else:
                        wo_op_slots.append((op, start, end, station_id))
                        cursor = end
                    resource_timeline[rkey].append((start, end, int(op.id), product_id))

                if not wo_op_slots:
                    continue

            for op, start, end, resource_id in wo_op_slots:
                proposals["operation_adjustments"].append(
                    {
                        "operation_id": int(op.id),
                        "planned_start_date": start.isoformat(),
                        "planned_end_date": end.isoformat(),
                    }
                )
                if use_line_resource:
                    if resource_id > 0 and int(op.assigned_production_line_id or 0) != resource_id:
                        proposals["operation_production_line_adjustments"].append(
                            {
                                "operation_id": int(op.id),
                                "assigned_production_line_id": resource_id,
                            }
                        )
                elif resource_id > 0 and int(op.assigned_station_id or 0) != resource_id:
                    proposals["operation_station_adjustments"].append(
                        {
                            "operation_id": int(op.id),
                            "assigned_station_id": resource_id,
                        }
                    )

            wo_start = wo_op_slots[0][1]
            wo_end = wo_op_slots[-1][2]
            if place_backward and wo.planned_end_date:
                due = _scheduling_dt(wo.planned_end_date)
                if wo_end > due:
                    proposals["warnings"].append(
                        f"工单 {wo.code} 倒排无法满足交期，最早可行完工 {wo_end.isoformat()}"
                    )
            proposals["work_order_adjustments"].append(
                {
                    "work_order_id": int(wo.id),
                    "planned_start_date": wo_start.isoformat(),
                    "planned_end_date": wo_end.isoformat(),
                }
            )
            scheduled_wo += 1

        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        _log(
            "done",
            f"完成：{scheduled_wo} 张工单提案，总耗时 {total_ms}ms",
            mark,
        )
        proposals["summary"] = (
            f"策略「{strategy_label(strategy)}」已为 {scheduled_wo} 张工单生成排产提案"
            f"（锚点 {anchor_day}"
            f"{'，含换型矩阵' if changeover_ctx and changeover_ctx.available else ''}，"
            f"{total_ms}ms）"
        )
        proposals["execution_log"] = execution_log
        return proposals

    async def _resolve_candidate_ids(
        self,
        tenant_id: int,
        request: SchedulingPlanRequest,
        now: datetime,
        *,
        use_line_resource: bool = False,
    ) -> List[int]:
        scope = str(request.scope or "selected").strip()
        if scope == "selected" and request.work_order_ids:
            return [int(i) for i in request.work_order_ids if int(i) > 0][:50]

        if scope == "local":
            return await self._resolve_local_candidate_ids(
                tenant_id, request, now, use_line_resource=use_line_resource
            )

        query = WorkOrder.filter(
            tenant_id=tenant_id,
            status__in=["released", "in_progress"],
            deleted_at__isnull=True,
        )
        if request.plan_date:
            day_start, day_end = _plan_day_bounds(request.plan_date)
            query = query.filter(planned_start_date__gte=day_start, planned_start_date__lte=day_end)

        wos = await query.all()
        ids: List[int] = []
        for wo in wos:
            if scope == "overdue":
                planned_end = _scheduling_dt(wo.planned_end_date) if wo.planned_end_date else None
                if planned_end and planned_end < now:
                    ids.append(int(wo.id))
            elif scope == "unscheduled":
                ops = await WorkOrderOperation.filter(
                    tenant_id=tenant_id,
                    work_order_id=wo.id,
                    deleted_at__isnull=True,
                ).all()
                if use_line_resource:
                    if any(
                        (
                            not op.planned_start_date
                            or not op.planned_end_date
                            or not op.assigned_production_line_id
                        )
                        and op.status not in {"completed", "cancelled"}
                        for op in ops
                    ):
                        ids.append(int(wo.id))
                elif not wo.planned_start_date or not wo.planned_end_date:
                    ids.append(int(wo.id))
                else:
                    if any(
                        (not op.planned_start_date or not op.planned_end_date or not op.assigned_station_id)
                        and op.status not in {"completed", "cancelled"}
                        for op in ops
                    ):
                        ids.append(int(wo.id))
            else:
                ids.append(int(wo.id))
        if request.work_order_ids:
            allowed = {int(i) for i in request.work_order_ids}
            ids = [i for i in ids if i in allowed]
        return ids[:50]

    async def _resolve_local_candidate_ids(
        self,
        tenant_id: int,
        request: SchedulingPlanRequest,
        now: datetime,
        *,
        use_line_resource: bool = False,
    ) -> List[int]:
        """局部重排：种子工单 + 同资源时间窗内邻域工单。"""
        window_hours = float(getattr(request, "local_window_hours", None) or 24)
        window_hours = max(1.0, min(window_hours, 168.0))
        seed_ids = [int(i) for i in (request.work_order_ids or []) if int(i) > 0]
        window_end = now + timedelta(hours=window_hours)
        if not seed_ids:
            # 无种子时取当前时刻附近已排工单
            near_q = WorkOrderOperation.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                planned_start_date__lte=window_end,
                planned_end_date__gte=now,
            )
            if use_line_resource:
                near_q = near_q.filter(assigned_production_line_id__gt=0)
            else:
                near_q = near_q.filter(assigned_station_id__gt=0)
            near_ops = await near_q.limit(80)
            seed_ids = list({int(op.work_order_id) for op in near_ops if op.work_order_id})[:20]
        if not seed_ids:
            return []

        seed_ops = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            work_order_id__in=seed_ids,
            deleted_at__isnull=True,
        ).all()
        if use_line_resource:
            line_ids = {
                int(op.assigned_production_line_id)
                for op in seed_ops
                if int(op.assigned_production_line_id or 0) > 0
            }
            resource_ids = {
                int(i) for i in (getattr(request, "resource_ids", None) or []) if int(i) > 0
            }
            line_ids |= resource_ids
            if not line_ids:
                return seed_ids[:50]
            neighbor_ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                assigned_production_line_id__in=list(line_ids),
                planned_start_date__lte=window_end,
                planned_end_date__gte=now - timedelta(hours=window_hours),
            ).all()
        else:
            station_ids = {
                int(op.assigned_station_id) for op in seed_ops if int(op.assigned_station_id or 0) > 0
            }
            resource_ids = {
                int(i) for i in (getattr(request, "resource_ids", None) or []) if int(i) > 0
            }
            if resource_ids:
                station_ids |= resource_ids
                line_stations = await Workstation.filter(
                    tenant_id=tenant_id,
                    production_line_id__in=list(resource_ids),
                    deleted_at__isnull=True,
                ).values_list("id", flat=True)
                station_ids |= {int(i) for i in line_stations}
            if not station_ids:
                return seed_ids[:50]
            neighbor_ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                assigned_station_id__in=list(station_ids),
                planned_start_date__lte=window_end,
                planned_end_date__gte=now - timedelta(hours=window_hours),
            ).all()
        ids = set(seed_ids)
        for op in neighbor_ops:
            if op.work_order_id:
                ids.add(int(op.work_order_id))
        return list(ids)[:50]

    @staticmethod
    async def _resolve_default_station_id(
        tenant_id: int,
        op: WorkOrderOperation,
        *,
        prefer_least_loaded: bool = False,
        resource_timeline: Optional[Dict[int, List[Tuple[datetime, datetime, int, int]]]] = None,
        current_station_id: int = 0,
    ) -> int:
        wc_id = int(op.work_center_id or 0)
        q = Workstation.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            is_active=True,
        )
        if wc_id > 0:
            q = q.filter(work_center_id=wc_id)
        stations = await q.order_by("id").all()
        if not stations:
            return int(current_station_id or 0)
        if not prefer_least_loaded or not resource_timeline:
            if current_station_id > 0:
                return int(current_station_id)
            return int(stations[0].id)
        best_id = int(current_station_id or 0)
        best_load = (
            _timeline_occupied_hours(resource_timeline.get(best_id, []))
            if best_id > 0
            else float("inf")
        )
        for st in stations:
            sid = int(st.id)
            load = _timeline_occupied_hours(resource_timeline.get(sid, []))
            if load < best_load:
                best_load = load
                best_id = sid
        return best_id
