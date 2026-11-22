"""假期导入：自定义休息制度允许不生成周休。"""

import pytest

from apps.master_data.schemas.performance_schemas import (
    BatchDeleteHolidaysRequest,
    BatchDeleteHolidaysResult,
)
from apps.master_data.services.performance_service import PerformanceService
from infra.exceptions.exceptions import ValidationError


def test_custom_rest_weekdays_may_be_empty():
    assert PerformanceService._resolve_rest_weekdays("custom", None) == []
    assert PerformanceService._resolve_rest_weekdays("custom", []) == []


def test_custom_rest_weekdays_keep_valid_days():
    assert PerformanceService._resolve_rest_weekdays("custom", [6, 6, 0]) == [6, 0]


def test_custom_rest_weekdays_reject_out_of_range():
    with pytest.raises(ValidationError):
        PerformanceService._resolve_rest_weekdays("custom", [7])


def test_preset_rest_modes_ignore_custom_days():
    assert PerformanceService._resolve_rest_weekdays("double", []) == [5, 6]
    assert PerformanceService._resolve_rest_weekdays("single", None) == [6]


def test_batch_delete_request_requires_uuid():
    with pytest.raises(ValueError):
        BatchDeleteHolidaysRequest.model_validate({"uuids": []})


def test_batch_delete_result_aliases():
    result = BatchDeleteHolidaysResult.model_validate(
        {"deleted_count": 2, "failed_count": 1, "failed_items": [{"uuid": "x", "reason": "假期不存在"}]}
    )
    dumped = result.model_dump(by_alias=True)
    assert dumped["deletedCount"] == 2
    assert dumped["failedCount"] == 1
