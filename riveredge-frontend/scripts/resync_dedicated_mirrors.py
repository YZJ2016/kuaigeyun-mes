#!/usr/bin/env python3
"""按 manifest 重建定制镜像页（覆盖 copy + import + URL 修正）。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mirror", ROOT / "scripts/mirror_dedicated_host_pages.py")
mirror = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mirror)

BACKEND = mirror.BACKEND


def load_manifest(code: str) -> dict:
    return json.loads((BACKEND / code.replace("-", "_") / "manifest.json").read_text("utf-8"))


def iter_paths(node) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        p = node.get("path")
        if isinstance(p, str):
            out.append(p.split("?")[0].rstrip("/"))
        for ch in node.get("children") or []:
            out.extend(iter_paths(ch))
    elif isinstance(node, list):
        for x in node:
            out.extend(iter_paths(x))
    return out


def is_mirror(dedicated: str, dr: str) -> bool:
    if dedicated == "funide-oa":
        return dr not in ("project-proposals", "workbench")
    if dedicated == "haoligo":
        return dr.startswith("master-data/") or dr.startswith("hr/")
    return False


def main() -> int:
    dedicated = sys.argv[1]
    paths = sorted(set(iter_paths(load_manifest(dedicated).get("menu_config") or {})))
    copied: set[tuple[str, str]] = set()
    n = 0
    for p in paths:
        if not p.startswith(f"/apps/{dedicated}/"):
            continue
        dr = p[len(f"/apps/{dedicated}/") :]
        if not is_mirror(dedicated, dr):
            continue
        if dr.startswith("master-data/"):
            host_app = "master-data"
        elif dr.startswith("hr/") or dr.startswith("approval/") or dr.startswith("collaboration/") or dr.startswith("compliance/") or dr.startswith("assets/"):
            host_app = "kuaioa"
        else:
            first = dr.split("/")[0]
            kuaiplm_roots = {
                "dashboard", "pending-inbox", "rd-projects", "rd-deliverables", "change-management",
                "knowledge-base", "bom-collaborations", "product-firmwares", "production-files",
                "lab-requests", "lab-board", "lab-judgment-rules", "annual-lab-plans", "trial-flows",
                "sample-process-applications", "material-reviews", "mold-sample-orders", "prototype-build-sheets",
            }
            host_app = "kuaiplm" if first in kuaiplm_roots or dr.startswith("phase2/") else "kuaizhizao"
        page_dir = mirror.resolve_host_page_dir(host_app, dr if host_app != "master-data" else dr)
        key = (host_app, page_dir)
        if key in copied:
            continue
        mirror.copy_page_tree(host_app, page_dir, dedicated)
        copied.add(key)
        n += 1

    for (ha, key), extras in mirror.ROUTE_EXTRA.get(dedicated, {}).items():
        for _, extra_page in extras:
            k = (ha, extra_page)
            if k in copied:
                continue
            mirror.copy_page_tree(ha, extra_page, dedicated)
            copied.add(k)
            n += 1

    import subprocess

    subprocess.run([sys.executable, str(ROOT / "scripts/fix_dedicated_mirror_urls.py"), dedicated], check=True)
    print(f"resynced {n} page trees for {dedicated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
