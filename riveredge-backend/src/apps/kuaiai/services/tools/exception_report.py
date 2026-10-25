"""KU-AI 场景写 Tool：生产异常上报（spec 214，经 HITL 确认闸）。

Tool 名：``create_material_shortage_exception`` /
``create_delivery_delay_exception`` / ``create_quality_exception``——
manifest ``kind=write``，装配期自动进入 spec 193
``HumanInTheLoopMiddleware`` 挂起，用户确认后才真正执行；同一 interrupt
单次认领保证幂等（spec 193 B-C1，本文件不做二次幂等）。

- 底层均为 ``ExceptionService.report_*``（现场提报系列，与移动端/车间
  同入口）：service 内置租户隔离、工单/物料存在性校验、同工单同物料
  未处理异常去重、``created_by`` → ``apply_create_audit`` 审计字段；
  创建调用包在 ``in_transaction`` 内（质量异常创建后站内通知同事务，
  通知失败整体回滚不留半成品）。
- 关联单复核（spec §1）：工单经 ``chat_tools._work_order_in_scope``
  （``kuaizhizao:work-order`` 行级范围）；物料经
  ``scene_tools._scoped_row_ids`` 套 ``master-data:material`` 资源键——
  范围外/非法 id 一律按不存在回复，不泄露存在性。
- 业务异常（``ValidationError``/``BusinessLogicError``/``NotFoundError``，
  infra 侧）→ service 文案截断透回；通用异常 → logger + 固定文案
  （失败关闭，不透出内部细节）。
- 审计：Tool 级 ``_audit_tool_call`` route 自动取首个 ``*_id`` 业务键
  （work_order_id/material_id），Tool 名本身编码异常类型。

T1 事实表（exception_service.py 为真源，spec §1 表与之冲突处以代码为准）：

- ``report_material_shortage``（:161）：``MaterialShortageReportCreate``
  ``material_id`` 单值必填 + ``shortage_quantity>0`` 必填——spec §1 的
  ``material_ids[]`` 与 ``description`` 在 service 层不存在，Tool 参数按
  service 签名收敛（``description`` 语义落 ``remarks``）。
- ``report_delivery_delay``（:227）：``delay_reason`` 必填（service
  内非空校验），spec §1 的 ``reason?``/``expected_date`` 无对应字段——
  ``expected_date`` 不映射（Known gaps 记缺口）。
- ``report_quality_exception``（:305）：``problem_description`` 必填；
  spec §1 的 ``description`` 即此字段。响应 ``uuid`` 为对外业务单号
  （与 ``_notify_quality_exception_created`` 的 ``exception_code`` 同口径）。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from loguru import logger
from tortoise.transactions import in_transaction

from core.ai.runtime.context import AiRuntimeContext
from infra.exceptions.exceptions import (
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 物料行级范围资源键（master_data manifest data_scope_key；
# 无显式策略=全部可见，策略生效即收敛）
_SCOPE_MATERIAL = "master-data:material"

# ExceptionService._normalize_alert_level 允许集（exception_service.py:147）
_ALERT_LEVELS = frozenset({"low", "medium", "high", "critical"})
# ExceptionService._normalize_severity（exception_service.py:155）
_SEVERITIES = frozenset({"minor", "major", "critical"})
# report_quality_exception allowed_types（exception_service.py:343-347）
_QUALITY_TYPES = frozenset(
    {"inspection_failure", "process_deviation", "customer_complaint"}
)

_DELAY_REASON_MAX = 500


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _parse_int_id(value: Any) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _parse_decimal(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _normalize_enum(
    value: Any, allowed: frozenset, label: str
) -> tuple[Optional[str], Optional[str]]:
    """可选闭集参数：缺省回 (None, None)；非法回 (None, 错误文案)。"""
    if value is None or str(value).strip() == "":
        return None, None
    v = str(value).strip().lower()
    if v not in allowed:
        return None, f"{label} 仅支持 {'/'.join(sorted(allowed))}"
    return v, None


async def _material_in_scope(ctx: AiRuntimeContext, material_id: Any) -> bool:
    """物料 by-ID 行级范围复核（``master-data:material``）。

    范围外/非法 id 一律按不存在处理（不泄露存在性）；范围解析异常
    失败关闭（按不可见处理）。
    """
    mid = _parse_int_id(material_id)
    if mid is None:
        return False
    try:
        from apps.master_data.models.material import Material

        visible = await _st()._scoped_row_ids(
            Material, ctx, _SCOPE_MATERIAL, {mid}
        )
        return mid in visible
    except Exception as exc:
        logger.warning(
            "AI tool 物料数据范围解析失败 error_type={}", type(exc).__name__
        )
        return False


def _biz_error_text(exc: Exception, prefix: str) -> str:
    message = str(getattr(exc, "message", "") or exc)[:200]
    return f"{prefix}：{message}"


async def create_material_shortage_exception(
    work_order_id: Any = None,
    material_id: Any = None,
    shortage_quantity: Any = None,
    required_quantity: Any = None,
    available_quantity: Any = None,
    alert_level: Optional[str] = None,
    remarks: Optional[str] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """创建缺料异常单（确认闸批准后执行；同工单同物料未处理单会被 service 拒绝）。

    ``material_id`` 为单值（service 一次一单料）；``shortage_quantity``
    必填且 >0；``required_quantity``>0 / ``available_quantity``≥0 可选，
    缺省时 service 按缺口口径补齐。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    wid = _parse_int_id(work_order_id)
    if wid is None:
        return "work_order_id 必填且须为正整数"
    mid = _parse_int_id(material_id)
    if mid is None:
        return "material_id 必填且须为正整数（service 单次创建仅支持单一物料）"
    shortage = _parse_decimal(shortage_quantity)
    if shortage is None or shortage <= 0:
        return "shortage_quantity 必填且须大于 0"
    required = None
    if required_quantity is not None:
        required = _parse_decimal(required_quantity)
        if required is None or required <= 0:
            return "required_quantity 须为大于 0 的数值"
    available = None
    if available_quantity is not None:
        available = _parse_decimal(available_quantity)
        if available is None or available < 0:
            return "available_quantity 须为不小于 0 的数值"
    level, err = _normalize_enum(alert_level, _ALERT_LEVELS, "alert_level")
    if err:
        return err
    if not await _ct()._work_order_in_scope(ctx, wid):
        return "工单不存在或超出当前用户数据范围"
    if not await _material_in_scope(ctx, mid):
        return "物料不存在或超出当前用户数据范围"
    try:
        from apps.kuaizhizao.schemas.material_shortage_exception import (
            MaterialShortageReportCreate,
        )
        from apps.kuaizhizao.services.exception_service import ExceptionService

        data = MaterialShortageReportCreate(
            work_order_id=wid,
            material_id=mid,
            shortage_quantity=shortage,
            available_quantity=available,
            required_quantity=required,
            alert_level=level,
            remarks=(str(remarks).strip() or None) if remarks else None,
        )
        async with in_transaction():
            resp = await ExceptionService().report_material_shortage(
                tenant_id=ctx.tenant_id,
                data=data,
                created_by=int(ctx.user.id),
            )
    except (ValidationError, BusinessLogicError, NotFoundError) as exc:
        return _biz_error_text(exc, "创建缺料异常失败")
    except Exception as exc:
        logger.warning(
            "AI tool create_material_shortage_exception 失败 error_type={}",
            type(exc).__name__,
        )
        return "创建缺料异常失败，请稍后重试"
    return (
        f"缺料异常已创建：单号 {getattr(resp, 'uuid', '')}，"
        f"工单 {getattr(resp, 'work_order_code', '')}，"
        f"物料 {getattr(resp, 'material_code', '')}"
        f"（{getattr(resp, 'material_name', '') or '未命名'}），"
        f"缺口 {_ct()._fmt_num(getattr(resp, 'shortage_quantity', None))}，"
        f"级别 {getattr(resp, 'alert_level', '') or '未知'}，"
        f"状态 {getattr(resp, 'status', '') or '未知'}，"
        f"建议 {getattr(resp, 'suggested_action', '') or '-'}"
        f"（记录 id={getattr(resp, 'id', '')}）"
    )


