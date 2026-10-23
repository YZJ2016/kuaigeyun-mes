"""KU-AI 场景只读 Tool：库存预警、补货建议与呆滞料（spec 196）。

Tool 名：``query_inventory_alerts`` / ``query_replenishment_suggestions`` /
``query_slow_moving_inventory``。

三个底层 service 均不接收 ``current_user``（T1 核实）：
- ``InventoryAlertService.get_alerts`` / ``ReplenishmentSuggestionService.get_suggestions``
  返回 (rows, total)，行 id 经 ``_scoped_row_ids`` 套 ``kuaizhizao:inventory``
  资源求交（spec 181 已注册该资源画像；manifest ``reference_resources`` 无
  inventory-alert / replenishment 专属 data_scope_key，沿用 inventory 键）。
- ``build_slow_moving_inventory``（经 ``ReportService.get_inventory_report``）
  行只含 batch_no/material_code，无 material_id/warehouse_id 且其
  ``warehouse_id`` 参数在服务内未生效（T1 事实）：适配层用
  ``MaterialBatch``（同过滤口径：未删/qty>0/in_stock/批号∈结果集）
  套 ``kuaizhizao:inventory`` 范围求 (material_id, batch_no) 可见对，
  并顺带取回 ``warehouse_name`` 展示；Tool ``warehouse_id`` 参数也在该
  查询上生效（等效于后置仓库过滤）。
- service 先分页后过滤会使 total 偏大：预警/建议过采样（上限 100 行）再按
  范围收敛，摘要总数以过滤后为准并注明「当前用户数据范围内」。
- 呆滞报表无金额/成本字段，预警/建议摘要不输出金额类字段。
"""

from __future__ import annotations

from typing import Any, List, Optional, Set, Tuple

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_SCOPE_INVENTORY = "kuaizhizao:inventory"

# 闭集参数（T1 从模型字段注释核实）
# InventoryAlert.alert_type（models/inventory_alert.py:165）
_ALERT_TYPES = frozenset({"low_stock", "high_stock", "expired"})
# InventoryAlert.status（:183）
_ALERT_STATUSES = frozenset({"pending", "processing", "resolved", "ignored"})
# InventoryAlert.alert_level（:179）
_ALERT_LEVELS = frozenset({"info", "warning", "critical"})
# ReplenishmentSuggestion.status（:99）
_SUGGESTION_STATUSES = frozenset({"pending", "processed", "ignored"})
# ReplenishmentSuggestion.priority（:87）
_SUGGESTION_PRIORITIES = frozenset({"high", "medium", "low"})
# ReplenishmentSuggestion.suggestion_type（:88）
_SUGGESTION_TYPES = frozenset({"low_stock", "demand_based", "seasonal"})

# 过采样上限：service 分页后再按数据范围收敛，多取减少「范围内行被顶掉」
_OVERSAMPLE_LIMIT = 100


def _ct():
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _fetch_limit(limit: Any) -> int:
    """用户 limit（≤20）放大到过采样上限内，供范围过滤后仍够页。"""
    return min(max(_ct()._clamp_limit(limit) * 5, 50), _OVERSAMPLE_LIMIT)


async def _scope_ids(model, ctx: AiRuntimeContext, ids: Set[int]) -> Set[int]:
    return await _st()._scoped_row_ids(model, ctx, _SCOPE_INVENTORY, ids)


def _fmt_inventory_alert_row(r: Any) -> str:
    """库存预警行摘要（Tool 与页上下文 reader 共用口径，spec 204 AC4）。"""
    return (
        f"物料 {getattr(r, 'material_code', '') or ''}"
        f"（{getattr(r, 'material_name', '') or '未命名'}）"
        f" @ {getattr(r, 'warehouse_name', '') or '未配置仓库'}："
        f"类型 {getattr(r, 'alert_type', '') or '未知'}，"
        f"级别 {getattr(r, 'alert_level', '') or '未知'}，"
        f"当前 {_ct()._fmt_num(getattr(r, 'current_quantity', None))}"
        f"/阈值 {_ct()._fmt_num(getattr(r, 'threshold_value', None))}，"
        f"状态 {getattr(r, 'status', '') or '未知'}，"
        f"触发 {getattr(r, 'triggered_at', '') or '未知'}"
        f"（id={getattr(r, 'id', '')}）"
    )


