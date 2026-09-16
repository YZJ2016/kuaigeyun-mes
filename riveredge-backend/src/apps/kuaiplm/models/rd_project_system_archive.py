"""研发项目体系归档八类（R-01 #70）。"""

from tortoise import fields

from core.models.base import BaseModel
from apps.kuaiplm.constants.rd_project_system_archive import (
    RdSystemArchiveAcceptanceStatus,
    RdSystemArchiveFillStatus,
)


class RdProjectSystemArchiveItem(BaseModel):
    """按项目预置的体系归档八类条目。"""

    tenant_id = fields.IntField(description="租户ID")
    project_id = fields.IntField(description="项目ID")
    archive_type_code = fields.CharField(max_length=50, description="归档类型编码")
    archive_type_name = fields.CharField(max_length=100, description="归档类型名称快照")
    sort_order = fields.IntField(default=0, description="排序")
    fill_status = fields.CharField(
        max_length=30,
        default=RdSystemArchiveFillStatus.EMPTY.value,
        description="empty/uploaded/linked/missing_marked",
    )
    file_uuid = fields.CharField(max_length=36, null=True, description="上传文件 UUID")
    file_name = fields.CharField(max_length=200, null=True, description="文件名")
    file_url = fields.CharField(max_length=500, null=True, description="文件 URL")
    linked_target_type = fields.CharField(max_length=50, null=True, description="关联目标类型")
    linked_target_id = fields.IntField(null=True, description="关联目标 ID")
    linked_target_uuid = fields.CharField(max_length=36, null=True, description="关联目标 UUID")
    linked_target_code = fields.CharField(max_length=100, null=True, description="关联目标编码")
    linked_target_name = fields.CharField(max_length=200, null=True, description="关联目标名称")
    acceptance_status = fields.CharField(
        max_length=30,
        default=RdSystemArchiveAcceptanceStatus.NONE.value,
        description="none/pending/accepted/rejected",
    )
    acceptance_notes = fields.TextField(null=True, description="验收备注")
    accepted_at = fields.DatetimeField(null=True, description="验收时间")
    accepted_by = fields.IntField(null=True, description="验收人")
    accepted_by_name = fields.CharField(max_length=100, null=True, description="验收人姓名")
    missing_notes = fields.TextField(null=True, description="缺项说明")
    missing_marked_at = fields.DatetimeField(null=True, description="标记缺项时间")
    missing_marked_by = fields.IntField(null=True, description="标记缺项人")
    missing_marked_by_name = fields.CharField(max_length=100, null=True, description="标记缺项人姓名")
    notes = fields.TextField(null=True, description="备注")
    updated_by = fields.IntField(null=True, description="更新人")
    updated_by_name = fields.CharField(max_length=100, null=True, description="更新人姓名")

    class Meta:
        table = "apps_kuaiplm_rd_project_system_archive_items"
        table_description = "快研发 - 项目体系归档八类"
        unique_together = (("tenant_id", "project_id", "archive_type_code"),)
        indexes = [
            ("tenant_id", "project_id"),
            ("tenant_id", "fill_status"),
            ("tenant_id", "acceptance_status"),
        ]
