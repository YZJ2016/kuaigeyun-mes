"""知识语料上传 .md 须通过公共文件白名单。"""

from types import SimpleNamespace

import pytest

from core.services.file.file_service import FileService


@pytest.mark.asyncio
async def test_markdown_upload_passes_extension_whitelist(monkeypatch):
    async def no_sensitive(*_args, **_kwargs):
        return False

    monkeypatch.setattr(
        "core.services.file.file_service.tenant_has_sensitive_word_control",
        no_sensitive,
    )

    stored: dict = {}

    class _Storage:
        async def put(self, key, data, content_type=None):
            stored["key"] = key
            stored["content_type"] = content_type
            stored["data"] = data

    async def resolve(_tenant_id):
        return _Storage(), {"key_prefix": "", "storage_backend": "local"}

    monkeypatch.setattr(
        "core.services.file.storage.resolve_storage_for_upload",
        resolve,
    )

    async def create_file(**kwargs):
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(FileService, "create_file", create_file)

    saved = await FileService.save_uploaded_file(
        tenant_id=1,
        file_content=b"# title\n",
        original_name="note.md",
    )

    assert saved.file_type == "text/markdown"
    assert stored["content_type"] == "text/markdown"
    assert stored["data"] == b"# title\n"
    assert stored["key"].endswith(".md")
