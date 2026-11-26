"""生产领料单表头（领用人 / 领用部门）校验。"""

from infra.exceptions.exceptions import ValidationError


def assert_production_picking_picker_and_department(
    *,
    picker_id: int | None,
    pick_department_id: int | None = None,
    pick_department_code: str | None = None,
) -> None:
    if int(picker_id or 0) <= 0:
        raise ValidationError("请选择领用人")
    dept_id = int(pick_department_id or 0)
    code = str(pick_department_code or "").strip()
    if dept_id <= 0 and not code:
        raise ValidationError("请选择领用部门")