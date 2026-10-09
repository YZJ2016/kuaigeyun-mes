#!/usr/bin/env python3
"""将镜像页内硬编码宿主 URL 改为定制应用 URL。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "apps"

REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "funide-oa": [
        ("/apps/kuaiplm/", "/apps/funide-oa/"),
        ("/apps/kuaizhizao/", "/apps/funide-oa/"),
        ("/apps/kuaioa/", "/apps/funide-oa/"),
        ("/apps/master-data/", "/apps/funide-oa/master-data/"),
    ],
    "haoligo": [
        ("/apps/master-data/", "/apps/haoligo/master-data/"),
        ("/apps/kuaioa/", "/apps/haoligo/"),
    ],
}


def main() -> int:
    dedicated = sys.argv[1]
    reps = REPLACEMENTS[dedicated]
    base = ROOT / dedicated / "pages"
    count = 0
    for fp in base.rglob("*"):
        if fp.suffix not in (".ts", ".tsx"):
            continue
        text = fp.read_text(encoding="utf-8")
        orig = text
        for old, new in reps:
            text = text.replace(old, new)
        if text != orig:
            fp.write_text(text, encoding="utf-8")
            count += 1
    print(f"url-fixed {count} files for {dedicated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
