"""KU-AI S3 单测：document_parsers 解析路由 + 失败关闭。

全部内存构造/库级 mock，不扫盘、不落临时文件。覆盖：
- txt/md utf-8 直解；docx/pptx/xlsx/pdf 路由到对应解析包（mock 库层）
- doc/ppt 旧二进制明确拒绝（提示转 docx/pptx）
- 魔数不符 / 空数据 / 抽出空文本 / 未知类型 → ValidationError
"""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.kuaiai.services import document_parsers
from apps.kuaiai.services.document_parsers import extract_text
from infra.exceptions.exceptions import ValidationError


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("placeholder.xml", "<x/>")
    return buf.getvalue()


class TestTextTypes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("ext", ["txt", "md", "markdown"])
    async def test_utf8_text(self, ext):
        result = await extract_text(ext, "你好，世界".encode("utf-8"))
        assert result == "你好，世界"

    @pytest.mark.asyncio
    async def test_gbk_fallback(self):
        """nit：utf-8 解码失败回落 GBK（中文 Windows 纯文本）。"""
        result = await extract_text("txt", "你好，世界".encode("gbk"))
        assert result == "你好，世界"

    @pytest.mark.asyncio
    async def test_text_invalid_utf8_fails(self):
        """utf-8/GBK 均解不了的字节序列仍拒绝（0xFF 非 GBK 合法首字节）。"""
        with pytest.raises(ValidationError):
            await extract_text("txt", b"\xff\xfe\x00bad")


class TestLegacyBinary:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "ext,target", [("doc", "docx"), ("ppt", "pptx")]
    )
    async def test_legacy_rejected(self, ext, target):
        with pytest.raises(ValidationError) as err:
            await extract_text(ext, b"\xd0\xcf\x11\xe0legacy")
        assert ext in str(err.value)
        assert target in str(err.value)


class TestMagicAndEmpty:
    @pytest.mark.asyncio
    async def test_pdf_bad_magic(self):
        with pytest.raises(ValidationError):
            await extract_text("pdf", b"not a pdf at all")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ext", ["docx", "pptx", "xlsx"])
    async def test_zip_types_bad_magic(self, ext):
        with pytest.raises(ValidationError):
            await extract_text(ext, b"\xd0\xcf\x11\xe0ole2")

    @pytest.mark.asyncio
    async def test_empty_data(self):
        with pytest.raises(ValidationError):
            await extract_text("txt", b"")

    @pytest.mark.asyncio
    async def test_blank_text_rejected(self):
        with pytest.raises(ValidationError):
            await extract_text("txt", "   \n\t ".encode("utf-8"))

    @pytest.mark.asyncio
    async def test_unknown_type(self):
        with pytest.raises(ValidationError):
            await extract_text("exe", b"MZ")


class TestRoutedParsers:
    """解析库层 mock：验证路由分发与结果汇总，不测第三方解析正确性。"""

    @pytest.mark.asyncio
    async def test_pdf_routes_to_pypdf(self):
        page = SimpleNamespace(extract_text=lambda: "PDF 文本")
        reader = MagicMock()
        reader.pages = [page]
        with patch("pypdf.PdfReader", return_value=reader):
            result = await extract_text("pdf", b"%PDF-1.4 fake")
        assert "PDF 文本" in result

    @pytest.mark.asyncio
    async def test_pdf_empty_extract_fails(self):
        page = SimpleNamespace(extract_text=lambda: "")
        reader = MagicMock()
        reader.pages = [page]
        with patch("pypdf.PdfReader", return_value=reader):
            with pytest.raises(ValidationError):
                await extract_text("pdf", b"%PDF-1.4 fake")

    @pytest.mark.asyncio
    async def test_docx_routes_to_python_docx(self):
        para = SimpleNamespace(text="段落一")
        document = SimpleNamespace(paragraphs=[para], tables=[])
        with patch("docx.Document", return_value=document):
            result = await extract_text("docx", _zip_bytes())
        assert "段落一" in result

    @pytest.mark.asyncio
    async def test_pptx_routes_to_python_pptx(self):
        shape = SimpleNamespace(
            has_text_frame=True,
            text_frame=SimpleNamespace(text="幻灯片文本"),
        )
        slide = SimpleNamespace(shapes=[shape])
        with patch(
            "pptx.Presentation",
            return_value=SimpleNamespace(slides=[slide]),
        ):
            result = await extract_text("pptx", _zip_bytes())
        assert "幻灯片文本" in result

    @pytest.mark.asyncio
    async def test_xlsx_routes_to_openpyxl(self):
        sheet = MagicMock()
        sheet.iter_rows.return_value = iter([("A1", None, "B1"), (None,)])
        workbook = MagicMock()
        workbook.worksheets = [sheet]
        with patch("openpyxl.load_workbook", return_value=workbook):
            result = await extract_text("xlsx", _zip_bytes())
        assert "A1 B1" in result

    @pytest.mark.asyncio
    async def test_parser_exception_becomes_validation_error(self):
        with patch("pypdf.PdfReader", side_effect=RuntimeError("boom")):
            with pytest.raises(ValidationError):
                await extract_text("pdf", b"%PDF-1.4 fake")

    @pytest.mark.asyncio
    async def test_source_type_case_and_dot(self):
        result = await extract_text(".TXT", "内容".encode("utf-8"))
        assert result == "内容"
