from types import SimpleNamespace

from apps.kuaiplm.utils.prototype_build_sheet_capabilities import (
    compute_prototype_build_sheet_capabilities,
)


def _base_row(**overrides):
    row = SimpleNamespace(
        status="draft",
        project_requirements="项目要求",
        project_attachments=[],
        electronics_status="ready",
        structure_status="ready",
        electronics_requirements="e",
        structure_requirements="s",
        manufacturing_opinion="",
        quality_opinion="",
        approved_at=None,
        issued_at=None,
        closed_at=None,
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def test_capabilities_draft_all_sections_ready_not_approved():
    row = _base_row()
    caps = compute_prototype_build_sheet_capabilities(row)
    assert caps["project_ready"]
    assert caps["electronics_ready"]
    assert caps["structure_ready"]
    assert not caps["approved"]
    assert not caps["issued"]
    assert not caps["signoffs_done"]


def test_capabilities_approved_requires_three_sections():
    row = _base_row(status="approved", approved_at="2026-10-08")
    caps = compute_prototype_build_sheet_capabilities(row)
    assert caps["approved"]

    row.electronics_status = "pending"
    caps = compute_prototype_build_sheet_capabilities(row)
    assert not caps["approved"]


def test_capabilities_issued_and_signoffs():
    row = _base_row(
        status="issued",
        approved_at="2026-10-08",
        issued_at="2026-10-08",
        manufacturing_opinion="制造意见",
        quality_opinion="质量意见",
    )
    caps = compute_prototype_build_sheet_capabilities(row)
    assert caps["issued"]
    assert caps["signoffs_done"]
    assert not caps["closed"]

    row.status = "closed"
    row.closed_at = "2026-10-08"
    caps = compute_prototype_build_sheet_capabilities(row)
    assert caps["closed"]
