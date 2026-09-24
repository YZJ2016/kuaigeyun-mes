"""KU-AI S2 受控写 Tool handler（KR-D10 五值闭集）+ manifest ``ai_tools`` 自注册。

Tool 名钉死五值：``search_knowledge`` / ``query_workorder`` /
``list_workorder_tasks`` / ``submit_production_feedback`` /
``update_workorder_status``。工单侧四个 Tool 一律调 kuaizhizao 既有 service
（带 ``ctx.tenant_id`` / ``ctx.user``），禁 SQL、禁裸 ORM 绕过权限；handler
返回给模型读的短摘要文本，不塞整单 JSON。

handler 约定见 ``core/ai/runtime/tool_bridge.py``：``async def handler(**args)
-> str``；签名声明 ``ctx`` 形参时桥接层补传 ``AiRuntimeContext``。空上下文与
底层异常一律回错误文案（失败关闭，KR-I3），不抛穿、不落敏感信息到返回值。

注册链路：``ToolRegistry.register_from_manifest`` 目前无 core 侧调用点；
本模块被 ``ToolRegistry.ensure_defaults`` 导入时，读取同目录 manifest.json
的 ``ai_tools`` 声明完成注册（handler + 真实业务权限码生效）；manifest 读取
失败时由 ensure_defaults 兜底注册无 handler 的定义，调用时回错，仍失败关闭。
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, List, Optional, Tuple

from loguru import logger
from tortoise.transactions import in_transaction

from core.ai.runtime.context import AiRuntimeContext, get_ai_context
from core.ai.tool_registry import ToolRegistry
from infra.exceptions.exceptions import (
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_ERR_SEARCH_KNOWLEDGE_STUB = "知识库检索暂未启用（S3 上线）"

# update_workorder_status 允许的目标状态：draft/released/split 走专门流程
# （提交/下达/拆分），不开放给 Tool 直改。
_UPDATEABLE_WORK_ORDER_STATUSES = frozenset(
    {"in_progress", "paused", "completed", "cancelled"}
)

# update_workorder_status 迁移白名单（当前态 → 允许目标态）：只放开
# 「开工 / 暂停 / 恢复 / 取消」四个受控迁移。completed 走完工流程、
# draft/released/split 走提交/下达/拆分专门流程，均不开放给 Tool 直改；
# 冻结单（is_frozen）任何迁移均拒绝。
_ALLOWED_STATUS_TRANSITIONS = {
    "released": frozenset({"in_progress"}),
    "in_progress": frozenset({"paused", "cancelled"}),
    "paused": frozenset({"in_progress"}),
}

_WORK_ORDER_STATUS_ZH = {
    "draft": "草稿",
    "released": "已下达",
    "in_progress": "进行中",
    "paused": "已暂停",
    "completed": "已完成",
    "cancelled": "已取消",
    "split": "已拆分",
}


def _resolve_ctx(ctx: Optional[AiRuntimeContext]) -> Optional[AiRuntimeContext]:
    return ctx if ctx is not None else get_ai_context()


def _ctx_ok(ctx: Optional[AiRuntimeContext]) -> bool:
    return (
        ctx is not None
        and bool(ctx.tenant_id)
        and getattr(ctx.user, "id", None) is not None
    )


def _fmt_num(value: Any) -> str:
    if value is None:
        return "0"
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if d == d.to_integral_value():
        return str(d.quantize(Decimal(1)))
    return str(d.normalize())


def _fmt_status(status: Optional[str]) -> str:
    s = str(status or "").strip()
    zh = _WORK_ORDER_STATUS_ZH.get(s)
    return f"{zh}({s})" if zh else (s or "未知")


def _clamp_limit(limit: Any, default: int = 10, upper: int = 20) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, upper))


def _fmt_work_order_row(wo: Any) -> str:
    return (
        f"工单 {getattr(wo, 'code', '')}"
        f"（{getattr(wo, 'name', None) or '未命名'}）："
        f"产品 {getattr(wo, 'product_name', '')}，"
        f"状态 {_fmt_status(getattr(wo, 'status', None))}，"
        f"计划 {_fmt_num(getattr(wo, 'quantity', None))}，"
        f"已完成 {_fmt_num(getattr(wo, 'completed_quantity', None))}"
        f"（id={getattr(wo, 'id', '')}）"
    )


def _display_name(user: Any) -> str:
    name = (
        getattr(user, "full_name", None)
        or getattr(user, "username", None)
        or ""
    )
    return str(name).strip() or f"用户{getattr(user, 'id', '')}"


async def search_knowledge(
    query: str,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """知识库检索（S3 才上线）：失败关闭 stub，禁止假检索。"""
    _ = query
    if not _ctx_ok(_resolve_ctx(ctx)):
        return _ERR_NO_CONTEXT
    return _ERR_SEARCH_KNOWLEDGE_STUB


async def query_workorder(
    work_order_id: Optional[int] = None,
    code: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """按 id 查工单详情摘要，或按编码/关键词/状态列表查询。"""
    ctx = _resolve_ctx(ctx)
    if not _ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        service = WorkOrderService()
        if work_order_id:
            wo = await service.get_work_order_by_id(ctx.tenant_id, int(work_order_id))
            return _fmt_work_order_row(wo)
        rows, total = await service.list_work_orders(
            ctx.tenant_id,
            current_user=ctx.user,
            code=(code or None),
            keyword=(keyword or None),
            status=(status or None),
            skip=0,
            limit=_clamp_limit(limit),
            include_downstream_push_progress=False,
        )
        if not rows:
            return "未查询到符合条件的工单"
        lines = [f"共 {total} 张工单，返回前 {len(rows)} 条："]
        lines.extend(_fmt_work_order_row(r) for r in rows)
        return "\n".join(lines)
    except NotFoundError:
        return f"工单不存在：{work_order_id}"
    except Exception as exc:
        logger.warning(
            "AI tool query_workorder 失败 error_type={}", type(exc).__name__
        )
        return "查询工单失败，请稍后重试"


async def list_workorder_tasks(
    work_order_id: int,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """列出工单工序任务（报工前先看 operation_id 与状态）。"""
    ctx = _resolve_ctx(ctx)
    if not _ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        ops = await WorkOrderService().get_work_order_operations(
            ctx.tenant_id, int(work_order_id)
        )
        if isinstance(ops, dict):
            ops = ops.get("operations") or []
        if not ops:
            return f"工单 {work_order_id} 暂无工序任务"
        lines = [f"工单 {work_order_id} 共 {len(ops)} 道工序："]
        for op in ops:
            lines.append(
                f"{getattr(op, 'sequence', '')}. "
                f"{getattr(op, 'operation_name', '')}"
                f"（{getattr(op, 'operation_code', '')}）："
                f"状态 {getattr(op, 'status', '')}，"
                f"已完成 {_fmt_num(getattr(op, 'completed_quantity', None))}，"
                f"合格 {_fmt_num(getattr(op, 'qualified_quantity', None))}，"
                f"不合格 {_fmt_num(getattr(op, 'unqualified_quantity', None))}"
                f"（operation_id={getattr(op, 'operation_id', '')}，"
                f"行id={getattr(op, 'id', '')}）"
            )
        return "\n".join(lines)
    except NotFoundError:
        return f"工单不存在：{work_order_id}"
    except Exception as exc:
        logger.warning(
            "AI tool list_workorder_tasks 失败 error_type={}", type(exc).__name__
        )
        return "查询工单工序失败，请稍后重试"


async def submit_production_feedback(
    work_order_id: int,
    operation_id: int,
    reported_quantity: Any,
    qualified_quantity: Optional[Any] = None,
    unqualified_quantity: Any = 0,
    work_hours: Optional[Any] = None,
    remarks: Optional[str] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """提交报工（本人自报；代报/小组报工走业务页面，不开放给 Tool）。"""
    ctx = _resolve_ctx(ctx)
    if not _ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        qty = Decimal(str(reported_quantity))
    except (InvalidOperation, ValueError):
        return "报工数量无效"
    if qty <= 0:
        return "报工数量必须大于 0"
    try:
        unq = Decimal(str(unqualified_quantity or 0))
        qual = (
            Decimal(str(qualified_quantity))
            if qualified_quantity is not None
            else qty - unq
        )
        hours = Decimal(str(work_hours)) if work_hours is not None else Decimal("0")
    except (InvalidOperation, ValueError):
        return "数量/工时参数无效"
    if unq < 0 or qual < 0 or hours < 0:
        return "数量/工时不能为负数"
    try:
        from apps.kuaizhizao.schemas.reporting_record import ReportingRecordCreate
        from apps.kuaizhizao.services.reporting_service import ReportingService
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        wo_service = WorkOrderService()
        wo = await wo_service.get_work_order_by_id(ctx.tenant_id, int(work_order_id))
        ops = await wo_service.get_work_order_operations(
            ctx.tenant_id, int(work_order_id)
        )
        if isinstance(ops, dict):
            ops = ops.get("operations") or []
        target = int(operation_id)
        op = next(
            (
                o
                for o in ops
                if int(getattr(o, "operation_id", 0) or 0) == target
                or int(getattr(o, "id", 0) or 0) == target
            ),
            None,
        )
        if op is None:
            return f"工单 {wo.code} 下未找到工序 {operation_id}"
        payload = ReportingRecordCreate(
            work_order_id=int(work_order_id),
            work_order_code=wo.code,
            work_order_name=wo.name or wo.code,
            operation_id=int(getattr(op, "operation_id", 0) or op.id),
            operation_code=op.operation_code,
            operation_name=op.operation_name,
            worker_id=int(ctx.user.id),
            worker_name=_display_name(ctx.user),
            reported_quantity=qty,
            qualified_quantity=qual,
            unqualified_quantity=unq,
            work_hours=hours,
            reported_at=datetime.now(),
            remarks=remarks,
        )
        record = await ReportingService().create_reporting_record(
            tenant_id=ctx.tenant_id,
            reporting_data=payload,
            reported_by=int(ctx.user.id),
            entry_mode="manual",
        )
        return (
            f"报工已提交：工单 {wo.code} 工序 {op.operation_name}，"
            f"报工 {_fmt_num(qty)}（合格 {_fmt_num(qual)}，"
            f"不合格 {_fmt_num(unq)}），报工记录 id={record.id}，"
            f"状态 {getattr(record, 'status', 'pending')}"
        )
    except (ValidationError, BusinessLogicError, NotFoundError) as exc:
        # 业务校验文案本就是用户可读信息；截断防超长
        message = str(getattr(exc, "message", "") or exc)[:200]
        return f"报工提交失败：{message}"
    except Exception as exc:
        logger.warning(
            "AI tool submit_production_feedback 失败 error_type={}",
            type(exc).__name__,
        )
        return "提交报工失败，请稍后重试"


async def update_workorder_status(
    work_order_id: int,
    status: str,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """更新工单状态（受控迁移白名单，见 _ALLOWED_STATUS_TRANSITIONS）。

    目标态闭集之外再叠加迁移校验：先取工单当前 status/is_frozen
    （service 层已做 tenant 过滤），非法迁移与冻结单一律拒绝；
    →cancelled 时与 ``update_work_order`` 的 cancel 分支同款副作用——
    同事务作废进行中线边备料单。
    """
    ctx = _resolve_ctx(ctx)
    if not _ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    target = str(status or "").strip()
    if target not in _UPDATEABLE_WORK_ORDER_STATUSES:
        allowed = "、".join(sorted(_UPDATEABLE_WORK_ORDER_STATUSES))
        return f"不支持的目标状态：{target or '空'}（允许：{allowed}）"
    try:
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        service = WorkOrderService()
        current_wo = await service.get_by_id(ctx.tenant_id, int(work_order_id))
        if getattr(current_wo, "is_frozen", False):
            raise ValidationError("工单已冻结，不允许变更状态")
        current = str(getattr(current_wo, "status", "") or "").strip()
        if target not in _ALLOWED_STATUS_TRANSITIONS.get(current, frozenset()):
            raise ValidationError(
                f"状态 {current or '未知'} 不允许变更为 {target}"
            )
        async with in_transaction():
            wo = await service.update_work_order_status(
                ctx.tenant_id,
                int(work_order_id),
                status=target,
                updated_by=int(ctx.user.id),
            )
            if target == "cancelled":
                # 取消副作用（与 update_work_order cancel 分支 :3051/:3180 同款）：
                # 软删该工单 draft/picking 态线边备料单及明细
                from apps.kuaizhizao.services.batching_order_service import (
                    BatchingOrderService,
                )

                await BatchingOrderService().void_open_batching_orders_for_work_order(
                    ctx.tenant_id, int(work_order_id)
                )
        return f"工单 {wo.code} 状态已更新为 {_fmt_status(target)}"
    except (ValidationError, BusinessLogicError, NotFoundError) as exc:
        message = str(getattr(exc, "message", "") or exc)[:200]
        return f"更新工单状态失败：{message}"
    except Exception as exc:
        logger.warning(
            "AI tool update_workorder_status 失败 error_type={}",
            type(exc).__name__,
        )
        return "更新工单状态失败，请稍后重试"


# 与 apps/kuaiai/manifest.json 的 ai_tools 保持同一份五值定义；
# ensure_defaults 兜底注册用（manifest 读取失败时无 handler，调用仍失败关闭）。
CHAT_TOOL_DEFINITIONS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索企业知识库（当前暂未启用）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_workorder",
            "description": "查询生产工单（按工单 id 查详情摘要，或按编码/关键词/状态列表查询）",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "integer", "description": "工单 ID"},
                    "code": {"type": "string", "description": "工单编码（模糊）"},
                    "keyword": {"type": "string", "description": "关键词（编码/名称/产品）"},
                    "status": {"type": "string", "description": "工单状态过滤"},
                    "limit": {"type": "integer", "description": "返回条数上限（默认10）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workorder_tasks",
            "description": "列出工单工序任务及各自状态/完成数量",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "integer", "description": "工单 ID"},
                },
                "required": ["work_order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_production_feedback",
            "description": "为工单工序提交报工（本人自报）",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "integer", "description": "工单 ID"},
                    "operation_id": {
                        "type": "integer",
                        "description": "工序 ID（list_workorder_tasks 返回的 operation_id）",
                    },
                    "reported_quantity": {"type": "number", "description": "报工数量"},
                    "qualified_quantity": {"type": "number", "description": "合格数量（缺省=报工-不合格）"},
                    "unqualified_quantity": {"type": "number", "description": "不合格数量"},
                    "work_hours": {"type": "number", "description": "工时（小时，可空）"},
                    "remarks": {"type": "string", "description": "备注"},
                },
                "required": ["work_order_id", "operation_id", "reported_quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_workorder_status",
            "description": "更新工单状态（仅放行迁移：已下达→in_progress、in_progress→paused、paused→in_progress、in_progress→cancelled）",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "integer", "description": "工单 ID"},
                    "status": {
                        "type": "string",
                        "enum": ["in_progress", "paused", "completed", "cancelled"],
                        "description": "目标状态",
                    },
                },
                "required": ["work_order_id", "status"],
            },
        },
    },
]


def _register_manifest_tools() -> None:
    """从同目录 manifest.json 注册 ``ai_tools``（handler + 权限码生效）。"""
    try:
        manifest_path = Path(__file__).resolve().parents[1] / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "kuaiai manifest 读取失败，AI tools 走兜底注册 error_type={}",
            type(exc).__name__,
        )
        return
    ToolRegistry.register_from_manifest("kuaiai", manifest)


_register_manifest_tools()
