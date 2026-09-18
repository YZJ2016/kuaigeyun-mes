from decimal import Decimal

import pytest

from apps.kuaizhizao.schemas.defect_record import DefectRecordCreateFromInspection
from apps.kuaizhizao.services.defect_record_service import DefectRecordService
from infra.exceptions.exceptions import ValidationError


def _line(qty: str, reason: str = "外观不良", disposition: str = "return") -> DefectRecordCreateFromInspection:
    return DefectRecordCreateFromInspection(
        defect_quantity=Decimal(qty),
        defect_type="appearance",
        defect_reason=reason,
        disposition=disposition,
    )


def test_validate_defect_lines_batch_accepts_split_quantities():
    svc = DefectRecordService()
    total = svc._validate_defect_lines_batch(
        [_line("5"), _line("15", reason="尺寸超差", disposition="quarantine")],
        existing_registered=Decimal("0"),
        unqualified_quantity=Decimal("20"),
        source="incoming",
    )
    assert total == Decimal("20")


def test_validate_defect_lines_batch_rejects_over_budget():
    svc = DefectRecordService()
    with pytest.raises(ValidationError, match="待登记不合格数量"):
        svc._validate_defect_lines_batch(
            [_line("12"), _line("12")],
            existing_registered=Decimal("0"),
            unqualified_quantity=Decimal("20"),
            source="incoming",
        )


def test_assert_defect_quantity_budget_counts_existing_registered():
    DefectRecordService._assert_defect_quantity_budget(
        Decimal("5"),
        existing_registered=Decimal("15"),
        unqualified_quantity=Decimal("20"),
    )
    with pytest.raises(ValidationError, match="待登记不合格数量"):
        DefectRecordService._assert_defect_quantity_budget(
            Decimal("6"),
            existing_registered=Decimal("15"),
            unqualified_quantity=Decimal("20"),
        )
