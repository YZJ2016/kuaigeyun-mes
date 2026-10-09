#!/usr/bin/env python3
"""守门：定制应用（is_dedicated）不得挂载/直链通用宿主页。

检查：
  1. manifest menu_config.path 必须落在 /apps/{dedicated}/（禁止侧栏直链 kuai*）
  2. 定制包不得 lazy/import() 宿主 pages/* 作为路由页（允许 import pages/shared 抽头）
  3. export { default } from 不得解析到宿主 pages（本地 Screen 薄封装允许）
  4. 宿主 kuai*/master-data 页面不得 compile-time import 定制应用页（documentReplacementRegistry 除外）
  5. 定制页 navigate/Link 到 /apps/kuai*|master-data → medium

用法:
  python scripts/scan_dedicated_page_split.py
  python scripts/scan_dedicated_page_split.py --fail-on high
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = FRONTEND_ROOT.parent
FRONTEND_SRC = FRONTEND_ROOT / "src"
BACKEND_APPS = REPO_ROOT / "riveredge-backend" / "src" / "apps"

HOST_APP_CODES = ("kuaiplm", "kuaizhizao", "kuaioa", "master-data", "kuaiqms", "kuaiems")
DEDICATED_DIR_ALLOWLIST = ("funide-oa", "haoligo")

MENU_PATH_HOST = re.compile(
    r'^/apps/(?:' + "|".join(re.escape(c) for c in HOST_APP_CODES) + r')(/|$)'
)
# 仅拦截「把宿主整页当路由模块挂进来」；允许 pages/shared、components 等共用抽头
LAZY_HOST_PAGE = re.compile(
    r"""(?:lazy\s*\(\s*\(\s*\)\s*=>\s*)?import\(\s*['"][^'"]*/(?:"""
    + "|".join(re.escape(c) for c in HOST_APP_CODES)
    + r""")/pages/(?!shared/)[^'"]+['"]\s*\)""",
)
EXPORT_DEFAULT_FROM = re.compile(
    r"""export\s+\{\s*default\s*\}\s+from\s+['"]([^'"]+)['"]""",
)
HOST_PAGES_SEG = re.compile(
    r"(?:^|/)(?:" + "|".join(re.escape(c) for c in HOST_APP_CODES) + r")/pages/(?!shared/)"
)
NAV_HOST_URL = re.compile(
    r"""['"`](/apps/(?:"""
    + "|".join(re.escape(c) for c in HOST_APP_CODES)
    + r""")/[^'"`]*)""",
)
IMPORT_DEDICATED_PAGE = re.compile(
    r"""from\s+['"][^'"]*/apps/(?:funide-oa|haoligo)/pages/""",
)


@dataclass
class Finding:
    severity: str  # high | medium | info
    code: str
    path: str
    detail: str


def iter_menu_paths(node: object) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        p = node.get("path")
        if isinstance(p, str) and p.startswith("/apps/"):
            out.append(p.split("?")[0].rstrip("/"))
        for ch in node.get("children") or []:
            out.extend(iter_menu_paths(ch))
    elif isinstance(node, list):
        for item in node:
            out.extend(iter_menu_paths(item))
    return out


def discover_dedicated_apps() -> list[tuple[str, Path, dict]]:
    apps: list[tuple[str, Path, dict]] = []
    if not BACKEND_APPS.is_dir():
        return apps
    for manifest_path in sorted(BACKEND_APPS.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not data.get("is_dedicated"):
            continue
        code = str(data.get("code") or "").strip()
        if not code:
            continue
        apps.append((code, manifest_path, data))
    return apps


def resolve_export_target(file_path: Path, spec: str) -> Path | None:
    if spec.startswith("."):
        # strip query; resolve relative
        base = (file_path.parent / spec).resolve()
        if base.suffix:
            return base if base.is_file() else None
        for cand in (base.with_suffix(".tsx"), base.with_suffix(".ts"), base / "index.tsx", base / "index.ts"):
            if cand.is_file():
                return cand.resolve()
        return None
    return None


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def scan_manifest(code: str, manifest_path: Path, data: dict) -> list[Finding]:
    findings: list[Finding] = []
    prefix = f"/apps/{code}"
    for path in iter_menu_paths(data.get("menu_config") or {}):
        if path == prefix or path.startswith(prefix + "/"):
            continue
        if MENU_PATH_HOST.match(path) or (
            path.startswith("/apps/") and not path.startswith(prefix)
        ):
            findings.append(
                Finding(
                    "high",
                    "menu_path_host",
                    str(manifest_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                    f"menu path {path!r} 未落在 {prefix}/（禁止定制侧栏挂宿主 URL）",
                )
            )
    return findings


def scan_dedicated_frontend(code: str) -> list[Finding]:
    findings: list[Finding] = []
    app_root = FRONTEND_SRC / "apps" / code
    if not app_root.is_dir():
        findings.append(
            Finding(
                "high",
                "dedicated_fe_missing",
                f"riveredge-frontend/src/apps/{code}",
                "后端 is_dedicated 但前端应用目录不存在",
            )
        )
        return findings

    for path in app_root.rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or not path.is_file():
            continue
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")

        if LAZY_HOST_PAGE.search(text):
            findings.append(
                Finding(
                    "high",
                    "lazy_host_page",
                    rel,
                    "定制包 lazy/import() 宿主 pages/* 作为路由页（须用本地副本）",
                )
            )

        for m in EXPORT_DEFAULT_FROM.finditer(text):
            spec = m.group(1)
            # 字面量已指向宿主 pages（非 shared）
            if HOST_PAGES_SEG.search(spec.replace("\\", "/")):
                findings.append(
                    Finding(
                        "high",
                        "reexport_host_page",
                        rel,
                        f"export default from 宿主页 {spec}",
                    )
                )
                continue
            target = resolve_export_target(path, spec)
            if target is None:
                continue
            try:
                rel_apps = target.resolve().relative_to(FRONTEND_SRC / "apps")
            except ValueError:
                continue
            parts = rel_apps.parts
            if (
                len(parts) >= 2
                and parts[0] in HOST_APP_CODES
                and parts[1] == "pages"
                and "shared" not in parts
            ):
                findings.append(
                    Finding(
                        "high",
                        "reexport_host_page",
                        rel,
                        f"export default from 宿主页 {rel_apps.as_posix()}",
                    )
                )

        # navigate / Link / href 到宿主应用 URL（页面内跳转）
        if NAV_HOST_URL.search(text):
            # 允许注释行
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                    continue
                hit = NAV_HOST_URL.search(line)
                if hit:
                    findings.append(
                        Finding(
                            "medium",
                            "navigate_host_url",
                            f"{rel}:{i}",
                            f"页面内跳转宿主 URL {hit.group(1)!r}（定制壳应优先本应用 path）",
                        )
                    )
    return findings


def scan_host_imports_dedicated() -> list[Finding]:
    findings: list[Finding] = []
    allow_files = {
        (FRONTEND_SRC / "utils" / "documentReplacementRegistry.ts").resolve(),
    }
    for host in HOST_APP_CODES:
        root = FRONTEND_SRC / "apps" / host
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".tsx"} or not path.is_file():
                continue
            if path.resolve() in allow_files:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if IMPORT_DEDICATED_PAGE.search(text):
                rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                findings.append(
                    Finding(
                        "high",
                        "host_imports_dedicated",
                        rel,
                        "宿主页 compile-time import 定制应用页（禁止绑客户；用 document 替代注册表）",
                    )
                )
    # registry 本身若 import 定制页是允许的
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on",
        choices=("high", "medium", "info", "never"),
        default="never",
        help="达到该级别及以上则 exit 1",
    )
    args = parser.parse_args()

    findings: list[Finding] = []
    dedicated = discover_dedicated_apps()
    if not dedicated:
        print("scan_dedicated_page_split: no is_dedicated apps found")
        return 0

    for code, manifest_path, data in dedicated:
        findings.extend(scan_manifest(code, manifest_path, data))
        findings.extend(scan_dedicated_frontend(code))
    findings.extend(scan_host_imports_dedicated())

    order = {"high": 0, "medium": 1, "info": 2}
    findings.sort(key=lambda f: (order.get(f.severity, 9), f.path, f.code))

    counts = {"high": 0, "medium": 0, "info": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
        print(f"[{f.severity}] {f.code}  {f.path}")
        print(f"         {f.detail}")

    print(
        f"\nscan_dedicated_page_split: dedicated_apps={len(dedicated)} "
        f"high={counts['high']} medium={counts['medium']} info={counts['info']}"
    )

    if args.fail_on == "never":
        return 0
    rank = {"high": 0, "medium": 1, "info": 2}[args.fail_on]
    worst = min((order[f.severity] for f in findings), default=99)
    return 1 if findings and worst <= rank else 0


if __name__ == "__main__":
    sys.exit(main())
