#!/usr/bin/env python3
"""
一次性镜像：将 manifest 中宿主菜单页复制到定制应用 pages/{hostApp}/ 下，并生成 Route 注册片段。

仅用于定制剥离；运行后须 tsc/打开关键页验证。禁止当作日常 codemod 反复跑。
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "apps"
BACKEND = ROOT.parent / "riveredge-backend" / "src" / "apps"

SKIP_DEDICATED_PATHS = {
    "funide-oa": {"/apps/funide-oa/project-proposals"},
}

ROUTE_EXTRA = {
    "funide-oa": {
        ("kuaiplm", "rd-projects"): [("rd-projects/detail/:id", "pages/rd-projects/detail")],
        ("kuaiplm", "knowledge-base"): [("knowledge-base/detail/:id", "pages/knowledge-base/detail")],
        ("master-data", "process/sop"): [
            ("master-data/process/sop/designer", "pages/process/sop/designer"),
            ("master-data/process/sop/execution", "pages/process/sop/execution"),
        ],
        ("master-data", "process/engineering-bom"): [
            ("master-data/process/engineering-bom/designer", "pages/materials/bom/designer"),
        ],
        ("master-data", "materials"): [
            ("master-data/materials/new", "pages/materials/management"),
            ("master-data/materials/:uuid/edit", "pages/materials/management"),
        ],
    },
    "haoligo": {
        ("kuaioa", "hr/payroll-settlements"): [("hr/payroll-settlements/detail", "pages/hr/payroll-settlements/detail")],
        ("kuaioa", "hr/welfare-batches"): [("hr/welfare-batches/detail", "pages/hr/welfare-batches/detail")],
        ("kuaioa", "hr/attendance"): [("hr/attendance/:id", "pages/hr/attendance/fill")],
    },
}


def load_manifest(app_code: str) -> dict:
    folder = app_code.replace("-", "_")
    path = BACKEND / folder / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def iter_menu_paths(node: dict) -> list[str]:
    paths: list[str] = []
    if isinstance(node, dict):
        p = node.get("path")
        if isinstance(p, str) and p.startswith("/apps/"):
            paths.append(p.split("?")[0].rstrip("/"))
        for ch in node.get("children") or []:
            paths.extend(iter_menu_paths(ch))
    elif isinstance(node, list):
        for item in node:
            paths.extend(iter_menu_paths(item))
    return paths


def host_path_to_dedicated_rest(host_path: str, dedicated: str) -> str | None:
    path = host_path.split("?")[0].rstrip("/")
    if path.startswith(f"/apps/{dedicated}/"):
        return None
    m = re.match(r"^/apps/([^/]+)/(.+)$", path)
    if not m:
        return None
    host_app, rest = m.group(1), m.group(2)
    if host_app == "master-data":
        return f"master-data/{rest}"
    if host_app in ("kuaiplm", "kuaizhizao", "kuaioa"):
        return rest
    return None


KUAIZHAO_PAGE_ALIASES: dict[str, str] = {
    "equipment-management/reports/equipment-maintenance-detail": "pages/equipment-management/reports/EquipmentMaintenanceDetail",
    "equipment-management/reports/equipment-maintenance-plan": "pages/equipment-management/reports/EquipmentMaintenancePlan",
    "equipment-management/reports/equipment-fault-analysis": "pages/equipment-management/reports/EquipmentFaultAnalysis",
    "equipment-management/reports/equipment-status-log": "pages/equipment-management/reports/EquipmentStatusLog",
    "equipment-management/reports/equipment-spot-check-summary": "pages/equipment-management/reports/EquipmentSpotCheckSummary",
    "equipment-management/reports/equipment-route-patrol-summary": "pages/equipment-management/reports/EquipmentRoutePatrolSummary",
    "equipment-management/reports/equipment-mttr-mtbf": "pages/equipment-management/reports/EquipmentMttrMtbfAnalysis",
    "production-execution/reports/production-daily": "pages/production-execution/reports/ProductionDaily",
    "quality-management/reports/quality-complaint-analysis": "pages/quality-management/reports/QualityComplaintAnalysis",
}

KUAIOA_PAGE_ALIASES: dict[str, str] = {
    "hr/attendance/day-register": "pages/hr/attendance/day-register.tsx",
}


def resolve_host_page_dir(host_app: str, dedicated_rest: str) -> str:
    if host_app == "master-data":
        sub = dedicated_rest[len("master-data/") :]
        if sub == "materials":
            return "pages/materials/management.tsx"
        if sub == "process/engineering-bom":
            return "pages/materials/bom"
        return f"pages/{sub}"
    if host_app == "kuaiplm":
        rest = dedicated_rest
        if rest == "lab-board":
            return "pages/lab-requests"
        return f"pages/{rest}"
    if host_app == "kuaioa":
        return KUAIOA_PAGE_ALIASES.get(dedicated_rest, f"pages/{dedicated_rest}")
    if host_app == "kuaizhizao":
        return KUAIZHAO_PAGE_ALIASES.get(dedicated_rest, f"pages/{dedicated_rest}")
    return f"pages/{dedicated_rest}"


FRONTEND_SRC = ROOT / "src"


def _strip_import_path(path: str) -> str:
    for suf in (".tsx", ".ts"):
        if path.endswith(suf):
            path = path[: -len(suf)]
            break
    if path.endswith("/index"):
        path = path[: -len("/index")]
    return path


def fix_imports(content: str, host_app: str, host_file: Path | None = None) -> str:
    """Rewrite relative imports for pages/{hostApp}/ nesting under a dedicated app.

    Host page:  apps/{host}/pages/...
    Mirror:     apps/{dedicated}/pages/{host}/...
    """
    host_pages = (SRC / host_app / "pages").resolve()
    host_app_root = (SRC / host_app).resolve()
    host_file_dir = host_file.resolve().parent if host_file else None

    def mirror_depth_to_apps() -> int:
        assert host_file_dir is not None
        rel_from_host_pages = host_file_dir.relative_to(host_pages)
        # mirror: apps/dedicated/pages/{host_app}/{rel…}
        return 3 + len(rel_from_host_pages.parts)

    def resolve_target(dots: str, tail: str) -> Path:
        assert host_file_dir is not None
        resolved = (host_file_dir / f"{dots}{tail}").resolve()
        if resolved.exists():
            return resolved
        for c in (
            resolved.with_suffix(".tsx"),
            resolved.with_suffix(".ts"),
            resolved.with_suffix(".less"),
            resolved.with_suffix(".css"),
            resolved / "index.tsx",
            resolved / "index.ts",
        ):
            if c.exists():
                return c
        return resolved

    def rewrite_path(dots: str, tail: str) -> str | None:
        """Return rewritten module path (no quotes), or None to keep original."""
        n = dots.count("../")
        if host_file_dir is not None:
            try:
                host_file_dir.relative_to(host_pages)
            except ValueError:
                host_file_dir_ok = False
            else:
                host_file_dir_ok = True
            if host_file_dir_ok:
                target = resolve_target(dots, tail)
                depth_apps = mirror_depth_to_apps()
                depth_src = depth_apps + 1

                try:
                    rel_pages = target.relative_to(host_pages)
                    new_path = _strip_import_path(f"{host_app}/pages/{rel_pages.as_posix()}")
                    return f"{'../' * depth_apps}{new_path}"
                except ValueError:
                    pass

                try:
                    rel_app = target.relative_to(host_app_root)
                    new_path = _strip_import_path(f"{host_app}/{rel_app.as_posix()}")
                    return f"{'../' * depth_apps}{new_path}"
                except ValueError:
                    pass

                try:
                    rel_src = target.relative_to(FRONTEND_SRC)
                    new_path = _strip_import_path(rel_src.as_posix())
                    if new_path.startswith("apps/"):
                        new_path = new_path[len("apps/") :]
                        return f"{'../' * depth_apps}{new_path}"
                    return f"{'../' * depth_src}{new_path}"
                except ValueError:
                    pass

        cross = ("kuaizhizao/", "kuaiplm/", "kuaioa/", "master-data/", "ind-", "apps/")
        if tail.startswith(cross):
            return f"{'../' * (n + 1)}{tail}"
        platform = ("components/", "hooks/", "constants/", "utils/", "services/")
        if n >= 4 and tail.startswith(platform):
            return f"{'../' * (n + 1)}{tail}"
        if tail.startswith("shared/"):
            return f"{'../' * (n + 2)}{host_app}/pages/{tail}"
        host_local = ("services/", "components/", "hooks/", "constants/", "layouts/", "types/", "utils/")
        if tail.startswith(host_local):
            return f"{'../' * (n + 2)}{host_app}/{tail}"
        return None

    def repl_from(m: re.Match) -> str:
        quote, dots, tail = m.group(1), m.group(2), m.group(3)
        if tail.startswith("../") or tail.startswith("./"):
            return m.group(0)
        rewritten = rewrite_path(dots, tail)
        if rewritten is None:
            return m.group(0)
        return f"from {quote}{rewritten}{quote}"

    def repl_dynamic(m: re.Match) -> str:
        quote, dots, tail = m.group(1), m.group(2), m.group(3)
        if tail.startswith("../") or tail.startswith("./"):
            return m.group(0)
        rewritten = rewrite_path(dots, tail)
        if rewritten is None:
            return m.group(0)
        return f"import({quote}{rewritten}{quote}"

    content = re.sub(r"from (['\"])((?:\.\./)+)([^'\"]+)\1", repl_from, content)
    content = re.sub(r"import\((['\"])((?:\.\./)+)([^'\"]+)\1", repl_dynamic, content)
    return content


def fix_persistence_and_host_path(content: str, dedicated: str, dedicated_rest: str) -> str:
    content = re.sub(
        r"columnPersistenceId:\s*'apps\.[^']+'",
        lambda m: m.group(0).replace("apps.", f"apps.{dedicated}.host.", 1)
        if "apps." + dedicated not in m.group(0)
        else m.group(0),
        content,
    )
    content = re.sub(
        r"columnPersistenceId=\{?['\"]apps\.[^'\"]+['\"]\}?",
        lambda m: m.group(0).replace("apps.", f"apps.{dedicated}.host.", 1)
        if dedicated not in m.group(0)
        else m.group(0),
        content,
    )

    dedicated_url = f"/apps/{dedicated}/{dedicated_rest}"
    content = re.sub(
        r"const HOST_PATH = '/apps/[^']+';",
        f"const HOST_PATH = '{dedicated_url}';",
        content,
    )
    return content


def resolve_src_root(host_app: str, page_dir: str) -> Path:
    src_root = SRC / host_app / page_dir
    if src_root.exists():
        return src_root
    tsx = Path(f"{src_root}.tsx")
    if tsx.exists():
        return tsx
    raise FileNotFoundError(f"missing host page: {src_root}")


def copy_page_tree(host_app: str, page_dir: str, dedicated: str) -> Path:
    src_root = resolve_src_root(host_app, page_dir)
    rel = page_dir.replace("pages/", "", 1) if page_dir.startswith("pages/") else page_dir
    dest_root = SRC / dedicated / "pages" / host_app / rel
    if dest_root.exists():
        if dest_root.is_dir():
            shutil.rmtree(dest_root)
        else:
            dest_root.unlink()
    dest_root.parent.mkdir(parents=True, exist_ok=True)
    def rewrite_copied_text(text: str, host_fp: Path, suffix: str) -> str:
        if suffix in (".ts", ".tsx"):
            text = fix_imports(text, host_app, host_file=host_fp)
            return fix_persistence_and_host_path(text, dedicated, "")
        if suffix in (".less", ".css", ".scss"):
            # Less/CSS @import relative paths need the same extra ../ as JS platform imports.
            def less_repl(m: re.Match) -> str:
                prefix, quote, dots, tail = m.group(1), m.group(2), m.group(3), m.group(4)
                rewritten = None
                # Reuse JS rewriter by synthesizing a from-import.
                probe = f"from {quote}{dots}{tail}{quote}"
                out = fix_imports(probe, host_app, host_file=host_fp)
                if out.startswith("from ") and out != probe:
                    # from 'path' → path
                    rewritten = out[len("from ") :].strip()
                    if rewritten[0] in "'\"" and rewritten[-1] == rewritten[0]:
                        rewritten = rewritten[1:-1]
                if rewritten is None:
                    return m.group(0)
                return f"{prefix}{quote}{rewritten}{quote}"

            return re.sub(
                r"(@import\s+(?:url\()?)(['\"])((?:\.\./)+)([^'\"]+)\2",
                less_repl,
                text,
            )
        return text

    if src_root.is_file():
        # Host single-file pages are *.tsx; page_dir may omit the suffix.
        dest_file = dest_root if dest_root.suffix else dest_root.with_suffix(src_root.suffix)
        if dest_file.exists():
            dest_file.unlink()
        shutil.copy2(src_root, dest_file)
        text = dest_file.read_text(encoding="utf-8")
        text = rewrite_copied_text(text, src_root, dest_file.suffix)
        dest_file.write_text(text, encoding="utf-8")
        # Copy same-directory ./ relative modules the entry imports (not full folder).
        sibling_pat = re.compile(r"""(?:from|import\()\s*['"](\./[^'"]+)['"]""")
        seen: set[Path] = set()
        queue = [src_root]
        while queue:
            cur = queue.pop()
            if cur in seen or not cur.exists() or not cur.is_file():
                continue
            seen.add(cur)
            for m in sibling_pat.finditer(cur.read_text(encoding="utf-8")):
                rel_mod = m.group(1)
                base = (cur.parent / rel_mod).resolve()
                candidates = [base, base.with_suffix(".tsx"), base.with_suffix(".ts"), base / "index.tsx", base / "index.ts"]
                for cand in candidates:
                    if not cand.exists() or not cand.is_file():
                        continue
                    if cand.parent != src_root.parent:
                        continue  # only same-dir helpers
                    dest_sib = dest_file.parent / cand.name
                    shutil.copy2(cand, dest_sib)
                    sib_text = dest_sib.read_text(encoding="utf-8")
                    # ./ stays; ../ escapes still need host_app / platform rewrite.
                    dest_sib.write_text(
                        rewrite_copied_text(sib_text, cand, dest_sib.suffix),
                        encoding="utf-8",
                    )
                    queue.append(cand)
                    break
        return dest_file
    shutil.copytree(src_root, dest_root)
    for fp in dest_root.rglob("*"):
        if fp.suffix not in (".ts", ".tsx", ".less", ".css", ".scss"):
            continue
        rel = fp.relative_to(dest_root)
        host_fp = src_root / rel
        text = fp.read_text(encoding="utf-8")
        text = rewrite_copied_text(text, host_fp, fp.suffix)
        fp.write_text(text, encoding="utf-8")
    return dest_root


def route_path_from_dedicated_rest(dedicated_rest: str) -> str:
    return dedicated_rest


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: mirror_dedicated_host_pages.py <funide-oa|haoligo>", file=sys.stderr)
        return 1
    dedicated = sys.argv[1]
    manifest = load_manifest(dedicated)
    menu = manifest.get("menu_config") or {}
    host_paths = sorted(set(iter_menu_paths(menu)))
    skip = SKIP_DEDICATED_PATHS.get(dedicated, set())

    entries: list[tuple[str, str, str]] = []
    manifest_replacements: dict[str, str] = {}
    copied: set[tuple[str, str]] = set()

    def ensure_copy(host_app: str, page_dir: str) -> None:
        key = (host_app, page_dir)
        if key in copied:
            return
        copy_page_tree(host_app, page_dir, dedicated)
        copied.add(key)

    def add_route(route_path: str, host_app: str, page_dir: str) -> None:
        rel = page_dir.replace("pages/", "", 1)
        if rel.endswith(".tsx"):
            rel = rel[: -len(".tsx")]
        import_path = f"./pages/{host_app}/{rel}"
        entries.append((route_path, import_path, host_app))

    for hp in host_paths:
        if hp in skip:
            continue
        dr = host_path_to_dedicated_rest(hp, dedicated)
        if not dr:
            continue
        host_app = hp.split("/")[2]
        page_dir = resolve_host_page_dir(host_app, dr)
        try:
            ensure_copy(host_app, page_dir)
        except FileNotFoundError as e:
            print(f"WARN skip {hp}: {e}", file=sys.stderr)
            continue
        add_route(route_path_from_dedicated_rest(dr), host_app, page_dir)
        manifest_replacements[hp] = f"/apps/{dedicated}/{dr}"

    for (ha, key), extras in ROUTE_EXTRA.get(dedicated, {}).items():
        for extra_route, extra_page in extras:
            try:
                ensure_copy(ha, extra_page)
            except FileNotFoundError:
                continue
            add_route(extra_route, ha, extra_page)

    routes_file = SRC / dedicated / "routes.host-mirror.generated.tsx"
    lines = [
        "/** AUTO-GENERATED by scripts/mirror_dedicated_host_pages.py — do not hand-edit */",
        "import React, { Suspense, lazy } from 'react';",
        "import { Route } from 'react-router-dom';",
        "import PageSkeleton from '../../components/page-skeleton';",
        "",
        "const withPageSuspense = (C: React.LazyExoticComponent<React.ComponentType>) => (",
        "  <Suspense fallback={<PageSkeleton />}><C /></Suspense>",
        ");",
        "",
    ]
    route_map: dict[str, str] = {}
    for route_path, import_path, _ in entries:
        route_map[route_path] = import_path
    for route_path, import_path in sorted(route_map.items(), key=lambda x: x[0]):
        var = re.sub(r"[^a-zA-Z0-9]", "_", route_path) + "Page"
        lines.append(f"const {var} = lazy(() => import('{import_path}'));")
    lines.append("")
    lines.append("export const dedicatedHostMirrorRoutes = (")
    lines.append("  <>")
    for route_path in sorted(route_map.keys()):
        var = re.sub(r"[^a-zA-Z0-9]", "_", route_path) + "Page"
        lines.append(f'    <Route path="{route_path}" element={{withPageSuspense({var})}} />')
    lines.append("  </>")
    lines.append(");")
    routes_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest_path = BACKEND / dedicated.replace("-", "_") / "manifest.json"
    text = manifest_path.read_text(encoding="utf-8")
    for old, new in sorted(manifest_replacements.items(), key=lambda x: -len(x[0])):
        text = text.replace(f'"path": "{old}"', f'"path": "{new}"')
    manifest_path.write_text(text, encoding="utf-8")

    print(f"mirrored {len(manifest_replacements)} menu paths for {dedicated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
