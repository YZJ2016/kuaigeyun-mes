"""KU-AI 场景只读 Tool：盘点差异解读（spec 217，S22）。

Tool 名：``query_stocktakings`` / ``analyze_stocktaking_variance``。

- ``query_stocktakings`` 底层 ``StocktakingService.list_stocktakings``
  （不接收 current_user）：返回行 id 经 ``scene_tools._scoped_row_ids``
  套 ``kuaizhizao:warehouse-management-stocktaking`` 资源求交（该模块未进
  manifest ``reference_resources``、无 data_scope_key，资源键按权限码去
  动作段推导，与 ``_permission_code_to_resource_key`` 同口径）；service
  先分页后过滤会偏宽，过采样（上限 100 行）再按范围收敛，总数以过滤后
  为准并注明「当前用户数据范围内，前 100 条候选内计」。
- ``analyze_stocktaking_variance`` 双视图，权限码按视图拆判（T1 事实：
  明细与历史**不同**读权限码——明细走 ``warehouse-management-stocktaking``
  :read，历史报表走 ``reports-stocktaking-history``:read；manifest 用
  ``permissions_any`` 任一放行后，本层按视图复核对应读权限，无权按视图
  拒绝，沿用 document_chain ``_perm_view`` 一次取码内存判定）：
  - 按单（默认 / stocktaking_id 必填）：源单先做行级范围复核
    （``warehouse-management-stocktaking`` 资源，范围外按不存在），明细
    经 ``StocktakingService.get_stocktaking_by_id``；聚合在适配层
    （spec §2）：按物料聚合账存/实盘/差异量/差异金额 → |差异金额| 降序
    TopN=10 + 按物料分组汇总（Material.group_id→MaterialGroup.name）。
  - ``view=history``：``_get_stocktaking_history`` 同口径明细行
    （Stocktaking 头按盘点日期 + ``reports-stocktaking-history`` 行级
    范围 → StocktakingItem 明细，内部上限截断注明）——报表 service
    方法为 ``ReportService.get_warehouse_report(report_type=
    "stocktaking-history")`` → ``_get_stocktaking_history``，其 item
    分页口径不含库位列且逐单不完整，故趋势与库位汇总用同过滤条件的
    明细查询一次性取数（同一数据源，可复算）。
- 差异口径（T1，stocktaking_service.py:483-485）：``difference_quantity
  = actual_quantity − book_quantity``（正=盘盈、负=盘亏），
  ``difference_amount = difference_quantity × unit_price``；差异率=
  |差异量|/账存（账存为 0 不计算，标「—」）。差异金额按 spec 允许输出；
  不输出创建/盘点/完成人姓名等操作员字段。
- 内部取数上限：按单明细 >2000 条截断注明；history 头 >50 单、
  明细 >2000 行截断注明（报表 service 内部另有 limit≤500 不采用，
  适配层自行设界保证单内明细可复算）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 行级数据范围资源键（= 权限码去动作段，与
# effective_access_service._permission_code_to_resource_key 同口径；
# stocktaking / reports-stocktaking-history 均未进 manifest
# reference_resources，无专属 data_scope_key）
_SCOPE_STOCKTAKING = "kuaizhizao:warehouse-management-stocktaking"
_SCOPE_STOCKTAKING_HISTORY = (
    "kuaizhizao:warehouse-management-reports-stocktaking-history"
)

# 视图权限码（明细与历史不同码 → 按视图拆判，spec §1 T1 分支）
_PERM_STOCKTAKING_READ = "kuaizhizao:warehouse-management-stocktaking:read"
_PERM_HISTORY_READ = (
    "kuaizhizao:warehouse-management-reports-stocktaking-history:read"
)

# Stocktaking.status 闭集（models/stocktaking.py:28 注释）
_STOCKTAKING_STATUSES = frozenset(
    {"draft", "in_progress", "completed", "cancelled"}
)
_STOCKTAKING_STATUS_ZH = {
    "draft": "草稿",
    "in_progress": "盘点中",
    "completed": "已完成",
    "cancelled": "已取消",
}
# Stocktaking.stocktaking_type / line_granularity（models/stocktaking.py:29,74）
_STOCKTAKING_TYPE_ZH = {
    "full": "全盘",
    "partial": "部分盘点",
    "cycle": "循环盘点",
}
_GRANULARITY_ZH = {"material": "物料粒度", "batch": "批次粒度"}
_STOCKTAKING_VIEWS = frozenset({"order", "history"})

_TOP_N = 10
_ORDER_ITEM_CAP = 2000  # 按单明细内部取数上限（超出截断注明）
_HISTORY_ORDER_CAP = 50  # history 视图盘点单上限
_HISTORY_ITEM_CAP = 2000  # history 视图明细行内部取数上限
_OVERSAMPLE_LIMIT = 100  # 列表过采样（service 分页后再按范围收敛）


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _dc():
    """document_chain 的 ``_perm_view``/``_code_allowed`` 延迟借用
    （双视图按视图判读权限的唯一路径，不复制实现）。"""
    from apps.kuaiai.services.tools import document_chain

    return document_chain


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fmt_dt(value: Any) -> str:
    """datetime/date 展示：datetime 经 API 同口径站点时区文本，date 取 ISO
    日（缺省 ''，交由调用方补「未知」）。stocktaking_date 为 DatetimeField。"""
    if value is None:
        return ""
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
    return s[:16] if s else ""


def _fmt_pct(ratio: Optional[Decimal]) -> str:
    if ratio is None:
        return "—"
    return f"{(ratio * 100).quantize(Decimal('0.1'))}%"


def _diff_rate(diff_qty: Decimal, book_qty: Decimal) -> Optional[Decimal]:
    """数量差异率 = |差异量| / 账存；账存为 0 返回 None（标「—」）。"""
    if book_qty == 0:
        return None
    return abs(diff_qty) / abs(book_qty)


def _diff_label(diff_qty: Decimal) -> str:
    if diff_qty > 0:
        return "盘盈"
    if diff_qty < 0:
        return "盘亏"
    return "持平"


def _fmt_stocktaking_row(s: Any) -> str:
    scope = _STOCKTAKING_TYPE_ZH.get(
        str(getattr(s, "stocktaking_type", "") or ""), ""
    ) or str(getattr(s, "stocktaking_type", "") or "未知")
    gran = _GRANULARITY_ZH.get(
        str(getattr(s, "line_granularity", "") or ""), ""
    )
    if gran:
        scope = f"{scope}/{gran}"
    if getattr(s, "include_zero_stock", False):
        scope += "（含零库存行）"
    status = str(getattr(s, "status", "") or "")
    status_zh = _STOCKTAKING_STATUS_ZH.get(status)
    status_text = f"{status_zh}({status})" if status_zh else (status or "未知")
    return (
        f"盘点单 {getattr(s, 'code', '')}"
        f" @ {getattr(s, 'warehouse_name', '') or '未配置仓库'}："
        f"{scope}，状态 {status_text}，"
        f"盘点日期 {_fmt_dt(getattr(s, 'stocktaking_date', None)) or '未知'}，"
        f"明细 {getattr(s, 'total_items', 0) or 0} 项"
        f"/已盘 {getattr(s, 'counted_items', 0) or 0}"
        f"/差异 {getattr(s, 'total_differences', 0) or 0}，"
        f"差异金额 {_ct()._fmt_num(getattr(s, 'total_difference_amount', None))}"
        f"（id={getattr(s, 'id', '')}）"
    )


async def query_stocktakings(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """盘点单摘要（单号/仓库/盘点范围/状态/盘点日期，范围内过滤）。

    ``date_start``/``date_end`` 按盘点日期过滤（YYYY-MM-DD，含界）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    s_status = (str(status).strip() or None) if status else None
    if s_status is not None and s_status not in _STOCKTAKING_STATUSES:
        return "status 仅支持 draft/in_progress/completed/cancelled"
    d_start = _st()._parse_date(date_start)
    if date_start and d_start is None:
        return "date_start 须为 YYYY-MM-DD"
    d_end = _st()._parse_date(date_end)
    if date_end and d_end is None:
        return "date_end 须为 YYYY-MM-DD"
    wid: Optional[int] = None
    if warehouse_id is not None and str(warehouse_id).strip() != "":
        try:
            wid = int(warehouse_id)
        except (TypeError, ValueError):
            return "warehouse_id 须为正整数"
        if wid <= 0:
            return "warehouse_id 须为正整数"
    try:
        from apps.kuaizhizao.services.stocktaking_service import (
            StocktakingService,
        )

        fetch = min(
            max(_ct()._clamp_limit(limit) * 5, 50), _OVERSAMPLE_LIMIT
        )
        resp = await StocktakingService().list_stocktakings(
            ctx.tenant_id,
            skip=0,
            limit=fetch,
            keyword=(str(keyword).strip() or None) if keyword else None,
            warehouse_id=wid,
            status=s_status,
            stocktaking_date_start=str(d_start) if d_start else None,
            stocktaking_date_end=str(d_end) if d_end else None,
        )
        rows = list(getattr(resp, "items", None) or [])
    except Exception as exc:
        logger.warning(
            "AI tool query_stocktakings 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询盘点单失败，请稍后重试"
    if not rows:
        return "未查询到符合条件的盘点单"

    try:
        from apps.kuaizhizao.models.stocktaking import Stocktaking

        visible = await _st()._scoped_row_ids(
            Stocktaking,
            ctx,
            _SCOPE_STOCKTAKING,
            {int(r.id) for r in rows if getattr(r, "id", None)},
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_stocktakings 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询盘点单失败，请稍后重试"
    rows = [r for r in rows if int(getattr(r, "id", 0) or 0) in visible]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的盘点单"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 张盘点单（当前用户数据范围内，"
        f"前 {_OVERSAMPLE_LIMIT} 条候选内计），返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_stocktaking_row(r))
    return "\n".join(lines)


async def _stocktaking_in_scope(
    ctx: AiRuntimeContext, stocktaking_id: Any
) -> Optional[int]:
    """盘点单 by-ID 行级范围复核；范围外/非法 id 返回 None（按不存在）。"""
    try:
        sid = int(stocktaking_id)
    except (TypeError, ValueError):
        return None
    if sid <= 0:
        return None
    try:
        from apps.kuaizhizao.models.stocktaking import Stocktaking

        visible = await _st()._scoped_row_ids(
            Stocktaking, ctx, _SCOPE_STOCKTAKING, {sid}
        )
        return sid if sid in visible else None
    except Exception as exc:
        logger.warning(
            "AI tool 盘点单数据范围解析失败 error_type={}", type(exc).__name__
        )
        return None


async def _material_group_names(
    ctx: AiRuntimeContext, material_ids: List[int]
) -> Dict[int, str]:
    """material_id → 物料分组名（Material.group_id → MaterialGroup.name）。"""
    if not material_ids:
        return {}
    from apps.master_data.models.material import Material, MaterialGroup

    mats = await Material.filter(
        tenant_id=ctx.tenant_id,
        id__in=list(material_ids),
        deleted_at__isnull=True,
    ).values("id", "group_id")
    group_ids = {
        int(m["group_id"]) for m in mats if m.get("group_id") is not None
    }
    names: Dict[int, str] = {}
    if group_ids:
        groups = await MaterialGroup.filter(
            tenant_id=ctx.tenant_id,
            id__in=list(group_ids),
            deleted_at__isnull=True,
        ).values("id", "name")
        names = {
            int(g["id"]): str(g.get("name") or "") for g in groups
        }
    return {
        int(m["id"]): names.get(int(m["group_id"]))
        if m.get("group_id") is not None
        else None
        for m in mats
    }


def _material_agg(items: List[Any]) -> Dict[int, Dict[str, Any]]:
    """按物料聚合明细（可复算口径：Σ账存 / Σ实盘 / Σ差异量 / Σ差异金额）。

    未盘行 actual_quantity 为 None 按 0 计入实盘合计（差异量取 service
    已存 ``difference_quantity`` 字段，与单头统计同口径）。
    """
    agg: Dict[int, Dict[str, Any]] = {}
    for it in items:
        mid = int(getattr(it, "material_id", 0) or 0)
        slot = agg.setdefault(
            mid,
            {
                "material_id": mid,
                "material_code": getattr(it, "material_code", "") or "",
                "material_name": getattr(it, "material_name", "") or "",
                "material_unit": getattr(it, "material_unit", "") or "",
                "lines": 0,
                "pending": 0,
                "book": Decimal("0"),
                "actual": Decimal("0"),
                "diff_qty": Decimal("0"),
                "diff_amt": Decimal("0"),
            },
        )
        slot["lines"] += 1
        actual = getattr(it, "actual_quantity", None)
        if actual is None:
            slot["pending"] += 1
        slot["book"] += _dec(getattr(it, "book_quantity", None))
        slot["actual"] += _dec(actual)
        slot["diff_qty"] += _dec(getattr(it, "difference_quantity", None))
        slot["diff_amt"] += _dec(getattr(it, "difference_amount", None))
    return agg


async def _variance_by_order(ctx: AiRuntimeContext, stocktaking_id: Any) -> str:
    admin, codes = await _dc()._perm_view(ctx)
    if not _dc()._code_allowed(_PERM_STOCKTAKING_READ, admin, codes):
        return "当前用户无权查看盘点单明细"
    sid = await _stocktaking_in_scope(ctx, stocktaking_id)
    if sid is None:
        return "盘点单不存在或超出当前用户数据范围"
    try:
        from apps.kuaizhizao.services.stocktaking_service import (
            StocktakingService,
        )
        from infra.exceptions.exceptions import NotFoundError

        try:
            resp = await StocktakingService().get_stocktaking_by_id(
                ctx.tenant_id, sid
            )
        except NotFoundError:
            return "盘点单不存在或超出当前用户数据范围"
    except Exception as exc:
        logger.warning(
            "AI tool analyze_stocktaking_variance 取单失败 error_type={}",
            type(exc).__name__,
        )
        return "分析盘点差异失败，请稍后重试"

    all_items = list(getattr(resp, "items", None) or [])
    truncated = len(all_items) > _ORDER_ITEM_CAP
    items = all_items[:_ORDER_ITEM_CAP]
    if not items:
        return (
            f"盘点单 {getattr(resp, 'code', '')} 暂无盘点明细，"
            "无可分析差异"
        )
    agg = _material_agg(items)
    total_lines = len(items)
    pending_lines = sum(v["pending"] for v in agg.values())
    diff_slots = [
        v for v in agg.values() if v["diff_qty"] != 0 or v["diff_amt"] != 0
    ]
    sum_book = sum((v["book"] for v in agg.values()), Decimal("0"))
    sum_diff = sum((v["diff_qty"] for v in agg.values()), Decimal("0"))
    sum_amt = sum((v["diff_amt"] for v in agg.values()), Decimal("0"))
    diff_line_count = sum(
        1
        for it in items
        if _dec(getattr(it, "difference_quantity", None)) != 0
    )

    head_status = str(getattr(resp, "status", "") or "")
    head_status_zh = _STOCKTAKING_STATUS_ZH.get(head_status)
    head_status_text = (
        f"{head_status_zh}({head_status})" if head_status_zh else (head_status or "未知")
    )
    out = [
        f"盘点单 {getattr(resp, 'code', '')}"
        f" @ {getattr(resp, 'warehouse_name', '') or '未配置仓库'}："
        f"状态 {head_status_text}，"
        f"盘点日期 {_fmt_dt(getattr(resp, 'stocktaking_date', None)) or '未知'}，"
        f"明细 {total_lines} 行（已盘 {total_lines - pending_lines} 行"
        f"{'、含 ' + str(pending_lines) + ' 行未录入实盘' if pending_lines else ''}，"
        f"差异 {diff_line_count} 行），"
        f"账面合计 {_ct()._fmt_num(sum_book)}，"
        f"差异量合计 {_ct()._fmt_num(sum_diff)}，"
        f"差异金额合计 {_ct()._fmt_num(sum_amt)}，"
        f"数量差异率 {_fmt_pct(_diff_rate(sum_diff, sum_book))}",
        "口径：差异量=实盘−账存（正=盘盈、负=盘亏），差异金额=差异量×单价；"
        "差异率=|差异量|/账存；数值按明细复算" + ("，明细超上限已截断" if truncated else ""),
    ]
    if not diff_slots:
        out.append("账实一致，无差异明细")
        return "\n".join(out)

    diff_slots.sort(
        key=lambda v: (abs(v["diff_amt"]), abs(v["diff_qty"])),
        reverse=True,
    )
    out.append(
        f"差异物料 Top{min(_TOP_N, len(diff_slots))}"
        f"（共 {len(diff_slots)} 种差异物料，按|差异金额|降序）："
    )
    for v in diff_slots[:_TOP_N]:
        out.append(
            f"- 物料 {v['material_code']}（{v['material_name'] or '未命名'}）："
            f"账存 {_ct()._fmt_num(v['book'])}"
            f"/实盘 {_ct()._fmt_num(v['actual'])}"
            f"/差异 {_ct()._fmt_num(v['diff_qty'])}（{_diff_label(v['diff_qty'])}）"
            f"/差异金额 {_ct()._fmt_num(v['diff_amt'])}"
            f"/差异率 {_fmt_pct(_diff_rate(v['diff_qty'], v['book']))}"
        )

    try:
        group_names = await _material_group_names(
            ctx, [v["material_id"] for v in diff_slots]
        )
        by_group: Dict[str, Dict[str, Any]] = {}
        for v in diff_slots:
            g = group_names.get(v["material_id"]) or "未分组"
            slot = by_group.setdefault(
                g,
                {"materials": 0, "diff_qty": Decimal("0"), "diff_amt": Decimal("0")},
            )
            slot["materials"] += 1
            slot["diff_qty"] += v["diff_qty"]
            slot["diff_amt"] += v["diff_amt"]
        groups = sorted(
            by_group.items(),
            key=lambda kv: (abs(kv[1]["diff_amt"]), abs(kv[1]["diff_qty"])),
            reverse=True,
        )
        out.append("按物料类别汇总（仅差异物料）：")
        for name, g in groups[:_TOP_N]:
            out.append(
                f"- {name}：差异物料 {g['materials']} 种，"
                f"差异量 {_ct()._fmt_num(g['diff_qty'])}，"
                f"差异金额 {_ct()._fmt_num(g['diff_amt'])}"
            )
    except Exception as exc:
        logger.warning(
            "AI tool analyze_stocktaking_variance 类别汇总失败 error_type={}",
            type(exc).__name__,
        )
        out.append("（物料类别汇总获取失败，差异明细不受影响）")
    return "\n".join(out)


async def _variance_history(
    ctx: AiRuntimeContext,
    date_start: Optional[str],
    date_end: Optional[str],
) -> str:
    admin, codes = await _dc()._perm_view(ctx)
    if not _dc()._code_allowed(_PERM_HISTORY_READ, admin, codes):
        return "当前用户无权查看盘点历史报表"
    d_start = _st()._parse_date(date_start)
    if date_start and d_start is None:
        return "date_start 须为 YYYY-MM-DD"
    d_end = _st()._parse_date(date_end)
    if date_end and d_end is None:
        return "date_end 须为 YYYY-MM-DD"
    try:
        from apps.kuaizhizao.models.stocktaking import (
            Stocktaking,
            StocktakingItem,
        )

        hqs = Stocktaking.filter(
            tenant_id=ctx.tenant_id, deleted_at__isnull=True
        )
        if d_start:
            hqs = hqs.filter(stocktaking_date__gte=d_start)
        if d_end:
            # 口径继承报表 service ``_get_stocktaking_history``
            # （report_service.py 同写 stocktaking_date__lte=end_d 直传
            # date）：date 按当日零点比较，d_end 当日零点后的盘点单不含。
            # 与 query_stocktakings 经 apply_equipment_document_date_range
            # 的「当日含界（combine(end, time.max)）」不同——为报表历史
            # 同口径继承，非缺陷，不改行为。
            hqs = hqs.filter(stocktaking_date__lte=d_end)
        hqs = await _st()._apply_scope(
            hqs, ctx.tenant_id, ctx, _SCOPE_STOCKTAKING_HISTORY
        )
        headers = await hqs.order_by("stocktaking_date", "id").values(
            "id", "code", "warehouse_name", "stocktaking_date", "status"
        )
    except Exception as exc:
        logger.warning(
            "AI tool analyze_stocktaking_variance(history) 取单失败 error_type={}",
            type(exc).__name__,
        )
        return "分析盘点差异失败，请稍后重试"
    if not headers:
        return "期间内当前用户数据范围内无盘点单记录"
    total_orders = len(headers)
    orders_truncated = total_orders > _HISTORY_ORDER_CAP
    headers = headers[:_HISTORY_ORDER_CAP]
    header_ids = [int(h["id"]) for h in headers]
    try:
        items = await StocktakingItem.filter(
            tenant_id=ctx.tenant_id,
            deleted_at__isnull=True,
            stocktaking_id__in=header_ids,
        ).order_by("stocktaking_id", "id").limit(_HISTORY_ITEM_CAP).values(
            "stocktaking_id",
            "location_code",
            "book_quantity",
            "actual_quantity",
            "difference_quantity",
            "difference_amount",
        )
        items_truncated = len(items) >= _HISTORY_ITEM_CAP
    except Exception as exc:
        logger.warning(
            "AI tool analyze_stocktaking_variance(history) 取明细失败 error_type={}",
            type(exc).__name__,
        )
        return "分析盘点差异失败，请稍后重试"

    by_order: Dict[int, Dict[str, Any]] = {
        int(h["id"]): {
            "lines": 0,
            "diff_lines": 0,
            "book": Decimal("0"),
            "diff_qty": Decimal("0"),
            "diff_amt": Decimal("0"),
        }
        for h in headers
    }
    by_loc: Dict[str, Dict[str, Any]] = {}
    for it in items:
        # 明细按 stocktaking_id__in=header_ids 取数，必命中 by_order
        slot = by_order[int(it["stocktaking_id"])]
        dq = _dec(it.get("difference_quantity"))
        da = _dec(it.get("difference_amount"))
        slot["lines"] += 1
        slot["book"] += _dec(it.get("book_quantity"))
        slot["diff_qty"] += dq
        slot["diff_amt"] += da
        loc = str(it.get("location_code") or "").strip() or "未指定库位"
        lslot = by_loc.setdefault(
            loc,
            {"lines": 0, "diff_lines": 0, "diff_qty": Decimal("0"), "diff_amt": Decimal("0")},
        )
        lslot["lines"] += 1
        lslot["diff_qty"] += dq
        lslot["diff_amt"] += da
        if dq != 0:
            slot["diff_lines"] += 1
            lslot["diff_lines"] += 1

    range_text = f"{d_start or '…'} ~ {d_end or '…'}"
    out = [
        f"盘点历史（盘点日期 {range_text}，范围内 {total_orders} 张盘点单，"
        f"样本明细 {len(items)} 行）：",
        "口径：差异量=实盘−账存；差异行占比=差异明细行/明细行；"
        "数量差异率=|Σ差异量|/Σ账存（账存为 0 标 —）"
        + ("；单数/明细超上限已截断" if (orders_truncated or items_truncated) else ""),
        "各盘点单差异率（按盘点日期升序）：",
    ]
    for h in headers:
        oid = int(h["id"])
        slot = by_order[oid]
        status = str(h.get("status") or "")
        status_zh = _STOCKTAKING_STATUS_ZH.get(status)
        status_text = f"{status_zh}({status})" if status_zh else (status or "未知")
        rate = (
            (Decimal(slot["diff_lines"]) / Decimal(slot["lines"]))
            if slot["lines"]
            else None
        )
        out.append(
            f"- {h.get('code') or ''}"
            f"（{_fmt_dt(h.get('stocktaking_date'))}，"
            f"{h.get('warehouse_name') or '未配置仓库'}，{status_text}）："
            f"明细 {slot['lines']} 行/差异 {slot['diff_lines']} 行"
            f"（差异行占比 {_fmt_pct(rate)}），"
            f"数量差异率 {_fmt_pct(_diff_rate(slot['diff_qty'], slot['book']))}，"
            f"差异金额 {_ct()._fmt_num(slot['diff_amt'])}"
            f"（id={oid}）"
        )
    diff_locs = [
        (loc, v) for loc, v in by_loc.items() if v["diff_lines"] > 0
    ]
    if not diff_locs:
        out.append("库位汇总：样本内各库位账实一致，无差异")
    else:
        diff_locs.sort(
            key=lambda kv: (abs(kv[1]["diff_amt"]), abs(kv[1]["diff_qty"])),
            reverse=True,
        )
        out.append(
            f"库位差异汇总（按|差异金额|降序，前 "
            f"{min(_TOP_N, len(diff_locs))} 个差异库位）："
        )
        for loc, v in diff_locs[:_TOP_N]:
            out.append(
                f"- 库位 {loc}：差异 {v['diff_lines']} 行"
                f"/明细 {v['lines']} 行，"
                f"差异量 {_ct()._fmt_num(v['diff_qty'])}，"
                f"差异金额 {_ct()._fmt_num(v['diff_amt'])}"
            )
    return "\n".join(out)


async def analyze_stocktaking_variance(
    stocktaking_id: Optional[int] = None,
    view: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """盘点差异解读：按单聚合差异 TopN + 物料类别汇总；view=history 给
    各盘点单差异率趋势与库位汇总。

    按单为默认视图，须 ``stocktaking_id``；``view=history`` 与
    ``stocktaking_id`` 互斥，支持 ``date_start``/``date_end``（盘点日期，
    YYYY-MM-DD 含界）。差异事实来自盘点明细确定性聚合；排查方向话术由
    模型另行生成（本 Tool 不生成建议）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    resolved_view = str(view or "order").strip().lower()
    if resolved_view not in _STOCKTAKING_VIEWS:
        return "view 仅支持 order（按单，须 stocktaking_id）|history（历史趋势）"
    if resolved_view == "history":
        if stocktaking_id is not None:
            return "view=history 与 stocktaking_id 不能同时使用"
        return await _variance_history(ctx, date_start, date_end)
    if stocktaking_id is None:
        return "按单分析须提供 stocktaking_id（盘点单 id，可由 query_stocktakings 获取）"
    return await _variance_by_order(ctx, stocktaking_id)
