from types import SimpleNamespace

from apps.kuaiplm.utils.bom_collab_capabilities import compute_bom_collab_capabilities


def test_bom_collab_capabilities_progression():
    row = SimpleNamespace(
        electronics_status="draft",
        structure_status="draft",
        status="draft",
        approved_at=None,
        entered_at=None,
    )
    caps = compute_bom_collab_capabilities(row, electronics_line_count=2, structure_line_count=0)
    assert caps["electronics_ready"] is True
    assert caps["structure_ready"] is False
    assert caps["approved"] is False

    row.structure_status = "ready"
    row.status = "approved"
    row.approved_at = object()
    caps2 = compute_bom_collab_capabilities(row, electronics_line_count=2, structure_line_count=3)
    assert caps2["structure_ready"] is True
    assert caps2["approved"] is True
    assert caps2["clerk_entered"] is False

    row.status = "entered"
    row.entered_at = object()
    caps3 = compute_bom_collab_capabilities(row, electronics_line_count=2, structure_line_count=3)
    assert caps3["clerk_entered"] is True
