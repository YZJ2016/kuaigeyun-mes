"""KU-AI 场景只读 Tool：模具寿命与工装状态（spec 216）。

Tool 名：``query_molds`` / ``query_tooling``；
权限码 ``kuaizhizao:equipment-management-molds:read`` /
``kuaizhizao:equipment-management-tool-ledger:read``
（两码均在 kuaizhizao manifest permissions 声明）。

T1 事实（写 spec §4）：
- 模具台账：``MoldService.list_molds(tenant_id, skip, limit, type, status,
  is_active, search, keyword, order_by, ...)``（services/mold_service.py），
  不接收 ``current_user``；行级范围由适配层套
  ``kuaizhizao:equipment-management-molds`` 资源收敛（页面功能码去 :read，
  manifest reference_resources 无专属 data_scope_key，无策略=全部，
  与 spec 210 同口径）。
- 寿命字段就在模具表：``Mold.total_usage_count``（累计模次）、
  ``Mold.design_lifetime``（设计寿命/使用次数=寿命上限）、
  ``Mold.last_maintenance_date``（上次保养日期）；无分散到生产记录。
  模型无预警阈值字段 → 固定阈值 20%：剩余寿命**未舍入真实比值**
  < 20% 计入预警（``life_warning_only``，舍入到 20.0% 展示值
  可能仍命中）；``design_lifetime`` 缺失/非正的行输出
  「无寿命数据」，无法判定低于阈值故不进预警名单。
- 模具状态闭集取 ``constants/mold_status.py`` ``MOLD_STATUS_SET``，
  历史值经 ``normalize_mold_status`` 归一（正常→待用）。
- 工装台账：``ToolService.list_tools(tenant_id, skip, limit, type, status,
  is_active, search, keyword, product_model, order_by, ...)``
  （services/tool_service.py），不接收 ``current_user``，无 location
  形参 → ``location`` 由适配层对 ``storage_location`` 模糊后过滤；
  行级范围套 ``kuaizhizao:equipment-management-tool-ledger``。
- 工装领用/归还为台账快照字段：``current_borrower_name`` /
  ``current_borrow_at`` / ``last_return_at`` / ``last_return_by_name``
  （models/tool.py），无需查 ToolUsage。
- 工装状态闭集取 ``constants/tool_status.py`` ``TOOL_STATUS_SET``，
  历史值经 ``normalize_tool_status`` 归一（正常→待用、领用中→在用）。
- 不输出供应商/制造商/采购日期等商务信息（状态字段本身可见）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 行级数据范围资源键（页面功能码去 :read）
_SCOPE_MOLD = "kuaizhizao:equipment-management-molds"
_SCOPE_TOOL = "kuaizhizao:equipment-management-tool-ledger"

# 寿命预警固定阈值（%）：模型无阈值字段（T1 定）
_LIFE_WARNING_PCT = 20.0

# 过采样上限：service 先分页后按数据范围/寿命预警/库位收敛，
# 多取减少「范围内行被顶掉」
_OVERSAMPLE_LIMIT = 100


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _opt_str(value: Any) -> Optional[str]:
    s = str(value or "").strip()
    return s or None


def _opt_bool(value: Any):
    """布尔参数归一：bool/"true"/"false"/1/0 → bool；None/"" → None；
    其他返回 ``_INVALID_BOOL`` 哨兵由调用方判错。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return _INVALID_BOOL


_INVALID_BOOL = object()


def _fetch_limit(limit: Any) -> int:
    """用户 limit（≤20）放大到过采样上限内，供范围过滤后仍够页。"""
    return min(max(_ct()._clamp_limit(limit) * 5, 50), _OVERSAMPLE_LIMIT)


def _fmt_dt(value: Any) -> str:
    """datetime/date 展示：datetime 经 API 同口径站点时区文本，date 取 ISO 日。"""
    if value is None:
        return "未知"
    try:
        from core.utils.timezone_utils import to_api_isoformat

        out = to_api_isoformat(value)
        if out:
            return out
    except Exception:
        pass
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    s = str(value).strip()
    return s[:19] if s else "未知"


