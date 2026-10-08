"""租户隔离装饰器：兼容单参 event 与双参 ctx 调用约定。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.tasks.dispatcher import TaskContext, TaskEvent, TaskStep, _run_handler
from core.utils.workflow_tenant_isolation import _extract_event, with_tenant_isolation


def test_extract_event_from_direct_task_event():
    """dispatcher 单参约定：handler(event)。"""
    event = TaskEvent(name="scheduled-task/execute", data={"tenant_id": 1, "task_uuid": "u"})
    assert _extract_event((event,), {}) is event


def test_extract_event_from_task_context():
    """双参约定：handler(ctx, step)。"""
    event = TaskEvent(name="x", data={"tenant_id": 2})
    ctx = TaskContext(event=event, run_id="r1")
    assert _extract_event((ctx, TaskStep()), {}) is event


@pytest.mark.asyncio
async def test_with_tenant_isolation_accepts_direct_task_event():
    """回归：scheduled-task/execute 经 _run_handler 直传 TaskEvent 时不得报缺少 event。"""
    seen = {}

    @with_tenant_isolation
    async def scheduled_task_executor_function(event):
        seen["tenant_id"] = event.data["tenant_id"]
        return {"success": True}

    tenant = SimpleNamespace(is_active=True)
    event = TaskEvent(
        name="scheduled-task/execute",
        data={"tenant_id": 7, "task_uuid": "abc"},
    )

    with patch(
        "core.utils.workflow_tenant_isolation.Tenant.get_or_none",
        new=AsyncMock(return_value=tenant),
    ):
        await _run_handler(scheduled_task_executor_function, event, "run-1")

    assert seen == {"tenant_id": 7}


@pytest.mark.asyncio
async def test_with_tenant_isolation_still_accepts_ctx_shape():
    @with_tenant_isolation
    async def handler(event):
        return {"ok": True, "data": event.data}

    tenant = SimpleNamespace(is_active=True)
    event = TaskEvent(name="approval/x", data={"tenant_id": 3})
    ctx = TaskContext(event=event, run_id="r")

    with patch(
        "core.utils.workflow_tenant_isolation.Tenant.get_or_none",
        new=AsyncMock(return_value=tenant),
    ):
        out = await handler(ctx, TaskStep())
    assert out == {"ok": True, "data": {"tenant_id": 3}}
