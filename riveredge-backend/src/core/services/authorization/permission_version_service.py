"""
权限版本服务
"""

from tortoise.exceptions import IntegrityError

from core.models.permission_version import PermissionVersion


class PermissionVersionService:
    @staticmethod
    async def _resolve_record(tenant_id: int, user_id: int | None) -> PermissionVersion | None:
        """取当前有效记录；若历史重复则保留最高 version 并删除多余行。"""
        rows = (
            await PermissionVersion.filter(tenant_id=tenant_id, user_id=user_id)
            .order_by("-version", "-id")
            .all()
        )
        if not rows:
            return None
        keep = rows[0]
        if len(rows) > 1:
            await PermissionVersion.filter(id__in=[r.id for r in rows[1:]]).delete()
        return keep

    @staticmethod
    async def get_version(tenant_id: int, user_id: int | None = None) -> int:
        record = await PermissionVersionService._resolve_record(tenant_id, user_id)
        if not record:
            return 1
        return record.version

    @staticmethod
    async def bump(tenant_id: int, user_id: int | None = None) -> int:
        record = await PermissionVersionService._resolve_record(tenant_id, user_id)
        if not record:
            try:
                record = await PermissionVersion.create(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    version=2,
                )
                return record.version
            except IntegrityError:
                # 并发创建或唯一索引冲突：再取一次后递增
                record = await PermissionVersionService._resolve_record(tenant_id, user_id)
                if not record:
                    raise
        record.version += 1
        await record.save()
        return record.version
