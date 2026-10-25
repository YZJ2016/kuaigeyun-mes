"""KU-AI 场景只读 Tool：ECN/ECR 变更影响分析（spec 212，S23）。

Tool 名：``query_ecn`` / ``analyze_ecn_impact``；权限码 ``kuaiplm:ecn:read``。

T1 事实（写 spec §4）：
- ``EngineeringChangeService.list(tenant_id, *, keyword, status, change_kind,
  project_id, skip, limit)`` → ``EngineeringChangeListResponse(items, total)``；
  keyword 仅 ``title__icontains``，无 ``date_start/date_end``/``current_user``
  形参；``EngineeringChangeListItem`` 不含物料行数与生效时间。故 ``query_ecn``
  按 service 同口径（tenant+软删+status+keyword）在适配层直查模型：
  keyword 扩为 ``ecn_code|title`` OR（按 ECN 号检索是首要用法）、
  ``date_start/date_end`` 对 ``created_at`` 含界过滤；涉及物料数经
  ``EngineeringChangeMaterialLine`` 与 service 同口径计数。
- kuaiplm 无 ECN 影响分析专用接口：``analyze_ecn_impact`` 由
  ``service.get`` 取 ECN+物料行，影响面在适配层拼（工单/批次 ORM 只读、
  ``list_bom_where_used``、物料绑定路线解析复用 process_routes 助手）。
- 应用可用性：``ApplicationService.get_application_by_code(tenant_id,
  "kuaiplm")`` 复核 ``is_installed and is_active``；manifest ``ai_tools``
  不支持 ``requires_app``（``register_from_manifest`` 只消费
  name/handler/permission/permissions_any/description/parameters），
  未启用时 Tool 返回固定文案而非错误。
- 影响面各分区按读权限码门控（与 spec 208 document_chain X3=a 同口径：
  无权分区只计数不展开），行级数据范围经 ``scene_tools._scoped_row_ids``：
  在制工单 ``kuaizhizao:work-order``、库存批次 ``kuaizhizao:inventory``、
  BOM 父件/物料 ``master-data:material``、工艺路线 ``master-data:process:route``，
  ECN 源单 ``kuaiplm:ecn``（kuaiplm manifest 无 data_scope_key，无策略=全部，
  未授权角色由 DataScopeService 失败关闭）。
- 不输出变更前后明细全文（before_desc/after_desc）、行级单价/成本金额。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from loguru import logger
from tortoise.expressions import Q

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_PLM_DISABLED = "PLM 应用未启用，无法执行该查询"

_KUAIPLM_APP = "kuaiplm"

_SCOPE_ECN = "kuaiplm:ecn"
_SCOPE_MATERIAL = "master-data:material"
_SCOPE_WORK_ORDER = "kuaizhizao:work-order"
_SCOPE_INVENTORY = "kuaizhizao:inventory"
_SCOPE_ROUTE = "master-data:process:route"

_PERM_WORK_ORDER = "kuaizhizao:work-order:read"
_PERM_INVENTORY = "kuaizhizao:inventory:read"
_PERM_ENGINEERING_BOM = "master-data:process:engineering-bom:read"
_PERM_ROUTE = "master-data:process:route:read"

# EngineeringChangeService.ALLOWED_STATUS 同源闭集
_ECN_STATUSES = frozenset(
    {"draft", "pending", "approved", "erp_pending", "erp_failed", "closed"}
)

# 在制工单口径：已下达未完工（released/in_progress/paused）
_WIP_WO_STATUSES = frozenset({"released", "in_progress", "paused"})

_DISPOSITION_ZH = {
    "scrap": "报废",
    "use_up": "耗尽使用",
    "rework": "返工",
    "return": "退回",
    "other": "其他",
}

# 影响分析参与分区查询的物料行上限（超限物料仍计入「涉及物料」总数）
_IMPACT_MATERIAL_MAX = 20
# 各分区返回前 N 条
_IMPACT_ITEM_MAX = 10
# query_ecn 行级范围收敛前的候选行上限
_ECN_CANDIDATE_MAX = 100


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


async def _plm_enabled(tenant_id: int) -> bool:
    """kuaiplm 是否已安装且启用（本租户）。"""
    from core.services.application.application_service import ApplicationService

    row = await ApplicationService.get_application_by_code(tenant_id, _KUAIPLM_APP)
    return bool(row and row.get("is_installed") and row.get("is_active"))


def _fmt_dt(value: Any) -> str:
    """datetime/date 展示：datetime 经 API 同口径站点时区文本，date 取 ISO
    日（缺省 ''，交由调用方补「未定/未知/未生效」）。"""
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


async def _perm_view(ctx: AiRuntimeContext):
    """(admin_bypass, 已授权限码集合)——复用 document_chain 同口径。"""
    from apps.kuaiai.services.tools import document_chain

    return await document_chain._perm_view(ctx)


def _code_allowed(permission: Optional[str], admin: bool, codes) -> bool:
    from apps.kuaiai.services.tools import document_chain

    return document_chain._code_allowed(permission, admin, codes)


def _disposition_zh(value: Any) -> str:
    key = str(value or "").strip().lower()
    return _DISPOSITION_ZH.get(key, key or "未指定")


async def query_ecn(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """工程变更单（ECN）有界摘要：编号/标题/状态/涉及物料数/创建与生效时间。

    数据范围：行级套 ``kuaiplm:ecn`` 数据范围；keyword 匹配单号或标题。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    status_norm = (str(status).strip().lower() or None) if status else None
    if status_norm is not None and status_norm not in _ECN_STATUSES:
        return "status 仅支持 draft/pending/approved/erp_pending/erp_failed/closed"
    start_d = _st()._parse_date(date_start) if date_start else None
    if date_start and start_d is None:
        return "date_start 须为 YYYY-MM-DD 格式的日期"
    end_d = _st()._parse_date(date_end) if date_end else None
    if date_end and end_d is None:
        return "date_end 须为 YYYY-MM-DD 格式的日期"

    try:
        if not await _plm_enabled(ctx.tenant_id):
            return _PLM_DISABLED

        from apps.kuaiplm.models.engineering_change import (
            EngineeringChange,
            EngineeringChangeMaterialLine,
        )

        lim = _ct()._clamp_limit(limit)
        kw = (str(keyword).strip() or None) if keyword else None
        qs = EngineeringChange.filter(
            tenant_id=ctx.tenant_id, deleted_at__isnull=True
        )
        if status_norm:
            qs = qs.filter(status=status_norm)
        if kw:
            qs = qs.filter(Q(ecn_code__icontains=kw) | Q(title__icontains=kw))
        if start_d:
            qs = qs.filter(
                created_at__gte=datetime.combine(start_d, datetime.min.time())
            )
        if end_d:
            qs = qs.filter(
                created_at__lte=datetime.combine(end_d, datetime.max.time())
            )
        # 候选行有界拉取后行级范围收敛（service total 为未收敛全租户计数，不回显）
        rows = await qs.order_by("-updated_at", "-id").limit(
            _ECN_CANDIDATE_MAX
        ).all()
        visible = await _st()._scoped_row_ids(
            EngineeringChange,
            ctx,
            _SCOPE_ECN,
            {int(r.id) for r in rows},
        )
        rows = [r for r in rows if int(r.id) in visible]

        mat_count: Dict[int, int] = {}
        if rows:
            ecn_ids = [int(r.id) for r in rows]
            mat_eids = await EngineeringChangeMaterialLine.filter(
                tenant_id=ctx.tenant_id,
                ecn_id__in=ecn_ids,
                deleted_at__isnull=True,
            ).values_list("ecn_id", flat=True)
            for eid in mat_eids:
                eid = int(eid)
                mat_count[eid] = mat_count.get(eid, 0) + 1
    except Exception as exc:
        logger.warning(
            "AI tool query_ecn 失败 error_type={}", type(exc).__name__
        )
        return "查询工程变更单失败，请稍后重试"

    if not rows:
        return "当前用户数据范围内未查询到符合条件的工程变更单"
    top = rows[:lim]
    lines = [
        f"共 {len(rows)} 张工程变更单（当前用户数据范围内，"
        f"前 {_ECN_CANDIDATE_MAX} 条候选内计），返回前 {len(top)} 张："
    ]
    for r in top:
        effective = _fmt_dt(
            getattr(r, "closed_at", None) or getattr(r, "approved_at", None)
        )
        lines.append(
            f"ECN {getattr(r, 'ecn_code', '') or ''}："
            f"{getattr(r, 'title', '') or '未命名'}，"
            f"状态 {getattr(r, 'status', '') or '未知'}，"
            f"涉及物料 {mat_count.get(int(r.id), 0)} 项，"
            f"创建 {_fmt_dt(getattr(r, 'created_at', None)) or '未知'}，"
            f"生效 {effective or '未生效'}"
            f"（id={getattr(r, 'id', '')}）"
        )
    return "\n".join(lines)


