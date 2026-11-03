"""HTML → PDF via Playwright Chromium (core shared engine)."""

from __future__ import annotations

import asyncio
import base64
import os
import platform
import re
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

_CSS_PAGE_SIZE_RE = re.compile(
    r"@page\s*\{[^}]*?\bsize\s*:\s*"
    r"(?P<w>\d+(?:\.\d+)?(?:mm|cm|in|px))"
    r"\s+"
    r"(?P<h>\d+(?:\.\d+)?(?:mm|cm|in|px))"
    r"(?:\s+(?:portrait|landscape))?\s*;",
    re.IGNORECASE | re.DOTALL,
)

_CSS_PAGE_NAMED_SIZE_RE = re.compile(
    r"@page\s*\{[^}]*?\bsize\s*:\s*"
    r"(?P<name>A3|A4|A5|Letter|Legal)"
    r"(?:\s+(?P<orient>portrait|landscape))?\s*;",
    re.IGNORECASE | re.DOTALL,
)

_NAMED_PAPER_SIZE_MM: dict[str, tuple[float, float]] = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
}


_RELATIVE_ASSET_IN_HTML_RE = re.compile(
    r"(?:\bsrc|\bhref)\s*=\s*[\"']/(?!/)",
    re.IGNORECASE,
)
_RELATIVE_CSS_URL_RE = re.compile(
    r"url\(\s*[\"']?/(?!/)",
    re.IGNORECASE,
)


def should_inject_base_href_for_pdf(html_string: str) -> bool:
    """打印 HTML 已内联 data URL 时不注入 base，避免 Chromium 去拉 BASE_URL 外链。"""
    if not html_string:
        return False
    if _RELATIVE_ASSET_IN_HTML_RE.search(html_string):
        return True
    return _RELATIVE_CSS_URL_RE.search(html_string) is not None


def inject_base_href_for_playwright(html_string: str, base_url: str) -> str:
    if not base_url:
        return html_string
    base = base_url.rstrip("/") + "/"
    if re.search(r"<base\b", html_string, flags=re.IGNORECASE):
        return html_string
    if re.search(r"<head[^>]*>", html_string, flags=re.IGNORECASE):
        return re.sub(
            r"(<head[^>]*>)",
            lambda m: m.group(1) + f'<base href="{base}"/>',
            html_string,
            count=1,
            flags=re.IGNORECASE,
        )
    if re.search(r"<html[^>]*>", html_string, flags=re.IGNORECASE):
        return re.sub(
            r"(<html[^>]*>)",
            lambda m: m.group(1) + f'<head><base href="{base}"/></head>',
            html_string,
            count=1,
            flags=re.IGNORECASE,
        )
    return f'<!DOCTYPE html><html><head><base href="{base}"/></head><body>{html_string}</body></html>'


_DATA_IMAGE_URL_RE = re.compile(
    r"(data:image/(?:png|jpeg|jpg|gif|webp|svg\+xml);base64,)([A-Za-z0-9+/=\s]+)",
    flags=re.IGNORECASE,
)

# 公章/Logo 等 data URL 过大时 Chromium 易在 evaluate/pdf 阶段 Target crashed
_MAX_DATA_IMAGE_B64_CHARS = 120_000
_PRINT_IMAGE_MAX_SIDE_PX = 384
# 1x1 透明 PNG：缩略失败或末次降级时替换，避免原图继续打崩 Chromium
_PLACEHOLDER_DATA_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5W2fQAAAAASUVORK5CYII="
)


