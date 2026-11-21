"""工序发料后同步工单工序开工。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.services.outsource_order_issue_bridge import OutsourceOrderIssueBridge


@pytest.mark.asyncio
async def test_apply_execution_start_marks_work_order_operation_in_progress():
    svc = OutsourceOrderIssueBridge()
    oo = SimpleNamespace(
        status="released",
        actual_start_date=None,
        work_order_operation_id=88,
        updated_by=None,
    )
    oo.save = AsyncMock()
    op = SimpleNamespace(
        id=88,
        status="assigned",
        actual_start_date=None,
    )
    op.save = AsyncMock()
    op_filter = AsyncMock()
    op_filter.first = AsyncMock(return_value=op)

    with patch(
        "apps.kuaizhizao.services.outsource_order_issue_bridge.WorkOrderOperation.filter",
        return_value=op_filter,
    ):
        await svc._apply_execution_start(tenant_id=1, oo=oo, updated_by=3)

    assert oo.status == "in_progress"
    assert op.status == "in_progress"
    assert op.actual_start_date is not None
    oo.save.assert_awaited_once()
    op.save.assert_awaited_once()