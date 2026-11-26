#!/usr/bin/env python3
"""上游同步文件级台账审计工具。

用途：把「每轮同步都要重新评估所有上游变更文件」降为「只评估 sha 变化过的文件」。

台账文件：docs/上游同步-文件级台账.tsv（TSV，# 行为注释）。
列：upstream_path \t sha_at_eval \t verdict \t note

verdict 约定：
  tracked     已评估（详细取/缓置判定见提交级台账 上游同步台账.md）
  applied     已完整摘取/适配落地（相对 --to 处全部 diff 均已处置；局部摘取禁止记 applied）
  ported      跨架构异位移植落地（如上游 kuaizhizao/finance/** 移植至本地 kuaicaiwu/**，或迁移重编号）
  superset    本地已是超集，跳过
  deferred    缓置或局部摘取未完（--note 必填，记录剩余项/依赖簇）
  domain-out  真域外（客户专属 haoligo/chenao/lianzhi、fast-deploy 等），不摘；严禁将异位移植财务或通用 core/infra 混标

命令：
  audit  --from <sha> --to <sha>            输出区间内文件四分类：NEW / REEVAL / DELETED / SKIP
  seed   --to <sha> <commit> [<commit>...]  把指定提交触及的文件按 --to 处 blob sha 登记为 tracked
  record --to <sha> --verdict <v> [--note s] <path>...   记录/更新单文件判定

典型一轮：
  python riveredge-backend/scripts/sync_upstream_audit.py audit --from <上轮tip> --to gitee/develop
  # 永远以 audit 输出为待办入口（勿直接按 TSV 存量行扫）；NEW/REEVAL 才是本轮真正要看的文件
  python riveredge-backend/scripts/sync_upstream_audit.py record --to gitee/develop --verdict applied <path>
"""

from __future__ import annotations

import argparse
from collections import Counter
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "docs" / "上游同步-文件级台账.tsv"

VERDICTS = ("tracked", "applied", "ported", "superset", "deferred", "domain-out")

HEADER = (
    "# 上游同步文件级台账（scripts/sync_upstream_audit.py 维护，勿手改列结构）\n"
    "# 列：upstream_path\tsha_at_eval\tverdict\tnote\n"
    "# verdict: tracked|applied|ported|superset|deferred|domain-out\n"
)