def shrink_data_image_url(
    data_url: str,
    *,
    max_side: int = _PRINT_IMAGE_MAX_SIDE_PX,
    max_b64_chars: int = _MAX_DATA_IMAGE_B64_CHARS,
    force: bool = False,
) -> str:
    """将过大的 data:image URL 缩略为 JPEG，避免打印 Chromium 崩溃。

    force 时：RGBA 铺白底转 JPEG；SVG / 解码失败改为占位图（禁止保留原大图）。
    """
    raw = (data_url or "").strip()
    if not raw.lower().startswith("data:image/"):
        return raw
    comma = raw.find(",")
    if comma < 0:
        return _PLACEHOLDER_DATA_IMAGE if force else raw
    header = raw[:comma].lower()
    payload = raw[comma + 1 :].strip()
    if "svg+xml" in header:
        # headless 对内嵌 SVG data URL 不稳定；强制降级为占位，业务图应走 PNG/JPEG
        return _PLACEHOLDER_DATA_IMAGE if force else raw
    try:
        from PIL import Image

        binary = base64.b64decode(payload, validate=False)
        img = Image.open(BytesIO(binary))
        side = max(64, min(int(max_side), 1024))
        oversized_bytes = len(payload) > max_b64_chars
        oversized_pixels = max(img.size) > side
        if not force and not oversized_bytes and not oversized_pixels:
            return raw
        # 打印场景：白底 JPEG 比带透明 PNG 更不易打崩 printToPDF
        if img.mode in ("RGBA", "LA"):
            rgba = img.convert("RGBA")
            rgba.thumbnail((side, side), Image.Resampling.LANCZOS)
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode == "P":
            converted = img.convert("RGBA")
            converted.thumbnail((side, side), Image.Resampling.LANCZOS)
            background = Image.new("RGB", converted.size, (255, 255, 255))
            background.paste(converted, mask=converted.split()[-1])
            img = background
        else:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail((side, side), Image.Resampling.LANCZOS)
        buf = BytesIO()
        quality = 70 if force else 85
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        if force:
            logger.warning("打印 data:image 缩略失败，改用占位图: {}", e)
            return _PLACEHOLDER_DATA_IMAGE
        logger.warning("打印 data:image 缩略失败，保留原图: {}", e)
        return raw


def shrink_oversized_data_images_in_html(
    html_string: str,
    *,
    max_side: int = _PRINT_IMAGE_MAX_SIDE_PX,
    max_b64_chars: int = _MAX_DATA_IMAGE_B64_CHARS,
    force_all: bool = False,
) -> str:
    """压缩 HTML 内 data:image（含 img src、CSS background-image:url(...)）。"""
    if not html_string or "data:image/" not in html_string.lower():
        return html_string

    def _repl(match: re.Match[str]) -> str:
        return shrink_data_image_url(
            match.group(0),
            max_side=max_side,
            max_b64_chars=max_b64_chars,
            force=force_all,
        )

    return _DATA_IMAGE_URL_RE.sub(_repl, html_string)


def replace_all_data_images_with_placeholder(html_string: str) -> str:
    """末次降级：全部内嵌图换成占位，优先保证 PDF 能出。"""
    if not html_string or "data:image/" not in html_string.lower():
        return html_string
    return _DATA_IMAGE_URL_RE.sub(_PLACEHOLDER_DATA_IMAGE, html_string)


def describe_print_html_for_error(html_string: str) -> str:
    """失败诊断：避免一律归因于「图片文件体积」。"""
    if not html_string:
        return "HTML 为空"
    raw = html_string.encode("utf-8")
    lower = html_string.lower()
    data_img = lower.count("data:image/")
    bg_data = lower.count("background-image") + lower.count("background_image")
    return (
        f"HTML 约 {len(raw)} 字节，"
        f"明细行约 {lower.count('<tr')}，"
        f"img 标签约 {lower.count('<img')}，"
        f"内嵌 data:image 约 {data_img} 处，"
        f"背景图样式约 {bg_data} 处"
    )


def wrap_html_document_for_print(html_string: str) -> str:
    """设计器/Jinja 常输出 style+片段；补齐文档壳，避免 headless printToPDF 异常。"""
    text = str(html_string or "")
    if not text.strip():
        return text
    if re.search(r"<html\b", text, flags=re.IGNORECASE):
        if re.search(r"<head\b", text, flags=re.IGNORECASE) and not re.search(
            r"<meta[^>]+charset", text, flags=re.IGNORECASE
        ):
            return re.sub(
                r"(<head[^>]*>)",
                r'\1<meta charset="utf-8"/>',
                text,
                count=1,
                flags=re.IGNORECASE,
            )
        return text
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/></head><body>'
        f"{text}</body></html>"
    )