def _remaining_life_ratio(mold: Any) -> Optional[float]:
    """剩余寿命真实比值（未舍入，0~1；已超寿命钳到 0）。

    ``design_lifetime`` 缺失或非正返回 None（无寿命数据）。
    寿命预警判定用本值；展示用 ``_remaining_life_pct`` 的舍入值。
    """
    lifetime = getattr(mold, "design_lifetime", None)
    try:
        lifetime = int(lifetime)
    except (TypeError, ValueError):
        return None
    if lifetime <= 0:
        return None
    used = getattr(mold, "total_usage_count", None) or 0
    try:
        used = int(used)
    except (TypeError, ValueError):
        used = 0
    return max(0, lifetime - used) / lifetime


def _remaining_life_pct(mold: Any) -> Optional[float]:
    """剩余寿命百分比展示值（舍入 1 位小数）；无寿命数据返回 None。

    预警判定勿用本值——舍入后 20.0% 可能对应真实比值仍低于阈值，
    应改用 ``_remaining_life_ratio`` 与阈值比较。
    """
    ratio = _remaining_life_ratio(mold)
    return round(ratio * 100, 1) if ratio is not None else None


def _fmt_mold_row(m: Any) -> str:
    """模具台账行摘要：编码/名称/累计模次/寿命上限/剩余寿命/状态/最近保养。

    不输出供应商、制造商、采购日期等商务信息。
    """
    parts = [
        f"模具 {getattr(m, 'code', '') or ''}"
        f"（{getattr(m, 'name', None) or '未命名'}）：",
        f"累计模次 {_ct()._fmt_num(getattr(m, 'total_usage_count', None))}",
    ]
    lifetime = getattr(m, "design_lifetime", None)
    pct = _remaining_life_pct(m)
    if pct is None:
        parts.append("寿命上限 未设置")
        parts.append("剩余寿命 无寿命数据")
    else:
        parts.append(f"寿命上限 {_ct()._fmt_num(lifetime)}")
        parts.append(f"剩余寿命 {pct}%")
    parts.append(f"状态 {getattr(m, 'status', '') or '未知'}")
    parts.append(f"最近保养 {_fmt_dt(getattr(m, 'last_maintenance_date', None))}")
    if not getattr(m, "is_active", True):
        parts.append("已停用")
    return (
        "，".join(parts)
        + f"（uuid={getattr(m, 'uuid', '')}，id={getattr(m, 'id', '')}）"
    )


def _fmt_tool_row(t: Any) -> str:
    """工装台账行摘要：编码/名称/库位/状态/领用归还信息。

    不输出供应商、制造商、采购日期等商务信息。
    """
    parts = [
        f"工装 {getattr(t, 'code', '') or ''}"
        f"（{getattr(t, 'name', None) or '未命名'}）：",
        f"库位 {getattr(t, 'storage_location', None) or '未设置'}",
        f"状态 {getattr(t, 'status', '') or '未知'}",
    ]
    borrower = getattr(t, "current_borrower_name", None)
    if borrower:
        parts.append(
            f"领用中 {borrower}（{_fmt_dt(getattr(t, 'current_borrow_at', None))}）"
        )
    else:
        parts.append("当前未领用")
    last_return_at = getattr(t, "last_return_at", None)
    if last_return_at:
        by = getattr(t, "last_return_by_name", None) or "未知"
        parts.append(f"最近归还 {_fmt_dt(last_return_at)}（{by}）")
    custodian = getattr(t, "custodian_name", None)
    if custodian:
        parts.append(f"保管人 {custodian}")
    if not getattr(t, "is_active", True):
        parts.append("已停用")
    return (
        "，".join(parts)
        + f"（uuid={getattr(t, 'uuid', '')}，id={getattr(t, 'id', '')}）"
    )


