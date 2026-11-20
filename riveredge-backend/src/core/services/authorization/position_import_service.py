"""岗位批量导入（金蝶岗位手工维护）。"""

from __future__ import annotations

from typing import Any, Dict, List

from core.models.department import Department
from core.models.position import Position
from core.utils.model_audit import load_audit_fields_for_create
from infra.exceptions.exceptions import ValidationError


class PositionImportService:
    @staticmethod
    async def import_positions_from_data(
        tenant_id: int,
        data: List[List[Any]],
        current_user_id: int,
    ) -> Dict[str, Any]:
        if not data or len(data) < 2:
            raise ValidationError("导入数据格式错误：至少需要表头和示例数据行")

        headers = [str(cell).strip() if cell is not None else "" for cell in data[0]]
        header_map = {
            "岗位名称": "name",
            "*岗位名称": "name",
            "name": "name",
            "*name": "name",
            "岗位代码": "code",
            "code": "code",
            "所属部门": "department",
            "department": "department",
            "启用": "is_active",
            "is_active": "is_active",
        }
        header_index_map: Dict[str, int] = {}
        for idx, header in enumerate(headers):
            if header and header in header_map:
                header_index_map[header_map[header]] = idx
        if "name" not in header_index_map:
            raise ValidationError("缺少必填字段：岗位名称")

        rows = data[2:] if len(data) > 2 else []
        non_empty_rows = [
            (row, idx + 3)
            for idx, row in enumerate(rows)
            if any(cell is not None and str(cell).strip() for cell in row)
        ]
        if not non_empty_rows:
            raise ValidationError("没有可导入的数据行（所有行都为空）")

        create_audit = await load_audit_fields_for_create(tenant_id, current_user_id)
        success_count = 0
        failure_count = 0
        errors: List[Dict[str, Any]] = []

        for row, row_idx in non_empty_rows:
            try:
                def cell(key: str) -> str:
                    col = header_index_map.get(key)
                    if col is None or col >= len(row):
                        return ""
                    return str(row[col] or "").strip()

                name = cell("name")
                if not name:
                    raise ValidationError("岗位名称为空")
                code = cell("code") or None
                dept_name = cell("department")
                department_id = None
                if dept_name:
                    dept = await Department.filter(
                        tenant_id=tenant_id,
                        name=dept_name,
                        deleted_at__isnull=True,
                    ).first()
                    if not dept:
                        dept = await Department.filter(
                            tenant_id=tenant_id,
                            code=dept_name,
                            deleted_at__isnull=True,
                        ).first()
                    if not dept:
                        raise ValidationError(f"所属部门「{dept_name}」不存在")
                    department_id = dept.id

                is_active_raw = cell("is_active")
                is_active = True
                if is_active_raw:
                    is_active = is_active_raw.lower() not in {"否", "0", "false", "禁用", "no", "n"}

                if code:
                    exists = await Position.filter(
                        tenant_id=tenant_id,
                        code=code,
                        deleted_at__isnull=True,
                    ).exists()
                    if exists:
                        raise ValidationError(f"岗位代码「{code}」已存在")

                await Position.create(
                    tenant_id=tenant_id,
                    name=name,
                    code=code,
                    department_id=department_id,
                    is_active=is_active,
                    **create_audit,
                )
                success_count += 1
            except Exception as exc:
                failure_count += 1
                errors.append({"row": row_idx, "error": str(exc)})

        return {
            "success": True,
            "message": "导入完成",
            "total": success_count + failure_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "errors": errors,
        }
