from types import SimpleNamespace

import pytest

from apps.kuaiplm.utils.engineering_change_capabilities import (
    compute_dcr_capabilities,
    compute_engineering_change_capabilities,
    dcr_request_ready,
    validate_dcr_on_submit,
)
from infra.exceptions.exceptions import ValidationError


def _dcr_row(**overrides):
    row = SimpleNamespace(
        change_reason="客户要求改型",
        change_kind="material",
        extension_payload={
            "entry_source": "design_change_request",
            "content_before": "旧",
            "content_after": "新",
            "change_product_type": "整机",
            "change_method": "换料",
        },
        status="draft",
        approved_at=None,
        closed_at=None,
    )
    for k, v in overrides.items():
        if k == "extension_payload":
            row.extension_payload = {**row.extension_payload, **v}
        else:
            setattr(row, k, v)
    return row


def test_dcr_request_ready():
    row = _dcr_row()
    assert dcr_request_ready(row)
    row.extension_payload = {**row.extension_payload, "content_after": ""}
    assert not dcr_request_ready(row)


def test_validate_dcr_on_submit():
    validate_dcr_on_submit(_dcr_row())
    with pytest.raises(ValidationError):
        validate_dcr_on_submit(_dcr_row(change_reason=""))


def test_dcr_capabilities_flow():
    row = _dcr_row()
    caps = compute_dcr_capabilities(row, signoffs=[], material_line_count=0)
    assert caps["is_design_change_request"]
    assert caps["request_ready"]
    assert not caps["approved"]
    assert not caps["issued_to_rd"]

    row.status = "approved"
    row.approved_at = object()
    caps = compute_dcr_capabilities(row, signoffs=[], material_line_count=0)
    assert caps["approved"]

    row.extension_payload = {
        **row.extension_payload,
        "rd_issued_at": "2026-10-08 10:00:00",
    }
    caps = compute_dcr_capabilities(
        row,
        signoffs=[SimpleNamespace(status="pending")],
        material_line_count=0,
    )
    assert caps["issued_to_rd"]
    assert not caps["rd_ready"]


def test_ecn_path_unchanged():
    row = SimpleNamespace(
        change_reason="r",
        change_kind="other",
        extension_payload={"entry_source": "engineering_change"},
        status="pending",
        approved_at=None,
        closed_at=None,
    )
    caps = compute_engineering_change_capabilities(
        row, signoffs=[], material_line_count=1
    )
    assert not caps["is_design_change_request"]
