from tortoise import fields

from core.models.base import BaseModel


class MoldProgramSheet(BaseModel):
    class Meta:
        table = "apps_ind_mold_program_sheets"
        table_description = "行业插件 模具程序单"
        app = "models"

    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=50, description="程序单号")
    work_order_id = fields.IntField(description="工单ID")
    work_order_code = fields.CharField(max_length=50, description="工单编码")
    program_name = fields.CharField(max_length=200, description="程序名称")
    program_status = fields.CharField(max_length=20, default="pending", description="pending/programmed")
    nc_file_path = fields.CharField(max_length=500, null=True, description="NC 文件路径")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True)
