from types import SimpleNamespace

import pytest

from apps.kuaiplm.utils.mold_sample_order_capabilities import (
    compute_mold_sample_order_capabilities,
    mold_sample_file_ready,
    validate_mold_sample_file_on_submit,
)
from infra.exceptions.exceptions import ValidationError


def test_file_ready():
    row = SimpleNamespace(file_uuid="abc")
    assert mold_sample_file_ready(row)
    row.file_uuid = ""
    assert not mold_sample_file_ready(row)


def test_validate_submit():
    validate_mold_sample_file_on_submit(SimpleNamespace(file_uuid="x"))
    with pytest.raises(ValidationError):
        validate_mold_sample_file_on_submit(SimpleNamespace(file_uuid=""))


def test_capabilities_flow():
    row = SimpleNamespace(
        file_uuid="f",
        status="draft",
        submitted_at=None,
        approved_at=None,
        sealed_at=None,
        archived_at=None,
    )
    caps = compute_mold_sample_order_capabilities(row)
    assert caps["file_uploaded"]
    assert not caps["approved"]

    row.status = "pending"
    row.submitted_at = object()
    caps = compute_mold_sample_order_capabilities(row)
    assert caps["submitted"]

    row.status = "approved"
    row.approved_at = object()
    caps = compute_mold_sample_order_capabilities(row)
    assert caps["approved"]

    row.status = "sealed"
    row.sealed_at = object()
    caps = compute_mold_sample_order_capabilities(row)
    assert caps["sealed"]

    row.status = "archived"
    row.archived_at = object()
    caps = compute_mold_sample_order_capabilities(row)
    assert caps["archived"]
