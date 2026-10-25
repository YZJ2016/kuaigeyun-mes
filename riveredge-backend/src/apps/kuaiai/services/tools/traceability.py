"""KU-AI 场景只读 Tool：批次/序列追溯（spec 207，X2=b）。

Tool 名：``trace_lineage``（按序列号/批号/工单号做正向/反向追溯）。

- 底层 ``TraceabilityService.build_profile(tenant_id, code, direction)``：
  service 不接收 ``current_user``——追溯路由 ``GET /traceability/profile``
  同样只按租户 + 权限码门控、无行级数据范围过滤，Tool 与接口同口径；
  业务读权限由 manifest ``ai_tools[*].permissions_any``
  （``kuaizhizao:quality-management-traceability:read`` |
  ``kuaizhizao:material-lifecycle-trace:read`` 任一命中，与路由
  ``require_all=False`` 同语义）经 tool_bridge RBAC 复核。
- 输出：锚点行 + 节点按「距锚点层级」（沿 edges BFS）分组列出，随行
  类型/物料/数量；节点超上限只列前若干层并注明已截断、完整追溯请
  到追溯页。
- 客户名称可出现（召回评估所需）；联系人/电话/地址不出现——输出仅
  取 profile 的编码/类型/物料/数量/状态字段，不取通讯信息。
- 召回范围由用户判断，本 Tool 只罗列链路，不做召回/冻结建议。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext
from infra.exceptions.exceptions import NotFoundError

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# direction 闭集：schemas.traceability_schemas.TraceDirection
_DIRECTIONS = frozenset({"forward", "backward", "both"})
_DIRECTION_ZH = {"forward": "正向", "backward": "反向", "both": "双向"}

_ANCHOR_TYPE_ZH = {
    "serial": "序列号",
    "batch": "批号",
    "work_order": "工单",
}

# 节点 type 中文化（graph_assembler 归并后的取值集合）
_NODE_TYPE_ZH = {
    "serial": "序列号",
    "batch": "批次",
    "work_order": "工单",
    "inbound": "入库",
    "outbound": "出库",
    "incoming_inspection": "来料检验",
    "process_inspection": "过程检验",
    "finished_goods_inspection": "成品检验",
    "oqc_inspection": "出货检验",
    "defect_record": "不合格品",
    "material_binding": "物料绑定",
}

# 层级展开上限：距锚点边数 ≤ _MAX_DEPTH 且节点行数 ≤ _MAX_NODES
_MAX_DEPTH = 5
_MAX_NODES = 20


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _node_depths(nodes: List[Any], edges: List[Any], anchor_id: str) -> Dict[str, int]:
    """沿 edges（无向看待）自锚点 BFS，得各节点「距锚点层级」。"""
    adj: Dict[str, List[str]] = {}
    for e in edges:
        src, tgt = getattr(e, "source", None), getattr(e, "target", None)
        if not src or not tgt:
            continue
        adj.setdefault(src, []).append(tgt)
        adj.setdefault(tgt, []).append(src)
    node_ids = {n.id for n in nodes}
    depth: Dict[str, int] = {}
    frontier = [anchor_id] if anchor_id in node_ids else []
    d = 0
    while frontier:
        nxt: List[str] = []
        for nid in frontier:
            if nid in depth:
                continue
            depth[nid] = d
            nxt.extend(adj.get(nid, []))
        frontier = nxt
        d += 1
    return depth


def _event_qty_map(events: List[Any]) -> Dict[tuple, Any]:
    """(document_type, document_code) → quantity，供节点行附数量。"""
    out: Dict[tuple, Any] = {}
    for ev in events or []:
        qty = getattr(ev, "quantity", None)
        if qty is None:
            continue
        key = (getattr(ev, "document_type", None), getattr(ev, "document_code", None))
        out.setdefault(key, qty)
    return out


def _fmt_node(node: Any, depth: Optional[int], qty_map: Dict[tuple, Any]) -> str:
    data = node.data or {}
    layer = f"第{depth}层" if depth is not None else "未连通"
    label = str(node.label or node.id or "?")
    ntype = _NODE_TYPE_ZH.get(str(node.type or ""), str(node.type or "未知"))
    seg = f"- [{layer}] {label}（{ntype}）"
    mat_code = data.get("material_code")
    mat_name = data.get("material_name")
    if mat_code or mat_name:
        seg += f"，物料 {mat_code or ''}（{mat_name or '未命名'}）"
    qty = qty_map.get((data.get("document_type"), data.get("document_code")))
    if qty is not None:
        seg += f"，数量 {_ct()._fmt_num(qty)}"
    status = data.get("status") or data.get("quality_status")
    if status:
        seg += f"，状态 {status}"
    return seg


async def trace_lineage(
    code: str,
    direction: str = "both",
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """批次/序列/工单正反向追溯链路摘要（与追溯 profile 接口同口径）。

    数据范围：service 无行级过滤（路由同样无），仅租户隔离 +
    tool_bridge 双码任一 RBAC。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    code_text = str(code or "").strip()
    if not code_text:
        return "code 为必填参数（序列号/批号/工单号）"
    resolved_direction = str(direction or "both").strip()
    if resolved_direction not in _DIRECTIONS:
        return "direction 仅支持 forward|backward|both"
    try:
        from apps.kuaizhizao.services.traceability import TraceabilityService

        profile = await TraceabilityService().build_profile(
            ctx.tenant_id, code_text, resolved_direction
        )
    except NotFoundError:
        return f"未找到追溯记录：{code_text}"
    except Exception as exc:
        logger.warning(
            "AI tool trace_lineage 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询追溯链路失败，请稍后重试"

    anchor = profile.anchor
    summary = profile.summary
    nodes = list(profile.nodes or [])
    edges = list(profile.edges or [])

    id_type = getattr(anchor.identifier_type, "value", anchor.identifier_type)
    atype = _ANCHOR_TYPE_ZH.get(str(id_type), str(id_type))
    head = (
        f"追溯码 {anchor.code}（{atype}，{_DIRECTION_ZH[resolved_direction]}）："
    )
    if anchor.material_code or anchor.material_name:
        head += (
            f"物料 {anchor.material_code or ''}"
            f"（{anchor.material_name or '未命名'}），"
        )
    head += (
        f"共 {summary.node_count} 个节点 / {summary.event_count} 条事件 /"
        f" {summary.edge_count} 条关联："
    )
    lines = [head]

    if not profile.events:
        lines.append("该标识暂无追溯事件记录")
        return "\n".join(lines)

    anchor_nid = f"{id_type}:{anchor.code}"
    depths = _node_depths(nodes, edges, anchor_nid)
    qty_map = _event_qty_map(list(profile.events or []))
    ordered = sorted(
        nodes,
        key=lambda n: (
            depths.get(n.id) if n.id in depths else len(nodes),
            str(n.id),
        ),
    )

    shown = 0
    truncated = False
    for node in ordered:
        depth = depths.get(node.id)
        if shown >= _MAX_NODES or (depth is not None and depth > _MAX_DEPTH):
            truncated = True
            break
        lines.append(_fmt_node(node, depth, qty_map))
        shown += 1
    if truncated or shown < len(ordered):
        lines.append(
            f"已截断：全图 {len(nodes)} 个节点，以上仅前 {shown} 个"
            f"（按层级展开至第 {_MAX_DEPTH} 层内），完整追溯请到追溯页"
        )
    return "\n".join(lines)
