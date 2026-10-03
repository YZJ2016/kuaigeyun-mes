"""绩效排班：加班/临时调整适用范围。"""

from typing import Literal, Optional, Tuple

PerformanceScopeType = Literal["plant", "department", "employee"]


def validate_scope_ids(
    scope_type: str,
    *,
    department_id: Optional[int],
    employee_id: Optional[int],
) -> None:
    st = (scope_type or "plant").strip().lower()
    if st == "plant":
        if department_id is not None or employee_id is not None:
            raise ValueError("整厂范围不可指定部门或人员")
        return
    if st == "department":
        if not department_id:
            raise ValueError("按部门范围须指定 departmentId")
        if employee_id is not None:
            raise ValueError("按部门范围不可指定 employeeId")
        return
    if st == "employee":
        if not employee_id:
            raise ValueError("按人员范围须指定 employeeId")
        return
    raise ValueError("scopeType 须为 plant、department 或 employee")


def scope_applies_to_row(
    scope_type: str,
    *,
    row_department_id: Optional[int],
    row_employee_id: Optional[int],
    viewer_employee_id: Optional[int],
    viewer_department_id: Optional[int],
) -> bool:
    """viewer 为空时仅整厂记录参与厂级合并；有 viewer 时叠加部门/人员。"""
    st = (scope_type or "plant").strip().lower()
    if st == "plant":
        return True
    if viewer_employee_id is None:
        return False
    if st == "department":
        if row_department_id is None or viewer_department_id is None:
            return False
        return int(row_department_id) == int(viewer_department_id)
    if st == "employee":
        if row_employee_id is None:
            return False
        return int(row_employee_id) == int(viewer_employee_id)
    return False


def normalized_scope_type(scope_type: Optional[str]) -> str:
    st = (scope_type or "plant").strip().lower()
    if st in ("plant", "department", "employee"):
        return st
    return "plant"