async def _impact_wip_orders(
    ctx: AiRuntimeContext, material_ids: List[int], allowed: bool
) -> List[str]:
    """受影响在制工单分区（计数 + 前 N 条；无权只计数）。"""
    from apps.kuaizhizao.models.work_order import WorkOrder

    qs = WorkOrder.filter(
        tenant_id=ctx.tenant_id,
        deleted_at__isnull=True,
        product_id__in=list(material_ids),
        status__in=list(_WIP_WO_STATUSES),
    )
    total = await qs.count()
    if total == 0:
        return ["受影响在制工单：无"]
    if not allowed:
        return [
            f"受影响在制工单：共 {total} 张"
            "（当前用户无工单读权限，不展开明细）"
        ]
    # 候选全量行级收敛后再截断展示（与 BOM 引用/工艺路线分区同口径）
    rows = await qs.order_by("-updated_at", "-id").all()
    visible = await _st()._scoped_row_ids(
        WorkOrder, ctx, _SCOPE_WORK_ORDER, {int(w.id) for w in rows}
    )
    rows = [w for w in rows if int(w.id) in visible]
    top = rows[:_IMPACT_ITEM_MAX]
    lines = [
        f"受影响在制工单：共 {total} 张（数据范围内 {len(rows)} 张），"
        f"返回前 {len(top)} 张："
    ]
    for w in top:
        lines.append(
            f"  工单 {getattr(w, 'code', '') or ''}"
            f"（{getattr(w, 'name', None) or getattr(w, 'product_name', '') or '未命名'}）："
            f"产品 {getattr(w, 'product_code', '') or ''}，"
            f"状态 {getattr(w, 'status', '') or '未知'}，"
            f"计划 {_ct()._fmt_num(getattr(w, 'quantity', None))}，"
            f"计划完工 {_fmt_dt(getattr(w, 'planned_end_date', None)) or '未排定'}"
        )
    return lines


