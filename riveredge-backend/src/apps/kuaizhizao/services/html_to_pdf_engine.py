"""HTML → PDF：仅在本模块的子进程里启动 Chromium。

API worker 通过 `python -m apps.kuaizhizao.services.html_to_pdf_engine` 调用，
Chromium / Playwright driver 崩溃或超内存时只杀死子进程，不带走 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.services.pdf.playwright_engine import (
    html_to_pdf_bytes_playwright_async,
    inject_base_href_for_playwright,
    parse_css_page_size,
    run_playwright_with_dedicated_loop,
)

__all__ = [
    "inject_base_href_for_playwright",
    "parse_css_page_size",
    "html_to_pdf_bytes_playwright_async",
    "run_playwright_with_dedicated_loop",
]


def _cli(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: html_to_pdf_engine <in.html> <out.pdf>", file=sys.stderr)
        return 2
    html_path = Path(argv[1])
    pdf_path = Path(argv[2])
    html = html_path.read_text(encoding="utf-8")
    pdf_path.write_bytes(run_playwright_with_dedicated_loop(html))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
