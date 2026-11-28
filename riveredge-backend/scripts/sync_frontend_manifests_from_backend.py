#!/usr/bin/env python3
"""
前端 manifest 镜像同步：后端 manifest.json 是唯一真源。

规则（.cursor/rules/manifest-unique-source.mdc）：
  - 菜单 / 权限码 / module_references 只改后端 src/apps/<app>/manifest.json
  - 前端 src/apps/<app>/manifest.json 是镜像，禁止手改
  - 本脚本把后端 manifest 逐字写入前端镜像（后端目录名 snake_case → 前端 kebab-case）

用法:
  python scripts/sync_frontend_manifests_from_backend.py            # 全部已存在镜像的应用
  python scripts/sync_frontend_manifests_from_backend.py --app kuaizhizao
  python scripts/sync_frontend_manifests_from_backend.py --check    # 只报差异不落盘
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_APPS = REPO_ROOT / "riveredge-backend" / "src" / "apps"
FRONTEND_APPS = REPO_ROOT / "riveredge-frontend" / "src" / "apps"


def frontend_manifest_path(backend_app: str) -> Path:
    return FRONTEND_APPS / backend_app.replace("_", "-") / "manifest.json"


def canonical_text(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def iter_backend_manifests(app: str | None):
    if app:
        path = BACKEND_APPS / app / "manifest.json"
        if not path.exists():
            raise SystemExit(f"后端应用 manifest 不存在: {path}")
        yield app, path
        return
    for entry in sorted(BACKEND_APPS.iterdir()):
        path = entry / "manifest.json"
        if entry.is_dir() and path.exists():
            yield entry.name, path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="后端 manifest → 前端镜像同步")
    parser.add_argument("--app", help="只同步单个应用 code（后端目录名）")
    parser.add_argument(
        "--check", action="store_true", help="只检查差异不落盘（有差异退出码 1）"
    )
    args = parser.parse_args(argv)

    changed = 0
    skipped = 0
    for app, src in iter_backend_manifests(args.app):
        dst = frontend_manifest_path(app)
        if not dst.parent.exists():
            print(f"[skip] {app}: 前端应用目录不存在 {dst.parent}")
            skipped += 1
            continue
        manifest = json.loads(src.read_text(encoding="utf-8"))
        new_text = canonical_text(manifest)
        if dst.exists() and dst.read_text(encoding="utf-8") == new_text:
            continue
        if args.check:
            print(f"[diff] {app}: {dst} 与后端不一致")
        else:
            dst.write_text(new_text, encoding="utf-8")
            print(f"[sync] {app} -> {dst}")
        changed += 1

    mode = "check" if args.check else "sync"
    print(f"{mode} 完成: {changed} 个差异, {skipped} 个跳过")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