_PAGE_MARGIN_BOX_RE = re.compile(
    r"@page\s*\{[^{}]*?@(?:top|bottom|left|right)-(?:left|center|right|top|bottom|middle)\s*\{[^}]*\}[^{}]*\}",
    flags=re.IGNORECASE | re.DOTALL,
)
_NESTED_MARGIN_BOX_RE = re.compile(
    r"@(?:top|bottom|left|right)-(?:left|center|right|top|bottom|middle)\s*\{[^}]*\}",
    flags=re.IGNORECASE | re.DOTALL,
)


def strip_chromium_risky_print_margin_boxes(html_string: str) -> str:
    """Chromium printToPDF 对 @page 边距盒页码支持不稳，默认去掉。"""
    if not html_string or "@" not in html_string:
        return html_string
    out = _PAGE_MARGIN_BOX_RE.sub("", html_string)
    # 仍嵌在更大 @page 规则里的边距盒
    return _NESTED_MARGIN_BOX_RE.sub("", out)


def prepare_html_for_playwright_pdf(
    html_string: str,
    *,
    max_side: int = _PRINT_IMAGE_MAX_SIDE_PX,
    max_b64_chars: int = _MAX_DATA_IMAGE_B64_CHARS,
    force_all: bool = False,
    strip_page_margin_boxes: bool = True,
) -> str:
    """打印入 Chromium 前：仅压过大内嵌图；默认去掉 @page 边距盒页码（部分 Chromium 在 emulate_media 崩溃）。"""
    out = shrink_oversized_data_images_in_html(
        html_string,
        max_side=max_side,
        max_b64_chars=max_b64_chars,
        force_all=force_all,
    )
    if strip_page_margin_boxes:
        out = strip_chromium_risky_print_margin_boxes(out)
    return out


def _is_playwright_set_content_timeout(error: BaseException) -> bool:
    msg = str(error) or ""
    low = msg.lower()
    return "set_content" in low and (
        "timeout" in low or 'waiting until "load"' in low or "waiting until 'load'" in low
    )


def _is_playwright_target_crashed(error: BaseException) -> bool:
    """可重试的打印失败（含旧 CDP printToPDF 与 CLI --print-to-pdf）。"""
    msg = str(error) or ""
    low = msg.lower()
    if "target crashed" in low or "page crashed" in low or "target closed" in low:
        return True
    if "printtopdf" in low and "printing failed" in low:
        return True
    if "protocol error" in low and "printtopdf" in low:
        return True
    if "print-to-pdf" in low or "chromium 打印失败" in msg:
        return True
    return False


def parse_css_page_size(html_string: str) -> Optional[Tuple[str, str]]:
    if not html_string:
        return None
    m = _CSS_PAGE_SIZE_RE.search(html_string)
    if m:
        return m.group("w"), m.group("h")
    named = _CSS_PAGE_NAMED_SIZE_RE.search(html_string)
    if not named:
        return None
    name = named.group("name").upper()
    dims = _NAMED_PAPER_SIZE_MM.get(name)
    if not dims:
        return None
    w_mm, h_mm = dims
    orient = (named.group("orient") or "portrait").strip().lower()
    if orient == "landscape":
        w_mm, h_mm = h_mm, w_mm
    return f"{w_mm}mm", f"{h_mm}mm"


def _repo_root() -> Path:
    # riveredge-backend/src/core/services/pdf/playwright_engine.py → 仓根
    return Path(__file__).resolve().parents[5]


_CHROMIUM_EXE_GLOBS = (
    "chromium-*/chrome-win64/chrome.exe",
    "chromium-*/chrome-linux*/chrome",
    "chromium-*/chrome-mac*/Chromium",
    "chromium_headless_shell-*/chrome-win64/headless_shell.exe",
    "chromium_headless_shell-*/chrome-linux*/chrome-headless-shell",
    "chromium_headless_shell-*/chrome-linux*/headless_shell",
)


def _iter_chromium_executables(browsers_dir: Path):
    if not browsers_dir.is_dir():
        return
    try:
        for pattern in _CHROMIUM_EXE_GLOBS:
            for hit in browsers_dir.glob(pattern):
                if hit.is_file():
                    yield hit
    except OSError:
        return


def _chromium_installed_in(browsers_dir: Path) -> bool:
    for _hit in _iter_chromium_executables(browsers_dir):
        return True
    return False


