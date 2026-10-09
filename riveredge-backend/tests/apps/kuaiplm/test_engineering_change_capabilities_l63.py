from types import SimpleNamespace

import pytest

from apps.kuaiplm.utils.engineering_change_capabilities import (
    compute_ecn_capabilities,
    ecn_rd_content_ready,
    signoffs_complete,
    validate_ecn_rd_on_submit,
)
from infra.exceptions.exceptions import ValidationError


def test_ecn_rd_content_ready():
    row = SimpleNamespace(
        change_reason="原因",
        change_kind="material",
        extension_payload={"content_before": "A", "content_after": "B"},
    )
    assert ecn_rd_content_ready(row, material_line_count=1)
    assert not ecn_rd_content_ready(row, material_line_count=0)


def test_validate_ecn_rd_on_submit():
    row = SimpleNamespace(
        change_reason="原因",
        change_kind="other",
        extension_payload={},
    )
    validate_ecn_rd_on_submit(row, material_line_count=1)
    with pytest.raises(ValidationError):
        validate_ecn_rd_on_submit(row, material_line_count=0)


def test_signoffs_complete():
    assert not signoffs_complete([])
    assert signoffs_complete([SimpleNamespace(status="signed"), SimpleNamespace(status="skipped")])


def test_compute_ecn_capabilities_flow():
    row = SimpleNamespace(
        change_reason="r",
        change_kind="material",
        extension_payload={"content_before": "a", "content_after": "b"},
        status="pending",
        approved_at=None,
        closed_at=None,
    )
    signs = [SimpleNamespace(status="pending"), SimpleNamespace(status="pending")]
    caps = compute_ecn_capabilities(row, signoffs=signs, material_line_count=2)
    assert caps["rd_ready"] and not caps["signoffs_done"]

    for s in signs:
        s.status = "signed"
    row.status = "erp_pending"
    row.approved_at = object()
    caps2 = compute_ecn_capabilities(row, signoffs=signs, material_line_count=2)
    assert caps2["signoffs_done"] and caps2["approved"]

    row.status = "closed"
    row.closed_at = object()
    caps3 = compute_ecn_capabilities(row, signoffs=signs, material_line_count=2)
    assert caps3["erp_closed"]
