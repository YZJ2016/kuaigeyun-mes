"""KU-AI 场景只读 Tool：检验单查询与供应商绩效（spec 209，S15；S12 明细）。

Tool 名：``query_incoming_inspections`` / ``query_process_inspections`` /
``query_finished_inspections`` / ``query_oqc_inspections`` /
``query_supplier_evaluations``。

T1 事实（各 service 过滤键 / 数据范围资源键）：

- ``IncomingInspectionService.list_incoming_inspections(tenant_id, skip,
  limit, **filters)``（quality_service.py:1191）支持键：status /
  quality_status / supplier_id / material_id / purchase_receipt_id /
  customer_material_registration_id / scoped_purchase_receipt_ids /
  keyword（inspection_code·material_code·material_name·supplier_name·
  purchase_receipt_code·purchase_order_code·customer_material_registration_code·
  outsource_material_receipt_code）/ inspection_start_date /
  inspection_end_date / created_start_date / created_end_date / order_by。
  无 material_name 之外的物料名精确过滤，无 inspection_result 过滤键。
- ``ProcessInspectionService.list_process_inspections``（:4350）支持键：
  status / quality_status / work_order_id / operation_id / id /
  scoped_work_order_ids / keyword / 日期同上。入口调用
  ``_heal_duplicate_pending_process_inspections``：同工单同工序多张待检验单
  会被合并删除（service 既有自愈行为，与列表页同口径，无参数可绕过）。
  无 material_id / supplier_id 过滤键。
- ``FinishedGoodsInspectionService.list_finished_goods_inspections``
  （:6041）支持键：status / quality_status / work_order_id / source_type /
  scoped_work_order_ids / keyword / 日期同上。无 material_id。
- ``OQCInspectionService.list``（quality_improvement_service.py:1056）
  显式参数：status / shipment_notice_id / sales_delivery_id / keyword /
  order_by / inspection_start_date / inspection_end_date /
  created_start_date / created_end_date。无 quality_status / material_id
  过滤。其 keyword_fields 含模型不存在字段 ``sales_delivery_code``
  （OQCInspection 无此列，迁移 292 建表亦无）→ 传 keyword 必抛
  FieldError，Tool 不暴露 keyword 参数（spec §1「只暴露 service 已支持
  的键」，该键实际不可用）。
- ``SupplierEvaluationService.list(tenant_id, *, skip, limit, keyword,
  status, period_type, period_year, supplier_id, order_by)``
  （supplier_evaluation_service.py:699）返回
  ``SupplierEvaluationListResponse``（.data ListItem / .total）。
- 行级范围：五个权限资源（quality-management-{incoming,process,
  finished-goods,oqc}-inspection、supplier-eval）在 kuaizhizao manifest
  ``reference_resources`` 的 ``data_scope_key`` 均为 null，且
  ``data_scope_setup.py`` 未注册画像。适配层统一用
  ``_scoped_row_ids(model, ctx, <各 Tool 权限资源键>, ids)`` 收敛：
  权限资源键与 tool_bridge RBAC 权限码同根（一 Tool 一键，SC-D7）；
  无角色授予该资源 → DataScopeService 内部失败关闭（id=-1），
  无显式策略 → 平台「无策略=全部」语义放行；若后续为这些资源注册画像
  并配置显式策略，本层随策略收敛。不照搬 analyze_quality 的
  ``kuaizhizao:quality-analysis`` 资源键（spec §1）。
- 检验结论字段口径：``quality_status`` ∈ {合格, 不合格, 待判定}；
  单据状态 ``status`` ∈ {待检验, 已检验, 待审核, 已审核, 已驳回}
  （document_action_policy/quality_inspection_record.py + conduct 写入值）。
  无 ``result`` 过滤键，spec 通用参数 result 落到 quality_status。
- masking：不落检验员/审核人联系方式、供应商联系人与电话、单价、金额等
  商务敏感字段（spec 195 同款约定；评价行亦不含价格字段）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, List, Optional, Set

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 各 Tool 行级范围资源键 = 各自 manifest 权限码资源段（SC-D7 一 Tool 一键；
# data_scope_key 均 null → 无显式策略=全部、无角色授予=失败关闭）
_SCOPE_INCOMING = "kuaizhizao:quality-management-incoming-inspection"
_SCOPE_PROCESS = "kuaizhizao:quality-management-process-inspection"
_SCOPE_FINISHED = "kuaizhizao:quality-management-finished-goods-inspection"
_SCOPE_OQC = "kuaizhizao:quality-management-oqc-inspection"
_SCOPE_SUPPLIER_EVAL = "kuaizhizao:supplier-eval"

# 闭集参数（T1 从 conduct/policy 写入值与 supplier_eval 常量核实）
_INSPECTION_STATUSES = frozenset({"待检验", "已检验", "待审核", "已审核", "已驳回"})
_QUALITY_STATUSES = frozenset({"合格", "不合格", "待判定"})
_EVAL_STATUSES = frozenset(
    {"draft", "pending", "approved", "rejected", "revoked"}
)
_EVAL_PERIOD_TYPES = frozenset({"annual", "quarterly"})
_EVAL_PERIOD_ZH = {"annual": "年度", "quarterly": "季度"}

# 过采样上限：service 先分页、适配层再按数据范围收敛，多取减少
# 「范围内行被顶掉」；最终行数仍 clamp 到 limit≤20
_OVERSAMPLE_LIMIT = 100


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    """scene_tools 私有助手延迟借用（_parse_date / _scoped_row_ids）。"""
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _fetch_limit(limit: Any) -> int:
    """用户 limit（≤20）放大到过采样上限内，供范围过滤后仍够页。"""
    return min(max(_ct()._clamp_limit(limit) * 5, 50), _OVERSAMPLE_LIMIT)


def _val(row: Any, key: str, default: Any = "") -> Any:
    """行字段统一读取：dict（IQC/IPQC/FQC payload）或 pydantic/对象（OQC、评价）。"""
    if isinstance(row, dict):
        v = row.get(key, default)
    else:
        v = getattr(row, key, default)
    return default if v is None else v


def _norm_opt(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip() or None


def _positive_id(value: Any, name: str) -> tuple:
    """→ (err, int_id)：可选正整数 id 校验（与 complaint_8d 同款）。"""
    if value is None or str(value).strip() == "":
        return None, None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return f"{name} 须为正整数", None
    if n <= 0:
        return f"{name} 须为正整数", None
    return None, n


def _validate_status(status: Optional[str]) -> tuple:
    """→ (err, norm)：检验单 status 闭集校验。"""
    s = _norm_opt(status)
    if s is not None and s not in _INSPECTION_STATUSES:
        return "status 仅支持 待检验/已检验/待审核/已审核/已驳回", None
    return None, s


def _validate_quality_status(quality_status: Optional[str]) -> tuple:
    qs = _norm_opt(quality_status)
    if qs is not None and qs not in _QUALITY_STATUSES:
        return "quality_status 仅支持 合格/不合格/待判定", None
    return None, qs


def _validate_dates(date_start: Any, date_end: Any) -> tuple:
    """→ (err, start_d, end_d)：YYYY-MM-DD 校验后转 date。"""
    start_d = _st()._parse_date(date_start) if date_start else None
    if date_start and start_d is None:
        return "date_start 须为 YYYY-MM-DD 格式的日期", None, None
    end_d = _st()._parse_date(date_end) if date_end else None
    if date_end and end_d is None:
        return "date_end 须为 YYYY-MM-DD 格式的日期", None, None
    return None, start_d, end_d


def _fmt_dt(value: Any) -> str:
    """datetime/date 展示：datetime 经 API 同口径站点时区文本，date 取 ISO
    日（缺省 ''，交由调用方补「未定」）。inspection_time 为 DatetimeField。"""
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


def _fmt_inspection_row(row: Any, party: str) -> str:
    """四个检验 Tool 共用的行摘要（字段口径一致）。"""
    return (
        f"检验单 {_val(row, 'inspection_code')}："
        f"物料 {_val(row, 'material_code')}"
        f"（{_val(row, 'material_name') or '未命名'}），"
        f"{party}，"
        f"检验 {_ct()._fmt_num(_val(row, 'inspection_quantity', None))}，"
        f"合格 {_ct()._fmt_num(_val(row, 'qualified_quantity', None))}，"
        f"不合格 {_ct()._fmt_num(_val(row, 'unqualified_quantity', None))}，"
        f"结论 {_val(row, 'quality_status') or '未知'}，"
        f"状态 {_val(row, 'status') or '未知'}，"
        f"检验时间 {_fmt_dt(_val(row, 'inspection_time', None)) or '未定'}"
        f"（id={_val(row, 'id')}）"
    )


def _party_incoming(row: Any) -> str:
    supplier = _val(row, "supplier_name")
    if supplier:
        return f"供应商 {supplier}"
    customer = _val(row, "customer_name")
    if customer:
        return f"客户 {customer}"
    return "供应商 未知"


def _party_process(row: Any) -> str:
    op = _val(row, "operation_name")
    return (
        f"工单 {_val(row, 'work_order_code') or '未知'}"
        + (f"，工序 {op}" if op else "")
    )


def _party_finished(row: Any) -> str:
    return f"工单 {_val(row, 'work_order_code') or '未知'}"


def _party_oqc(row: Any) -> str:
    decision = _val(row, "release_decision")
    return (
        f"客户 {_val(row, 'customer_name') or '未知'}，"
        f"发货通知 {_val(row, 'shipment_notice_code') or '无'}"
        + (f"，放行 {decision}" if decision else "")
    )


async def _finish_inspection_list(
    ctx: AiRuntimeContext,
    *,
    model: Any,
    resource: str,
    rows: List[Any],
    label: str,
    limit: int,
    party_of: Callable[[Any], str],
) -> str:
    """范围收敛 → 截断 → 有界摘要（四检验 Tool 共用尾部口径）。"""
    if not rows:
        return f"未查询到符合条件的{label}"
    ids: Set[int] = {
        int(_val(r, "id") or 0) for r in rows if _val(r, "id") is not None
    }
    try:
        visible = await _st()._scoped_row_ids(model, ctx, resource, ids)
    except Exception as exc:
        logger.warning(
            "AI tool {} 数据范围失败 error_type={}", label, type(exc).__name__
        )
        return f"查询{label}失败，请稍后重试"
    rows = [r for r in rows if int(_val(r, "id") or 0) in visible]
    if not rows:
        return f"当前用户数据范围内未查询到符合条件的{label}"
    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 张{label}（当前用户数据范围内，"
        f"前 {_OVERSAMPLE_LIMIT} 条候选内计），返回前 {len(top)} 张："
    ]
    for r in top:
        lines.append(_fmt_inspection_row(r, party_of(r)))
    return "\n".join(lines)


async def query_incoming_inspections(
    keyword: Optional[str] = None,
    supplier_id: Optional[int] = None,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    quality_status: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """来料检验单摘要（单号/物料/供应商/检验数/合格与不合格数/结论/时间）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    err, status_norm = _validate_status(status)
    if err:
        return err
    err, qs_norm = _validate_quality_status(quality_status)
    if err:
        return err
    err, start_d, end_d = _validate_dates(date_start, date_end)
    if err:
        return err
    err, sid = _positive_id(supplier_id, "supplier_id")
    if err:
        return err
    err, mid = _positive_id(material_id, "material_id")
    if err:
        return err
    try:
        from apps.kuaizhizao.services.quality_service import (
            IncomingInspectionService,
        )

        result = await IncomingInspectionService().list_incoming_inspections(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            keyword=_norm_opt(keyword),
            supplier_id=sid,
            material_id=mid,
            status=status_norm,
            quality_status=qs_norm,
            inspection_start_date=start_d,
            inspection_end_date=end_d,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_incoming_inspections 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询来料检验单失败，请稍后重试"
    rows = list((result or {}).get("data") or [])
    from apps.kuaizhizao.models.incoming_inspection import IncomingInspection

    return await _finish_inspection_list(
        ctx,
        model=IncomingInspection,
        resource=_SCOPE_INCOMING,
        rows=rows,
        label="来料检验单",
        limit=limit,
        party_of=_party_incoming,
    )


async def query_process_inspections(
    keyword: Optional[str] = None,
    work_order_id: Optional[int] = None,
    operation_id: Optional[int] = None,
    status: Optional[str] = None,
    quality_status: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """过程检验单摘要（单号/物料/工单与工序/检验数/合格与不合格数/结论/时间）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    err, status_norm = _validate_status(status)
    if err:
        return err
    err, qs_norm = _validate_quality_status(quality_status)
    if err:
        return err
    err, start_d, end_d = _validate_dates(date_start, date_end)
    if err:
        return err
    err, wo_id = _positive_id(work_order_id, "work_order_id")
    if err:
        return err
    err, op_id = _positive_id(operation_id, "operation_id")
    if err:
        return err
    try:
        from apps.kuaizhizao.services.quality_service import (
            ProcessInspectionService,
        )

        result = await ProcessInspectionService().list_process_inspections(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            keyword=_norm_opt(keyword),
            work_order_id=wo_id,
            operation_id=op_id,
            status=status_norm,
            quality_status=qs_norm,
            inspection_start_date=start_d,
            inspection_end_date=end_d,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_process_inspections 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询过程检验单失败，请稍后重试"
    rows = list((result or {}).get("data") or [])
    from apps.kuaizhizao.models.process_inspection import ProcessInspection

    return await _finish_inspection_list(
        ctx,
        model=ProcessInspection,
        resource=_SCOPE_PROCESS,
        rows=rows,
        label="过程检验单",
        limit=limit,
        party_of=_party_process,
    )


async def query_finished_inspections(
    keyword: Optional[str] = None,
    work_order_id: Optional[int] = None,
    status: Optional[str] = None,
    quality_status: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """成品检验单摘要（单号/物料/工单/检验数/合格与不合格数/结论/时间）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    err, status_norm = _validate_status(status)
    if err:
        return err
    err, qs_norm = _validate_quality_status(quality_status)
    if err:
        return err
    err, start_d, end_d = _validate_dates(date_start, date_end)
    if err:
        return err
    err, wo_id = _positive_id(work_order_id, "work_order_id")
    if err:
        return err
    try:
        from apps.kuaizhizao.services.quality_service import (
            FinishedGoodsInspectionService,
        )

        result = (
            await FinishedGoodsInspectionService().list_finished_goods_inspections(
                ctx.tenant_id,
                skip=0,
                limit=_fetch_limit(limit),
                keyword=_norm_opt(keyword),
                work_order_id=wo_id,
                status=status_norm,
                quality_status=qs_norm,
                inspection_start_date=start_d,
                inspection_end_date=end_d,
            )
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_finished_inspections 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询成品检验单失败，请稍后重试"
    rows = list((result or {}).get("data") or [])
    from apps.kuaizhizao.models.finished_goods_inspection import (
        FinishedGoodsInspection,
    )

    return await _finish_inspection_list(
        ctx,
        model=FinishedGoodsInspection,
        resource=_SCOPE_FINISHED,
        rows=rows,
        label="成品检验单",
        limit=limit,
        party_of=_party_finished,
    )


async def query_oqc_inspections(
    status: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """OQC 出货检验单摘要（单号/物料/客户与发货通知/检验数/结论/放行/时间）。

    底层 ``OQCInspectionService.list`` 的 keyword 过滤器引用不存在字段
    ``sales_delivery_code``（恒 FieldError），本 Tool 不暴露 keyword。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    err, status_norm = _validate_status(status)
    if err:
        return err
    err, start_d, end_d = _validate_dates(date_start, date_end)
    if err:
        return err
    try:
        from apps.kuaizhizao.services.quality_improvement_service import (
            OQCInspectionService,
        )

        result = await OQCInspectionService().list(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            status=status_norm,
            inspection_start_date=start_d,
            inspection_end_date=end_d,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_oqc_inspections 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询出货检验单失败，请稍后重试"
    rows = list((result or {}).get("data") or [])
    from apps.kuaizhizao.models.oqc_inspection import OQCInspection

    return await _finish_inspection_list(
        ctx,
        model=OQCInspection,
        resource=_SCOPE_OQC,
        rows=rows,
        label="出货检验单",
        limit=limit,
        party_of=_party_oqc,
    )


def _fmt_eval_period(row: Any) -> str:
    ptype = str(_val(row, "period_type") or "").strip().lower()
    year = _val(row, "period_year", None)
    zh = _EVAL_PERIOD_ZH.get(ptype, ptype or "周期")
    if ptype == "quarterly":
        quarter = _val(row, "period_quarter", None)
        return f"{year} 年 Q{quarter}（季度）" if quarter else f"{year} 年（季度）"
    return f"{year} 年度" if zh == "年度" else f"{year}（{zh}）"


def _fmt_eval_row(row: Any) -> str:
    """供应商评价行摘要：供应商/周期/得分/等级/状态；无联系人与价格字段。"""
    supplier = _val(row, "supplier_name") or "未知"
    code = _val(row, "supplier_code")
    supplier_text = f"供应商 {supplier}（{code}）" if code else f"供应商 {supplier}"
    score = _val(row, "score", None)
    score_text = _ct()._fmt_num(score) if score is not None else "未评分"
    grade = _val(row, "grade") or "未评级"
    rect = ""
    if _val(row, "needs_rectification", False):
        rect = f"，整改 {_val(row, 'rectification_status') or 'none'}"
    return (
        f"评价单 {_val(row, 'code')}："
        f"{supplier_text}，"
        f"周期 {_fmt_eval_period(row)}，"
        f"得分 {score_text}，等级 {grade}，"
        f"状态 {_val(row, 'status') or '未知'}{rect}"
        f"（id={_val(row, 'id')}）"
    )


async def query_supplier_evaluations(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    period_type: Optional[str] = None,
    period_year: Optional[int] = None,
    supplier_id: Optional[int] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """供应商评价摘要（供应商/评价周期/得分/等级/状态），读结果不重算。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    status_norm = _norm_opt(status)
    if status_norm is not None:
        status_norm = status_norm.lower()
        if status_norm not in _EVAL_STATUSES:
            return "status 仅支持 draft/pending/approved/rejected/revoked"
    ptype = _norm_opt(period_type)
    if ptype is not None:
        ptype = ptype.lower()
        if ptype not in _EVAL_PERIOD_TYPES:
            return "period_type 仅支持 annual/quarterly"
    year: Optional[int] = None
    if period_year is not None and str(period_year).strip() != "":
        try:
            year = int(period_year)
        except (TypeError, ValueError):
            return "period_year 须为 2000-2100 的整数年份"
        if year < 2000 or year > 2100:
            return "period_year 须为 2000-2100 的整数年份"
    err, sid = _positive_id(supplier_id, "supplier_id")
    if err:
        return err
    try:
        from apps.kuaizhizao.services.supplier_evaluation_service import (
            SupplierEvaluationService,
        )

        result = await SupplierEvaluationService().list(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            keyword=_norm_opt(keyword),
            status=status_norm,
            period_type=ptype,
            period_year=year,
            supplier_id=sid,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_supplier_evaluations 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询供应商评价失败，请稍后重试"
    rows = list(getattr(result, "data", None) or [])
    if not rows:
        return "未查询到符合条件的供应商评价"
    ids: Set[int] = {
        int(_val(r, "id") or 0) for r in rows if _val(r, "id") is not None
    }
    try:
        from apps.kuaizhizao.models.supplier_evaluation import SupplierEvaluation

        visible = await _st()._scoped_row_ids(
            SupplierEvaluation, ctx, _SCOPE_SUPPLIER_EVAL, ids
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_supplier_evaluations 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询供应商评价失败，请稍后重试"
    rows = [r for r in rows if int(_val(r, "id") or 0) in visible]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的供应商评价"
    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 张供应商评价（当前用户数据范围内，"
        f"前 {_OVERSAMPLE_LIMIT} 条候选内计），返回前 {len(top)} 张："
    ]
    for r in top:
        lines.append(_fmt_eval_row(r))
    return "\n".join(lines)
