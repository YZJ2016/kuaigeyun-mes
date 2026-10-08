"""
工位操作员会话

记录工位终端上经过刷脸/员工码确认的当前操作员会话。
只存凭据 SHA-256 哈希，不存原始凭据、人脸特征或员工码明文。
"""

from tortoise import fields

from core.models.base import BaseModel


class StationOperatorSession(BaseModel):
    """工位操作员会话（绑定租户、终端账号、工位、操作员与确认方式）"""

    class Meta:
        table = "apps_kuaizhizao_station_operator_sessions"
        table_description = "快格轻制造 - 工位操作员会话"
        app = "models"
        indexes = [
            ("tenant_id", "terminal_user_id", "status"),
            ("tenant_id", "credential_hash"),
            ("tenant_id", "workstation_id"),
        ]

    tenant_id = fields.IntField(description="租户ID")
    terminal_user_id = fields.IntField(description="终端登录账号ID")
    workstation_id = fields.IntField(null=True, description="工位ID")
    workstation_name = fields.CharField(max_length=200, null=True, description="工位名称")
    operator_employee_id = fields.IntField(description="操作员员工档案ID（KuaioaEmployeeProfile）")
    operator_user_id = fields.IntField(description="操作员关联系统用户ID")
    operator_name = fields.CharField(max_length=100, description="操作员姓名")
    confirm_method = fields.CharField(max_length=20, description="确认方式 face/employee_code")
    credential_hash = fields.CharField(max_length=64, description="会话凭据 SHA-256 哈希")
    status = fields.CharField(max_length=20, default="active", description="active/closed")
    issued_at = fields.DatetimeField(description="签发时间")
    last_seen_at = fields.DatetimeField(description="最后活动时间")
    closed_at = fields.DatetimeField(null=True, description="关闭时间")
    close_reason = fields.CharField(
        max_length=32,
        null=True,
        description="关闭原因 explicit_switch/terminal_logout/replaced/explicit_close",
    )
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