async def create_delivery_delay_exception(
    work_order_id: Any = None,
    delay_reason: Any = None,
    delay_days: Any = None,
    alert_level: Optional[str] = None,
    remarks: Optional[str] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """创建交期延期异常单（确认闸批准后执行；同工单未处理延期单会被 service 拒绝）。

    ``delay_reason`` 必填（≤500 字）；``delay_days`` 可选，缺省由 service
    按工单计划完工日推算（工单无计划完工日期时 service 要求必填）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    wid = _parse_int_id(work_order_id)
    if wid is None:
        return "work_order_id 必填且须为正整数"
    reason = str(delay_reason or "").strip()
    if not reason:
        return "delay_reason 必填（延期原因，≤500 字）"
    if len(reason) > _DELAY_REASON_MAX:
        return f"delay_reason 超长（≤{_DELAY_REASON_MAX} 字）"
    days = None
    if delay_days is not None:
        try:
            days = int(delay_days)
        except (TypeError, ValueError):
            return "delay_days 须为不小于 0 的整数"
        if days < 0:
            return "delay_days 须为不小于 0 的整数"
    level, err = _normalize_enum(alert_level, _ALERT_LEVELS, "alert_level")
    if err:
        return err
    if not await _ct()._work_order_in_scope(ctx, wid):
        return "工单不存在或超出当前用户数据范围"
    try:
        from apps.kuaizhizao.schemas.delivery_delay_exception import (
            DeliveryDelayReportCreate,
        )
        from apps.kuaizhizao.services.exception_service import ExceptionService

        data = DeliveryDelayReportCreate(
            work_order_id=wid,
            delay_reason=reason,
            delay_days=days,
            alert_level=level,
            remarks=(str(remarks).strip() or None) if remarks else None,
        )
        async with in_transaction():
            resp = await ExceptionService().report_delivery_delay(
                tenant_id=ctx.tenant_id,
                data=data,
                created_by=int(ctx.user.id),
            )
    except (ValidationError, BusinessLogicError, NotFoundError) as exc:
        return _biz_error_text(exc, "创建延期异常失败")
    except Exception as exc:
        logger.warning(
            "AI tool create_delivery_delay_exception 失败 error_type={}",
            type(exc).__name__,
        )
        return "创建延期异常失败，请稍后重试"
    return (
        f"延期异常已创建：单号 {getattr(resp, 'uuid', '')}，"
        f"工单 {getattr(resp, 'work_order_code', '')}，"
        f"延期 {getattr(resp, 'delay_days', '')} 天，"
        f"原因 {getattr(resp, 'delay_reason', '') or reason}，"
        f"级别 {getattr(resp, 'alert_level', '') or '未知'}，"
        f"状态 {getattr(resp, 'status', '') or '未知'}，"
        f"建议 {getattr(resp, 'suggested_action', '') or '-'}"
        f"（记录 id={getattr(resp, 'id', '')}）"
    )


async def create_quality_exception(
    problem_description: Any = None,
    work_order_id: Any = None,
    material_id: Any = None,
    severity: Optional[str] = None,
    exception_type: Optional[str] = None,
    batch_no: Optional[str] = None,
    remarks: Optional[str] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """创建质量异常单（确认闸批准后执行；创建后 service 触发站内通知）。

    ``problem_description`` 必填；``severity`` 闭集 minor/major/critical
    （缺省 minor）；``exception_type`` 闭集 inspection_failure/
    process_deviation/customer_complaint（缺省 process_deviation）；
    工单/物料可选，给了就做存在性与行级范围复核。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    desc = str(problem_description or "").strip()
    if not desc:
        return "problem_description 必填（问题描述）"
    sev, err = _normalize_enum(severity, _SEVERITIES, "severity")
    if err:
        return err
    e_type, err = _normalize_enum(
        exception_type, _QUALITY_TYPES, "exception_type"
    )
    if err:
        return err
    wid = None
    if work_order_id is not None:
        wid = _parse_int_id(work_order_id)
        if wid is None:
            return "work_order_id 须为正整数"
        if not await _ct()._work_order_in_scope(ctx, wid):
            return "工单不存在或超出当前用户数据范围"
    mid = None
    if material_id is not None:
        mid = _parse_int_id(material_id)
        if mid is None:
            return "material_id 须为正整数"
        if not await _material_in_scope(ctx, mid):
            return "物料不存在或超出当前用户数据范围"
    try:
        from apps.kuaizhizao.schemas.quality_exception import (
            QualityExceptionReportCreate,
        )
        from apps.kuaizhizao.services.exception_service import ExceptionService

        data = QualityExceptionReportCreate(
            problem_description=desc,
            work_order_id=wid,
            material_id=mid,
            batch_no=(str(batch_no).strip() or None) if batch_no else None,
            severity=sev or "minor",
            exception_type=e_type or "process_deviation",
            remarks=(str(remarks).strip() or None) if remarks else None,
        )
        async with in_transaction():
            resp = await ExceptionService().report_quality_exception(
                tenant_id=ctx.tenant_id,
                data=data,
                created_by=int(ctx.user.id),
            )
    except (ValidationError, BusinessLogicError, NotFoundError) as exc:
        return _biz_error_text(exc, "创建质量异常失败")
    except Exception as exc:
        logger.warning(
            "AI tool create_quality_exception 失败 error_type={}",
            type(exc).__name__,
        )
        return "创建质量异常失败，请稍后重试"
    out = (
        f"质量异常已创建：单号 {getattr(resp, 'uuid', '')}，"
        f"类型 {getattr(resp, 'exception_type', '')}，"
        f"严重程度 {getattr(resp, 'severity', '') or '未知'}，"
        f"状态 {getattr(resp, 'status', '') or '未知'}"
    )
    if getattr(resp, "work_order_code", None):
        out += f"，工单 {resp.work_order_code}"
    if getattr(resp, "material_code", None):
        out += (
            f"，物料 {resp.material_code}"
            f"（{getattr(resp, 'material_name', '') or '未命名'}）"
        )
    return out + f"（记录 id={getattr(resp, 'id', '')}）"
