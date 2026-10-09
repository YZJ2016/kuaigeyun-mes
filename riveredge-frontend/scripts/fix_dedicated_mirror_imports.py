#!/usr/bin/env python3
"""修正定制镜像页相对 import（pages/{hostApp}/ 比宿主页多一层）。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_APPS = ("kuaiplm", "kuaizhizao", "kuaioa", "master-data")

spec = importlib.util.spec_from_file_location(
    "mirror_dedicated_host_pages", ROOT / "scripts" / "mirror_dedicated_host_pages.py"
)
mirror = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mirror)


def main() -> int:
    dedicated = sys.argv[1] if len(sys.argv) > 1 else "funide-oa"
    base = ROOT / "src" / "apps" / dedicated / "pages"
    count = 0
    for host_app in HOST_APPS:
        host_root = base / host_app
        if not host_root.exists():
            continue
        for fp in host_root.rglob("*"):
            if fp.suffix not in (".ts", ".tsx"):
                continue
            # Re-derive from host source when possible; otherwise rewrite in place is unsafe.
            # In-place: reverse is hard — prefer resync. Here only re-apply on already-mirrored
            # content that still has the buggy host_app/components/uni-table shape by
            # re-copying from host via resync_dedicated_mirrors.py.
            text = fp.read_text(encoding="utf-8")
            # No-op marker: this script now delegates to resync for correctness.
            _ = text
            _ = host_app
            count += 0
    print(
        f"use: python scripts/resync_dedicated_mirrors.py {dedicated}\n"
        f"(fix_imports lives in mirror_dedicated_host_pages.py; in-place rewrite skipped)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
