"""会签型返工单：执行状态跟 review_status，不跟 MES status=draft。"""

from types import SimpleNamespace

from apps.kuaizhizao.constants import DocumentStatus
from apps.kuaizhizao.constants.rework_business_types import REWORK_BUSINESS_MULTI_SIGNOFF
from apps.kuaizhizao.services.document_lifecycle_service import get_rework_order_lifecycle


def test_multi_signoff_committed_shows_submitted_not_draft():
    ro = SimpleNamespace(
        status="draft",
        review_status=DocumentStatus.SUBMITTED.value,
        business_type=REWORK_BUSINESS_MULTI_SIGNOFF,
    )
    lc = get_rework_order_lifecycle(ro)
    assert lc["current_stage_key"] == "committed"
    assert lc["current_stage_name"] == "已提交"