async def _impact_batches(
    ctx: AiRuntimeContext,
    material_ids: List[int],
    material_code_by_id: Dict[int, str],
    allowed: bool,
) -> List[str]:
    """受影响库存批次分区（在库批次，计数 + 前 N 条）。"""
    from apps.master_data.models.material_batch import MaterialBatch

    qs = MaterialBatch.filter(
        tenant_id=ctx.tenant_id,
        deleted_at__isnull=True,
        material_id__in=list(material_ids),
        status="in_stock",
        quantity__gt=0,
    )
    total = await qs.count()
    if total == 0:
        return ["受影响库存批次：无"]
    if not allowed:
        return [
            f"受影响库存批次：共 {total} 批"
            "（当前用户无库存读权限，不展开明细）"
        ]
    # 候选全量行级收敛后再截断展示（与 BOM 引用/工艺路线分区同口径）
    rows = await qs.order_by("material_id", "batch_no").all()
    visible = await _st()._scoped_row_ids(
        MaterialBatch, ctx, _SCOPE_INVENTORY, {int(b.id) for b in rows}
    )
    rows = [b for b in rows if int(b.id) in visible]
    top = rows[:_IMPACT_ITEM_MAX]
    lines = [
        f"受影响库存批次：共 {total} 批（数据范围内 {len(rows)} 批），"
        f"返回前 {len(top)} 批："
    ]
    for b in top:
        mcode = material_code_by_id.get(int(b.material_id), str(b.material_id))
        lines.append(
            f"  物料 {mcode} 批号 {getattr(b, 'batch_no', '') or ''}"
            f" @ {getattr(b, 'warehouse_name', None) or '未归属仓'}："
            f"结存 {_ct()._fmt_num(getattr(b, 'quantity', None))}"
        )
    return lines


