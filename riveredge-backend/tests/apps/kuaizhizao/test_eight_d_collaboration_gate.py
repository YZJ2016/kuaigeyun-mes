"""8D 协同门禁（legacy vs collaborative）。"""

import pytest

from apps.kuaizhizao.models.quality_8d_report import Quality8DReport
from apps.kuaizhizao.services.document_action_policy.eight_d_report import derive_eight_d_report_capabilities
from apps.kuaizhizao.services.eight_d_collaboration_service import (
    EightDCollaborationGate,
    EightDCollaborationService,
)


def test_legacy_report_transition_when_stage_html_filled():
    report = Quality8DReport(
        id=1,
        tenant_id=1,
        report_code="8D001",
        title="t",
        status="d0_prepare",
        coordination_mode="legacy",
        d0_prepare="<p>ok</p>",
    )
    caps = derive_eight_d_report_capabilities(report)
    assert caps.transition.allowed is True


def test_collaborative_blocks_transition_until_stage_approved():
    report = Quality8DReport(
        id=1,
        tenant_id=1,
        report_code="8D001",
        title="t",
        status="d0_prepare",
        coordination_mode="collaborative",
        d0_prepare="<p>ok</p>",
    )
    report._eight_d_gate = EightDCollaborationGate(  # noqa: SLF001
        current_stage_approved=False,
        reason="eight_d_report.transition.stage_not_approved",
    )
    caps = derive_eight_d_report_capabilities(report)
    assert caps.transition.allowed is False
    assert caps.transition.reason == "eight_d_report.transition.stage_not_approved"


@pytest.mark.asyncio
async def test_collaborative_champion_bypasses_transition_gate_without_approval():
    report = Quality8DReport(
        id=1,
        tenant_id=1,
        report_code="8D001",
        title="t",
        status="d0_prepare",
        coordination_mode="collaborative",
        d0_prepare="<p>ok</p>",
        owner_id=42,
    )
    gate = await EightDCollaborationService.transition_gate(1, report, actor_user_id=42)
    assert gate.current_stage_approved is True
    assert gate.reason is None
    report._eight_d_gate = gate  # noqa: SLF001
    caps = derive_eight_d_report_capabilities(report)
    assert caps.transition.allowed is True