async def query_molds(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    life_warning_only: Optional[bool] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """模具台账与寿命摘要：编码/名称/累计模次/寿命上限/剩余寿命/状态/最近保养。

    ``life_warning_only=true`` 时只列剩余寿命低于 20% 阈值的模具
    （无寿命数据的模具无法判定，不进预警名单）。
    数据范围：service 不接收 ``current_user``，行 id 套
    ``kuaizhizao:equipment-management-molds`` 资源收敛。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    from apps.kuaizhizao.constants.mold_status import (
        MOLD_STATUS_SET,
        MOLD_STATUS_VALUES,
        normalize_mold_status,
    )

    status_norm = _opt_str(status)
    if status_norm is not None:
        status_norm = normalize_mold_status(status_norm)
        if status_norm not in MOLD_STATUS_SET:
            return "status 仅支持 " + "/".join(MOLD_STATUS_VALUES)
    warning_only = _opt_bool(life_warning_only)
    if warning_only is _INVALID_BOOL:
        return "life_warning_only 仅支持 true/false"
    lim = _ct()._clamp_limit(limit)

    try:
        from apps.kuaizhizao.models.mold import Mold
        from apps.kuaizhizao.services.mold_service import MoldService

        rows, _total = await MoldService.list_molds(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            status=status_norm,
            keyword=_opt_str(keyword),
        )
        visible = await _st()._scoped_row_ids(
            Mold,
            ctx,
            _SCOPE_MOLD,
            {int(getattr(r, "id", 0) or 0) for r in rows} - {0},
        )
        rows = [
            r
            for r in rows
            if r is not None and int(getattr(r, "id", 0) or 0) in visible
        ]
        if warning_only:
            rows = [
                r
                for r in rows
                if (ratio := _remaining_life_ratio(r)) is not None
                and ratio * 100 < _LIFE_WARNING_PCT
            ]
    except Exception as exc:
        logger.warning(
            "AI tool query_molds 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询模具台账失败，请稍后重试"

    if not rows:
        if warning_only:
            return "当前用户数据范围内未查询到寿命预警的模具"
        return "当前用户数据范围内未查询到符合条件的模具"

    top = rows[:lim]
    if warning_only:
        lines = [
            f"共 {len(rows)} 副模具剩余寿命低于 "
            f"{_LIFE_WARNING_PCT:.0f}%（当前用户数据范围内，上限内计），"
            f"返回前 {len(top)} 副："
        ]
    else:
        lines = [
            f"共 {len(rows)} 副模具（当前用户数据范围内，上限内计），"
            f"返回前 {len(top)} 副："
        ]
    for m in top:
        lines.append(_fmt_mold_row(m))
    return "\n".join(lines)


async def query_tooling(
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """工装台账摘要：编码/名称/库位/状态/领用归还信息。

    ``location`` 对存放位置模糊匹配（service 无该形参，适配层后过滤）。
    数据范围：service 不接收 ``current_user``，行 id 套
    ``kuaizhizao:equipment-management-tool-ledger`` 资源收敛。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    from apps.kuaizhizao.constants.tool_status import (
        TOOL_STATUS_SET,
        TOOL_STATUS_VALUES,
        normalize_tool_status,
    )

    status_norm = _opt_str(status)
    if status_norm is not None:
        status_norm = normalize_tool_status(status_norm)
        if status_norm not in TOOL_STATUS_SET:
            return "status 仅支持 " + "/".join(TOOL_STATUS_VALUES)
    location_norm = _opt_str(location)
    lim = _ct()._clamp_limit(limit)

    try:
        from apps.kuaizhizao.models.tool import Tool
        from apps.kuaizhizao.services.tool_service import ToolService

        rows, _total = await ToolService.list_tools(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            status=status_norm,
            keyword=_opt_str(keyword),
        )
        visible = await _st()._scoped_row_ids(
            Tool,
            ctx,
            _SCOPE_TOOL,
            {int(getattr(r, "id", 0) or 0) for r in rows} - {0},
        )
        rows = [
            r
            for r in rows
            if r is not None and int(getattr(r, "id", 0) or 0) in visible
        ]
        if location_norm:
            needle = location_norm.lower()
            rows = [
                r
                for r in rows
                if needle
                in str(getattr(r, "storage_location", "") or "").lower()
            ]
    except Exception as exc:
        logger.warning(
            "AI tool query_tooling 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询工装台账失败，请稍后重试"

    if not rows:
        return "当前用户数据范围内未查询到符合条件的工装"

    top = rows[:lim]
    lines = [
        f"共 {len(rows)} 件工装（当前用户数据范围内，上限内计），"
        f"返回前 {len(top)} 件："
    ]
    for t in top:
        lines.append(_fmt_tool_row(t))
    return "\n".join(lines)
