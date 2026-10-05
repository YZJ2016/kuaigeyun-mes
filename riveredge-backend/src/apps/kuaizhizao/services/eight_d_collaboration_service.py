"""8D 协同：阶段指派、行动项、门禁与个人待办。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from apps.kuaizhizao.models.quality_8d_action_item import Quality8DActionItem
from apps.kuaizhizao.models.quality_8d_report import Quality8DReport
from apps.kuaizhizao.models.quality_8d_stage_assignment import Quality8DStageAssignment
from apps.kuaizhizao.schemas.quality_improvement import (
    Quality8DActionItemCreate,
    Quality8DActionItemResponse,
    Quality8DActionItemUpdate,
    Quality8DStageAssignmentBatchUpsert,
    Quality8DStageAssignmentResponse,
)
from apps.kuaizhizao.services.quality_improvement_service import VALID_8D_STATUS_FLOW, _8D_STAGE_LABELS
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from core.models.approval_instance import ApprovalInstance
from core.models.approval_process import ApprovalProcess
from core.models.approval_task import ApprovalTask
from loguru import logger

_ACTION_DISCIPLINES = frozenset({"d3_containment", "d5_corrective", "d6_verification"})
_DISCIPLINE_TO_STAGE = {
    "d3_containment": "d3_containment",
    "d5_corrective": "d5_corrective_action",
    "d6_verification": "d6_implement_result",
}
_STAGES_WITH_ACTIONS = frozenset({"d3_containment", "d5_corrective_action", "d6_implement_result"})
_PERSONAL_TASK_PROCESS_CODE = "personal_task"


@dataclass
class EightDCollaborationGate:
    current_stage_approved: bool = True
    action_items_verified: bool = True
    reason: Optional[str] = None


class EightDCollaborationService:
    @staticmethod
    def _workbench_path(report_id: int, stage_key: Optional[str] = None) -> str:
        base = f"/apps/kuaizhizao/quality-management/eight-d-reports/{report_id}/workbench"
        if stage_key:
            return f"{base}?stage={stage_key}"
        return base

    @staticmethod
    async def _resolve_user_name(tenant_id: int, user_id: Optional[int]) -> Optional[str]:
        if not user_id:
            return None
        from infra.models.user import User

        user = await User.get_or_none(id=user_id, tenant_id=tenant_id)
        if not user:
            return None
        return user.full_name or user.username

    @staticmethod
    async def _get_report(tenant_id: int, report_id: int) -> Quality8DReport:
        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        return row

    @staticmethod
    def _is_collaborative(report: Quality8DReport) -> bool:
        return (report.coordination_mode or "legacy").strip() == "collaborative"

    @staticmethod
    def _is_champion(report: Quality8DReport, user_id: int) -> bool:
        if report.owner_id and report.owner_id == user_id:
            return True
        if report.created_by and report.created_by == user_id and not report.owner_id:
            return True
        return False

    @staticmethod
    async def bootstrap_on_create(
        tenant_id: int,
        report: Quality8DReport,
        *,
        champion_user_id: int,
        champion_name: str,
    ) -> None:
        if not EightDCollaborationService._is_collaborative(report):
            return
        if not report.owner_id:
            report.owner_id = champion_user_id
            report.owner_name = champion_name
            await report.save(update_fields=["owner_id", "owner_name", "updated_at"])
        stage = report.status if report.status in VALID_8D_STATUS_FLOW else "d0_prepare"
        await Quality8DStageAssignment.get_or_create(
            tenant_id=tenant_id,
            report_id=report.id,
            stage_key=stage,
            defaults={
                "assignee_user_id": report.owner_id,
                "assignee_name": report.owner_name,
                "status": "in_progress",
            },
        )

    @staticmethod
    async def ensure_stage_row(
        tenant_id: int,
        report_id: int,
        stage_key: str,
        *,
        assignee_user_id: Optional[int] = None,
        assignee_name: Optional[str] = None,
    ) -> Quality8DStageAssignment:
        row, _ = await Quality8DStageAssignment.get_or_create(
            tenant_id=tenant_id,
            report_id=report_id,
            stage_key=stage_key,
            defaults={
                "assignee_user_id": assignee_user_id,
                "assignee_name": assignee_name,
                "status": "pending" if assignee_user_id else "pending",
            },
        )
        return row

    @staticmethod
    async def list_assignments(tenant_id: int, report_id: int) -> List[Quality8DStageAssignmentResponse]:
        rows = await Quality8DStageAssignment.filter(tenant_id=tenant_id, report_id=report_id).order_by("id")
        return [Quality8DStageAssignmentResponse.model_validate(r) for r in rows]

    @staticmethod
    async def upsert_assignments(
        tenant_id: int,
        report_id: int,
        user_id: int,
        payload: Quality8DStageAssignmentBatchUpsert,
    ) -> List[Quality8DStageAssignmentResponse]:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        if not EightDCollaborationService._is_collaborative(report):
            raise BusinessLogicError("仅协同模式 8D 可指派阶段负责人")
        if not EightDCollaborationService._is_champion(report, user_id):
            raise BusinessLogicError("仅报告牵头人可指派阶段负责人")
        if report.status == "closed":
            raise BusinessLogicError("已关闭的 8D 不可指派")

        out: List[Quality8DStageAssignmentResponse] = []
        for item in payload.items:
            if item.stage_key not in VALID_8D_STATUS_FLOW or item.stage_key == "closed":
                raise ValidationError(f"非法阶段: {item.stage_key}")
            name = item.assignee_name
            if item.assignee_user_id and not name:
                name = await EightDCollaborationService._resolve_user_name(tenant_id, item.assignee_user_id)
            row = await EightDCollaborationService.ensure_stage_row(
                tenant_id,
                report_id,
                item.stage_key,
            )
            prev_assignee = row.assignee_user_id
            row.assignee_user_id = item.assignee_user_id
            row.assignee_name = name
            row.due_date = item.due_date
            if row.status == "pending" and item.assignee_user_id:
                row.status = "in_progress"
            await row.save()
            out.append(Quality8DStageAssignmentResponse.model_validate(row))
            if item.assignee_user_id and item.assignee_user_id != prev_assignee:
                await EightDCollaborationService._notify_assignee(
                    tenant_id,
                    report,
                    item.stage_key,
                    item.assignee_user_id,
                    name,
                )
                await EightDCollaborationService._create_assignee_task(
                    tenant_id,
                    submitter_id=user_id,
                    assignee_id=item.assignee_user_id,
                    report=report,
                    stage_key=item.stage_key,
                    due_date=item.due_date,
                )
        return out

    @staticmethod
    async def submit_stage(tenant_id: int, report_id: int, stage_key: str, user_id: int) -> Quality8DStageAssignmentResponse:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        if not EightDCollaborationService._is_collaborative(report):
            raise BusinessLogicError("仅协同模式可提交阶段")
        row = await Quality8DStageAssignment.get_or_none(
            tenant_id=tenant_id, report_id=report_id, stage_key=stage_key
        )
        if not row or row.assignee_user_id != user_id:
            raise BusinessLogicError("仅本阶段负责人可提交")
        if row.status not in ("pending", "in_progress"):
            raise BusinessLogicError("当前阶段状态不可提交")
        if stage_key in _STAGES_WITH_ACTIONS:
            await EightDCollaborationService._assert_action_items_done_for_stage(tenant_id, report_id, stage_key)
        row.status = "submitted"
        row.submitted_at = resolve_business_datetime()
        await row.save()
        if report.owner_id:
            await EightDCollaborationService._notify_champion_stage_submitted(tenant_id, report, stage_key)
        return Quality8DStageAssignmentResponse.model_validate(row)

    @staticmethod
    async def approve_stage(tenant_id: int, report_id: int, stage_key: str, user_id: int, user_name: str) -> Quality8DStageAssignmentResponse:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        if not EightDCollaborationService._is_collaborative(report):
            raise BusinessLogicError("仅协同模式可确认阶段")
        if not EightDCollaborationService._is_champion(report, user_id):
            raise BusinessLogicError("仅报告牵头人可确认阶段")
        row = await Quality8DStageAssignment.get_or_none(
            tenant_id=tenant_id, report_id=report_id, stage_key=stage_key
        )
        if not row or row.status != "submitted":
            raise BusinessLogicError("仅已提交阶段可确认")
        if stage_key in _STAGES_WITH_ACTIONS:
            await EightDCollaborationService._assert_action_items_verified_for_stage(tenant_id, report_id, stage_key)
        row.status = "approved"
        row.approved_at = resolve_business_datetime()
        row.approved_by = user_id
        row.approved_by_name = user_name
        await row.save()
        return Quality8DStageAssignmentResponse.model_validate(row)

    @staticmethod
    async def reject_stage(
        tenant_id: int,
        report_id: int,
        stage_key: str,
        user_id: int,
        user_name: str,
        reason: str,
    ) -> Quality8DStageAssignmentResponse:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        if not EightDCollaborationService._is_champion(report, user_id):
            raise BusinessLogicError("仅报告牵头人可驳回阶段")
        row = await Quality8DStageAssignment.get_or_none(
            tenant_id=tenant_id, report_id=report_id, stage_key=stage_key
        )
        if not row or row.status != "submitted":
            raise BusinessLogicError("仅已提交阶段可驳回")
        row.status = "in_progress"
        row.submitted_at = None
        await row.save()
        if row.assignee_user_id:
            await EightDCollaborationService._notify_stage_rejected(
                tenant_id, report, stage_key, row.assignee_user_id, reason
            )
        return Quality8DStageAssignmentResponse.model_validate(row)

    @staticmethod
    async def list_action_items(tenant_id: int, report_id: int, discipline: Optional[str] = None) -> List[Quality8DActionItemResponse]:
        q = Quality8DActionItem.filter(tenant_id=tenant_id, report_id=report_id)
        if discipline:
            q = q.filter(discipline=discipline)
        rows = await q.order_by("sort_order", "id")
        return [Quality8DActionItemResponse.model_validate(r) for r in rows]

    @staticmethod
    async def create_action_item(
        tenant_id: int,
        report_id: int,
        user_id: int,
        payload: Quality8DActionItemCreate,
    ) -> Quality8DActionItemResponse:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        if report.status == "closed":
            raise BusinessLogicError("已关闭的 8D 不可新建行动项")
        if payload.discipline not in _ACTION_DISCIPLINES:
            raise ValidationError("行动项仅适用于 D3/D5/D6")
        await EightDCollaborationService._assert_can_edit_stage(report, user_id, _DISCIPLINE_TO_STAGE[payload.discipline])
        name = payload.assignee_name
        if payload.assignee_user_id and not name:
            name = await EightDCollaborationService._resolve_user_name(tenant_id, payload.assignee_user_id)
        row = await Quality8DActionItem.create(
            tenant_id=tenant_id,
            report_id=report_id,
            discipline=payload.discipline,
            title=payload.title.strip(),
            description=(payload.description or "").strip() or None,
            assignee_user_id=payload.assignee_user_id,
            assignee_name=name,
            due_date=payload.due_date,
            sort_order=payload.sort_order,
            evidence_attachments=payload.evidence_attachments,
            status="open",
        )
        if payload.assignee_user_id:
            await EightDCollaborationService._notify_action_assigned(tenant_id, report, row)
        return Quality8DActionItemResponse.model_validate(row)

    @staticmethod
    async def update_action_item(
        tenant_id: int,
        report_id: int,
        item_id: int,
        user_id: int,
        payload: Quality8DActionItemUpdate,
    ) -> Quality8DActionItemResponse:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        row = await Quality8DActionItem.get_or_none(id=item_id, tenant_id=tenant_id, report_id=report_id)
        if not row:
            raise NotFoundError("行动项不存在")
        stage = _DISCIPLINE_TO_STAGE[row.discipline]
        await EightDCollaborationService._assert_can_edit_stage(report, user_id, stage, action_item=row)
        data = payload.model_dump(exclude_unset=True)
        if "assignee_user_id" in data and data["assignee_user_id"] and not data.get("assignee_name"):
            data["assignee_name"] = await EightDCollaborationService._resolve_user_name(
                tenant_id, data["assignee_user_id"]
            )
        if data:
            await row.update_from_dict(data).save()
        return Quality8DActionItemResponse.model_validate(row)

    @staticmethod
    async def delete_action_item(tenant_id: int, report_id: int, item_id: int, user_id: int) -> None:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        row = await Quality8DActionItem.get_or_none(id=item_id, tenant_id=tenant_id, report_id=report_id)
        if not row:
            raise NotFoundError("行动项不存在")
        if not EightDCollaborationService._is_champion(report, user_id):
            raise BusinessLogicError("仅报告牵头人可删除行动项")
        await row.delete()

    @staticmethod
    async def complete_action_item(
        tenant_id: int,
        report_id: int,
        item_id: int,
        user_id: int,
    ) -> Quality8DActionItemResponse:
        row = await Quality8DActionItem.get_or_none(id=item_id, tenant_id=tenant_id, report_id=report_id)
        if not row:
            raise NotFoundError("行动项不存在")
        if row.assignee_user_id != user_id:
            raise BusinessLogicError("仅行动项责任人可标记完成")
        if row.status != "open":
            raise BusinessLogicError("仅进行中的行动项可完成")
        row.status = "done"
        row.completed_at = resolve_business_datetime()
        await row.save()
        return Quality8DActionItemResponse.model_validate(row)

    @staticmethod
    async def verify_action_item(
        tenant_id: int,
        report_id: int,
        item_id: int,
        user_id: int,
        user_name: str,
    ) -> Quality8DActionItemResponse:
        report = await EightDCollaborationService._get_report(tenant_id, report_id)
        if not EightDCollaborationService._is_champion(report, user_id):
            raise BusinessLogicError("仅报告牵头人可验证行动项")
        row = await Quality8DActionItem.get_or_none(id=item_id, tenant_id=tenant_id, report_id=report_id)
        if not row:
            raise NotFoundError("行动项不存在")
        if row.status != "done":
            raise BusinessLogicError("仅已完成的行动项可验证")
        row.status = "verified"
        row.verified_by = user_id
        row.verified_by_name = user_name
        row.verified_at = resolve_business_datetime()
        await row.save()
        return Quality8DActionItemResponse.model_validate(row)

    @staticmethod
    async def count_open_actions(tenant_id: int, report_id: int) -> int:
        return await Quality8DActionItem.filter(
            tenant_id=tenant_id,
            report_id=report_id,
        ).exclude(status__in=["verified", "cancelled"]).count()

    @staticmethod
    async def transition_gate(tenant_id: int, report: Quality8DReport) -> EightDCollaborationGate:
        if not EightDCollaborationService._is_collaborative(report):
            return EightDCollaborationGate()
        if report.status == "closed":
            return EightDCollaborationGate()
        stage = report.status
        assignment = await Quality8DStageAssignment.get_or_none(
            tenant_id=tenant_id, report_id=report.id, stage_key=stage
        )
        if not assignment or assignment.status != "approved":
            return EightDCollaborationGate(
                current_stage_approved=False,
                action_items_verified=True,
                reason="eight_d_report.transition.stage_not_approved",
            )
        if stage in _STAGES_WITH_ACTIONS:
            items = await Quality8DActionItem.filter(
                tenant_id=tenant_id,
                report_id=report.id,
            ).exclude(status="cancelled")
            disciplines = {
                "d3_containment": "d3_containment",
                "d5_corrective_action": "d5_corrective",
                "d6_implement_result": "d6_verification",
            }
            disc = disciplines.get(stage)
            if disc:
                stage_items = [i for i in items if i.discipline == disc]
                if stage_items and any(i.status != "verified" for i in stage_items):
                    return EightDCollaborationGate(
                        current_stage_approved=True,
                        action_items_verified=False,
                        reason="eight_d_report.transition.actions_not_verified",
                    )
        return EightDCollaborationGate()

    @staticmethod
    async def on_report_transition(tenant_id: int, report: Quality8DReport, new_status: str) -> None:
        if not EightDCollaborationService._is_collaborative(report) or new_status == "closed":
            return
        name = report.owner_name
        await EightDCollaborationService.ensure_stage_row(
            tenant_id,
            report.id,
            new_status,
            assignee_user_id=report.owner_id,
            assignee_name=name,
        )
        row = await Quality8DStageAssignment.get(
            tenant_id=tenant_id, report_id=report.id, stage_key=new_status
        )
        if row.status == "pending":
            row.status = "in_progress"
            await row.save(update_fields=["status", "updated_at"])

    @staticmethod
    async def filter_report_ids_my_stage_pending(tenant_id: int, user_id: int) -> Set[int]:
        rows = await Quality8DStageAssignment.filter(
            tenant_id=tenant_id,
            assignee_user_id=user_id,
            status__in=["pending", "in_progress"],
        ).values_list("report_id", flat=True)
        return set(rows)

    @staticmethod
    async def filter_report_ids_my_action_pending(tenant_id: int, user_id: int) -> Set[int]:
        rows = await Quality8DActionItem.filter(
            tenant_id=tenant_id,
            assignee_user_id=user_id,
            status="open",
        ).values_list("report_id", flat=True)
        return set(rows)

    @staticmethod
    async def assert_can_edit_stage_content(
        tenant_id: int,
        report: Quality8DReport,
        user_id: int,
        stage_key: str,
    ) -> None:
        if not EightDCollaborationService._is_collaborative(report):
            return
        if EightDCollaborationService._is_champion(report, user_id):
            return
        row = await Quality8DStageAssignment.get_or_none(
            tenant_id=tenant_id, report_id=report.id, stage_key=stage_key
        )
        if row and row.assignee_user_id == user_id and row.status in ("pending", "in_progress", "submitted"):
            return
        raise BusinessLogicError("无权编辑该阶段内容")

    @staticmethod
    async def _assert_can_edit_stage(
        report: Quality8DReport,
        user_id: int,
        stage_key: str,
        *,
        action_item: Optional[Quality8DActionItem] = None,
    ) -> None:
        if not EightDCollaborationService._is_collaborative(report):
            return
        if EightDCollaborationService._is_champion(report, user_id):
            return
        if action_item and action_item.assignee_user_id == user_id:
            return
        assignment = await Quality8DStageAssignment.get_or_none(
            tenant_id=report.tenant_id, report_id=report.id, stage_key=stage_key
        )
        if assignment and assignment.assignee_user_id == user_id:
            return
        raise BusinessLogicError("无权维护该阶段行动项")

    @staticmethod
    async def _assert_action_items_done_for_stage(tenant_id: int, report_id: int, stage_key: str) -> None:
        disc_map = {
            "d3_containment": "d3_containment",
            "d5_corrective_action": "d5_corrective",
            "d6_implement_result": "d6_verification",
        }
        disc = disc_map.get(stage_key)
        if not disc:
            return
        items = await Quality8DActionItem.filter(
            tenant_id=tenant_id, report_id=report_id, discipline=disc
        ).exclude(status="cancelled")
        if not items:
            return
        if any(i.status == "open" for i in items):
            raise BusinessLogicError("请先完成本阶段全部行动项后再提交")

    @staticmethod
    async def _assert_action_items_verified_for_stage(tenant_id: int, report_id: int, stage_key: str) -> None:
        disc_map = {
            "d3_containment": "d3_containment",
            "d5_corrective_action": "d5_corrective",
            "d6_implement_result": "d6_verification",
        }
        disc = disc_map.get(stage_key)
        if not disc:
            return
        items = await Quality8DActionItem.filter(
            tenant_id=tenant_id, report_id=report_id, discipline=disc
        ).exclude(status="cancelled")
        if not items:
            return
        if any(i.status != "verified" for i in items):
            raise BusinessLogicError("请先验证本阶段全部行动项后再确认")

    @staticmethod
    async def _create_assignee_task(
        tenant_id: int,
        submitter_id: int,
        assignee_id: int,
        report: Quality8DReport,
        stage_key: str,
        due_date,
    ) -> None:
        if assignee_id == submitter_id:
            return
        process = await ApprovalProcess.filter(tenant_id=tenant_id, code=_PERSONAL_TASK_PROCESS_CODE).first()
        if not process:
            process = await ApprovalProcess.create(
                tenant_id=tenant_id,
                name="个人任务",
                code=_PERSONAL_TASK_PROCESS_CODE,
                description="8D 阶段指派待办",
                nodes=[],
                config={"is_personal": True},
                is_active=True,
            )
        label = _8D_STAGE_LABELS.get(stage_key, stage_key)
        path = EightDCollaborationService._workbench_path(report.id, stage_key)
        inst = await ApprovalInstance.create(
            tenant_id=tenant_id,
            process=process,
            title=f"8D {report.report_code} {label}",
            content=f"请在截止前完成阶段作业：{report.title}",
            remind_at=due_date,
            data={
                "is_personal": True,
                "eight_d_report_id": report.id,
                "stage_key": stage_key,
                "detail_path": path,
            },
            status="pending",
            submitter_id=submitter_id,
            current_approver_id=assignee_id,
            submitted_at=resolve_business_datetime(),
        )
        await ApprovalTask.create(
            tenant_id=tenant_id,
            approval_instance=inst,
            node_id="personal_task",
            approver_id=assignee_id,
            status="pending",
        )

    @staticmethod
    async def _send_internal(tenant_id: int, user_id: int, subject: str, content: str, detail_path: str) -> None:
        from core.schemas.message_template import SendMessageRequest
        from core.services.messaging.message_service import MessageService

        try:
            req = SendMessageRequest(
                type="internal",
                recipient=str(user_id),
                subject=subject,
                content=content,
                variables={"detail_path": detail_path, "message_category": "process"},
            )
            await MessageService.send_message(tenant_id, req)
        except Exception as exc:
            logger.error("8D 站内信失败 tenant={} user={}: {}", tenant_id, user_id, exc)

    @staticmethod
    async def _notify_assignee(
        tenant_id: int,
        report: Quality8DReport,
        stage_key: str,
        assignee_id: int,
        assignee_name: Optional[str],
    ) -> None:
        label = _8D_STAGE_LABELS.get(stage_key, stage_key)
        path = EightDCollaborationService._workbench_path(report.id, stage_key)
        await EightDCollaborationService._send_internal(
            tenant_id,
            assignee_id,
            f"8D 阶段指派 {report.report_code}",
            f"您已被指派为「{label}」负责人：{report.title}",
            path,
        )

    @staticmethod
    async def _notify_champion_stage_submitted(tenant_id: int, report: Quality8DReport, stage_key: str) -> None:
        if not report.owner_id:
            return
        label = _8D_STAGE_LABELS.get(stage_key, stage_key)
        path = EightDCollaborationService._workbench_path(report.id, stage_key)
        await EightDCollaborationService._send_internal(
            tenant_id,
            report.owner_id,
            f"8D 阶段待确认 {report.report_code}",
            f"「{label}」已提交，请确认：{report.title}",
            path,
        )

    @staticmethod
    async def _notify_stage_rejected(
        tenant_id: int,
        report: Quality8DReport,
        stage_key: str,
        assignee_id: int,
        reason: str,
    ) -> None:
        label = _8D_STAGE_LABELS.get(stage_key, stage_key)
        path = EightDCollaborationService._workbench_path(report.id, stage_key)
        await EightDCollaborationService._send_internal(
            tenant_id,
            assignee_id,
            f"8D 阶段已驳回 {report.report_code}",
            f"「{label}」需修改：{reason}",
            path,
        )

    @staticmethod
    async def _notify_action_assigned(tenant_id: int, report: Quality8DReport, item: Quality8DActionItem) -> None:
        if not item.assignee_user_id:
            return
        path = EightDCollaborationService._workbench_path(report.id, _DISCIPLINE_TO_STAGE[item.discipline])
        await EightDCollaborationService._send_internal(
            tenant_id,
            item.assignee_user_id,
            f"8D 行动项 {report.report_code}",
            f"行动项「{item.title}」待处理：{report.title}",
            path,
        )

    @staticmethod
    def action_items_for_print(tenant_id: int, report_id: int) -> Dict:
        """同步上下文外由 print_service await 调用。"""
        return {}