def find_playwright_chromium_executable() -> Optional[str]:
    """只扫 PLAYWRIGHT_BROWSERS_PATH / 默认缓存目录，禁止启动 Playwright 驱动。

    在 Ubuntu 26.04 上，一旦本进程跑过 ``async_playwright()``，随后同二进制的
    ``--print-to-pdf`` 子进程会挂死不出 PDF；因此出稿路径不得 import/启动驱动。
    """
    apply_usable_playwright_browsers_path()
    candidates: list[Path] = []
    env = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if env:
        candidates.append(Path(env))
    candidates.append(_repo_root() / ".playwright-browsers")
    candidates.extend(_default_ms_playwright_dirs())
    seen: set[str] = set()
    for base in candidates:
        key = str(base.resolve()) if base.exists() else str(base)
        if key in seen:
            continue
        seen.add(key)
        for hit in _iter_chromium_executables(base):
            return str(hit.resolve())
    return None


def _default_ms_playwright_dirs() -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []
    if platform.system() == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "ms-playwright")
    dirs.append(home / ".cache" / "ms-playwright")
    return dirs


def apply_writable_playwright_tmpdir() -> None:
    """安装/解压时避免系统 Temp 不可写（Windows EPERM）。"""
    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    base = Path(browsers) if browsers else (_repo_root() / ".playwright-browsers")
    tmp = base / ".tmp"
    try:
        tmp.mkdir(parents=True, exist_ok=True)
        probe = tmp / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return
    os.environ["TEMP"] = str(tmp)
    os.environ["TMP"] = str(tmp)
    os.environ["TMPDIR"] = str(tmp)


def apply_usable_playwright_browsers_path() -> Optional[str]:
    """纠正不可用的 PLAYWRIGHT_BROWSERS_PATH（Cursor sandbox / 跨机 Linux 路径等）。

    优先保留已含 Chromium 的当前值；否则回退仓根 ``.playwright-browsers``、
    本机 ms-playwright 缓存；仍无则清除错误 env，交给 Playwright 默认解析。
    """
    current = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    normalized = current.replace("\\", "/").lower()
    current_is_sandbox = "cursor-sandbox-cache" in normalized

    candidates: list[Path] = []
    if current and not current_is_sandbox:
        candidates.append(Path(current))
    candidates.append(_repo_root() / ".playwright-browsers")
    candidates.extend(_default_ms_playwright_dirs())

    seen: set[str] = set()
    for cand in candidates:
        key = str(cand.resolve()) if cand.exists() else str(cand)
        if key in seen:
            continue
        seen.add(key)
        if not _chromium_installed_in(cand):
            continue
        chosen = str(cand)
        if current != chosen:
            logger.info(
                "PLAYWRIGHT_BROWSERS_PATH 回退: {!r} → {!r}",
                current or "(未设置)",
                chosen,
            )
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = chosen
        apply_writable_playwright_tmpdir()
        return chosen

    if current and (current_is_sandbox or not _chromium_installed_in(Path(current))):
        logger.warning(
            "清除不可用的 PLAYWRIGHT_BROWSERS_PATH={!r}，改用 Playwright 默认缓存",
            current,
        )
        os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        apply_writable_playwright_tmpdir()
        return None

    apply_writable_playwright_tmpdir()
    return current or None


def _playwright_chromium_missing_hint(executable_path: str | None) -> str:
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "(未设置，默认 ~/.cache/ms-playwright)"
    return (
        f"未找到 Playwright Chromium（期望: {executable_path!r}）。"
        f"PLAYWRIGHT_BROWSERS_PATH={browsers_path}。"
        "安装时必须导出与 API 相同的 PLAYWRIGHT_BROWSERS_PATH，否则会装到 ~/.cache/ms-playwright 而进程找不到。"
        "示例：export PLAYWRIGHT_BROWSERS_PATH=/opt/kuaigeyun/.playwright-browsers；"
        "若报 does not support … ubuntu26.04：再 export PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64；"
        "然后：cd riveredge-backend && uv run --extra pdf python -m playwright install chromium；"
        "Linux 缺库再：uv run --extra pdf python -m playwright install-deps chromium。"
        "并确认 deploy.env 的 PLAYWRIGHT_BROWSERS_PATH 与 API 进程一致。"
    )


_PRINT_CLI_TIMEOUT_SEC = 120


