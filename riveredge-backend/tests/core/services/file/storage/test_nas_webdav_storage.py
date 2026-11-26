"""NAS WebDAV 存储路径与配置校验。"""

import pytest

from core.services.file.storage.nas_webdav_storage import (
    NasWebDavStorage,
    _NAS_WEBDAV_WRITE_PROBE_KEY,
    _parse_content_range_total,
    _parse_dav_getcontentlength,
    build_nas_webdav_relative_key,
)
from infra.exceptions.exceptions import ValidationError


def test_nas_webdav_write_probe_matches_upload_depth():
    parts = _NAS_WEBDAV_WRITE_PROBE_KEY.split("/")
    assert len(parts) >= 4
    assert parts[0] == "_riveredge_probe"


def test_build_nas_webdav_relative_key_root_and_key():
    assert build_nas_webdav_relative_key("/riveredge", "1/2026/11/uuid.bin") == (
        "riveredge/1/2026/11/uuid.bin"
    )
    assert build_nas_webdav_relative_key("", "1/2026/11/uuid.bin") == "1/2026/11/uuid.bin"
    assert build_nas_webdav_relative_key("riveredge", "") == "riveredge"


def test_nas_webdav_object_href_encodes_segments():
    storage = NasWebDavStorage(
        {
            "base_url": "https://nas.example:5006/dav",
            "username": "erp",
            "password": "secret",
            "root_path": "/files",
        }
    )
    href = storage.object_href("10/2026/11/测试.pdf")
    assert href.startswith("https://nas.example:5006/dav/")
    assert "%E6%B5%8B%E8%AF%95" in href


def test_parse_dav_getcontentlength_from_propfind():
    xml = (
        '<?xml version="1.0"?>'
        '<d:multistatus xmlns:d="DAV:">'
        '<d:response><d:propstat><d:prop>'
        "<d:getcontentlength>27</d:getcontentlength>"
        "</d:prop></d:propstat></d:response></d:multistatus>"
    )
    assert _parse_dav_getcontentlength(xml) == 27


def test_parse_content_range_total():
    assert _parse_content_range_total("bytes 0-0/1048576") == 1048576
    assert _parse_content_range_total("bytes */*") is None


def test_nas_webdav_requires_credentials():
    with pytest.raises(ValidationError):
        NasWebDavStorage(
            {
                "base_url": "https://nas.example:5006/",
                "username": "",
                "password": "x",
                "root_path": "/",
            }
        )


def test_nas_webdav_defaults_verify_ssl_off():
    storage = NasWebDavStorage(
        {
            "base_url": "https://nas.example:5006/dav",
            "username": "erp",
            "password": "secret",
            "root_path": "/",
        }
    )
    assert storage.verify_ssl is False
    storage_on = NasWebDavStorage(
        {
            "base_url": "https://nas.example:5006/dav",
            "username": "erp",
            "password": "secret",
            "verify_ssl": True,
        }
    )
    assert storage_on.verify_ssl is True


def test_build_nas_webdav_relative_key_rejects_path_traversal():
    for bad in ("../etc/passwd", "1/2026/../secret.bin", "./foo", "a/./b"):
        with pytest.raises(ValidationError):
            build_nas_webdav_relative_key("/riveredge", bad)
    with pytest.raises(ValidationError):
        build_nas_webdav_relative_key("/riveredge/../escape", "1/a.bin")


def test_nas_webdav_rejects_url_userinfo():
    with pytest.raises(ValidationError):
        NasWebDavStorage(
            {
                "base_url": "https://user:pass@nas.example:5006/dav",
                "username": "erp",
                "password": "secret",
            }
        )


@pytest.mark.asyncio
async def test_nas_webdav_put_file_missing_does_not_leak_local_path(tmp_path):
    storage = NasWebDavStorage(
        {
            "base_url": "https://nas.example:5006/dav",
            "username": "erp",
            "password": "secret",
        }
    )
    missing_path = str(tmp_path / "very_secret_local_dir" / "missing.bin")
    with pytest.raises(ValidationError) as exc_info:
        await storage.put_file(missing_path, "1/2026/11/a.bin")
    assert "very_secret_local_dir" not in str(exc_info.value)
    assert missing_path not in str(exc_info.value)
