"""会签编排 v2 多分区门禁（纯对象，无 DB）."""

import pytest
from infra.exceptions.exceptions import ValidationError

from apps.kuaizhizao.constants.rework_signoff_chain import SIGNOFF_FLOW_KEY
from apps.kuaizhizao.constants.rework_signoff_sections import (
    POSITION_REVIEW_SUB_SECTIONS,
    REWORK_EXEC_SUB_SECTIONS,
)
from apps.kuaizhizao.services.rework_signoff_orchestrator import ReworkSignoffOrchestrator


class _Order:
    def __init__(self, extension_payload: dict | None = None) -> None:
        self.extension_payload = extension_payload or {}
        self.id = 1
        self.need_warehouse_in = True


def _orch() -> ReworkSignoffOrchestrator:
    return ReworkSignoffOrchestrator(service=object())


def test_assert_multi_sections_missing_raises():
    order = _Order(
        {
            SIGNOFF_FLOW_KEY: {
                "chain_version": 2,
                "section_done": {"position_review": {"prod_mgr": True}},
            },
        },
    )
    orch = _orch()
    with pytest.raises(ValidationError, match="须完成全部分区填报"):
        orch._assert_multi_sections_done(order, "position_review", POSITION_REVIEW_SUB_SECTIONS)


def test_assert_multi_sections_all_done_passes():
    done = {k: True for k in POSITION_REVIEW_SUB_SECTIONS}
    order = _Order({SIGNOFF_FLOW_KEY: {"chain_version": 2, "section_done": {"position_review": done}}})
    _orch()._assert_multi_sections_done(order, "position_review", POSITION_REVIEW_SUB_SECTIONS)


@pytest.mark.asyncio
async def test_assert_node_ready_rework_exec_requires_fields_and_sections():
    order = _Order(
        {
            "warehouse_confirm_notes": "ok",
            "production_exec_notes": "ok",
            SIGNOFF_FLOW_KEY: {
                "chain_version": 2,
                "section_done": {
                    "rework_exec": {k: True for k in REWORK_EXEC_SUB_SECTIONS},
                },
            },
        },
    )
    orch = _orch()
    with pytest.raises(ValidationError, match="PQC"):
        await orch._assert_node_ready(1, order, "rework_exec")

    order.extension_payload["quality_pqc_exec_notes"] = "done"
    await orch._assert_node_ready(1, order, "rework_exec")