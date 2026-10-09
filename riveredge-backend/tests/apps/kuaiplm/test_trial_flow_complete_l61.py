from types import SimpleNamespace

import pytest

from apps.kuaiplm.utils.trial_flow_complete_capabilities import (
    complete_trial_content_ready,
    compute_trial_flow_complete_capabilities,
    validate_complete_trial_on_submit,
)
from infra.exceptions.exceptions import ValidationError


def test_complete_trial_content_ready():
    ext = {"trial_reason": "试产", "sample_management": "留样 3 件"}
    assert complete_trial_content_ready(title="T", extension_payload=ext, material_line_count=1)
    assert not complete_trial_content_ready(title="T", extension_payload=ext, material_line_count=0)
    assert not complete_trial_content_ready(
        title="T", extension_payload={"trial_reason": "x"}, material_line_count=1
    )


def test_validate_complete_trial_on_submit():
    validate_complete_trial_on_submit(
        title="试流",
        extension_payload={"trial_reason": "r", "sample_management": "s"},
        material_line_count=2,
    )
    with pytest.raises(ValidationError):
        validate_complete_trial_on_submit(
            title="试流",
            extension_payload={"trial_reason": "r"},
            material_line_count=1,
        )


def test_compute_complete_capabilities_progression():
    row = SimpleNamespace(
        business_type="complete",
        title="整机试流",
        extension_payload={"trial_reason": "r", "sample_management": "s"},
        status="draft",
        submitted_at=None,
        closed_at=None,
    )
    steps = [
        SimpleNamespace(step_key="purchasing", status="pending"),
        SimpleNamespace(step_key="iqc", status="pending"),
        SimpleNamespace(step_key="conclusion_rd", status="pending"),
    ]
    caps = compute_trial_flow_complete_capabilities(row, steps=steps, material_line_count=1)
    assert caps["filled"] is True
    assert caps["dept_approved"] is False
    assert caps["results_done"] is False

    row.status = "in_progress"
    row.submitted_at = object()
    steps[0].status = "done"
    steps[1].status = "done"
    caps2 = compute_trial_flow_complete_capabilities(row, steps=steps, material_line_count=1)
    assert caps2["dept_approved"] is True
    assert caps2["results_done"] is True
    assert caps2["conclusions_done"] is False

    steps[2].status = "done"
    row.status = "closed"
    row.closed_at = object()
    caps3 = compute_trial_flow_complete_capabilities(row, steps=steps, material_line_count=1)
    assert caps3["conclusions_done"] is True
    assert caps3["archived"] is True


def test_non_complete_returns_empty_caps():
    row = SimpleNamespace(business_type="component", title="x")
    assert compute_trial_flow_complete_capabilities(row, steps=[], material_line_count=0) == {}