async def _impact_bom_refs(
    ctx: AiRuntimeContext,
    material_ids: List[int],
    material_code_by_id: Dict[int, str],
    allowed: bool,
) -> List[str]:
    """受影响 BOM 引用分区（物料作为子件被哪些父件/BOM 引用）。"""
    from apps.master_data.models.material import Material
    from apps.master_data.services.material_service import MaterialService

    items: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for mid in material_ids:
        result = await MaterialService.list_bom_where_used(
            ctx.tenant_id, mid, recursive=False
        )
        for row in (result or {}).get("items") or []:
            bid = int(row.get("bom_id") or 0)
            if bid and bid in seen:
                continue
            if bid:
                seen.add(bid)
            row = dict(row)
            row["_component_id"] = mid
            items.append(row)
    total = len(items)
    if total == 0:
        return ["受影响 BOM 引用：无"]
    if not allowed:
        return [
            f"受影响 BOM 引用：共 {total} 处"
            "（当前用户无工程 BOM 读权限，不展开明细）"
        ]
    parent_ids = {int(r["material_id"]) for r in items if r.get("material_id")}
    visible = await _st()._scoped_row_ids(
        Material, ctx, _SCOPE_MATERIAL, parent_ids
    )
    items = [r for r in items if int(r.get("material_id") or 0) in visible]
    top = items[:_IMPACT_ITEM_MAX]
    lines = [
        f"受影响 BOM 引用：共 {total} 处（数据范围内 {len(items)} 处），"
        f"返回前 {len(top)} 处："
    ]
    for r in top:
        child = material_code_by_id.get(
            int(r.get("_component_id") or 0), str(r.get("_component_id") or "")
        )
        lines.append(
            f"  {child} → 父件 {r.get('material_code') or ''}"
            f"（{r.get('material_name') or '未命名'}），"
            f"BOM {r.get('bom_code') or '-'} 版本 {r.get('version') or '-'}，"
            f"用量 {_ct()._fmt_num(r.get('quantity'))}{r.get('unit') or ''}，"
            f"审核 {r.get('approval_status') or '未知'}"
        )
    return lines


async def _impact_route_refs(
    ctx: AiRuntimeContext,
    material_ids: List[int],
    material_code_by_id: Dict[int, str],
    allowed: bool,
) -> List[str]:
    """受影响工艺路线引用分区（物料绑定路线：物料级→分组兜底）。"""
    from apps.kuaiai.services.tools import process_routes as pr
    from apps.master_data.models.process import ProcessRoute

    route_ids_by_material: Dict[int, int] = {}
    for mid in material_ids:
        rid = await pr._resolve_material_route_id(ctx, mid)
        if rid is not None:
            route_ids_by_material[mid] = int(rid)
    total = len(route_ids_by_material)
    if total == 0:
        return ["受影响工艺路线：无"]
    if not allowed:
        return [
            f"受影响工艺路线：共 {total} 条绑定"
            "（当前用户无工艺路线读权限，不展开明细）"
        ]
    route_ids = set(route_ids_by_material.values())
    routes = await ProcessRoute.filter(
        tenant_id=ctx.tenant_id,
        id__in=list(route_ids),
        deleted_at__isnull=True,
    ).all()
    visible = await _st()._scoped_row_ids(
        ProcessRoute, ctx, _SCOPE_ROUTE, {int(r.id) for r in routes}
    )
    route_by_id = {int(r.id): r for r in routes if int(r.id) in visible}
    shown = [
        (mid, rid)
        for mid, rid in route_ids_by_material.items()
        if rid in route_by_id
    ]
    lines = [
        f"受影响工艺路线：共 {total} 条绑定"
        f"（数据范围内 {len(shown)} 条），返回前 {min(len(shown), _IMPACT_ITEM_MAX)} 条："
    ]
    for mid, rid in shown[:_IMPACT_ITEM_MAX]:
        route = route_by_id[rid]
        mcode = material_code_by_id.get(mid, str(mid))
        lines.append(
            f"  {mcode} → 路线 {getattr(route, 'code', '') or ''}"
            f"（{getattr(route, 'name', '') or '未命名'}，"
            f"版本 {getattr(route, 'version', None) or '1.0'}）"
        )
    return lines


