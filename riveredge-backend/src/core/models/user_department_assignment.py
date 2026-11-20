"""用户部门任职（主部门与兼职）。"""

from tortoise import fields

from .base import BaseModel


class UserDepartmentAssignment(BaseModel):
    """用户在某部门的任职关系；主部门与 User.department 保持一致，由服务层维护。"""

    id = fields.IntField(pk=True)
    user_id = fields.IntField(description="用户 ID")
    department_id = fields.IntField(description="部门 ID")
    is_primary = fields.BooleanField(default=False, description="是否主部门")

    class Meta:
        table = "core_user_department_assignments"
        unique_together = (("tenant_id", "user_id", "department_id"),)
        indexes = [
            ("tenant_id", "user_id"),
        ]