def _print_temp_parent() -> Path:
    """打印 HTML/PDF 临时目录父路径。

    ``apply_writable_playwright_tmpdir`` 会把 TEMP 指到 ``.playwright-browsers/.tmp``，
    Chromium 对该路径下 file:// + --print-to-pdf 会挂死；Linux 固定用 /tmp。
    """
    if platform.system() == "Linux":
        return Path("/tmp")
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or tempfile.gettempdir()
    return Path(local)


def _resolve_playwright_chromium_exe() -> str:
    exe = find_playwright_chromium_executable()
    if not exe or not os.path.isfile(exe):
        raise RuntimeError(_playwright_chromium_missing_hint(exe))
    return exe


async def _html_to_pdf_once(html_for_playwright: str) -> bytes:
    """用 Playwright 自带 Chromium 的 CLI ``--print-to-pdf`` 出 PDF。

    Ubuntu 26.04 + Chromium 153 上 CDP ``Page.printToPDF``（Playwright ``page.pdf``）
    对空白页也会 Printing failed / Target crashed；同二进制 CLI 稳定。纸张走 HTML
    内 ``@page``，禁止再走 CDP 双路径。出稿进程内禁止 ``async_playwright()``，
    否则随后 CLI 子进程会挂死。
    """
    exe = _resolve_playwright_chromium_exe()
    html_body = wrap_html_document_for_print(html_for_playwright)
    page_size = parse_css_page_size(html_body)
    if page_size:
        logger.info("PDF 按 CSS @page 尺寸导出: {} x {}", page_size[0], page_size[1])
    else:
        logger.warning("未解析到 @page size，PDF 将依赖 Chromium 默认纸张")

    if os.environ.get("RIVEREDGE_PRINT_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        debug_path = os.path.join(os.getcwd(), "debug_last_print.html")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(html_body)
        logger.info("DEBUG: Final HTML captured to {}", debug_path)

    parent = _print_temp_parent()
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="riveredge-print-", dir=str(parent)) as td:
        html_path = Path(td) / "print.html"
        pdf_path = Path(td) / "print.pdf"
        html_path.write_text(html_body, encoding="utf-8")

        pdf_out = str(pdf_path.resolve())
        html_uri = html_path.resolve().as_uri()
        # 参数与线上已验证的原生 CLI 对齐；勿擅自加 user-data-dir/start_new_session
        #（本机 Ubuntu 26.04 上额外参数会导致 --print-to-pdf 挂死）。
        cmd = [
            exe,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_out}",
            html_uri,
        ]
        if platform.system() == "Linux":
            cmd.insert(1, "--no-sandbox")

        stderr_path = Path(td) / "chromium.stderr"
        # --disable-dev-shm-usage 时 Chromium 走 TMPDIR；API 进程若被
        # apply_writable_playwright_tmpdir 改写 TEMP→.playwright-browsers/.tmp，
        # 共享内存会 Permission denied 并挂死。子进程强制 TMP=/tmp，且默认不传
        # --disable-dev-shm-usage（本机 /dev/shm 充足）。
        child_env = os.environ.copy()
        tmp_root = str(_print_temp_parent())
        child_env["TMPDIR"] = tmp_root
        child_env["TEMP"] = tmp_root
        child_env["TMP"] = tmp_root

        def _run_chromium_cli() -> subprocess.CompletedProcess[bytes]:
            with open(stderr_path, "wb") as err_f:
                return subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=err_f,
                    env=child_env,
                    timeout=_PRINT_CLI_TIMEOUT_SEC,
                    check=False,
                )

        try:
            completed = await asyncio.to_thread(_run_chromium_cli)
        except FileNotFoundError as e:
            raise RuntimeError(_playwright_chromium_missing_hint(exe)) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"打印 PDF 失败：Chromium --print-to-pdf 超时（{_PRINT_CLI_TIMEOUT_SEC}s）。"
            ) from e
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "sigtrap" in low or "signal=sigtrap" in low:
                raise RuntimeError(
                    f"启动 Chromium 失败（进程被 SIGTRAP 杀掉）: {msg}。"
                    "常见原因：1) 打印子进程仍被 RLIMIT_AS 限制"
                    "（确认已部署「默认不限制」版本，或显式设 RIVEREDGE_PRINT_AS_LIMIT_GB=0）；"
                    "2) 缺系统库：cd riveredge-backend && "
                    "uv run --extra pdf python -m playwright install-deps chromium；"
                    "3) 宿主机物理内存不足导致崩溃。"
                ) from e
            raise RuntimeError(
                f"启动 Chromium 失败: {msg}。"
                "常见原因：缺系统库（install-deps）、PLAYWRIGHT_BROWSERS_PATH 不一致、"
                "或机器内存不足。"
            ) from e

        stderr_text = ""
        if stderr_path.is_file():
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
        if (
            completed.returncode != 0
            or not pdf_path.is_file()
            or pdf_path.stat().st_size < 64
        ):
            detail = stderr_text[-800:] if stderr_text else f"exit={completed.returncode}"
            raise RuntimeError(f"Chromium 打印失败（--print-to-pdf）：{detail}")
        return pdf_path.read_bytes()


