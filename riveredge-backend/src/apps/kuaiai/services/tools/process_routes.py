"""KU-AI 场景只读 Tool：工艺路线（spec 200；spec 213 补 view=parameters）。

Tool 名：``query_process_routes``；权限码 ``master-data:process:route:read``
（与列表路由同源 manifest 权限段），数据范围键 ``master-data:process:route``
逐行套 ``_scoped_row_ids`` 收敛。

T1 事实（写 §4）：
- ``ProcessService.list_process_routes(tenant_id, skip, limit, is_active,
  keyword, ...)`` → ``(items, total)``，keyword 模糊 code/name/description；
  无 ``material_id`` 形参——物料绑定路线经 ``Material.process_route_id``
  （物料级）→ ``MaterialGroup.process_route_id``（分组兜底）解析出路线 id
  后逐行过滤。service 的 ``total`` 未做物料/行级范围收敛（全租户计数），
  摘要不回显 total，只回显收敛后条数（评审 minor-7）。
- 工序序列不复制解析：``get_process_route_tree(tenant_id, is_active=None,
  route_ids=已收敛路线 id)`` 按 id 收窄路线与引用工序批量取树
  （评审 minor-7：不再全租户拉树）。

spec 213 T1 结论（复用，不新登记 Tool）：本单元需求 ``material_id|view`` 与
既有参数面重合（material_id 反查 + 工序节点序列），仅补
``view=parameters``——物料级工序参数经
``MaterialProductProcessService.get_for_material(tenant_id, material.uuid)``
（路线模板行与物料产品工艺存储行合并口径，与产品工艺页同源）；物料行级
套 ``master-data:material`` 数据范围。``route_id`` 直查未补（按路线编码
可用 keyword 命中），记入 spec 213 §4 偏差。计件单价 piece_rate 属工资
敏感不输出。
"""

from __future__ import annotations

from typing import Any, List, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_SCOPE_ROUTE = "master-data:process:route"
_SCOPE_MATERIAL = "master-data:material"

# view 闭集（spec 213）：nodes 路线+工序序列（既有默认），
# parameters 物料级工序参数（工时/准备/报工/委外，不含计件单价）
_ROUTE_VIEWS = frozenset({"nodes", "parameters"})


def _ct():
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


async def _resolve_material_route_id(ctx: AiRuntimeContext, material_id: int):
    """物料绑定路线 id：物料级 → 分组兜底；物料缺失/未绑定 → None。"""
    from apps.master_data.models.material import Material, MaterialGroup

    material = await Material.filter(
        tenant_id=ctx.tenant_id,
        id=int(material_id),
        deleted_at__isnull=True,
    ).first()
    if material is None:
        return None
    if getattr(material, "process_route_id", None):
        return int(material.process_route_id)
    group_id = getattr(material, "group_id", None)
    if group_id:
        group = await MaterialGroup.filter(
            tenant_id=ctx.tenant_id,
            id=int(group_id),
            deleted_at__isnull=True,
        ).first()
        if group is not None and getattr(group, "process_route_id", None):
            return int(group.process_route_id)
    return None


def _route_line(route: Any, tree_map: dict) -> str:
    ops = list(getattr(tree_map.get(getattr(route, "id", None)), "operations", None) or [])
    op_text = " → ".join(
        f"{getattr(o, 'code', '')} {getattr(o, 'name', '')}".strip() or "-"
        for o in ops
    ) or "未配置工序"
    status = "启用" if getattr(route, "is_active", True) else "停用"
    version = getattr(route, "version", None) or "1.0"
    return (
        f"路线 {getattr(route, 'code', '-')} {getattr(route, 'name', '-')}："
        f"版本 {version}，{status}，工序：{op_text}"
    )


def _fmt_seconds(value: Any) -> str:
    """秒数 → '3600 秒'（缺省 '—'）。"""
    if value is None:
        return "—"
    try:
        return f"{float(value):g} 秒"
    except (TypeError, ValueError):
        return str(value)


def _fmt_line_parameters(line: Any) -> str:
    """产品工艺工序行摘要：工时/准备/报工/委外/超报（不含计件单价）。"""
    std = _fmt_seconds(getattr(line, "standard_time", None))
    qty = _ct()._fmt_num(getattr(line, "standard_time_qty", None) or 1)
    parts = [
        f"标准工时 {std}/每 {qty} 件",
        f"准备 {_fmt_seconds(getattr(line, 'setup_time', None))}",
        f"报工 {getattr(line, 'reporting_type', None) or 'quantity'}",
    ]
    if getattr(line, "is_node_operation", False):
        parts.append("节点工序")
    if getattr(line, "is_outsourced", False):
        text = "委外"
        days = getattr(line, "outsource_lead_time_days", None)
        if days is not None:
            text += f"（提前期 {days} 天"
            supplier = getattr(line, "outsource_supplier_name", None)
            if supplier:
                text += f"，供应商 {supplier}"
            text += "）"
        parts.append(text)
    mode = str(getattr(line, "over_report_mode", None) or "none")
    if mode != "none":
        value = _ct()._fmt_num(getattr(line, "over_report_value", None))
        parts.append(f"超报 {mode} {value}")
    return (
        f"  工序 {getattr(line, 'code', '') or ''}"
        f"（{getattr(line, 'name', '') or '未命名'}）：" + "，".join(parts)
    )


