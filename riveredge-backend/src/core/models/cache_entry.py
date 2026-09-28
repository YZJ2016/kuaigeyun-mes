from tortoise import fields

from .base import BaseModel


class CacheEntry(BaseModel):
    id = fields.IntField(pk=True, description="缓存主键")
    namespace = fields.CharField(max_length=64, description="命名空间")
    key = fields.CharField(max_length=512, description="缓存键")
    value = fields.TextField(description="缓存值（JSON或纯文本）")
    expires_at = fields.DatetimeField(null=True, description="过期时间")

    class Meta:
        table = "core_cache_entries"
        # spec 143：PG 缓存为全局基础设施表（键命名空间自带隔离语义，
        # tenant_id 不参与读写），退出强制隔离
        tenant_isolation = "platform"
        unique_together = [("namespace", "key")]
        indexes = [
            ("namespace", "key"),
            ("expires_at",),
            ("updated_at",),
        ]
