"""
质量改进服务：8D / SPC。

出货检验（OQC）已迁至 oqc_inspection_service（执行语义）；本文件再导出以保持旧 import。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

from tortoise.queryset import Q
from tortoise.transactions import in_transaction

from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.quality_8d_report import Quality8DReport
from apps.kuaizhizao.models.quality_8d_stage_revision import Quality8DStageRevision
from apps.kuaizhizao.models.spc_sample import SPCSample
from apps.kuaizhizao.schemas.quality_improvement import (
    Quality8DCreate,
    Quality8DHistoryEntry,
    Quality8DLifecycleStage,
    Quality8DListResponse,
    Quality8DResponse,
    Quality8DStageRevisionEntry,
    Quality8DStageUnlockRequest,
    Quality8DTransition,
    Quality8DUpdate,
    SPCChartResponse,
    SPCPoint,
    SPCSampleCreate,
    SPCSampleListResponse,
    SPCSampleResponse,
)
from apps.kuaizhizao.services.oqc_inspection_service import OQCInspectionService
from apps.kuaizhizao.services.spc_list_core import apply_spc_sample_list_filters
from core.utils.timezone_utils import resolve_business_datetime, to_api_isoformat
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

__all__ = [
    "VALID_8D_STATUS_FLOW",
    "_8D_STAGE_LABELS",
    "Quality8DService",
    "OQCInspectionService",
    "SPCService",
]

VALID_8D_STATUS_FLOW = [
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
]
_8D_STAGE_LABELS: Dict[str, str] = {
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
_8D_STAGE_REQUIRED_FIELD: Dict[str, str] = {
    "d0_prepare": "d0_prepare",
    "d1_team": "d1_team",
    "d2_problem": "d2_problem",
    "d3_containment": "d3_containment",
    "d4_root_cause": "d4_root_cause",
    "d5_corrective_action": "d5_corrective_action",
    "d6_implement_result": "d6_implement_result",
    "d7_prevent_recurrence": "d7_prevent_recurrence",
    "d8_team_congratulation": "d8_team_congratulation",
}
_HISTORY_LINE_PATTERN = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s*"
    r"(?:(?P<from_status>[a-z0-9_]+)\s*->\s*)?"
    r"(?P<status>[a-z0-9_]+)\s*:\s*(?P<remarks>.*)$"
)

def _build_quick_code(prefix: str) -> str:
    """仅用于无编码规则上下文的临时单号（如 8D）；OQC 须走 OQC_INSPECTION_CODE。"""
    now = resolve_business_datetime()
    return f"{prefix}{now.strftime('%Y%m%d%H%M%S%f')[-12:]}"


class Quality8DService(AppBaseService[Quality8DReport]):
    def __init__(self) -> None:
        super().__init__(Quality8DReport)

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        return (value or "").strip()

    @staticmethod
    def _normalize_stage_html(value: Optional[str]) -> Optional[str]:
        import re

        text = (value or "").strip()
        if not text or text == "<p><br></p>":
            return None
        empty_block = re.compile(r"<p(?:\s[^>]*)?>(?:\s|&nbsp;|<br\s*/?>)*</p>", re.I)
        empty_li = re.compile(r"<li(?:\s[^>]*)?>(?:\s|&nbsp;|<br\s*/?>)*</li>", re.I)
        prev = None
        while prev != text:
            prev = text
            text = empty_block.sub("", text)
            text = empty_li.sub("", text)
        text = text.strip()
        return text or None

    @staticmethod
    def _split_remarks(remarks_text: Optional[str]) -> tuple[str, List[str]]:
        user_lines: List[str] = []
        history_lines: List[str] = []
        for line in (remarks_text or "").splitlines():
            raw = line.strip()
            if not raw:
                continue
            if _HISTORY_LINE_PATTERN.match(raw):
                history_lines.append(raw)
            else:
                user_lines.append(raw)
        return "\n".join(user_lines).strip(), history_lines

    @staticmethod
    def _join_remarks(user_remarks: str, history_lines: List[str]) -> Optional[str]:
        parts: List[str] = []
        if user_remarks.strip():
            parts.append(user_remarks.strip())
        parts.extend(history_lines)
        return "\n".join(parts) if parts else None

    def _infer_previous_status(self, to_status: str) -> Optional[str]:
        try:
            idx = VALID_8D_STATUS_FLOW.index(to_status)
        except ValueError:
            return None
        return VALID_8D_STATUS_FLOW[idx - 1] if idx > 0 else None

    def _current_stage_index(self, status: str) -> int:
        try:
            return VALID_8D_STATUS_FLOW.index(status)
        except ValueError as exc:
            raise BusinessLogicError(f"非法 8D 阶段: {status}") from exc

    def _next_status(self, status: str) -> Optional[str]:
        idx = self._current_stage_index(status)
        return VALID_8D_STATUS_FLOW[idx + 1] if idx < len(VALID_8D_STATUS_FLOW) - 1 else None

    def _build_lifecycle_stages(self, status: str) -> List[Quality8DLifecycleStage]:
        current_idx = self._current_stage_index(status)
        stages: List[Quality8DLifecycleStage] = []
        for idx, key in enumerate(VALID_8D_STATUS_FLOW):
            if idx < current_idx:
                stage_status = "done"
            elif idx == current_idx:
                stage_status = "active"
            else:
                stage_status = "pending"
            stages.append(
                Quality8DLifecycleStage(
                    key=key,
                    label=_8D_STAGE_LABELS.get(key, key),
                    status=stage_status,
                )
            )
        return stages

    def _stage_field_keys(self) -> List[str]:
        return list(_8D_STAGE_REQUIRED_FIELD.values())

    def _is_stage_unlocked(self, row: Quality8DReport, stage_key: str) -> bool:
        unlocks = row.stage_unlocks if isinstance(row.stage_unlocks, dict) else {}
        return stage_key in unlocks

    def _can_edit_stage(self, row: Quality8DReport, stage_key: str) -> bool:
        if stage_key not in _8D_STAGE_REQUIRED_FIELD:
            return False
        if row.status == "closed":
            return self._is_stage_unlocked(row, stage_key)
        current_idx = self._current_stage_index(row.status)
        stage_idx = self._current_stage_index(stage_key)
        if stage_idx < 0:
            return False
        if stage_idx == current_idx:
            return True
        if stage_idx < current_idx:
            return self._is_stage_unlocked(row, stage_key)
        return False

    def _is_completed_stage(self, row: Quality8DReport, stage_key: str) -> bool:
        if stage_key not in _8D_STAGE_REQUIRED_FIELD:
            return False
        if row.status == "closed":
            return True
        try:
            stage_idx = self._current_stage_index(stage_key)
            current_idx = self._current_stage_index(row.status)
        except BusinessLogicError:
            return False
        return stage_idx < current_idx

    async def _next_revision_no(self, tenant_id: int, report_id: int, stage_key: str) -> int:
        latest = (
            await Quality8DStageRevision.filter(
                tenant_id=tenant_id,
                report_id=report_id,
                stage_key=stage_key,
            )
            .order_by("-revision_no")
            .first()
        )
        return (latest.revision_no if latest else 0) + 1

    async def _record_stage_revision(
        self,
        *,
        tenant_id: int,
        report_id: int,
        stage_key: str,
        action: str,
        content: Optional[str],
        change_reason: Optional[str],
        user_id: int,
        user_name: str,
    ) -> Quality8DStageRevision:
        revision_no = await self._next_revision_no(tenant_id, report_id, stage_key)
        return await Quality8DStageRevision.create(
            tenant_id=tenant_id,
            report_id=report_id,
            stage_key=stage_key,
            revision_no=revision_no,
            action=action,
            content=content,
            change_reason=change_reason,
            changed_by=user_id,
            changed_by_name=user_name,
            changed_at=resolve_business_datetime(),
            created_by=user_id,
            created_by_name=user_name,
            updated_by=user_id,
            updated_by_name=user_name,
        )

    @staticmethod
    def _strip_stage_plain_text(value: Optional[str]) -> str:
        if not value:
            return ""
        text = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
        text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = text.replace("&nbsp;", " ")
        return " ".join(text.split()).strip()

    def _prepare_stage_field_changes(
        self, row: Quality8DReport, data: Dict[str, Any]
    ) -> List[tuple[str, str, Optional[str]]]:
        """对比规范化后的正文，仅保留真正有变更的阶段字段。"""
        changes: List[tuple[str, str, Optional[str]]] = []
        for stage_key in self._stage_field_keys():
            if stage_key not in data:
                continue
            normalized_new = self._normalize_stage_html(data.get(stage_key))
            new_value = self._normalize_text(normalized_new)
            old_raw = getattr(row, stage_key, None)
            old_value = self._normalize_text(self._normalize_stage_html(old_raw))
            if new_value == old_value:
                data.pop(stage_key)
                continue
            if self._strip_stage_plain_text(old_raw) == self._strip_stage_plain_text(normalized_new):
                data.pop(stage_key)
                continue
            data[stage_key] = normalized_new
            changes.append((stage_key, old_value, normalized_new))
        return changes

    def _validate_stage_field_updates(self, row: Quality8DReport, changed_stage_keys: List[str]) -> None:
        if not changed_stage_keys:
            return
        for stage_key in changed_stage_keys:
            if not self._can_edit_stage(row, stage_key):
                label = _8D_STAGE_LABELS.get(stage_key, stage_key)
                if self._is_completed_stage(row, stage_key):
                    raise BusinessLogicError(f"阶段 {label} 已完成，请先申请修改后再编辑")
                raise BusinessLogicError(f"阶段 {label} 尚未开放编辑")

    def _validate_closed_report_update(
        self,
        row: Quality8DReport,
        data: Dict[str, Any],
        changed_stage_keys: List[str],
    ) -> None:
        if row.status != "closed":
            return
        allowed = set(self._stage_field_keys()) | {"remarks", "attachments", "verification_result"}
        blocked = set(data.keys()) - allowed
        if blocked:
            raise BusinessLogicError("已关闭的 8D 报告仅可修改已申请解锁的阶段内容")
        self._validate_stage_field_updates(row, changed_stage_keys)

    def _build_response(self, row: Quality8DReport) -> Quality8DResponse:
        base = Quality8DResponse.model_validate(row)
        next_status = self._next_status(row.status)
        suggestions: List[str] = []
        if next_status:
            suggestions.append(f"推进到 {_8D_STAGE_LABELS.get(next_status, next_status)}")
        if row.status != "closed":
            suggestions.append("更新当前阶段内容并保存")
        if row.status == "d8_team_congratulation":
            suggestions.append("填写验证结果后关闭")
        resp = base.model_copy(
            update={
                "lifecycle_stages": self._build_lifecycle_stages(row.status),
                "next_status": next_status,
                "next_step_suggestions": suggestions,
            }
        )
        from apps.kuaizhizao.services.document_action_policy.enricher import (
            enrich_eight_d_report_capabilities_on_response,
        )
        return enrich_eight_d_report_capabilities_on_response(row, resp)

    async def _build_response_enriched(
        self,
        tenant_id: int,
        row: Quality8DReport,
        *,
        viewer_user_id: Optional[int] = None,
    ) -> Quality8DResponse:
        from apps.kuaizhizao.services.eight_d_collaboration_service import EightDCollaborationService

        gate = await EightDCollaborationService.transition_gate(
            tenant_id, row, actor_user_id=viewer_user_id
        )
        setattr(row, "_eight_d_gate", gate)
        resp = self._build_response(row)
        assignments = await EightDCollaborationService.list_assignments(tenant_id, row.id)
        open_count = await EightDCollaborationService.count_open_actions(tenant_id, row.id)
        return resp.model_copy(
            update={
                "stage_assignments": assignments,
                "open_action_items_count": open_count,
            }
        )

    def _validate_stage_completion_before_transition(
        self,
        row: Quality8DReport,
        to_status: str,
        verification_result: Optional[str],
    ) -> None:
        if row.status == "closed":
            raise BusinessLogicError("已关闭的 8D 报告不可再流转")
        expected_next = self._next_status(row.status)
        if expected_next != to_status:
            raise BusinessLogicError(
                f"仅允许按顺序推进到下一阶段：当前 {_8D_STAGE_LABELS.get(row.status, row.status)}，"
                f"下一步应为 {_8D_STAGE_LABELS.get(expected_next or '', expected_next or '-')}"
            )
        required_field = _8D_STAGE_REQUIRED_FIELD.get(row.status)
        if required_field and not self._normalize_text(getattr(row, required_field, None)):
            raise BusinessLogicError(
                f"推进前需先完善当前阶段内容：{_8D_STAGE_LABELS.get(row.status, row.status)}"
            )
        if to_status == "closed":
            resolved_verification = self._normalize_text(verification_result) or self._normalize_text(
                row.verification_result
            )
            if not resolved_verification:
                raise BusinessLogicError("关闭前必须填写验证结果")

    async def _validate_stage_completion_before_transition_async(
        self,
        tenant_id: int,
        row: Quality8DReport,
        to_status: str,
        verification_result: Optional[str],
        *,
        actor_user_id: Optional[int] = None,
    ) -> None:
        self._validate_stage_completion_before_transition(row, to_status, verification_result)
        from apps.kuaizhizao.services.eight_d_collaboration_service import EightDCollaborationService

        if EightDCollaborationService._is_collaborative(row):
            gate = await EightDCollaborationService.transition_gate(
                tenant_id, row, actor_user_id=actor_user_id
            )
            if not gate.current_stage_approved:
                from apps.kuaizhizao.services.document_action_policy.types import CAPABILITY_REASON_MESSAGES

                code = gate.reason or "eight_d_report.transition.stage_not_approved"
                raise BusinessLogicError(CAPABILITY_REASON_MESSAGES.get(code, "当前阶段尚未确认"))
            if not gate.action_items_verified:
                from apps.kuaizhizao.services.document_action_policy.types import CAPABILITY_REASON_MESSAGES

                code = gate.reason or "eight_d_report.transition.actions_not_verified"
                raise BusinessLogicError(CAPABILITY_REASON_MESSAGES.get(code, "行动项尚未全部验证"))

    def _append_transition_history_line(
        self,
        row: Quality8DReport,
        payload: Quality8DTransition,
        old_status: str,
        operator_name: str,
    ) -> None:
        detail = self._normalize_text(payload.remarks)
        if not detail:
            detail = (
                f"{operator_name} 推进至 "
                f"{_8D_STAGE_LABELS.get(payload.to_status, payload.to_status)}"
            )
        ts = to_api_isoformat(resolve_business_datetime())
        line = f"[{ts}] {old_status} -> {payload.to_status}: {detail}"
        user_part, history_lines = self._split_remarks(row.remarks)
        history_lines.append(line)
        row.remarks = self._join_remarks(user_part, history_lines)

    def _parse_history_from_remarks(self, row: Quality8DReport) -> List[Quality8DHistoryEntry]:
        base_tz = row.created_at.tzinfo or timezone.utc

        def _normalize_ts(ts: datetime) -> datetime:
            if ts.tzinfo is None:
                return ts.replace(tzinfo=base_tz)
            return ts.astimezone(base_tz)

        def _sort_key(entry: Quality8DHistoryEntry) -> float:
            ts = entry.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=base_tz)
            return ts.astimezone(timezone.utc).timestamp()

        history: List[Quality8DHistoryEntry] = [
            Quality8DHistoryEntry(
                timestamp=_normalize_ts(row.created_at),
                action="created",
                to_status=VALID_8D_STATUS_FLOW[0],
                remarks="8D 报告创建",
            )
        ]
        remarks_text = row.remarks or ""
        for line in remarks_text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            matched = _HISTORY_LINE_PATTERN.match(raw)
            if not matched:
                continue
            ts_str = matched.group("ts")
            status = matched.group("status")
            detail = matched.group("remarks")
            from_status = matched.group("from_status") or self._infer_previous_status(status)
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = row.updated_at
            ts = _normalize_ts(ts)
            history.append(
                Quality8DHistoryEntry(
                    timestamp=ts,
                    action="transition",
                    from_status=from_status,
                    to_status=status,
                    remarks=detail or None,
                )
            )
        if row.closed_at:
            history.append(
                Quality8DHistoryEntry(
                    timestamp=_normalize_ts(row.closed_at),
                    action="closed",
                    from_status="d8_team_congratulation",
                    to_status="closed",
                    verification_result=row.verification_result,
                )
            )
        history.sort(key=_sort_key)
        return history

    async def create_report(self, tenant_id: int, user_id: int, payload: Quality8DCreate) -> Quality8DResponse:
        report_code = payload.report_code
        if not report_code:
            report_code = _build_quick_code("8D")

        user_info = await self.get_user_info(user_id)
        create_data = payload.model_dump(exclude={"report_code"})
        if not create_data.get("coordination_mode"):
            create_data["coordination_mode"] = "collaborative"
        if not create_data.get("owner_id"):
            create_data["owner_id"] = user_id
            create_data["owner_name"] = user_info["name"]
        report = await Quality8DReport.create(
            tenant_id=tenant_id,
            report_code=report_code,
            created_by=user_id,
            created_by_name=user_info["name"],
            updated_by=user_id,
            updated_by_name=user_info["name"],
            **create_data,
        )
        from apps.kuaizhizao.services.eight_d_collaboration_service import EightDCollaborationService

        await EightDCollaborationService.bootstrap_on_create(
            tenant_id,
            report,
            champion_user_id=user_id,
            champion_name=user_info["name"],
        )
        return await self._build_response_enriched(tenant_id, report, viewer_user_id=user_id)

    async def list_reports(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        owner_id: Optional[int] = None,
        overdue_only: bool = False,
        my_stage_pending: bool = False,
        my_action_pending: bool = False,
        viewer_user_id: Optional[int] = None,
        keyword: Optional[str] = None,
        order_by: Optional[str] = None,
        created_start_date: Optional[str] = None,
        created_end_date: Optional[str] = None,
        due_start_date: Optional[str] = None,
        due_end_date: Optional[str] = None,
    ) -> Quality8DListResponse:
        from apps.kuaizhizao.services.quality_service import (
            EIGHT_D_REPORT_SORTABLE_FIELDS,
            _apply_quality_inspection_list_filters,
            _parse_optional_api_date,
            _resolve_quality_list_order_by,
        )
        from datetime import time as dt_time

        query = Quality8DReport.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            query = query.filter(status=status)
        if severity:
            query = query.filter(severity=severity)
        if owner_id:
            query = query.filter(owner_id=owner_id)
        if overdue_only:
            query = query.filter(due_date__lt=resolve_business_datetime()).exclude(status="closed")
        if viewer_user_id and (my_stage_pending or my_action_pending):
            from apps.kuaizhizao.services.eight_d_collaboration_service import EightDCollaborationService

            ids: set[int] = set()
            if my_stage_pending:
                ids |= await EightDCollaborationService.filter_report_ids_my_stage_pending(
                    tenant_id, viewer_user_id
                )
            if my_action_pending:
                ids |= await EightDCollaborationService.filter_report_ids_my_action_pending(
                    tenant_id, viewer_user_id
                )
            if not ids:
                return Quality8DListResponse(items=[], total=0)
            query = query.filter(id__in=list(ids))
        query = _apply_quality_inspection_list_filters(
            query,
            {
                "keyword": keyword,
                "created_start_date": created_start_date,
                "created_end_date": created_end_date,
            },
            keyword_fields=["report_code", "title", "owner_name"],
        )
        due_start = _parse_optional_api_date(due_start_date)
        due_end = _parse_optional_api_date(due_end_date)
        if due_start is not None:
            query = query.filter(due_date__gte=datetime.combine(due_start, dt_time.min))
        if due_end is not None:
            query = query.filter(due_date__lte=datetime.combine(due_end, dt_time.max))
        total = await query.count()
        order_clause = _resolve_quality_list_order_by(
            order_by,
            EIGHT_D_REPORT_SORTABLE_FIELDS,
            "-created_at",
        )
        rows = await query.order_by(order_clause).offset(skip).limit(limit)
        items: List[Quality8DResponse] = []
        for row in rows:
            items.append(
                await self._build_response_enriched(
                    tenant_id, row, viewer_user_id=viewer_user_id
                )
            )
        return Quality8DListResponse(items=items, total=total)

    async def get_report(
        self,
        tenant_id: int,
        report_id: int,
        *,
        viewer_user_id: Optional[int] = None,
    ) -> Quality8DResponse:
        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        return await self._build_response_enriched(tenant_id, row, viewer_user_id=viewer_user_id)

    def _relock_completed_stages(
        self,
        row: Quality8DReport,
        stage_keys: List[str],
        *,
        user_id: int,
        user_name: str,
    ) -> None:
        if not stage_keys:
            return
        unlocks = dict(row.stage_unlocks) if isinstance(row.stage_unlocks, dict) else {}
        relocked: List[str] = []
        for stage_key in stage_keys:
            if stage_key not in unlocks:
                continue
            unlocks.pop(stage_key)
            relocked.append(stage_key)
        if not relocked:
            return
        row.stage_unlocks = unlocks or None
        row.updated_by = user_id
        row.updated_by_name = user_name

    async def update_report(self, tenant_id: int, report_id: int, user_id: int, payload: Quality8DUpdate) -> Quality8DResponse:
        from apps.kuaizhizao.services.document_action_policy.eight_d_report import (
            assert_eight_d_report_capability,
        )

        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        data = payload.model_dump(exclude_unset=True)
        submitted_completed_unlocked = [
            stage_key
            for stage_key in self._stage_field_keys()
            if stage_key in data
            and self._is_completed_stage(row, stage_key)
            and self._is_stage_unlocked(row, stage_key)
        ]
        stage_changes = self._prepare_stage_field_changes(row, data)
        changed_stage_keys = [item[0] for item in stage_changes]
        if row.status == "closed" and changed_stage_keys:
            pass
        else:
            assert_eight_d_report_capability(row, "update")
        if "status" in data and data.get("status") not in (None, row.status):
            raise BusinessLogicError("请通过“推进阶段”接口更新 8D 阶段")
        self._validate_closed_report_update(row, data, changed_stage_keys)
        if row.status != "closed":
            self._validate_stage_field_updates(row, changed_stage_keys)
        from apps.kuaizhizao.services.eight_d_collaboration_service import EightDCollaborationService

        for stage_key in changed_stage_keys:
            await EightDCollaborationService.assert_can_edit_stage_content(
                tenant_id, row, user_id, stage_key
            )
        user_info = await self.get_user_info(user_id)
        if "remarks" in data:
            user_part = self._normalize_text(data.get("remarks"))
            _, history_lines = self._split_remarks(row.remarks)
            data["remarks"] = self._join_remarks(user_part, history_lines)
        if data:
            data["updated_by"] = user_id
            data["updated_by_name"] = user_info["name"]
            await row.update_from_dict(data).save()
            for stage_key, _old_value, new_value in stage_changes:
                await self._record_stage_revision(
                    tenant_id=tenant_id,
                    report_id=report_id,
                    stage_key=stage_key,
                    action="save",
                    content=new_value or None,
                    change_reason=None,
                    user_id=user_id,
                    user_name=user_info["name"],
                )
        if submitted_completed_unlocked:
            self._relock_completed_stages(
                row,
                submitted_completed_unlocked,
                user_id=user_id,
                user_name=user_info["name"],
            )
            await row.save(update_fields=["stage_unlocks", "updated_by", "updated_by_name", "updated_at"])
            for stage_key in submitted_completed_unlocked:
                await self._record_stage_revision(
                    tenant_id=tenant_id,
                    report_id=report_id,
                    stage_key=stage_key,
                    action="edit_complete",
                    content=getattr(row, stage_key, None),
                    change_reason=None,
                    user_id=user_id,
                    user_name=user_info["name"],
                )
        return await self._build_response_enriched(tenant_id, row, viewer_user_id=user_id)

    async def transition(self, tenant_id: int, report_id: int, user_id: int, payload: Quality8DTransition) -> Quality8DResponse:
        from apps.kuaizhizao.services.document_action_policy.eight_d_report import (
            assert_eight_d_report_capability,
        )

        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        if payload.to_status not in VALID_8D_STATUS_FLOW:
            raise BusinessLogicError(f"非法 8D 阶段: {payload.to_status}")
        action = "close" if payload.to_status == "closed" else "transition"
        assert_eight_d_report_capability(row, action)
        await self._validate_stage_completion_before_transition_async(
            tenant_id,
            row,
            payload.to_status,
            payload.verification_result,
            actor_user_id=user_id,
        )
        old_status = row.status
        user_info = await self.get_user_info(user_id)
        required_field = _8D_STAGE_REQUIRED_FIELD.get(old_status)
        if required_field:
            await self._record_stage_revision(
                tenant_id=tenant_id,
                report_id=report_id,
                stage_key=required_field,
                action="transition_snapshot",
                content=getattr(row, required_field, None),
                change_reason=f"推进至 {_8D_STAGE_LABELS.get(payload.to_status, payload.to_status)}",
                user_id=user_id,
                user_name=user_info["name"],
            )
        row.status = payload.to_status
        if payload.to_status == "closed":
            row.closed_at = resolve_business_datetime()
            row.verification_result = self._normalize_text(payload.verification_result) or row.verification_result
        self._append_transition_history_line(row, payload, old_status, user_info["name"])
        row.updated_by = user_id
        row.updated_by_name = user_info["name"]
        await row.save()
        from apps.kuaizhizao.services.eight_d_collaboration_service import EightDCollaborationService

        await EightDCollaborationService.on_report_transition(tenant_id, row, payload.to_status)
        if payload.to_status == "closed":
            await self._close_linked_quality_exception_on_8d_close(
                tenant_id=tenant_id,
                report=row,
                handled_by=user_id,
            )
        resp = await self._build_response_enriched(tenant_id, row, viewer_user_id=user_id)
        return resp.model_copy(
            update={
                "next_step_suggestions": [
                    f"阶段已从 {_8D_STAGE_LABELS.get(old_status, old_status)} 推进到 "
                    f"{_8D_STAGE_LABELS.get(row.status, row.status)}"
                ]
                + resp.next_step_suggestions
            }
        )

    async def _close_linked_quality_exception_on_8d_close(
        self,
        *,
        tenant_id: int,
        report: Quality8DReport,
        handled_by: int,
    ) -> None:
        """8D 关闭时同步关闭关联质量异常（优先主键，其次不合格品台账同检验单）。"""
        from apps.kuaizhizao.services.exception_service import ExceptionService

        svc = ExceptionService()
        remarks = f"[8D 关闭] {report.report_code}"
        verification = self._normalize_text(report.verification_result) or "8D 报告已关闭"
        if report.quality_exception_id:
            await svc.close_open_quality_exception_by_id(
                tenant_id,
                int(report.quality_exception_id),
                handled_by,
                remarks=remarks,
                verification_result=verification,
            )
            return
        if not report.defect_record_id:
            return
        from apps.kuaizhizao.models.defect_record import DefectRecord
        from apps.kuaizhizao.services.defect_record_service import DefectRecordService

        defect = await DefectRecord.get_or_none(
            id=int(report.defect_record_id),
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        )
        if not defect:
            return
        link = DefectRecordService._resolve_linked_inspection(defect)
        if not link:
            return
        source_type, source_id = link
        await svc.close_open_quality_exceptions_for_inspection(
            tenant_id,
            inspection_source_type=source_type,
            inspection_record_id=source_id,
            handled_by=handled_by,
            remarks=remarks,
            verification_result=verification,
        )

    async def delete_report(self, tenant_id: int, report_id: int, user_id: int) -> None:
        from apps.kuaizhizao.services.document_action_policy.eight_d_report import (
            assert_eight_d_report_capability,
        )

        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        assert_eight_d_report_capability(row, "delete")
        row.deleted_at = resolve_business_datetime()
        await row.save(update_fields=["deleted_at"])

    async def get_history(self, tenant_id: int, report_id: int) -> List[Quality8DHistoryEntry]:
        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        return self._parse_history_from_remarks(row)

    async def request_stage_unlock(
        self,
        tenant_id: int,
        report_id: int,
        user_id: int,
        payload: Quality8DStageUnlockRequest,
    ) -> Quality8DResponse:
        from apps.kuaizhizao.services.document_action_policy.eight_d_report import (
            assert_eight_d_report_capability,
        )

        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        if row.status != "closed":
            assert_eight_d_report_capability(row, "update")
        stage_key = self._normalize_text(payload.stage_key)
        reason = self._normalize_text(payload.reason)
        if stage_key not in _8D_STAGE_REQUIRED_FIELD:
            raise BusinessLogicError(f"非法 8D 阶段: {stage_key}")
        if not reason:
            raise BusinessLogicError("请填写修改原因")
        if not self._is_completed_stage(row, stage_key):
            label = _8D_STAGE_LABELS.get(stage_key, stage_key)
            raise BusinessLogicError(f"阶段 {label} 尚未完成，无需申请修改")
        if self._can_edit_stage(row, stage_key):
            label = _8D_STAGE_LABELS.get(stage_key, stage_key)
            raise BusinessLogicError(f"阶段 {label} 已处于可编辑状态")
        user_info = await self.get_user_info(user_id)
        now = resolve_business_datetime()
        unlocks = dict(row.stage_unlocks) if isinstance(row.stage_unlocks, dict) else {}
        unlocks[stage_key] = {
            "unlocked_at": to_api_isoformat(now),
            "unlocked_by": user_id,
            "unlocked_by_name": user_info["name"],
            "reason": reason,
        }
        row.stage_unlocks = unlocks
        row.updated_by = user_id
        row.updated_by_name = user_info["name"]
        await row.save()
        await self._record_stage_revision(
            tenant_id=tenant_id,
            report_id=report_id,
            stage_key=stage_key,
            action="unlock_request",
            content=getattr(row, stage_key, None),
            change_reason=reason,
            user_id=user_id,
            user_name=user_info["name"],
        )
        return await self._build_response_enriched(tenant_id, row, viewer_user_id=user_id)

    async def get_stage_revisions(
        self,
        tenant_id: int,
        report_id: int,
        stage_key: Optional[str] = None,
    ) -> List[Quality8DStageRevisionEntry]:
        row = await Quality8DReport.get_or_none(id=report_id, tenant_id=tenant_id, deleted_at__isnull=True)
        if not row:
            raise NotFoundError("8D 报告不存在")
        query = Quality8DStageRevision.filter(tenant_id=tenant_id, report_id=report_id)
        if stage_key:
            query = query.filter(stage_key=stage_key)
        rows = await query.order_by("-changed_at", "-revision_no")
        return [Quality8DStageRevisionEntry.model_validate(item) for item in rows]


class SPCService(AppBaseService[SPCSample]):
    def __init__(self) -> None:
        super().__init__(SPCSample)

    async def create_sample(self, tenant_id: int, user_id: int, payload: SPCSampleCreate) -> SPCSampleResponse:
        row = await SPCSample.create(
            tenant_id=tenant_id,
            **payload.model_dump(),
        )
        return SPCSampleResponse.model_validate(row)

    async def list_samples(
        self,
        tenant_id: int,
        characteristic_name: Optional[str] = None,
        keyword: Optional[str] = None,
        sample_time_from: Optional[datetime] = None,
        sample_time_to: Optional[datetime] = None,
        order_by: Optional[str] = None,
        skip: int = 0,
        limit: int = 200,
    ) -> SPCSampleListResponse:
        query = SPCSample.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        query, primary_order, secondary_order = apply_spc_sample_list_filters(
            query,
            keyword=keyword,
            characteristic_name=characteristic_name,
            sample_time_from=sample_time_from,
            sample_time_to=sample_time_to,
            order_by=order_by,
        )
        total = await query.count()
        rows = await query.order_by(primary_order, secondary_order).offset(skip).limit(limit)
        return SPCSampleListResponse(
            items=[SPCSampleResponse.model_validate(row) for row in rows],
            total=total,
        )

    async def build_imr_chart(
        self,
        tenant_id: int,
        characteristic_name: str,
        limit: int = 50,
    ) -> SPCChartResponse:
        rows = await SPCSample.filter(
            tenant_id=tenant_id,
            characteristic_name=characteristic_name,
            deleted_at__isnull=True,
        ).order_by("-sample_time").limit(limit)
        points_raw = list(reversed(rows))
        values = [float(row.sample_value) for row in points_raw]
        if not values:
            return SPCChartResponse(
                characteristic_name=characteristic_name,
                chart_type="imr",
                mean=0,
                sigma=0,
                ucl=0,
                lcl=0,
                points=[],
                triggered_summary=[],
            )
        center = mean(values)
        sigma = pstdev(values) if len(values) > 1 else 0
        ucl = center + 3 * sigma
        lcl = center - 3 * sigma

        points: List[SPCPoint] = []
        triggered_summary: List[str] = []
        increasing_count = 1
        decreasing_count = 1
        for idx, row in enumerate(points_raw):
            current = float(row.sample_value)
            rules: List[str] = []
            out_of_control = current > ucl or current < lcl
            if out_of_control:
                rules.append("3sigma_out_of_control")
            if idx > 0:
                prev = float(points_raw[idx - 1].sample_value)
                if current > prev:
                    increasing_count += 1
                    decreasing_count = 1
                elif current < prev:
                    decreasing_count += 1
                    increasing_count = 1
                else:
                    increasing_count = 1
                    decreasing_count = 1
                if increasing_count >= 6:
                    rules.append("six_points_increasing")
                if decreasing_count >= 6:
                    rules.append("six_points_decreasing")
            if rules:
                triggered_summary.extend(rules)
            points.append(
                SPCPoint(
                    sample_time=row.sample_time,
                    sample_value=current,
                    out_of_control=out_of_control,
                    triggered_rules=rules,
                )
            )

        return SPCChartResponse(
            characteristic_name=characteristic_name,
            chart_type="imr",
            mean=center,
            sigma=sigma,
            ucl=ucl,
            lcl=lcl,
            points=points,
            triggered_summary=sorted(set(triggered_summary)),
        )
