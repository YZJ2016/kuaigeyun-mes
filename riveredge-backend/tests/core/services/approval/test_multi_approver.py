"""审批多审批人：标识解析、或签/会签完成判定与待办数据可见性。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.approval.approval_data_scope import (
    list_pending_approver_entity_ids,
    user_is_pending_approver_for_entity,
)
from core.services.approval.approval_instance_service import ApprovalInstanceService


def _make_instance(*, approval_type: str = "OR", node_id: str = "approval-1") -> MagicMock:
    instance = MagicMock()
    instance.current_node = node_id
    instance.process = MagicMock()
    instance.process.nodes = {
        "nodes": [
            {
                "id": node_id,
                "type": "approval",
                "data": {"approvalType": approval_type, "label": "审核"},
            }
        ],
        "edges": [],
    }
    return instance


def _task(*, status: str, sign_type: str | None = None) -> MagicMock:
    t = MagicMock()
    t.status = status
    t.sign_type = sign_type
    return t


class TestCheckNodeCompletion:
    @pytest.mark.asyncio
    async def test_or_sign_completes_when_one_approved_and_peer_still_pending(self):
        """或签：一人通过即完成，不等待其他指定人。"""
        instance = _make_instance(approval_type="OR")
        qs = MagicMock()
        qs.all = AsyncMock(
            return_value=[
                _task(status="approved"),
                _task(status="pending"),
            ]
        )
        with patch(
            "core.services.approval.approval_instance_service.ApprovalTask.filter",
            return_value=qs,
        ):
            done, status = await ApprovalInstanceService._check_node_completion(instance)
        assert done is True
        assert status == "approved"

    @pytest.mark.asyncio
    async def test_or_sign_waits_for_after_sign_pending(self):
        """或签后加签：须等后加签人处理完。"""
        instance = _make_instance(approval_type="OR")
        qs = MagicMock()
        qs.all = AsyncMock(
            return_value=[
                _task(status="approved"),
                _task(status="pending", sign_type="after"),
            ]
        )
        with patch(
            "core.services.approval.approval_instance_service.ApprovalTask.filter",
            return_value=qs,
        ):
            done, status = await ApprovalInstanceService._check_node_completion(instance)
        assert done is False
        assert status == "pending"

    @pytest.mark.asyncio
    async def test_or_sign_reject_completes_immediately(self):
        instance = _make_instance(approval_type="OR")
        qs = MagicMock()
        qs.all = AsyncMock(
            return_value=[
                _task(status="rejected"),
                _task(status="pending"),
            ]
        )
        with patch(
            "core.services.approval.approval_instance_service.ApprovalTask.filter",
            return_value=qs,
        ):
            done, status = await ApprovalInstanceService._check_node_completion(instance)
        assert done is True
        assert status == "rejected"

    @pytest.mark.asyncio
    async def test_and_sign_waits_until_all_approved(self):
        """会签：一人通过、另一人仍 pending 时不完成。"""
        instance = _make_instance(approval_type="AND")
        qs = MagicMock()
        qs.all = AsyncMock(
            return_value=[
                _task(status="approved"),
                _task(status="pending"),
            ]
        )
        with patch(
            "core.services.approval.approval_instance_service.ApprovalTask.filter",
            return_value=qs,
        ):
            done, status = await ApprovalInstanceService._check_node_completion(instance)
        assert done is False
        assert status == "pending"

    @pytest.mark.asyncio
    async def test_and_sign_completes_when_all_approved(self):
        instance = _make_instance(approval_type="AND")
        qs = MagicMock()
        qs.all = AsyncMock(
            return_value=[
                _task(status="approved"),
                _task(status="approved"),
            ]
        )
        with patch(
            "core.services.approval.approval_instance_service.ApprovalTask.filter",
            return_value=qs,
        ):
            done, status = await ApprovalInstanceService._check_node_completion(instance)
        assert done is True
        assert status == "approved"


class TestResolveApproverIdentifiers:
    @pytest.mark.asyncio
    async def test_mixed_uuid_and_numeric_ids(self):
        uuid_a = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        async def _first():
            return MagicMock(id=101)

        with patch(
            "core.services.approval.approval_instance_service.User.filter",
        ) as user_filter:
            user_mock = MagicMock()
            user_mock.first = _first
            user_filter.return_value = user_mock

            ids = await ApprovalInstanceService._resolve_approver_ids_from_identifiers(
                1,
                [uuid_a, 202],
                by_uuid=None,
            )
        assert ids == [101, 202]


class TestApprovalDataScope:
    @pytest.mark.asyncio
    async def test_list_pending_entity_ids_from_tasks(self):
        inst = MagicMock()
        inst.data = {"entity_type": "sales_order", "entity_id": 9001}
        task = MagicMock()
        task.approval_instance = inst

        with patch(
            "core.services.approval.approval_data_scope.ApprovalTask.filter",
        ) as task_filter:
            qs = MagicMock()
            qs.prefetch_related.return_value = qs
            qs.all = AsyncMock(return_value=[task])
            task_filter.return_value = qs

            ids = await list_pending_approver_entity_ids(1, 55, "sales_order")
        assert ids == {9001}

    @pytest.mark.asyncio
    async def test_user_is_pending_approver_for_entity(self):
        with patch(
            "core.services.approval.approval_data_scope.list_pending_approver_entity_ids",
            new_callable=AsyncMock,
            return_value={42, 43},
        ):
            assert await user_is_pending_approver_for_entity(1, 7, "sales_order", 42)
            assert not await user_is_pending_approver_for_entity(1, 7, "sales_order", 99)


class TestDepartmentManagerResolution:
    @pytest.mark.asyncio
    async def test_resolve_managers_for_department_uuids(self):
        dept = MagicMock(manager_id=88)
        with patch(
            "core.services.approval.approval_instance_service.Department.filter",
        ) as dept_filter:
            dept_filter.return_value.all = AsyncMock(return_value=[dept])
            with patch.object(
                ApprovalInstanceService,
                "_filter_active_user_ids",
                new_callable=AsyncMock,
                return_value=[88],
            ):
                ids = await ApprovalInstanceService._resolve_managers_for_department_uuids(
                    1, ["dept-uuid-1"]
                )
        assert ids == [88]


class TestResolveNodeApproversFailClosed:
    @pytest.mark.asyncio
    async def test_user_type_without_ids_raises(self):
        from infra.exceptions.exceptions import ValidationError

        instance = MagicMock()
        instance.tenant_id = 1
        instance.submitter_id = 99
        instance.data = {}
        node = {"id": "n1", "data": {"approverType": "user", "approverIds": []}}

        with patch.object(
            ApprovalInstanceService,
            "_resolve_approver_ids_from_identifiers",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with pytest.raises(ValidationError, match="未配置有效指定人员"):
                await ApprovalInstanceService._resolve_node_approvers(node, instance)

    @pytest.mark.asyncio
    async def test_form_select_uses_snapshot(self):
        instance = MagicMock()
        instance.tenant_id = 1
        instance.submitter_id = 99
        instance.data = {"selected_approver_user_ids": [7, 8]}
        node = {"id": "n1", "data": {"approverType": "form_select"}}

        with patch.object(
            ApprovalInstanceService,
            "_resolve_approver_ids_from_identifiers",
            new_callable=AsyncMock,
            return_value=[7, 8],
        ), patch.object(
            ApprovalInstanceService,
            "_filter_active_user_ids",
            new_callable=AsyncMock,
            return_value=[7, 8],
        ):
            ids = await ApprovalInstanceService._resolve_node_approvers(node, instance)
        assert ids == [7, 8]

    @pytest.mark.asyncio
    async def test_unknown_approver_type_raises(self):
        from infra.exceptions.exceptions import ValidationError

        instance = MagicMock()
        instance.tenant_id = 1
        instance.submitter_id = 99
        instance.data = {}
        node = {"id": "n1", "data": {"approverType": "optional"}}

        with pytest.raises(ValidationError, match="不支持的审批人类型"):
            await ApprovalInstanceService._resolve_node_approvers(node, instance)

    @pytest.mark.asyncio
    async def test_auto_pass_follows_configured_default_branch(self):
        """上一审批人被跳过时，条件节点按已勾选的默认分支继续。"""
        instance = MagicMock()
        instance.id = 1
        instance.submitter_id = 9
        instance.data = {}
        instance.save = AsyncMock()
        condition = {
            "id": "c1",
            "type": "condition",
            "data": {
                "label": "是否选择总经理",
                "routeMode": "previous_approver",
                "conditions": [
                    {"label": "特批是（需总经理特批）"},
                    {"label": "分支 2", "isDefault": True},
                ],
            },
        }
        instance.process = MagicMock()
        instance.process.nodes = {
            "nodes": [
                {"id": "a1", "type": "approval", "data": {"label": "审批节点"}},
                condition,
                {"id": "gm", "type": "approval", "data": {"label": "总经理"}},
                {"id": "end", "type": "end", "data": {"label": "结束"}},
            ],
            "edges": [
                {"source": "a1", "target": "c1"},
                {"source": "c1", "target": "gm"},
                {"source": "c1", "target": "end"},
            ],
        }
        node = {"id": "a1", "type": "approval", "data": {"label": "审批节点"}}
        with patch.object(
            ApprovalInstanceService,
            "_create_approval_history",
            new_callable=AsyncMock,
        ), patch.object(
            ApprovalInstanceService,
            "_create_node_tasks",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await ApprovalInstanceService._auto_pass_empty_approval_node(1, instance, node)
        assert instance.data["__branch_index_c1"] == 1

    @pytest.mark.asyncio
    async def test_manager_without_department_leader_skips_node(self):
        """直属部门没有可用负责人时跳过本节点，不把待办回给提交人。"""
        from infra.exceptions.exceptions import ValidationError

        instance = MagicMock()
        instance.id = 5
        instance.tenant_id = 1
        instance.submitter_id = 10
        instance.data = {}
        node = {
            "id": "n1",
            "type": "approval",
            "data": {"approverType": "manager", "emptyApproverPolicy": "block"},
        }

        with patch.object(
            ApprovalInstanceService,
            "_resolve_node_approvers",
            new_callable=AsyncMock,
            side_effect=ValidationError("制单人直属部门未配置可用负责人，无法提交审核"),
        ), patch.object(
            ApprovalInstanceService,
            "_auto_pass_empty_approval_node",
            new_callable=AsyncMock,
            return_value=[],
        ) as skipped:
            await ApprovalInstanceService._create_node_tasks(1, instance, node)
        skipped.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multi_level_manager_level_two(self):
        instance = MagicMock()
        instance.tenant_id = 1
        instance.submitter_id = 10
        instance.data = {}
        node = {
            "id": "n2",
            "data": {"approverType": "multi_level_manager", "managerLevel": 2},
        }

        with patch.object(
            ApprovalInstanceService,
            "_resolve_submitter_department_manager_at_level",
            new_callable=AsyncMock,
            return_value=[42],
        ) as mock_level:
            ids = await ApprovalInstanceService._resolve_node_approvers(node, instance)
        mock_level.assert_awaited_once_with(1, 10, 2)
        assert ids == [42]

    @pytest.mark.asyncio
    async def test_multi_level_manager_missing_level_returns_empty(self):
        """组织树不足 N 级时解析结果为空列表；阻断与否由创建任务侧按 emptyApproverPolicy 决定。"""
        instance = MagicMock()
        instance.tenant_id = 1
        instance.submitter_id = 10
        instance.data = {}
        node = {
            "id": "n2",
            "data": {"approverType": "multi_level_manager", "managerLevel": 2},
        }

        with patch.object(
            ApprovalInstanceService,
            "_resolve_submitter_department_manager_at_level",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_level:
            ids = await ApprovalInstanceService._resolve_node_approvers(node, instance)
        mock_level.assert_awaited_once_with(1, 10, 2)
        assert ids == []


class TestEvaluateConditionsNumeric:
    def test_gt_with_string_actual_and_numeric_threshold(self):
        instance = MagicMock()
        instance.data = {"total_request_amount": "60000"}
        conditions = [{"field": "total_request_amount", "operator": ">", "value": 50000}]
        idx = ApprovalInstanceService._evaluate_conditions(instance, conditions)
        assert idx == 0

    def test_gt_skips_to_next_branch_when_below_threshold(self):
        instance = MagicMock()
        instance.data = {"total_request_amount": 40000}
        conditions = [
            {"field": "total_request_amount", "operator": ">", "value": 50000},
            {"field": "total_request_amount", "operator": "<", "value": 50000},
        ]
        idx = ApprovalInstanceService._evaluate_conditions(instance, conditions)
        assert idx == 1