async def query_inventory_alerts(
    alert_type: Optional[str] = None,
    status: Optional[str] = None,
    alert_level: Optional[str] = None,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    keyword: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """库存预警摘要（物料/仓库/类型/级别/当前量/阈值/状态，范围内过滤）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    a_type = (str(alert_type).strip() or None) if alert_type else None
    if a_type is not None and a_type not in _ALERT_TYPES:
        return "alert_type 仅支持 low_stock/high_stock/expired"
    a_status = (str(status).strip() or None) if status else None
    if a_status is not None and a_status not in _ALERT_STATUSES:
        return "status 仅支持 pending/processing/resolved/ignored"
    a_level = (str(alert_level).strip() or None) if alert_level else None
    if a_level is not None and a_level not in _ALERT_LEVELS:
        return "alert_level 仅支持 info/warning/critical"
    try:
        from apps.kuaizhizao.services.inventory_alert_service import (
            InventoryAlertService,
        )

        rows, _total = await InventoryAlertService().get_alerts(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            alert_type=a_type,
            status=a_status,
            alert_level=a_level,
            material_id=int(material_id) if material_id else None,
            warehouse_id=int(warehouse_id) if warehouse_id else None,
            keyword=(str(keyword).strip() or None) if keyword else None,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_inventory_alerts 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询库存预警失败，请稍后重试"
    rows = list(rows or [])
    if not rows:
        return "未查询到符合条件的库存预警"

    try:
        from apps.kuaizhizao.models.inventory_alert import InventoryAlert

        visible = await _scope_ids(
            InventoryAlert,
            ctx,
            {int(r.id) for r in rows if getattr(r, "id", None)},
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_inventory_alerts 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询库存预警失败，请稍后重试"
    rows = [r for r in rows if int(getattr(r, "id", 0) or 0) in visible]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的库存预警"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条库存预警（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_inventory_alert_row(r))
    return "\n".join(lines)


async def query_replenishment_suggestions(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    suggestion_type: Optional[str] = None,
    material_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    keyword: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """补货建议摘要（物料/建议量/建议下单日期/优先级/状态，范围内过滤）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    s_status = (str(status).strip() or None) if status else None
    if s_status is not None and s_status not in _SUGGESTION_STATUSES:
        return "status 仅支持 pending/processed/ignored"
    s_priority = (str(priority).strip() or None) if priority else None
    if s_priority is not None and s_priority not in _SUGGESTION_PRIORITIES:
        return "priority 仅支持 high/medium/low"
    s_type = (str(suggestion_type).strip() or None) if suggestion_type else None
    if s_type is not None and s_type not in _SUGGESTION_TYPES:
        return "suggestion_type 仅支持 low_stock/demand_based/seasonal"
    try:
        from apps.kuaizhizao.services.replenishment_suggestion_service import (
            ReplenishmentSuggestionService,
        )

        rows, _total = await ReplenishmentSuggestionService().get_suggestions(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            status=s_status,
            priority=s_priority,
            suggestion_type=s_type,
            material_id=int(material_id) if material_id else None,
            warehouse_id=int(warehouse_id) if warehouse_id else None,
            keyword=(str(keyword).strip() or None) if keyword else None,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_replenishment_suggestions 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询补货建议失败，请稍后重试"
    rows = list(rows or [])
    if not rows:
        return "未查询到符合条件的补货建议"

    try:
        from apps.kuaizhizao.models.replenishment_suggestion import (
            ReplenishmentSuggestion,
        )

        visible = await _scope_ids(
            ReplenishmentSuggestion,
            ctx,
            {int(r.id) for r in rows if getattr(r, "id", None)},
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_replenishment_suggestions 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询补货建议失败，请稍后重试"
    rows = [r for r in rows if int(getattr(r, "id", 0) or 0) in visible]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的补货建议"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条补货建议（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        order_date = getattr(r, "suggested_order_date", None)
        lines.append(
            f"物料 {getattr(r, 'material_code', '') or ''}"
            f"（{getattr(r, 'material_name', '') or '未命名'}）"
            f" @ {getattr(r, 'warehouse_name', '') or '未配置仓库'}："
            f"建议补货 {_ct()._fmt_num(getattr(r, 'suggested_quantity', None))}，"
            f"建议下单 {order_date or '未定'}，"
            f"优先级 {getattr(r, 'priority', '') or '未知'}，"
            f"类型 {getattr(r, 'suggestion_type', '') or '未知'}，"
            f"状态 {getattr(r, 'status', '') or '未知'}"
            f"（id={getattr(r, 'id', '')}）"
        )
    return "\n".join(lines)


async def _slow_moving_visible(
    ctx: AiRuntimeContext,
    rows: List[dict],
    warehouse_id: Optional[int],
) -> dict:
    """呆滞行可见性：MaterialBatch（批号∈结果集、未删、qty>0、in_stock）
    套 ``kuaizhizao:inventory`` 范围，返回 {(material_id, batch_no):
    warehouse_name}。物料 code→id 经 Material 解析（行只有 material_code）。"""
    from apps.master_data.models.material import Material
    from apps.master_data.models.material_batch import MaterialBatch

    codes = {str(r.get("material_code") or "") for r in rows}
    codes.discard("")
    batch_nos = {str(r.get("batch_no") or "") for r in rows}
    batch_nos.discard("")
    if not codes or not batch_nos:
        return {}, {}
    mats = await Material.filter(
        tenant_id=ctx.tenant_id, main_code__in=list(codes)
    ).values("id", "main_code")
    code_to_mid = {m["main_code"]: int(m["id"]) for m in mats}
    if not code_to_mid:
        return {}, code_to_mid
    qs = MaterialBatch.filter(
        tenant_id=ctx.tenant_id,
        deleted_at__isnull=True,
        quantity__gt=0,
        status="in_stock",
        batch_no__in=list(batch_nos),
        material_id__in=list(code_to_mid.values()),
    )
    if warehouse_id:
        qs = qs.filter(warehouse_id=int(warehouse_id))
    qs = await _st()._apply_scope(qs, ctx.tenant_id, ctx, _SCOPE_INVENTORY)
    out = {}
    for b in await qs.values("material_id", "batch_no", "warehouse_name"):
        out[(int(b["material_id"]), str(b["batch_no"]))] = (
            b.get("warehouse_name") or ""
        )
    return out, code_to_mid


async def query_slow_moving_inventory(
    warehouse_id: Optional[int] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """呆滞料摘要（物料/仓库/结存/库龄天数，MaterialBatch 在库口径）。

    底层 ``build_slow_moving_inventory`` 的 ``warehouse_id`` 参数在服务内未
    生效（T1 事实），Tool 的仓库过滤经可见批次查询生效。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        from apps.kuaizhizao.services.report_service import ReportService

        report = await ReportService().get_inventory_report(
            ctx.tenant_id,
            "slow_moving",
        )
        rows = list((report or {}).get("data") or [])
    except Exception as exc:
        logger.warning(
            "AI tool query_slow_moving_inventory 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询呆滞料失败，请稍后重试"
    if not rows:
        return "未查询到呆滞料记录"

    try:
        visible, code_to_mid = await _slow_moving_visible(
            ctx, rows, int(warehouse_id) if warehouse_id else None
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_slow_moving_inventory 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询呆滞料失败，请稍后重试"

    def _key(r: dict) -> Tuple[Optional[int], str]:
        return (
            code_to_mid.get(str(r.get("material_code") or "")),
            str(r.get("batch_no") or ""),
        )

    rows = [r for r in rows if _key(r) in visible]
    if not rows:
        return "当前用户数据范围内未查询到呆滞料记录"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条呆滞批次（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        wh = visible.get(_key(r)) or "未配置仓库"
        lines.append(
            f"物料 {r.get('material_code') or ''}"
            f"（{r.get('material_name') or '未命名'}）"
            f" @ {wh}："
            f"批次 {r.get('batch_no') or '无批号'}，"
            f"结存 {_ct()._fmt_num(r.get('quantity'))}，"
            f"库龄 {r.get('age_days') or 0} 天，"
            f"最后变动 {r.get('last_move_date') or '未知'}"
        )
    return "\n".join(lines)
