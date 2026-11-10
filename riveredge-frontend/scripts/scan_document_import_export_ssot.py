#!/usr/bin/env python3
"""守门：导入导出 SSOT —— 禁止物料按码旁路匹配、禁止旁路 SheetJS 导出、禁止导入全局去逗号。

用法:
  python scripts/scan_document_import_export_ssot.py
  python scripts/scan_document_import_export_ssot.py --fail-on high
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
EXTS = {".ts", ".tsx"}
SKIP_PARTS = {"locales", "node_modules", "__snapshots__", ".vite"}

# 允许的真源文件（旁路检测排除）
ALLOW_EXPORT_WRITE = {
    "utils/exportRecordsXlsx.ts",
}
ALLOW_MATERIAL_RESOLVE = {
    "apps/master-data/utils/materialImportResolve.ts",
}
ALLOW_COMMA_STRIP = {
    "utils/spreadsheetPreserveText.ts",
    "utils/spreadsheetPreserveText.test.ts",
}

# 页面内用缓存条数短路再匹配物料（历史假未命中）
CACHE_SHORTCUT = re.compile(
    r"materials?\w*\.length\s*<\s*50|"
    r"materialList\w*\.length\s*<\s*50|"
    r"materialsForImport\.length\s*<\s*50",
    re.I,
)

# 本地按 mainCode/code 大小写比较（应走 findMaterialByImportCode）
LOCAL_CODE_EQ = re.compile(
    r"""
    \(?\s*m(?:aterial)?\s*\.\s*(?:mainCode|main_code|code)
    [^)]{0,80}?
    \)\s*\.?\s*toUpperCase\s*\(\s*\)
    \s*===
    |
    \(?\s*(?:m\.mainCode|m\.main_code|m\.code|material\.mainCode)
    [^;\n]{0,60}?
    ===\s*(?:materialCode|productCode|codeNorm)
    """,
    re.I | re.VERBOSE,
)

# 旁路 SheetJS 写盘
SHEETJS_WRITE = re.compile(
    r"\bXLSX\.utils\.aoa_to_sheet\b|\bXLSX\.writeFile\b",
)

# uni-import / spreadsheet 路径禁止裸全局去逗号（数值列应走 spreadsheetPlainCellText）
BARE_COMMA_STRIP = re.compile(r"""\.replace\(\s*/,/g\s*,\s*['\"]['\"]\s*\)""")

HARDCODED_NOT_FOUND = re.compile(r"未找到产品")


def rel_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if path.suffix not in EXTS or not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        files.append(path)
    return files


def scan_file(path: Path) -> list[tuple[str, str, int, str]]:
    """返回 (severity, rule, line_no, line)"""
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = rel_posix(path)
    hits: list[tuple[str, str, int, str]] = []
    lines = text.splitlines()

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue

        if CACHE_SHORTCUT.search(line):
            hits.append(("high", "material_cache_shortcut", i, stripped[:160]))

        if LOCAL_CODE_EQ.search(line) and rel not in ALLOW_MATERIAL_RESOLVE:
            hits.append(("high", "local_material_code_eq", i, stripped[:160]))

        if SHEETJS_WRITE.search(line) and rel not in ALLOW_EXPORT_WRITE:
            hits.append(("high", "sheetjs_export_bypass", i, stripped[:160]))

        if HARDCODED_NOT_FOUND.search(line) and "materialImportResolve" not in rel:
            # 注释里的说明可忽略；代码字符串算 medium
            if "'" in line or '"' in line or "`" in line:
                hits.append(("medium", "hardcoded_material_not_found", i, stripped[:160]))

        in_import_stack = (
            "/uni-import/" in f"/{rel}"
            or rel.startswith("utils/spreadsheetCellPlainString.ts")
            or rel.startswith("utils/spreadsheetPreserveText")
        )
        if in_import_stack and BARE_COMMA_STRIP.search(line) and rel not in ALLOW_COMMA_STRIP:
            hits.append(("high", "bare_comma_strip_on_import", i, stripped[:160]))

    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on",
        choices=("none", "high", "medium"),
        default="none",
        help="达到该级别即非零退出",
    )
    args = parser.parse_args()

    all_hits: list[tuple[str, str, str, int, str]] = []
    for path in iter_source_files():
        for sev, rule, line_no, snippet in scan_file(path):
            all_hits.append((sev, rule, rel_posix(path), line_no, snippet))

    by_sev = {"high": 0, "medium": 0}
    for sev, rule, rel, line_no, snippet in sorted(all_hits, key=lambda x: (x[0], x[2], x[3])):
        by_sev[sev] = by_sev.get(sev, 0) + 1
        print(f"[{sev}] {rule} {rel}:{line_no}: {snippet}")

    print(
        f"\nsummary: high={by_sev.get('high', 0)} medium={by_sev.get('medium', 0)} "
        f"files_scanned={len(iter_source_files())}"
    )

    order = {"none": 0, "medium": 1, "high": 2}
    threshold = order[args.fail_on]
    worst = 0
    if by_sev.get("medium"):
        worst = max(worst, 1)
    if by_sev.get("high"):
        worst = max(worst, 2)
    if worst >= threshold and args.fail_on != "none":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