async def html_to_pdf_bytes_playwright_async(html_string: str) -> bytes:
    apply_usable_playwright_browsers_path()
    # 仅确认 Chromium 二进制在盘；不要 import playwright.async_api（见 find_playwright_chromium_executable）
    _resolve_playwright_chromium_exe()

    from infra.config.infra_config import infra_settings as settings

    base_url = settings.BASE_URL
    if not base_url:
        host = "localhost" if settings.HOST == "0.0.0.0" else settings.HOST
        base_url = f"http://{host}:{settings.PORT}"
    prepared = prepare_html_for_playwright_pdf(html_string)
    if should_inject_base_href_for_pdf(prepared):
        html_for_playwright = inject_base_href_for_playwright(prepared, base_url)
    else:
        html_for_playwright = prepared

    try:
        return await _html_to_pdf_once(html_for_playwright)
    except Exception as first_error:
        if _is_playwright_set_content_timeout(first_error):
            diag = describe_print_html_for_error(html_string)
            detail = str(first_error).strip() or type(first_error).__name__
            raise RuntimeError(
                "打印 PDF 失败：Chromium 加载 HTML 超时。"
                f"（{diag}；{detail}）。"
                "线上常见原因：模板仍引用站点 BASE_URL 下未内联的图片或字体，"
                "打印子进程访问公网域名失败或挂起；与服务器内存无关。"
            ) from first_error
        if not _is_playwright_target_crashed(first_error):
            raise
        logger.warning(
            "打印 PDF Chromium 渲染失败，将强缩略内嵌图后重试: {}",
            first_error,
        )
        prepared_retry = prepare_html_for_playwright_pdf(
            html_string,
            max_side=256,
            max_b64_chars=80_000,
            force_all=True,
            strip_page_margin_boxes=True,
        )
        if should_inject_base_href_for_pdf(prepared_retry):
            html_retry = inject_base_href_for_playwright(prepared_retry, base_url)
        else:
            html_retry = prepared_retry
        try:
            return await _html_to_pdf_once(html_retry)
        except Exception as retry_error:
            if not _is_playwright_target_crashed(retry_error):
                raise
            logger.warning(
                "打印 PDF 强缩略后仍失败，去掉全部内嵌图再试: {}",
                retry_error,
            )
            html_stripped = replace_all_data_images_with_placeholder(html_retry)
            try:
                return await _html_to_pdf_once(html_stripped)
            except Exception as layout_retry_error:
                if not _is_playwright_target_crashed(layout_retry_error):
                    raise
                retry_error = layout_retry_error
            diag = describe_print_html_for_error(html_string)
            detail = str(retry_error).strip() or type(retry_error).__name__
            raise RuntimeError(
                "打印 PDF 失败：Chromium 渲染进程异常退出（Target crashed）。"
                f"（{diag}；原始错误：{detail}）。"
                "这与单据行数、HTML 体积通常无关；请核对 Playwright Chromium 版本与系统依赖，"
                "或开启 RIVEREDGE_PRINT_DEBUG=1 在 API 工作目录查看 debug_last_print.html。"
            ) from retry_error


def run_playwright_with_dedicated_loop(html_string: str) -> bytes:
    apply_usable_playwright_browsers_path()
    if platform.system() == "Windows":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(html_to_pdf_bytes_playwright_async(html_string))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        loop.close()
