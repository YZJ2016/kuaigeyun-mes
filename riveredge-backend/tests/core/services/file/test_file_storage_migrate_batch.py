"""文件存储迁移批次上限（NAS WebDAV 小批避免网关超时）。"""

from core.services.file.file_service import (
    LEFTOVER_TIER_UUIDS_PER_BATCH_BY_BACKEND,
    MIGRATE_BATCH_LIMIT_BY_BACKEND,
    _resolve_leftover_tier_batch,
    _resolve_migrate_batch_limit,
)


def test_nas_webdav_migrate_batch_capped():
    assert MIGRATE_BATCH_LIMIT_BY_BACKEND["nas_webdav"] == 4
    assert _resolve_migrate_batch_limit("nas_webdav", 50) == 4
    assert _resolve_migrate_batch_limit("nas_webdav", 2) == 2


def test_cos_migrate_batch_respects_request():
    assert _resolve_migrate_batch_limit("tencent_cos", 50) == 50
    assert _resolve_migrate_batch_limit("minio", 100) == 100


def test_leftover_tier_batch_for_nas():
    assert LEFTOVER_TIER_UUIDS_PER_BATCH_BY_BACKEND["nas_webdav"] == 3
    assert _resolve_leftover_tier_batch("nas_webdav") == 3
    assert _resolve_leftover_tier_batch("minio") >= 10