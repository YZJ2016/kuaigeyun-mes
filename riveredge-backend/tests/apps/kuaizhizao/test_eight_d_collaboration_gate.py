"""8D 协同门禁（legacy vs collaborative）。"""

from apps.kuaizhizao.models.quality_8d_report import Quality8DReport
from apps.kuaizhizao.services.document_action_policy.eight_d_report import derive_eight_d_report_capabilities
from apps.kuaizhizao.services.eight_d_collaboration_service import EightDCollaborationGate


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