async def _query_route_parameters(
    ctx: AiRuntimeContext, material_id: int, lim: int
) -> str:
    """view=parameters：物料级工序参数（路线模板行+物料产品工艺合并口径）。"""
    from apps.master_data.models.material import Material

    try:
        material = await Material.filter(
            tenant_id=ctx.tenant_id,
            id=int(material_id),
            deleted_at__isnull=True,
        ).first()
        if material is None:
            return "物料不存在"
        visible = await _st()._scoped_row_ids(
            Material, ctx, _SCOPE_MATERIAL, {int(material.id)}
        )
        if int(material.id) not in visible:
            return "当前用户数据范围内无该物料"

        from apps.master_data.services.material_product_process_service import (
            MaterialProductProcessService,
        )
        from infra.exceptions.exceptions import NotFoundError

        try:
            resp = await MaterialProductProcessService.get_for_material(
                ctx.tenant_id, str(material.uuid)
            )
        except NotFoundError:
            return "物料不存在"
    except Exception as exc:
        logger.warning(
            "AI tool query_process_routes parameters 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询工艺路线失败，请稍后重试"

    mcode = getattr(material, "main_code", None) or getattr(material, "code", "")
    rows = list(getattr(resp, "lines", None) or [])
    if not rows:
        return (
            f"物料 {mcode}（{getattr(material, 'name', '') or '未命名'}）"
            "暂无配置工序参数"
        )
    top = rows[:lim]
    lines = [
        f"物料 {mcode}（{getattr(material, 'name', '') or '未命名'}）"
        f"工序参数共 {len(rows)} 道，返回前 {len(top)} 道："
    ]
    for ln in top:
        lines.append(_fmt_line_parameters(ln))
    if len(rows) > lim:
        lines.append(f"……另有 {len(rows) - lim} 道未展开")
    return "\n".join(lines)


async def query_process_routes(
    keyword: Optional[str] = None,
    material_id: Optional[int] = None,
    view: str = "nodes",
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """工艺路线有界摘要：编码/名称/版本/工序序列（工序编码+名称）。

    view=nodes（默认）既有行为不变；view=parameters 须传 material_id，
    输出物料级工序参数（工时/准备/报工/委外/超报，不含计件单价）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    resolved_view = str(view or "nodes").strip()
    if resolved_view not in _ROUTE_VIEWS:
        return "view 仅支持 nodes|parameters"
    lim = _ct()._clamp_limit(limit)
    kw = (str(keyword).strip() or None) if keyword else None
    mat_id: Optional[int] = None
    if material_id is not None:
        try:
            mat_id = int(material_id)
        except (TypeError, ValueError):
            return "material_id 须为物料 ID 整数"
        if mat_id <= 0:
            return "material_id 须为物料 ID 正整数"
    if resolved_view == "parameters":
        if mat_id is None:
            return "view=parameters 须传 material_id（工序参数为物料级数据）"
        return await _query_route_parameters(ctx, mat_id, lim)
    try:
        wanted_route_id: Optional[int] = None
        if mat_id is not None:
            wanted_route_id = await _resolve_material_route_id(ctx, mat_id)
            if wanted_route_id is None:
                return "该物料未绑定工艺路线或物料不存在"

        from apps.master_data.models.process import ProcessRoute
        from apps.master_data.services.process_service import ProcessService

        items, _total = await ProcessService.list_process_routes(
            ctx.tenant_id,
            skip=0,
            limit=lim,
            keyword=kw,
        )
        if wanted_route_id is not None:
            items = [
                r for r in items if int(getattr(r, "id", 0) or 0) == wanted_route_id
            ]
            if not items:
                # keyword 叠加时可能把目标路线滤掉；直接补查该行（仍过数据范围）
                row = await ProcessRoute.filter(
                    tenant_id=ctx.tenant_id,
                    id=wanted_route_id,
                    deleted_at__isnull=True,
                ).first()
                items = [row] if row is not None else []
        ids = {int(getattr(r, "id", 0) or 0) for r in items} - {0}
        visible = await _st()._scoped_row_ids(
            ProcessRoute, ctx, _SCOPE_ROUTE, ids
        )
        items = [r for r in items if int(getattr(r, "id", 0) or 0) in visible]

        tree_map = {}
        if items:
            # 只按已收敛 route ids 取树（含工序），不拉全租户路线/工序
            tree = await ProcessService.get_process_route_tree(
                ctx.tenant_id,
                is_active=None,
                route_ids=[int(r.id) for r in items],
            )
            tree_map = {getattr(t, "id", None): t for t in tree}
    except Exception as exc:
        logger.warning(
            "AI tool query_process_routes 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询工艺路线失败，请稍后重试"

    if not items:
        return "未查询到符合条件的工艺路线"
    # 计数口径（评审 minor-7）：service total 是未做物料/行级范围收敛的
    # 全租户计数，不回显；以收敛后条数为准并标注口径
    lines: List[str] = [
        f"共 {len(items)} 条工艺路线（当前用户数据范围内，"
        f"上限 {lim} 条内计）："
    ]
    for r in items:
        lines.append(_route_line(r, tree_map))
    return "\n".join(lines)