async def analyze_ecn_impact(
    ecn_id: int,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """ECN 影响面分析：变更物料行 + 在制工单/库存批次/BOM/工艺引用清单。

    各分区独立降级（单分区查询失败只影响该分区文案）；无关联分区如实
    输出「无」。不输出变更前后明细全文。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        ecn_pk = int(ecn_id)
    except (TypeError, ValueError):
        return "ecn_id 须为工程变更单 ID 整数"
    if ecn_pk <= 0:
        return "ecn_id 须为工程变更单 ID 正整数"
    try:
        if not await _plm_enabled(ctx.tenant_id):
            return _PLM_DISABLED

        from apps.kuaiplm.models.engineering_change import EngineeringChange
        from apps.kuaiplm.services.engineering_change_service import (
            EngineeringChangeService,
        )
        from infra.exceptions.exceptions import NotFoundError

        try:
            resp = await EngineeringChangeService().get(ctx.tenant_id, ecn_pk)
        except NotFoundError:
            return "工程变更单不存在"
        # 源单 by-ID 行级数据范围复核（spec §1）
        visible = await _st()._scoped_row_ids(
            EngineeringChange, ctx, _SCOPE_ECN, {ecn_pk}
        )
        if ecn_pk not in visible:
            return "当前用户数据范围内无该工程变更单"
        admin, codes = await _perm_view(ctx)
    except Exception as exc:
        logger.warning(
            "AI tool analyze_ecn_impact 失败 error_type={}",
            type(exc).__name__,
        )
        return "分析工程变更影响失败，请稍后重试"

    materials = list(getattr(resp, "materials", None) or [])
    material_ids = [
        int(m.material_id) for m in materials if getattr(m, "material_id", None)
    ]
    material_code_by_id: Dict[int, str] = {
        int(m.material_id): str(getattr(m, "material_code", "") or m.material_id)
        for m in materials
        if getattr(m, "material_id", None)
    }
    head = (
        f"ECN {getattr(resp, 'ecn_code', '') or ''}："
        f"{getattr(resp, 'title', '') or '未命名'}，"
        f"状态 {getattr(resp, 'status', '') or '未知'}，"
        f"类型 {getattr(resp, 'change_kind', '') or '未知'}，"
        f"涉及物料 {len(materials)} 项"
    )
    out: List[str] = [head]
    if materials:
        mat_lines = ["变更物料行："]
        for m in materials[:_IMPACT_ITEM_MAX]:
            mat_lines.append(
                f"  {getattr(m, 'material_code', '') or ''}"
                f"（{getattr(m, 'material_name', '') or '未命名'}），"
                f"处置 {_disposition_zh(getattr(m, 'disposition', None))}"
                f"（行id={getattr(m, 'id', '')}）"
            )
        if len(materials) > _IMPACT_ITEM_MAX:
            mat_lines.append(
                f"  ……另有 {len(materials) - _IMPACT_ITEM_MAX} 行未展开"
            )
        out.extend(mat_lines)
    else:
        out.append("变更物料行：无")

    if not material_ids:
        out.append("该 ECN 无物料行，无下游影响面可查")
        return "\n".join(out)

    section_material_ids = material_ids[:_IMPACT_MATERIAL_MAX]
    sections = (
        (
            "在制工单",
            _PERM_WORK_ORDER,
            lambda: _impact_wip_orders(
                ctx,
                section_material_ids,
                _code_allowed(_PERM_WORK_ORDER, admin, codes),
            ),
        ),
        (
            "库存批次",
            _PERM_INVENTORY,
            lambda: _impact_batches(
                ctx,
                section_material_ids,
                material_code_by_id,
                _code_allowed(_PERM_INVENTORY, admin, codes),
            ),
        ),
        (
            "BOM 引用",
            _PERM_ENGINEERING_BOM,
            lambda: _impact_bom_refs(
                ctx,
                section_material_ids,
                material_code_by_id,
                _code_allowed(_PERM_ENGINEERING_BOM, admin, codes),
            ),
        ),
        (
            "工艺路线",
            _PERM_ROUTE,
            lambda: _impact_route_refs(
                ctx,
                section_material_ids,
                material_code_by_id,
                _code_allowed(_PERM_ROUTE, admin, codes),
            ),
        ),
    )
    for title, _perm, builder in sections:
        try:
            out.extend(await builder())
        except Exception as exc:
            # 单分区失败降级该分区文案（可选应用/表缺失不影响其余分区）
            logger.warning(
                "AI tool analyze_ecn_impact 分区失败 section={} error_type={}",
                title,
                type(exc).__name__,
            )
            out.append(f"受影响{title}：查询失败")
    if len(material_ids) > _IMPACT_MATERIAL_MAX:
        out.append(
            f"（影响面分区按前 {_IMPACT_MATERIAL_MAX} 项变更物料统计，"
            f"共 {len(material_ids)} 项）"
        )
    return "\n".join(out)
