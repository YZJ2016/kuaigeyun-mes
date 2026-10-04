"""
备份下载鉴权服务

与文件预览一致：先通过带 Authorization 的 API 换取短效 download_token，
再由浏览器 / 下载管理器直接流式拉取 zip，避免 JWT 出现在 URL 或 JS blob 缓冲。
"""

from datetime import timedelta
import os
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from loguru import logger

from core.services.system.backup_storage import (
    _is_under_dir,
    resolve_backup_file_path,
    resolve_data_backup_dir,
)
from infra.config.infra_config import infra_settings as settings
from core.utils.timezone_utils import now_utc


class BackupDownloadService:
    TOKEN_SECRET = getattr(settings, "JWT_SECRET_KEY", getattr(settings, "SECRET_KEY", "your-secret-key"))
    TOKEN_EXPIRES_IN = 3600

    @staticmethod
    def generate_download_token(
        backup_uuid: str,
        tenant_id: Optional[int],
        *,
        is_infra_admin: bool = False,
    ) -> str:
        now = now_utc()
        payload = {
            "backup_uuid": backup_uuid,
            "tenant_id": tenant_id,
            "is_infra_admin": bool(is_infra_admin),
            "exp": now + timedelta(seconds=BackupDownloadService.TOKEN_EXPIRES_IN),
            "iat": now,
        }
        return jwt.encode(payload, BackupDownloadService.TOKEN_SECRET, algorithm="HS256")

    @staticmethod
    def verify_download_token(token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                BackupDownloadService.TOKEN_SECRET,
                algorithms=["HS256"],
            )
            return payload
        except JWTError as exc:
            message = str(exc).lower()
            if "expired" in message or "exp" in message:
                raise ValueError("下载链接已过期，请重新点击下载") from exc
            raise ValueError("下载链接无效") from exc

    @staticmethod
    def build_download_url(
        backup_uuid: str,
        tenant_id: Optional[int],
        *,
        is_infra_admin: bool = False,
    ) -> str:
        download_token = BackupDownloadService.generate_download_token(
            backup_uuid, tenant_id, is_infra_admin=is_infra_admin
        )
        # 相对路径走当前页面 origin（与文件预览一致）。拼 BASE_URL 会在局域网 IP /
        # Vite 开发端口与 .env 不一致时变成 ERR_CONNECTION_REFUSED。
        return (
            f"/api/v1/core/data-backups/{backup_uuid}/download"
            f"?download_token={download_token}"
        )

    @staticmethod
    def resolve_backup_file(backup_uuid: str, tenant_id: Optional[int], file_path: str | None) -> tuple[str, str]:
        if not file_path:
            raise ValueError("备份文件不存在")

        abs_path = resolve_backup_file_path(file_path)
        if not abs_path:
            logger.error(
                "备份文件已丢失: backup_uuid={}, stored_path={}",
                backup_uuid,
                file_path,
            )
            raise ValueError("备份文件已丢失")

        backups_dir = resolve_data_backup_dir()
        if not _is_under_dir(abs_path, backups_dir):
            logger.error("备份路径越界: file_path={}, backups_dir={}", abs_path, backups_dir)
            raise ValueError("无效的备份路径")

        filename = os.path.basename(abs_path)
        return abs_path, filename