_FINANCE_PORT_SUBSTRINGS = (
    "apps/kuaizhizao/finance/",
    "apps/kuaizhizao/pages/finance-management/",
    "apps/kuaizhizao/services/finance/",
    "apps/kuaizhizao/types/finance/",
)
_FINANCE_PORT_BASENAMES = (
    "financeListCore.ts",
    "partnerStatementAmountUtils.ts",
    "pullReceiptFinanceLines.ts",
)
_SHARED_CORE_PREFIXES = (
    "riveredge-backend/src/core/",
    "riveredge-backend/src/infra/",
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def blob_sha(rev: str, path: str) -> str | None:
    """rev:path 的 blob sha；不存在返回 None。"""
    r = git("rev-parse", "--verify", "--quiet", f"{rev}:{path}", check=False)
    return r.stdout.strip() or None if r.returncode == 0 else None


def blob_shas_at(rev: str, paths: list[str]) -> dict[str, str]:
    """一次 ls-tree 批量取 rev 处各 path 的 blob sha（audit 热路径）。"""
    result: dict[str, str] = {}
    # Windows CreateProcess 命令行上限 ~32k，分批防 WinError 206
    for i in range(0, len(paths), 150):
        out = git(
            "ls-tree", "-r", "--format=%(objectname) %(path)",
            rev, "--", *paths[i : i + 150],
        ).stdout
        for line in out.splitlines():
            sha, _, path = line.partition(" ")
            result[path] = sha
    return result


def load_ledger() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    if not LEDGER.exists():
        return rows
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if not parts[0].strip():
            continue
        parts += [""] * (4 - len(parts))
        rows[parts[0]] = parts[1:4]
    return rows


def _sanitize_tsv_note(note: str) -> str:
    return " ".join(str(note or "").replace("\t", " ").splitlines()).strip()


def save_ledger(rows: dict[str, list[str]]) -> None:
    body = "".join(
        f"{p}\t{v[0]}\t{v[1]}\t{_sanitize_tsv_note(v[2])}\n"
        for p, v in sorted(rows.items())
        if p.strip()
    )
    LEDGER.write_text(HEADER + body, encoding="utf-8")


def _warn_domain_out_risk(path: str) -> str | None:
    if any(sub in path for sub in _FINANCE_PORT_SUBSTRINGS) or path.endswith(_FINANCE_PORT_BASENAMES):
        return (
            f"[WARN] {path}: 疑似上游财务路径（本地权威为 apps/kuaicaiwu），"
            "若已异位移植请用 --verdict ported，勿混标 domain-out"
        )
    if path.startswith(_SHARED_CORE_PREFIXES):
        return (
            f"[WARN] {path}: 通用 core/infra 文件被标为 domain-out，"
            "请确认非随客户/财务域误标"
        )
    return None


def is_excluded_artifact(path: str) -> bool:
    """构建产物/依赖目录不入台账（上游 dist 已移出主仓，入册只会产生噪声行）。"""
    p = path.strip().strip('"')
    return "/dist/" in f"/{p}" or p.endswith((".gz", ".br")) or "node_modules/" in p


def changed_paths(frm: str, to: str) -> list[tuple[str, str]]:
    """from..to 的 name-status；返回 (status, to侧路径)。rename 取新路径。"""
    out = git("diff", "--name-status", "-M", frm, to, "--").stdout
    items: list[tuple[str, str]] = []
    for line in out.splitlines():
        cols = line.split("\t")
        if not cols[0]:
            continue
        status = cols[0][0]
        if not is_excluded_artifact(cols[-1]):
            items.append((status, cols[-1]))
    return items


def files_touched_by(commit: str) -> list[str]:
    out = git("show", "--format=", "--name-only", "-M", commit).stdout
    return [l for l in out.splitlines() if l.strip() and not is_excluded_artifact(l)]


def cmd_audit(args: argparse.Namespace) -> int:
    rows = load_ledger()
    buckets: dict[str, list[tuple[str, str]]] = {
        "NEW": [], "REEVAL": [], "DELETED": [], "SKIP": [],
    }
    items = changed_paths(args.frm, args.to)
    live = [p for s, p in items if s != "D" and p in rows]
    shas = blob_shas_at(args.to, live)
    for status, path in items:
        if status == "D":
            if path in rows and rows[path][0] == "DELETED":
                buckets["SKIP"].append((path, rows[path][1]))
            else:
                buckets["DELETED"].append((path, rows.get(path, ["", "?", ""])[1]))
            continue
        if path not in rows:
            buckets["NEW"].append((path, "-"))
            continue
        sha = shas.get(path)
        if sha is None:
            if rows[path][0] == "DELETED":
                buckets["SKIP"].append((path, rows[path][1]))
            else:
                buckets["DELETED"].append((path, rows[path][1]))
        elif sha == rows[path][0]:
            buckets["SKIP"].append((path, rows[path][1]))
        else:
            buckets["REEVAL"].append((path, rows[path][1]))
    for name in ("NEW", "REEVAL", "DELETED", "SKIP"):
        bucket_items = buckets[name]
        breakdown = ""
        if name in ("REEVAL", "SKIP") and bucket_items:
            counts = Counter(v for _, v in bucket_items)
            breakdown = " [" + ", ".join(f"{k}:{counts[k]}" for k in sorted(counts)) + "]"
        print(f"\n== {name} ({len(bucket_items)}){breakdown} ==")
        for path, verdict in bucket_items:
            print(f"  {verdict:>10}  {path}")
    need = len(buckets["NEW"]) + len(buckets["REEVAL"]) + len(buckets["DELETED"])
    print(f"\n需评估 {need}；可跳 {len(buckets['SKIP'])}")
    skip_open = Counter(v for _, v in buckets["SKIP"] if v in ("deferred", "tracked"))
    if skip_open:
        detail = ", ".join(f"{k}={skip_open[k]}" for k in sorted(skip_open))
        print(
            f"[WARN] SKIP 中仍含 {sum(skip_open.values())} 条未闭环行（{detail}），"
            "请核对是否需收口，切勿视同已完成忽略",
            file=sys.stderr,
        )
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    rows = load_ledger()
    added = skipped = 0
    for commit in args.commits:
        for path in files_touched_by(commit):
            if path in rows:
                skipped += 1
                continue
            sha = blob_sha(args.to, path)
            rows[path] = [sha or "DELETED", "tracked", f"seed from {commit[:10]}"]
            added += 1
    save_ledger(rows)
    print(f"seed: +{added} 行，已有 {skipped} 跳过（sha 记自 {args.to[:10]}）")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    rows = load_ledger()
    cleaned_paths: list[str] = []
    for raw in args.paths:
        path = raw.strip()
        if not path or path.startswith("#") or any(ch in path for ch in ("\t", "\r", "\n")):
            print(f"[ERROR] 非法路径（空/注释/含制表符或换行）: {raw!r}", file=sys.stderr)
            return 2
        cleaned_paths.append(path)
    if args.verdict == "deferred":
        missing_note = [
            p for p in cleaned_paths
            if not (args.note.strip() if args.note is not None else (rows.get(p, ["", "", ""])[2].strip()))
        ]
        if missing_note:
            print(
                "[ERROR] verdict=deferred 必须提供非空 --note（写明剩余项或缓置理由，防止局部摘取失踪）",
                file=sys.stderr,
            )
            return 2
    for path in cleaned_paths:
        if args.verdict == "domain-out":
            warn = _warn_domain_out_risk(path)
            if warn:
                print(warn, file=sys.stderr)
        sha = blob_sha(args.to, path)
        old = rows.get(path)
        note = args.note if args.note is not None else (old[2] if old else "")
        rows[path] = [sha or "DELETED", args.verdict, note]
    save_ledger(rows)
    print(f"record: {len(cleaned_paths)} 行 verdict={args.verdict}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("audit", help="区间内变更文件四分类")
    p.add_argument("--from", dest="frm", required=True)
    p.add_argument("--to", required=True)
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser("seed", help="按提交触及文件登记 tracked")
    p.add_argument("--to", required=True)
    p.add_argument("commits", nargs="+")
    p.set_defaults(fn=cmd_seed)

    p = sub.add_parser("record", help="记录单文件判定")
    p.add_argument("--to", required=True)
    p.add_argument("--verdict", required=True, choices=list(VERDICTS))
    p.add_argument("--note", default=None)
    p.add_argument("paths", nargs="+")
    p.set_defaults(fn=cmd_record)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
