"""
需求计算业务自动化（Taskiq）：创建后自动执行，完成后自动下推采购。
"""

from typing import Any, Dict

from loguru import logger

from apps.kuaizhizao.constants.demand_computation_status import (
    DEMAND_COMPUTATION_STATUS_COMPLETED,
)
from core.tasks.dispatcher import TaskEvent, dispatch_event
from core.tasks.event_compat import Event, TriggerEvent
from core.utils.workflow_tenant_isolation import with_tenant_isolation
from core.workflows.client import workflow_client
from infra.domain.tenant_context import get_current_tenant_id


EVENT_NAME = "demand-computation/auto-run"


async def enqueue_demand_computation_automation(
    *,
    tenant_id: int,
    computation_id: int,
    operator_id: int,
) -> list[str]:
    """投递自动执行/下推任务；无 handler 或投递失败时返回空列表。"""
    return await dispatch_event(
        TaskEvent(
            name=EVENT_NAME,
            data={
                "tenant_id": int(tenant_id),
                "computation_id": int(computation_id),
                "operator_id": int(operator_id),
            },
        )
    )


async def _append_computation_note(
    tenant_id: int,
    computation_id: int,
    note: str,
) -> None:
    from apps.kuaizhizao.models.demand_computation import DemandComputation

    row = await DemandComputation.get_or_none(tenant_id=tenant_id, id=computation_id)
    if not row:
        return
    prefix = "[业务自动化] "
    text = f"{prefix}{note}".strip()
    prev = (row.notes or "").strip()
    merged = f"{prev}\n{text}".strip() if prev else text
    row.notes = merged[:2000]
    await row.save(update_fields=["notes", "updated_at"])


@workflow_client.create_function(
    fn_id="demand-computation-auto-run",
    name="需求计算自动执行与下推采购",
    trigger=TriggerEvent(event=EVENT_NAME),
    retries=2,
)
@with_tenant_isolation
async def demand_computation_auto_run_function(event: Event) -> Dict[str, Any]:
    tenant_id = get_current_tenant_id()
    data = event.data or {}
    computation_id = int(data.get("computation_id") or 0)
    operator_id = int(data.get("operator_id") or 0)
    if computation_id <= 0 or operator_id <= 0:
        return {"success": False, "error": "缺少 computation_id 或 operator_id"}

    from apps.kuaizhizao.models.demand_computation import DemandComputation
    from apps.kuaizhizao.services.demand_computation_service import DemandComputationService
    from apps.kuaizhizao.services.document_push_pull_service import DocumentPushPullService
    from infra.services.business_config_service import BusinessConfigService

    cfg = BusinessConfigService()
    auto_execute = await cfg.auto_execute_computation_on_create(tenant_id)
    auto_push = await cfg.auto_push_purchase_on_computation_complete(tenant_id)
    if not auto_execute and not auto_push:
        return {"success": True, "skipped": True, "reason": "automation_off"}

    computation = await DemandComputation.get_or_none(tenant_id=tenant_id, id=computation_id)
    if not computation:
        return {"success": False, "error": f"需求计算不存在: {computation_id}"}

    svc = DemandComputationService()
    result: Dict[str, Any] = {
        "success": True,
        "computation_id": computation_id,
        "executed": False,
        "pushed": False,
    }

    try:
        if auto_execute:
            status = str(computation.computation_status or "").strip()
            if status == DEMAND_COMPUTATION_STATUS_COMPLETED:
                result["executed"] = True
                result["execute_skipped"] = "already_completed"
            else:
                await svc.execute_computation(
                    tenant_id=tenant_id,
                    computation_id=computation_id,
                    operator_id=operator_id,
                )
                result["executed"] = True
                computation = await DemandComputation.get_or_none(
                    tenant_id=tenant_id, id=computation_id
                )

        if auto_push:
            status = str(getattr(computation, "computation_status", None) or "").strip()
            if status != DEMAND_COMPUTATION_STATUS_COMPLETED:
                msg = f"自动下推采购跳过：计算未完成（当前状态 {status or '空'}）"
                await _append_computation_note(tenant_id, computation_id, msg)
                result["push_skipped"] = msg
                return result

            require_pr = await cfg.require_purchase_requisition(tenant_id)
            push_svc = DocumentPushPullService()
            if require_pr:
                push_result = await push_svc.push_document(
                    tenant_id=tenant_id,
                    source_type="demand_computation",
                    source_id=computation_id,
                    target_type="purchase_requisition",
                    created_by=operator_id,
                )
                result["pushed"] = True
                result["push_target"] = "purchase_requisition"
                result["push_result"] = push_result
            else:
                push_result = await push_svc.push_document(
                    tenant_id=tenant_id,
                    source_type="demand_computation",
                    source_id=computation_id,
                    target_type="purchase_order",
                    created_by=operator_id,
                )
                result["pushed"] = True
                result["push_target"] = "purchase_order"
                result["push_result"] = push_result
                # 采购订单自动审核/收货通知由 generate→try_auto_approve_purchase_order 统一处理

        return result
    except Exception as exc:
        logger.warning(
            "需求计算自动执行/下推失败 tenant={} computation={}: {}",
            tenant_id,
            computation_id,
            exc,
        )
        await _append_computation_note(
            tenant_id,
            computation_id,
            f"自动执行或下推失败：{exc}",
        )
        return {"success": False, "computation_id": computation_id, "error": str(exc)}
