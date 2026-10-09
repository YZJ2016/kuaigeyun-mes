"""L53 交付物下发范围常量（不 import 重型 service）。"""

from apps.kuaiplm.constants.rd_deliverable_issue import RD_DELIVERABLE_TYPES_ISSUE_SCOPED


def test_l53_drawing_types_in_issue_scope():
    for code in (
        "drawing_silkscreen",
        "drawing_assembly",
        "drawing_packaging",
        "drawing_pcb_assembly",
    ):
        assert code in RD_DELIVERABLE_TYPES_ISSUE_SCOPED


def test_general_deliverable_not_issue_scoped():
    assert "part_spec" not in RD_DELIVERABLE_TYPES_ISSUE_SCOPED


def test_l57_customer_doc_types_in_issue_scope():
    assert "customer_spec" in RD_DELIVERABLE_TYPES_ISSUE_SCOPED
    assert "customer_approval" in RD_DELIVERABLE_TYPES_ISSUE_SCOPED
