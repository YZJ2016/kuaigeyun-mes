"""KU-AI 场景只读 Tool：工艺路线（spec 200）。

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
"""

from __future__ import annotations

from typing import Any, List, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_SCOPE_ROUTE = "master-data:process:route"


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


async def query_process_routes(
    keyword: Optional[str] = None,
    material_id: Optional[int] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """工艺路线有界摘要：编码/名称/版本/工序序列（工序编码+名称）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    lim = _ct()._clamp_limit(limit)
    kw = (str(keyword).strip() or None) if keyword else None
    mat_id: Optional[int] = None
    if material_id is not None:
        try:
            mat_id = int(material_id)
        except (TypeError, ValueError):
            return "material_id 须为物料 ID 整数"
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
        f"上限 {lim} 条内计），返回前 {len(items)} 条："
    ]
    for r in items:
        lines.append(_route_line(r, tree_map))
    return "\n".join(lines)
