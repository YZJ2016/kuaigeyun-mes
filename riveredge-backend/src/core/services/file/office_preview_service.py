"""
Office 文档高级预览：LibreOffice 无头转 PDF（Word/PPT）。

Excel（xls/xlsx）不走本服务，由前端 Univer Sheet 预览。
有 soffice/libreoffice 时由 FilePreviewService 对 Word/PPT 返回 preview_mode=advanced；
未安装时回落简易预览（前端 react-doc-viewer）。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from infra.config.infra_config import infra_settings as settings


_OFFICE_EXTENSIONS = frozenset({
    "doc", "docx", "ppt", "pptx", "odt", "odp",
})

_OFFICE_MIMES = frozenset({
    "application/msword",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.presentation",
})

_CONVERT_TIMEOUT_SEC = 120
_convert_lock = asyncio.Lock()
_soffice_cache: Optional[str] = None
_soffice_resolved = False


class OfficePreviewService:
    """LibreOffice → PDF 缓存与转换。"""

    CACHE_DIR_NAME = "office-preview"

    @staticmethod
    def is_office_document(
        file_type: Optional[str] = None,
        file_extension: Optional[str] = None,
    ) -> bool:
        ext = (file_extension or "").strip().lower().lstrip(".")
        if ext in _OFFICE_EXTENSIONS:
            return True
        mime = (file_type or "").strip().lower()
        if mime in _OFFICE_MIMES:
            return True
        if "wordprocessingml" in mime or "presentationml" in mime:
            return True
        if mime in ("application/msword", "application/vnd.ms-powerpoint"):
            return True
        return False

    @staticmethod
    def resolve_soffice_binary() -> Optional[str]:
        global _soffice_cache, _soffice_resolved
        if _soffice_resolved:
            return _soffice_cache

        candidates: list[str] = []
        for name in ("soffice", "libreoffice"):
            found = shutil.which(name)
            if found:
                candidates.append(found)

        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        candidates.extend(
            [
                "/usr/bin/soffice",
                "/usr/bin/libreoffice",
                "/usr/lib/libreoffice/program/soffice",
                os.path.join(program_files, "LibreOffice", "program", "soffice.exe"),
                os.path.join(program_files_x86, "LibreOffice", "program", "soffice.exe"),
            ]
        )

        for path in candidates:
            if path and os.path.isfile(path) and os.access(path, os.X_OK if os.name != "nt" else os.F_OK):
                _soffice_cache = path
                _soffice_resolved = True
                return _soffice_cache

        _soffice_cache = None
        _soffice_resolved = True
        return None

    @classmethod
    def is_available(cls) -> bool:
        return cls.resolve_soffice_binary() is not None

    @classmethod
    def cache_dir(cls) -> str:
        upload = getattr(settings, "FILE_UPLOAD_DIR", "./uploads")
        path = os.path.join(upload, cls.CACHE_DIR_NAME)
        os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def cache_pdf_path(cls, file_uuid: str, stamp: str) -> str:
        safe_uuid = str(file_uuid).replace("/", "_")
        safe_stamp = "".join(c for c in stamp if c.isalnum() or c in ("-", "_"))[:64] or "0"
        return os.path.join(cls.cache_dir(), f"{safe_uuid}_{safe_stamp}.pdf")

    @staticmethod
    def source_stamp(file_row: Any) -> str:
        updated = getattr(file_row, "updated_at", None) or getattr(file_row, "created_at", None)
        if updated is not None and hasattr(updated, "timestamp"):
            return str(int(updated.timestamp()))
        size = getattr(file_row, "file_size", None) or 0
        return f"s{size}"

    @classmethod
    def _convert_sync(
        cls,
        soffice: str,
        source_bytes: bytes,
        source_ext: str,
        out_pdf: str,
    ) -> None:
        ext = (source_ext or "bin").lstrip(".").lower() or "bin"
        with tempfile.TemporaryDirectory(prefix="office-preview-") as tmp:
            tmp_dir = Path(tmp)
            src_path = tmp_dir / f"source.{ext}"
            src_path.write_bytes(source_bytes)
            out_dir = tmp_dir / "out"
            out_dir.mkdir()
            profile_dir = tmp_dir / "profile"
            profile_dir.mkdir()
            # 独立 UserInstallation，避免多进程争用默认 profile
            user_install = Path(profile_dir).as_uri()
            cmd = [
                soffice,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--norestore",
                f"-env:UserInstallation={user_install}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(src_path),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=_CONVERT_TIMEOUT_SEC,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                raise RuntimeError(f"LibreOffice 转换超时（{_CONVERT_TIMEOUT_SEC}s）") from e

            if proc.returncode != 0:
                stderr = (proc.stderr or b"").decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"LibreOffice 转换失败: {stderr or proc.returncode}")

            pdfs = list(out_dir.glob("*.pdf"))
            if not pdfs:
                raise RuntimeError("LibreOffice 未产出 PDF")
            os.makedirs(os.path.dirname(out_pdf) or ".", exist_ok=True)
            shutil.copyfile(str(pdfs[0]), out_pdf)

    @classmethod
    async def ensure_pdf_bytes(
        cls,
        *,
        file_uuid: str,
        file_row: Any,
        source_bytes: bytes,
        file_extension: Optional[str],
    ) -> bytes:
        soffice = cls.resolve_soffice_binary()
        if not soffice:
            raise RuntimeError("未安装 LibreOffice（soffice）")

        stamp = cls.source_stamp(file_row)
        pdf_path = cls.cache_pdf_path(file_uuid, stamp)
        if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
            with open(pdf_path, "rb") as f:
                return f.read()

        # 清理同 uuid 旧缓存
        safe_uuid = str(file_uuid).replace("/", "_")
        for old in Path(cls.cache_dir()).glob(f"{safe_uuid}_*.pdf"):
            if str(old) != pdf_path:
                try:
                    old.unlink(missing_ok=True)
                except OSError:
                    pass

        ext = (file_extension or "").strip().lstrip(".") or "bin"
        async with _convert_lock:
            if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
                with open(pdf_path, "rb") as f:
                    return f.read()
            logger.info(f"Office 高级预览转换: uuid={file_uuid} ext={ext}")
            await asyncio.to_thread(
                cls._convert_sync,
                soffice,
                source_bytes,
                ext,
                pdf_path,
            )
        with open(pdf_path, "rb") as f:
            return f.read()
