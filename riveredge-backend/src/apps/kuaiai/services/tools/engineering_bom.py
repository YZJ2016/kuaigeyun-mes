"""KU-AI 场景只读 Tool：工程 BOM 与物料/图纸反查（spec 212 X4=a + spec 213，S24）。

Tool 名：``query_material_where_used`` / ``query_drawing_where_used`` /
``query_engineering_bom``。

- X4=a（spec 212 §1 已选定）：where-used 拆两个 Tool、一 Tool 一权限码——
  ``query_material_where_used`` 仅 BOM 反查（``master-data:process:
  engineering-bom:read``），``query_drawing_where_used`` 仅图纸反查
  （``master-data:process:drawing-where-used:read``）；工艺引用不单列视图
  （物料→工艺路线绑定走 ``query_process_routes(material_id=…)``）。
- ``query_material_where_used``：``MaterialService.list_bom_where_used``
  （recursive 可选多阶），父件行级套 ``master-data:material`` 数据范围。
- ``query_drawing_where_used``：``DrawingWhereUsedService.query``，
  ``material_id``（物料→引用图纸，正向）或 ``drawing_uuid``（图纸→被引用
  对象，反向）二选一必填；图纸密级由 service 经 ``current_user``
  ``allowed_security_levels`` 收敛。
- ``query_engineering_bom``：``MaterialService.generate_bom_hierarchy``
  （与工程 BOM 页/打印同源的层级树），view=tree 缩进 / flat 平铺 /
  substitutes 替代料组；``level`` 展开深度 1-5；节点超 ``_BOM_NODE_MAX``
  截断并注明总节点数；物料/子件行级套 ``master-data:material`` 数据范围
  （material:bom reference_resources 无独立 data_scope_key，物料即范围键，
  spec 213 T1 定）。
- 不输出供应商进价、客户专属信息、图纸文件正文。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

_SCOPE_MATERIAL = "master-data:material"

_BOM_VIEWS = frozenset({"tree", "flat", "substitutes"})
_BOM_LEVEL_MAX = 5
# BOM 树/平铺展开节点上限（超出截断并注明总节点数）
_BOM_NODE_MAX = 50

_USAGE_KIND_ZH = {
    "material": "物料",
    "bom": "BOM",
    "process_route": "工艺路线",
    "operation": "工序",
    "work_order": "工单",
}


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


async def _material_row(ctx: AiRuntimeContext, material_id: int):
    """物料行（tenant+软删）；不存在返回 None。"""
    from apps.master_data.models.material import Material

    return await Material.filter(
        tenant_id=ctx.tenant_id,
        id=int(material_id),
        deleted_at__isnull=True,
    ).first()


async def _material_visible(ctx: AiRuntimeContext, material_id: int) -> bool:
    """物料行级数据范围复核（master-data:material）。"""
    from apps.master_data.models.material import Material

    visible = await _st()._scoped_row_ids(
        Material, ctx, _SCOPE_MATERIAL, {int(material_id)}
    )
    return int(material_id) in visible


async def query_material_where_used(
    material_id: int,
    recursive: bool = False,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """物料 BOM 反查：该物料被哪些父件/BOM 作为子件引用（X4=a 仅 BOM 视图）。

    ``recursive=True`` 展开多阶引用链（path 为 子件 > … > 父件 路径）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        mid = int(material_id)
    except (TypeError, ValueError):
        return "material_id 须为物料 ID 整数"
    if mid <= 0:
        return "material_id 须为物料 ID 正整数"
    try:
        material = await _material_row(ctx, mid)
        if material is None:
            return "物料不存在"
        if not await _material_visible(ctx, mid):
            return "当前用户数据范围内无该物料"

        from apps.master_data.models.material import Material
        from apps.master_data.services.material_service import MaterialService

        result = await MaterialService.list_bom_where_used(
            ctx.tenant_id, mid, recursive=bool(recursive)
        )
        items = list((result or {}).get("items") or [])
        total = int((result or {}).get("total") or len(items))
        parent_ids = {int(r["material_id"]) for r in items if r.get("material_id")}
        visible = await _st()._scoped_row_ids(
            Material, ctx, _SCOPE_MATERIAL, parent_ids
        )
        items = [r for r in items if int(r.get("material_id") or 0) in visible]
    except Exception as exc:
        logger.warning(
            "AI tool query_material_where_used 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询物料 BOM 反查失败，请稍后重试"

    mcode = getattr(material, "main_code", None) or getattr(material, "code", "")
    if not items:
        return f"物料 {mcode}（{getattr(material, 'name', '') or '未命名'}）未被任何 BOM 引用"
    lim = _ct()._clamp_limit(limit)
    top = items[:lim]
    scope_note = "多阶" if recursive else "直接父件"
    lines = [
        f"物料 {mcode}（{getattr(material, 'name', '') or '未命名'}）"
        f"被 {total} 处 BOM 引用（{scope_note}，数据范围内 {len(items)} 处），"
        f"返回前 {len(top)} 处："
    ]
    for r in top:
        path_note = ""
        if recursive and r.get("path"):
            path_note = f"，路径 {r.get('path')}"
        lines.append(
            f"  父件 {r.get('material_code') or ''}"
            f"（{r.get('material_name') or '未命名'}）："
            f"BOM {r.get('bom_code') or '-'} 版本 {r.get('version') or '-'}，"
            f"用量 {_ct()._fmt_num(r.get('quantity'))}{r.get('unit') or ''}，"
            f"审核 {r.get('approval_status') or '未知'}"
            f"{path_note}"
        )
    if len(items) > lim:
        lines.append(f"……另有 {len(items) - lim} 处未展开")
    return "\n".join(lines)


async def query_drawing_where_used(
    material_id: Optional[int] = None,
    drawing_uuid: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """图纸反查（X4=a 仅图纸视图）：物料→引用图纸，或图纸→被引用对象。

    ``material_id`` 与 ``drawing_uuid`` 二选一必填；密级收敛由
    ``DrawingWhereUsedService(current_user=ctx.user)`` 保证。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    has_material = material_id is not None and str(material_id).strip() != ""
    has_drawing = bool(str(drawing_uuid or "").strip())
    if has_material == has_drawing:
        return "material_id 与 drawing_uuid 须且只须传一个"
    material_uuid: Optional[str] = None
    if has_material:
        try:
            mid = int(material_id)
        except (TypeError, ValueError):
            return "material_id 须为物料 ID 整数"
        if mid <= 0:
            return "material_id 须为物料 ID 正整数"
        try:
            material = await _material_row(ctx, mid)
            if material is None:
                return "物料不存在"
            if not await _material_visible(ctx, mid):
                return "当前用户数据范围内无该物料"
            material_uuid = str(getattr(material, "uuid", "") or "")
        except Exception as exc:
            logger.warning(
                "AI tool query_drawing_where_used 物料解析失败 error_type={}",
                type(exc).__name__,
            )
            return "查询图纸反查失败，请稍后重试"

    try:
        from apps.master_data.services.drawing_where_used_service import (
            DrawingWhereUsedService,
        )
        from infra.exceptions.exceptions import NotFoundError

        try:
            resp = await DrawingWhereUsedService.query(
                ctx.tenant_id,
                material_uuid=material_uuid,
                drawing_uuid=(
                    str(drawing_uuid).strip() if has_drawing else None
                ),
                current_user=ctx.user,
            )
        except NotFoundError as exc:
            return str(exc) or "目标不存在"
    except Exception as exc:
        logger.warning(
            "AI tool query_drawing_where_used 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询图纸反查失败，请稍后重试"

    lim = _ct()._clamp_limit(limit)
    direction = getattr(resp, "direction", "") or ""
    if direction == "forward":
        drawings = list(getattr(resp, "drawings", None) or [])
        if not drawings:
            return "该物料未被任何图纸引用"
        top = drawings[:lim]
        lines = [f"引用该物料的图纸共 {len(drawings)} 张，返回前 {len(top)} 张："]
        for d in top:
            lines.append(
                f"  图纸 {getattr(d, 'code', '') or ''}"
                f"（{getattr(d, 'name', '') or '未命名'}，"
                f"版本 {getattr(d, 'revision', '') or '-'}，"
                f"密级 {getattr(d, 'security_level', '') or '-'}，"
                f"状态 {getattr(d, 'status', '') or '未知'}）"
            )
        if len(drawings) > lim:
            lines.append(f"……另有 {len(drawings) - lim} 张未展开")
        return "\n".join(lines)

    usages = list(getattr(resp, "usages", None) or [])
    drawing = (list(getattr(resp, "drawings", None) or []) or [None])[0]
    head = "图纸反查："
    if drawing is not None:
        head = (
            f"图纸 {getattr(drawing, 'code', '') or ''}"
            f"（{getattr(drawing, 'name', '') or '未命名'}，"
            f"版本 {getattr(drawing, 'revision', '') or '-'}）被引用情况："
        )
    if not usages:
        return f"{head}未被任何对象引用"
    top = usages[:lim]
    lines = [f"{head}共 {len(usages)} 处，返回前 {len(top)} 处："]
    for u in top:
        zh = _USAGE_KIND_ZH.get(str(getattr(u, "kind", "") or ""), "引用")
        extra = getattr(u, "extra", None)
        extra_text = f"，{extra}" if extra else ""
        lines.append(
            f"  {zh} {getattr(u, 'code', '') or ''}"
            f"（{getattr(u, 'name', '') or '未命名'}{extra_text}）"
        )
    if len(usages) > lim:
        lines.append(f"……另有 {len(usages) - lim} 处未展开")
    return "\n".join(lines)


def _walk_bom_items(
    items: List[Dict[str, Any]],
    level_cap: int,
    parent_key: str,
    depth: int = 1,
    visible: Optional[Set[int]] = None,
    hidden: Optional[List[int]] = None,
) -> List[Tuple[Dict[str, Any], str]]:
    """DFS 展开 BOM 树 → [(item, parent_key)]，深度 ≤ level_cap。

    ``visible`` 提供时：component_id 不可见的节点连同其子树整体剔除并
    计入 ``hidden``（无权节点只计数，与 document_chain X3=a 同口径）。
    """
    out: List[Tuple[Dict[str, Any], str]] = []
    for it in items or []:
        if depth > level_cap:
            continue
        if visible is not None and int(it.get("component_id") or 0) not in visible:
            if hidden is not None:
                hidden[0] += 1 + _count_subtree_nodes(it)
            continue
        out.append((it, parent_key))
        out.extend(
            _walk_bom_items(
                list(it.get("children") or []),
                level_cap,
                str(it.get("component_code") or it.get("component_id") or ""),
                depth + 1,
                visible=visible,
                hidden=hidden,
            )
        )
    return out


def _count_subtree_nodes(item: Dict[str, Any]) -> int:
    """item 的子孙节点总数（不含自身，供 hidden 计数）。"""
    children = list(item.get("children") or [])
    return len(children) + sum(_count_subtree_nodes(c) for c in children)


def _bom_item_text(it: Dict[str, Any]) -> str:
    text = (
        f"{it.get('component_code') or ''}"
        f"（{it.get('component_name') or '未命名'}）"
        f"用量 {_ct()._fmt_num(it.get('quantity'))}{it.get('unit') or ''}"
    )
    waste = it.get("waste_rate") or 0
    try:
        if float(waste):
            text += f"，损耗 {_ct()._fmt_num(waste)}%"
    except (TypeError, ValueError):
        pass
    if it.get("is_alternative"):
        text += "，替代料"
    if it.get("is_configurable"):
        text += "，配置位"
    return text


async def query_engineering_bom(
    material_id: Optional[int] = None,
    bom_id: Optional[int] = None,
    view: str = "tree",
    level: int = 5,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """工程 BOM 问答：tree 层级缩进 / flat 平铺 / substitutes 替代料组。

    ``material_id``（默认或最新版本）与 ``bom_id``（行 id → 定位物料+版本）
    二选一必填；``level`` 展开深度 1-5。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    resolved_view = str(view or "tree").strip()
    if resolved_view not in _BOM_VIEWS:
        return "view 仅支持 tree|flat|substitutes"
    try:
        level_cap = int(level)
    except (TypeError, ValueError):
        return "level 须为 1-5 的整数"
    if not 1 <= level_cap <= _BOM_LEVEL_MAX:
        return "level 须为 1-5 的整数"
    has_material = material_id is not None and str(material_id).strip() != ""
    has_bom = bom_id is not None and str(bom_id).strip() != ""
    if has_material == has_bom:
        return "material_id 与 bom_id 须且只须传一个"

    try:
        from apps.master_data.models.material import BOM, Material

        mid: Optional[int] = None
        version: Optional[str] = None
        if has_bom:
            try:
                bid = int(bom_id)
            except (TypeError, ValueError):
                return "bom_id 须为 BOM 行 ID 整数"
            if bid <= 0:
                return "bom_id 须为 BOM 行 ID 正整数"
            bom_row = await BOM.filter(
                tenant_id=ctx.tenant_id, id=bid, deleted_at__isnull=True
            ).first()
            if bom_row is None:
                return "BOM 不存在"
            mid = int(bom_row.material_id)
            version = getattr(bom_row, "version", None) or None
        else:
            try:
                mid = int(material_id)
            except (TypeError, ValueError):
                return "material_id 须为物料 ID 整数"
            if mid <= 0:
                return "material_id 须为物料 ID 正整数"

        material = await _material_row(ctx, mid)
        if material is None:
            return "物料不存在"
        if not await _material_visible(ctx, mid):
            return "当前用户数据范围内无该物料"

        from apps.master_data.services.material_service import MaterialService

        hierarchy = await MaterialService.generate_bom_hierarchy(
            ctx.tenant_id, mid, version=version
        )
        root_key = str(
            (hierarchy or {}).get("material_code")
            or getattr(material, "main_code", "")
            or getattr(material, "code", "")
            or ""
        )
        raw_items = list((hierarchy or {}).get("items") or [])
        probe = _walk_bom_items(raw_items, level_cap, root_key)
        component_ids = {
            int(it.get("component_id"))
            for it, _p in probe
            if it.get("component_id")
        }
        visible = await _st()._scoped_row_ids(
            Material, ctx, _SCOPE_MATERIAL, component_ids
        )
        hidden_counter = [0]
        visible_items = _walk_bom_items(
            raw_items,
            level_cap,
            root_key,
            visible=visible,
            hidden=hidden_counter,
        )
        hidden = hidden_counter[0]
    except Exception as exc:
        logger.warning(
            "AI tool query_engineering_bom 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询工程 BOM 失败，请稍后重试"

    mcode = (
        (hierarchy or {}).get("material_code")
        or getattr(material, "main_code", "")
        or getattr(material, "code", "")
        or ""
    )
    mname = (hierarchy or {}).get("material_name") or getattr(material, "name", "")
    ver = (hierarchy or {}).get("version") or version or "-"
    head = f"物料 {mcode}（{mname or '未命名'}）BOM 版本 {ver}"
    if not probe:
        return f"{head}：无 BOM 明细"
    if not visible_items:
        return f"{head}：明细均在当前用户数据范围外"

    if resolved_view == "substitutes":
        groups: Dict[Tuple[str, Any], List[Dict[str, Any]]] = {}
        for it, parent in visible_items:
            gid = it.get("alternative_group_id")
            if gid is None:
                continue
            groups.setdefault((parent, gid), []).append(it)
        if not groups:
            return f"{head}：无替代料组配置"
        lines = [f"{head}：{len(groups)} 个替代料组："]
        for (parent, gid), rows in groups.items():
            lines.append(f"  替代组 {gid}（父件 {parent} 下）：")
            for it in sorted(
                rows, key=lambda x: int(x.get("priority") or 0)
            ):
                lines.append(
                    f"    {_bom_item_text(it)}，优先级 {it.get('priority') or 0}"
                )
        return "\n".join(lines)

    total = len(visible_items)
    shown = visible_items[:_BOM_NODE_MAX]
    lines = [f"{head}（展开深度 ≤{level_cap}，共 {total} 节点）："]
    if resolved_view == "flat":
        for idx, (it, _p) in enumerate(shown, start=1):
            lines.append(
                f"  {idx}. L{int(it.get('level') or 0) + 1} {_bom_item_text(it)}"
            )
    else:
        for it, _p in shown:
            indent = "  " * (int(it.get("level") or 0) + 1)
            lines.append(f"{indent}{_bom_item_text(it)}")
    if total > _BOM_NODE_MAX:
        lines.append(
            f"……已截断，本层展开共 {total} 节点，仅显示前 {_BOM_NODE_MAX} 个"
        )
    if hidden:
        lines.append(f"……另有 {hidden} 个节点超出当前用户数据范围未显示")
    return "\n".join(lines)
