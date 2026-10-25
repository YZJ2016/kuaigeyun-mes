"""KU-AI 场景只读 Tool：MRP 例外收件箱解读（spec 205）。

Tool 名：``query_mrp_exceptions``。

T1 事实（写 §4）：
- 底层 ``DemandComputationService.get_mrp_exception_inbox(tenant_id, *,
  computation_id, code, severity, skip, limit, max_computations)``
  （demand_computation_service.py:2200）与 ``GET /mrp-exception-inbox``
  路由同 service 同参数：返回 dict 含 ``total`` / ``error_count`` /
  ``warning_count`` / ``summary_by_code`` / ``items``；``items`` 已按
  严重级（error→warning→info）→ 例外码优先级 → 最新计算 排序
  （``_exception_inbox_sort_key``），适配层不重排，天然「错误级在前」。
- 行字段：``code``/``severity``/``message``/``qty``/``bucket_date``/
  ``material_code``/``material_name``/``document_code``/
  ``document_source_type``/``computation_id``/``computation_code``/
  ``computation_end_time``/``item_id``/``inbox_key``；无「建议动作」独立
  字段，建议性文案在 ``message`` 内（``_normalize_exception`` 统一产出）。
- service 与路由均不接收 ``current_user``：Tool 与路由同口径，不额外
  加数据范围也不放宽（spec 205 §1，§4 记该事实）。
- ``max_computations`` 缺省 ``None`` 时扫描全部已完成计算，与路由缺省
  一致（service 内 ``capped`` 仅在显式传值时生效）；Tool 不暴露该参数，
  扫描范围与收件箱缺省相同。
- ``severity`` 闭集 error|warning|info（``_exception_level`` 只产出
  这三值）；``code`` 为自由串精确匹配，不做闭集（与路由一致）。
- 不输出单价/金额等商务敏感字段；只留例外码/严重级/物料/数量/需求日期/
  单据/计算编号。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# severity 闭集：mrp_llc_engine._exception_level 全部返回值
_MRP_SEVERITIES = frozenset({"error", "warning", "info"})

_SEVERITY_ZH = {
    "error": "错误",
    "warning": "警告",
    "info": "提示",
}


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _fmt_time(value: Any) -> str:
    """计算完成时间可读文本：datetime 经 API 同口径站点时区文本（缺省
    「未知」）。"""
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
    return s[:16] if s else "未知"


def _fmt_exception_row(row: Dict[str, Any]) -> str:
    """例外行摘要：严重级+例外码+物料+数量+需求日期+单据+文案+计算编号。"""
    sev = str(row.get("severity") or "")
    sev_zh = _SEVERITY_ZH.get(sev, sev or "未知")
    doc_code = row.get("document_code")
    doc_type = row.get("document_source_type")
    doc_seg = f"，单据 {doc_code}（{doc_type}）" if doc_code else ""
    qty = row.get("qty")
    qty_seg = (
        f"，数量 {_ct()._fmt_num(qty)}" if qty is not None else ""
    )
    return (
        f"[{sev_zh}] {row.get('code') or '未知例外'}："
        f"物料 {row.get('material_code') or ''}"
        f"（{row.get('material_name') or '未命名'}）{qty_seg}，"
        f"需求日期 {row.get('bucket_date') or '未定'}{doc_seg} — "
        f"{row.get('message') or '无说明'}"
        f"（计算 {row.get('computation_code') or row.get('computation_id') or ''}"
        f"，完成于 {_fmt_time(row.get('computation_end_time'))}，"
        f"item={row.get('item_id') or ''}）"
    )


async def query_mrp_exceptions(
    computation_id: Optional[int] = None,
    code: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """MRP 例外收件箱摘要（错误优先，含按例外码分布）。

    与 ``GET /mrp-exception-inbox`` 同 service 同口径：数据范围不经
    ``current_user``（路由亦如此），租户隔离仅 ``ctx.tenant_id``。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    sev = (str(severity).strip() or None) if severity else None
    if sev is not None and sev not in _MRP_SEVERITIES:
        return "severity 仅支持 error/warning/info"
    comp_id = None
    if computation_id is not None:
        try:
            comp_id = int(computation_id)
        except (TypeError, ValueError):
            return "computation_id 须为整数"
        if comp_id <= 0:
            return "computation_id 须为正整数"
    code_norm = (str(code).strip() or None) if code else None
    try:
        from apps.kuaizhizao.services.demand_computation_service import (
            DemandComputationService,
        )

        result = await DemandComputationService().get_mrp_exception_inbox(
            ctx.tenant_id,
            computation_id=comp_id,
            code=code_norm,
            severity=sev,
            skip=0,
            limit=_ct()._clamp_limit(limit),
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_mrp_exceptions 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询 MRP 例外失败，请稍后重试"

    items = list((result or {}).get("items") or [])
    if not items:
        return "未查询到符合条件的 MRP 例外"
    total = int((result or {}).get("total") or len(items))
    error_count = int((result or {}).get("error_count") or 0)
    warning_count = int((result or {}).get("warning_count") or 0)
    info_count = max(total - error_count - warning_count, 0)

    head = (
        f"共 {total} 条 MRP 例外（错误 {error_count} / 警告 {warning_count}"
        f" / 提示 {info_count}），已按错误优先排序，返回前 {len(items)} 条："
    )
    lines = [head]
    summary_by_code = (result or {}).get("summary_by_code") or {}
    if summary_by_code:
        dist = "、".join(
            f"{k}×{v}" for k, v in summary_by_code.items()
        )
        lines.append(f"按例外码分布：{dist}")
    for row in items:
        lines.append(_fmt_exception_row(row))
    return "\n".join(lines)
