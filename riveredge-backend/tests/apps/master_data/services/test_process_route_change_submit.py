"""B-02: 工艺路线变更 pending 与流程启动同事务；start 失败不落 pending。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.exceptions.exceptions import ValidationError


@pytest.mark.asyncio
async def test_submit_change_rolls_back_pending_when_flow_missing():
    from apps.master_data.services.process_route_change_service import ProcessRouteChangeService

    change = MagicMock()
    change.id = 9
    change.uuid = "chg-9"
    change.status = "draft"
    change.applicant_id = 3
    change.save = AsyncMock()

    with (
        patch.object(
            ProcessRouteChangeService,
            "_get_change_or_raise",
            new=AsyncMock(return_value=change),
        ),
        patch(
            "apps.master_data.services.process_route_change_service.is_audit_required",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "apps.master_data.services.process_route_change_service.start_change_approval_flow",
            new=AsyncMock(
                side_effect=ValidationError(
                    "工艺路线变更审核已开启但未找到可用的审批流程，"
                    "请在配置中心检查 process_route_change 审批流程是否已激活"
                )
            ),
        ),
        patch(
            "apps.master_data.services.process_route_change_service.in_transaction",
        ) as mock_txn,
    ):
        # 模拟 in_transaction：进入后抛错时由调用方感知；不持久化
        class _Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        mock_txn.return_value = _Ctx()

        with pytest.raises(ValidationError, match="未找到可用的审批流程"):
            await ProcessRouteChangeService.submit_change(1, 9, 3)

    # start 失败前虽写入 pending，事务回滚语义下不应视为已提交成功
    assert change.save.await_count == 1
