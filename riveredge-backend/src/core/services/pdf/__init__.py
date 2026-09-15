"""Core PDF utilities (Playwright HTML → PDF)."""

from core.services.pdf.playwright_engine import (
    html_to_pdf_bytes_playwright_async,
    inject_base_href_for_playwright,
    parse_css_page_size,
    run_playwright_with_dedicated_loop,
)

__all__ = [
    "html_to_pdf_bytes_playwright_async",
    "inject_base_href_for_playwright",
    "parse_css_page_size",
    "run_playwright_with_dedicated_loop",
]
