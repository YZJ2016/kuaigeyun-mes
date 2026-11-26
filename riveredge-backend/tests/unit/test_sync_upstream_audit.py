"""sync_upstream_audit.py 台账防漏与分类护栏单测。"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "sync_upstream_audit.py"
    spec = importlib.util.spec_from_file_location("sync_upstream_audit", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_record_ported_and_rejects_blank_path_or_unnoted_deferred(tmp_path, monkeypatch, capsys):
    mod = _load_module()
    ledger = tmp_path / "ledger.tsv"
    monkeypatch.setattr(mod, "LEDGER", ledger)
    monkeypatch.setattr(mod, "blob_sha", lambda rev, path: f"sha_{Path(path).name}")

    # 空路径必须拒绝
    rc = mod.cmd_record(
        argparse.Namespace(to="tip", verdict="applied", note="ok", paths=["  "])
    )
    assert rc == 2
    assert "非法路径" in capsys.readouterr().err

    # deferred 缺少 note 必须拒绝
    rc = mod.cmd_record(
        argparse.Namespace(
            to="tip",
            verdict="deferred",
            note=None,
            paths=["riveredge-backend/src/apps/kuaizhizao/services/purchase_service.py"],
        )
    )
    assert rc == 2
    assert "verdict=deferred" in capsys.readouterr().err

    # ported 正常落账且写入最新 header
    rc = mod.cmd_record(
        argparse.Namespace(
            to="tip",
            verdict="ported",
            note="移植至 apps/kuaicaiwu",
            paths=["riveredge-backend/src/apps/kuaizhizao/finance/models/fund_transfer.py"],
        )
    )
    assert rc == 0
    rows = mod.load_ledger()
    assert rows["riveredge-backend/src/apps/kuaizhizao/finance/models/fund_transfer.py"] == [
        "sha_fund_transfer.py",
        "ported",
        "移植至 apps/kuaicaiwu",
    ]
    assert "ported" in ledger.read_text(encoding="utf-8").splitlines()[2]


def test_record_domain_out_warns_on_finance_and_core_paths(tmp_path, monkeypatch, capsys):
    mod = _load_module()
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "ledger.tsv")
    monkeypatch.setattr(mod, "blob_sha", lambda rev, path: "abc123")

    rc = mod.cmd_record(
        argparse.Namespace(
            to="tip",
            verdict="domain-out",
            note="test",
            paths=[
                "riveredge-backend/src/apps/kuaizhizao/finance/api/finance/fund_transfers.py",
                "riveredge-backend/src/infra/api/business_config/business_config.py",
            ],
        )
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "--verdict ported" in err
    assert "通用 core/infra 文件" in err


def test_audit_prints_breakdown_and_warns_on_open_skip_rows(tmp_path, monkeypatch, capsys):
    mod = _load_module()
    ledger = tmp_path / "ledger.tsv"
    ledger.write_text(
        mod.HEADER
        + "a.py\tsha_old\tapplied\told\n"
        + "b.py\tsha_same\tdeferred\t待补剩余片段\n"
        + "c.py\tsha_old2\tported\t已移植\n"
        + "\tbad_sha\tsuperset\t脏空路径\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "LEDGER", ledger)
    monkeypatch.setattr(
        mod,
        "changed_paths",
        lambda frm, to: [("M", "a.py"), ("M", "b.py"), ("M", "c.py"), ("A", "d.py")],
    )
    monkeypatch.setattr(
        mod,
        "blob_shas_at",
        lambda rev, paths: {"a.py": "sha_new", "b.py": "sha_same", "c.py": "sha_new2"},
    )

    rc = mod.cmd_audit(argparse.Namespace(frm="base", to="tip"))
    assert rc == 0
    captured = capsys.readouterr()
    assert "== NEW (1) ==" in captured.out
    assert "== REEVAL (2) [applied:1, ported:1] ==" in captured.out
    assert "== SKIP (1) [deferred:1] ==" in captured.out
    assert "需评估 3；可跳 1" in captured.out
    assert "SKIP 中仍含 1 条未闭环行（deferred=1）" in captured.err


def test_record_rejects_tab_newline_path_and_sanitizes_note(tmp_path, monkeypatch, capsys):
    mod = _load_module()
    ledger = tmp_path / "ledger.tsv"
    monkeypatch.setattr(mod, "LEDGER", ledger)
    monkeypatch.setattr(mod, "blob_sha", lambda rev, path: "sha_ok")

    rc = mod.cmd_record(
        argparse.Namespace(to="tip", verdict="applied", note="ok", paths=["bad\tpath.py"])
    )
    assert rc == 2
    assert "非法路径" in capsys.readouterr().err

    rc = mod.cmd_record(
        argparse.Namespace(
            to="tip",
            verdict="applied",
            note="line1\tcol2\nline2",
            paths=["good/file.py"],
        )
    )
    assert rc == 0
    rows = mod.load_ledger()
    assert rows["good/file.py"] == ["sha_ok", "applied", "line1 col2 line2"]


def test_audit_marks_recorded_deleted_as_skip(tmp_path, monkeypatch, capsys):
    mod = _load_module()
    ledger = tmp_path / "ledger.tsv"
    ledger.write_text(
        mod.HEADER
        + "gone_recorded.py\tDELETED\tdeleted\t已评估删除\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "LEDGER", ledger)
    monkeypatch.setattr(
        mod,
        "changed_paths",
        lambda frm, to: [("D", "gone_recorded.py"), ("D", "gone_new.py")],
    )
    monkeypatch.setattr(mod, "blob_shas_at", lambda rev, paths: {})

    rc = mod.cmd_audit(argparse.Namespace(frm="base", to="tip"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "== DELETED (1) ==" in out
    assert "== SKIP (1) [deleted:1] ==" in out
    assert "需评估 1；可跳 1" in out

