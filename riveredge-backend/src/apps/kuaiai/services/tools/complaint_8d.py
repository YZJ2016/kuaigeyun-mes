"""KU-AI 场景只读 Tool：客诉/8D 报告查询（spec 215，S14）。

Tool 名：``query_complaints`` / ``query_8d_reports``。

T1 事实（写 spec §4）：

- ``QualityComplaintService.list(tenant_id, *, skip, limit, keyword, status,
  business_type, defect_category, include_export_masked, order_by)``
  （quality_complaint_service.py:237）**不支持** customer_id / material_id /
  日期过滤，且返回的 ``QualityComplaintListItem`` 不含 customer_id /
  material_id / eight_d_report_id（schemas/quality_complaint.py:104）。spec
  §1 要求 Tool 暴露这三个过滤键——照搬 ``query_ecn``（ecn_impact.py）先例，
  适配层用与 service 同口径的模型基座谓词（tenant_id + 软删 + status）
  直查 ``QualityComplaint``，补 customer_id/material_id 过滤与
  created_at 站点日历日界过滤（``site_day_bounds_utc`` 转 UTC 半开区间），
  候选行 ≤ ``_COMPLAINT_CANDIDATE_MAX`` 后行级范围收敛。
- ``QualityComplaintService.get(tenant_id, complaint_id)``（:234）→
  ``QualityComplaintResponse``，含 ``eight_d_report_id``；客诉→8D 为
  单链字段（Quality8DReport 无 complaint_id 列）。``query_8d_reports`` 的
  ``complaint_id`` 参数先解析客诉得到 eight_d_report_id（客诉行先套
  ``_SCOPE_COMPLAINT`` 行级范围复核，范围外不透存在性），再
  ``Quality8DService().get_report(tenant_id, report_id)`` 取单条
  （quality_improvement_service.py:582），避免关联报告落在列表分页窗外。
- ``Quality8DService.list_reports(tenant_id, skip, limit, status, severity,
  owner_id, overdue_only, my_stage_pending, my_action_pending,
  viewer_user_id, keyword, order_by, created_start_date, created_end_date,
  due_start_date, due_end_date)``（quality_improvement_service.py:504）→
  ``Quality8DListResponse(items, total)``；keyword 匹配
  report_code/title/owner_name（:562）。本 Tool 仅暴露
  keyword/status/complaint_id（spec §1 参数闭集），my_*/overdue 等
  视图开关不外放。``EightDCollaborationService`` 只有阶段协同/行动项/
  门禁方法，无列表方法，不用于本 Tool。
- 8D 阶段闭集 = ``VALID_8D_STATUS_FLOW``（d0_prepare…d8_team_congratulation
  + closed，quality_improvement_service.py:45）；客诉状态闭集 =
  ``ALLOWED_STATUS``（quality_complaint_service.py:92：
  draft/pending/approved/rejected/processing/closed/revoked）。
- 权限码（kuaizhizao manifest permissions 核实）：客诉
  ``kuaizhizao:quality-complaint:read``（注意非 quality-management-*
  号段）、8D ``kuaizhizao:quality-management-eight-d-reports:read``。
- 行级范围：``quality-complaint`` 与 ``quality-management-eight-d-reports``
  均不在 manifest ``reference_resources``（data_scope_key 无从谈起），
  ``data_scope_*`` 注册文件亦无画像。适配层统一用
  ``_scoped_row_ids(model, ctx, <各 Tool 权限资源键>, ids)`` 收敛（SC-D7
  一 Tool 一键）：无角色授予 → DataScopeService 失败关闭；无显式策略 →
  平台「无策略=全部」语义放行。
- masking：不输出客户/供应商联系人、电话、商务条款、金额；不输出
  整改说明（supplier_response）、扩展载荷、撤销原因及创建/更新人姓名
  （与 spec 195/209 同款约定）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Set

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 行级范围资源键 = 各 Tool manifest 权限码资源段（SC-D7 一 Tool 一键）
_SCOPE_COMPLAINT = "kuaizhizao:quality-complaint"
_SCOPE_8D = "kuaizhizao:quality-management-eight-d-reports"

# 闭集参数（T1 从 service ALLOWED_STATUS / VALID_8D_STATUS_FLOW 核实）
_COMPLAINT_STATUSES = frozenset(
    {"draft", "pending", "approved", "rejected", "processing", "closed", "revoked"}
)
_8D_STATUSES = frozenset(
    {
        "d0_prepare",
        "d1_team",
        "d2_problem",
        "d3_containment",
        "d4_root_cause",
        "d5_corrective_action",
        "d6_implement_result",
        "d7_prevent_recurrence",
        "d8_team_congratulation",
        "closed",
    }
)

# 与 service._8D_STAGE_LABELS 同口径的阶段中文标签（输出用）
_8D_STAGE_ZH = {
    "d0_prepare": "D0 准备响应",
    "d1_team": "D1 组建团队",
    "d2_problem": "D2 问题描述",
    "d3_containment": "D3 临时遏制",
    "d4_root_cause": "D4 根因分析",
    "d5_corrective_action": "D5 纠正措施",
    "d6_implement_result": "D6 实施验证",
    "d7_prevent_recurrence": "D7 防再发",
    "d8_team_congratulation": "D8 总结",
    "closed": "已关闭",
}

_COMPLAINT_TYPE_ZH = {
    "iqc_incoming": "IQC来料批次投诉",
    "line_incoming": "产线来料投诉",
    "pqc": "PQC投诉",
    "oqc": "OQC投诉",
    "customer": "客户投诉",
}

# 客诉模型直查候选上限（service 无 customer_id/material_id/日期过滤键，
# 与 query_ecn 同口径先候选后范围收敛）
_COMPLAINT_CANDIDATE_MAX = 100
# 8D list_reports 过采样上限（先过滤后截断，范围内行不被顶掉）
_8D_OVERSAMPLE_LIMIT = 100


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    """scene_tools 私有助手延迟借用（_parse_date / _scoped_row_ids）。"""
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _norm_opt(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip() or None


def _val(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        v = row.get(key, default)
    else:
        v = getattr(row, key, default)
    return default if v is None else v


def _fmt_dt(value: Any) -> str:
    """datetime/date 展示：datetime 经 API 同口径站点时区文本，date 取 ISO 日
    （缺省 ''，交由调用方补「未定/未知」）。"""
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


def _positive_id(value: Any, name: str) -> tuple:
    """→ (err, int_id)：可选正整数 id 校验。"""
    if value is None or str(value).strip() == "":
        return None, None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return f"{name} 须为正整数", None
    if n <= 0:
        return f"{name} 须为正整数", None
    return None, n


def _validate_dates(date_start: Any, date_end: Any) -> tuple:
    """→ (err, start_d, end_d)：YYYY-MM-DD 校验后转 date。"""
    start_d = _st()._parse_date(date_start) if date_start else None
    if date_start and start_d is None:
        return "date_start 须为 YYYY-MM-DD 格式的日期", None, None
    end_d = _st()._parse_date(date_end) if date_end else None
    if date_end and end_d is None:
        return "date_end 须为 YYYY-MM-DD 格式的日期", None, None
    return None, start_d, end_d


def _fmt_complaint_row(row: Any) -> str:
    """客诉行摘要：单号/标题/类型/客户或供应商来源/物料/状态/时效/关联8D。"""
    customer = _val(row, "customer_name")
    supplier = _val(row, "supplier_name")
    if customer:
        source = f"客户 {customer}"
    elif supplier:
        source = f"供应商 {supplier}"
    else:
        source = "来源 未知"
    bt = _COMPLAINT_TYPE_ZH.get(
        str(_val(row, "business_type") or ""), _val(row, "business_type") or "未知"
    )
    linked = ""
    if _val(row, "eight_d_report_id", None):
        linked = f"，关联8D id={_val(row, 'eight_d_report_id')}"
    return (
        f"投诉单 {_val(row, 'code')}：{_val(row, 'title') or '未命名'}，"
        f"类型 {bt}，"
        f"{source}，"
        f"物料 {_val(row, 'material_code')}"
        f"（{_val(row, 'material_name') or '未命名'}），"
        f"批次 {_val(row, 'batch_no') or '无'}，"
        f"状态 {_val(row, 'status') or '未知'}，"
        f"要求完成 {_fmt_dt(_val(row, 'due_at', None)) or '未定'}，"
        f"创建 {_fmt_dt(_val(row, 'created_at', None)) or '未知'}"
        f"{linked}"
        f"（id={_val(row, 'id')}）"
    )


def _fmt_8d_row(row: Any) -> str:
    """8D 行摘要：编号/标题/阶段/严重程度/截止/关闭/未闭环行动项/关联单。"""
    status = str(_val(row, "status") or "")
    stage = _8D_STAGE_ZH.get(status, status or "未知")
    closed = ""
    if _val(row, "closed_at", None):
        closed = f"，关闭 {_fmt_dt(_val(row, 'closed_at', None))}"
    actions = ""
    open_actions = _val(row, "open_action_items_count", 0)
    try:
        if int(open_actions or 0) > 0:
            actions = f"，未闭环行动项 {int(open_actions)}"
    except (TypeError, ValueError):
        pass
    # 关联单只有 id 列（Quality8DResponse 无 code 联查），与客诉行
    # 「关联8D id=…」同口径做非空标注
    linked = ""
    if _val(row, "quality_exception_id", None):
        linked += f"，关联质量异常#{_val(row, 'quality_exception_id')}"
    if _val(row, "defect_record_id", None):
        linked += f"，关联不合格台账#{_val(row, 'defect_record_id')}"
    return (
        f"8D 报告 {_val(row, 'report_code')}：{_val(row, 'title') or '未命名'}，"
        f"阶段 {stage}，"
        f"严重程度 {_val(row, 'severity') or '未知'}，"
        f"截止 {_fmt_dt(_val(row, 'due_date', None)) or '未定'}"
        f"{closed}{actions}{linked}"
        f"（id={_val(row, 'id')}）"
    )


async def query_complaints(
    customer_id: Optional[int] = None,
    material_id: Optional[int] = None,
    status: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """质量投诉单摘要（单号/类型/客户或供应商/物料/状态/时效/关联8D）。

    日期过滤对 ``created_at`` 含界；customer_id/material_id 按模型字段精确
    过滤（service.list 不支持，按 query_ecn 先例在适配层直查模型）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    status_norm = _norm_opt(status)
    if status_norm is not None:
        status_norm = status_norm.lower()
        if status_norm not in _COMPLAINT_STATUSES:
            return (
                "status 仅支持 draft/pending/approved/rejected/processing/"
                "closed/revoked"
            )
    err, cid = _positive_id(customer_id, "customer_id")
    if err:
        return err
    err, mid = _positive_id(material_id, "material_id")
    if err:
        return err
    err, start_d, end_d = _validate_dates(date_start, date_end)
    if err:
        return err
    try:
        from apps.kuaizhizao.models.quality_complaint import QualityComplaint

        qs = QualityComplaint.filter(
            tenant_id=ctx.tenant_id, deleted_at__isnull=True
        )
        if status_norm:
            qs = qs.filter(status=status_norm)
        if cid:
            qs = qs.filter(customer_id=cid)
        if mid:
            qs = qs.filter(material_id=mid)
        if start_d or end_d:
            # created_at 含界按站点日历日界转 UTC（不落 naive UTC 日界），
            # 半开区间 [start, end) 与 site_day_bounds_utc 契约一致
            from core.utils.timezone_utils import (
                site_day_bounds_utc,
                to_naive_utc,
            )
        if start_d:
            start_utc, _ = site_day_bounds_utc(start_d)
            qs = qs.filter(created_at__gte=to_naive_utc(start_utc))
        if end_d:
            _, end_utc = site_day_bounds_utc(end_d)
            qs = qs.filter(created_at__lt=to_naive_utc(end_utc))
        rows = await qs.order_by("-created_at", "-id").limit(
            _COMPLAINT_CANDIDATE_MAX
        ).all()
    except Exception as exc:
        logger.warning(
            "AI tool query_complaints 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询质量投诉单失败，请稍后重试"
    if not rows:
        return "未查询到符合条件的质量投诉单"
    ids: Set[int] = {
        int(_val(r, "id") or 0) for r in rows if _val(r, "id") is not None
    }
    try:
        visible = await _st()._scoped_row_ids(
            QualityComplaint, ctx, _SCOPE_COMPLAINT, ids
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_complaints 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询质量投诉单失败，请稍后重试"
    rows = [r for r in rows if int(_val(r, "id") or 0) in visible]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的质量投诉单"
    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 张质量投诉单（当前用户数据范围内，"
        f"前 {_COMPLAINT_CANDIDATE_MAX} 条候选内计），返回前 {len(top)} 张："
    ]
    for r in top:
        lines.append(_fmt_complaint_row(r))
    return "\n".join(lines)


def _fetch_8d_limit(limit: Any) -> int:
    """用户 limit（≤20）放大到过采样上限内，供范围过滤后仍够页。"""
    return min(max(_ct()._clamp_limit(limit) * 5, 50), _8D_OVERSAMPLE_LIMIT)


def _8d_matches(report: Any, status_norm: Optional[str], keyword: Optional[str]) -> bool:
    """complaint_id 解析路径上的确定性再过滤（与 list_reports 同口径）。"""
    if status_norm and str(_val(report, "status") or "") != status_norm:
        return False
    if keyword:
        kw = keyword.lower()
        hay = " ".join(
            str(_val(report, k) or "")
            for k in ("report_code", "title", "owner_name")
        ).lower()
        if kw not in hay:
            return False
    return True


async def _finish_8d_rows(
    ctx: AiRuntimeContext,
    *,
    rows: List[Any],
    limit: int,
    candidate_window: bool = True,
) -> str:
    """范围收敛 → 截断 → 有界摘要（8D 列表/单条共用尾部口径）。

    ``candidate_window=False``（complaint_id 单结果路径）不拼「前 N 条候选
    内计」——该路径未经候选窗口过采样，措辞会误导。
    """
    if not rows:
        return "未查询到符合条件的 8D 报告"
    ids: Set[int] = {
        int(_val(r, "id") or 0) for r in rows if _val(r, "id") is not None
    }
    try:
        from apps.kuaizhizao.models.quality_8d_report import Quality8DReport

        visible = await _st()._scoped_row_ids(
            Quality8DReport, ctx, _SCOPE_8D, ids
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_8d_reports 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询 8D 报告失败，请稍后重试"
    rows = [r for r in rows if int(_val(r, "id") or 0) in visible]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的 8D 报告"
    top = rows[: _ct()._clamp_limit(limit)]
    if candidate_window:
        head = (
            f"共 {len(rows)} 张 8D 报告（当前用户数据范围内，"
            f"前 {_8D_OVERSAMPLE_LIMIT} 条候选内计），返回前 {len(top)} 张："
        )
    else:
        head = (
            f"共 {len(rows)} 张 8D 报告（当前用户数据范围内），"
            f"返回前 {len(top)} 张："
        )
    lines = [head]
    for r in top:
        lines.append(_fmt_8d_row(r))
    return "\n".join(lines)


async def query_8d_reports(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    complaint_id: Optional[int] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """8D 报告摘要（编号/标题/阶段/严重程度/截止/未闭环行动项）。

    ``complaint_id``：先经 ``QualityComplaintService.get`` 解析客诉的
    ``eight_d_report_id``，再 ``Quality8DService.get_report`` 取单条
    （客诉→8D 为单链字段，列表分页可能漏取）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    status_norm = _norm_opt(status)
    if status_norm is not None:
        status_norm = status_norm.lower()
        if status_norm not in _8D_STATUSES:
            return (
                "status 仅支持 d0_prepare/d1_team/d2_problem/d3_containment/"
                "d4_root_cause/d5_corrective_action/d6_implement_result/"
                "d7_prevent_recurrence/d8_team_congratulation/closed"
            )
    err, cid = _positive_id(complaint_id, "complaint_id")
    if err:
        return err
    kw = _norm_opt(keyword)
    try:
        from apps.kuaizhizao.services.quality_improvement_service import (
            Quality8DService,
        )

        if cid:
            from apps.kuaizhizao.models.quality_complaint import (
                QualityComplaint,
            )
            from apps.kuaizhizao.services.quality_complaint_service import (
                QualityComplaintService,
            )
            from infra.exceptions.exceptions import NotFoundError

            try:
                complaint = await QualityComplaintService().get(
                    ctx.tenant_id, cid
                )
            except NotFoundError:
                return "未查询到对应客诉单"
            # 客诉行级范围复核（analyze_ecn_impact 源单同款）：范围外不透
            # 存在性，按「数据范围内未查询到」归一；_scoped_row_ids 失败
            # 由外层 except 归一为固定失败文案
            visible_c = await _st()._scoped_row_ids(
                QualityComplaint, ctx, _SCOPE_COMPLAINT, {cid}
            )
            if cid not in visible_c:
                return "当前用户数据范围内未查询到对应客诉单"
            report_id = _val(complaint, "eight_d_report_id", None)
            if not report_id:
                return "该客诉单尚未关联 8D 报告"
            try:
                report = await Quality8DService().get_report(
                    ctx.tenant_id, int(report_id)
                )
            except NotFoundError:
                return "客诉关联的 8D 报告不存在或已删除"
            if not _8d_matches(report, status_norm, kw):
                return "未查询到符合条件的 8D 报告"
            return await _finish_8d_rows(
                ctx, rows=[report], limit=limit, candidate_window=False
            )

        result = await Quality8DService().list_reports(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_8d_limit(limit),
            status=status_norm,
            keyword=kw,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_8d_reports 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询 8D 报告失败，请稍后重试"
    rows = list(getattr(result, "items", None) or [])
    return await _finish_8d_rows(ctx, rows=rows, limit=limit)
