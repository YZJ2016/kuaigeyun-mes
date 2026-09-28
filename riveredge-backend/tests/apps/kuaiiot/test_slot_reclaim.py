"""spec 150：槽位收归，只去掉 kuaiiot 的忽略与专业包名单。"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_slot_reclaim_keeps_edge_agent_and_other_apps():
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    ignored = [line.strip() for line in gitignore.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert "riveredge-backend/src/apps/kuaiiot/" not in ignored
    assert "riveredge-frontend/src/apps/kuaiiot/" not in ignored
    assert "riveredge-backend/src/apps/kuaireport/" not in ignored
    assert "riveredge-frontend/src/apps/kuaireport/" not in ignored
    assert "riveredge-backend/src/apps/haoligo/" in ignored
    assert "riveredge-frontend/src/apps/haoligo/" in ignored
    assert "riveredge-backend/src/apps/funide_oa/" in ignored
    assert "riveredge-frontend/src/apps/funide-oa/" in ignored
    assert "apps/kuaiiot 槽位收归本仓" in gitignore

    workspace = (REPO / "fast-deploy/tools/workspace/generate_workspace.py").read_text(encoding="utf-8")
    assert 'PRO_APPS = ["kuaiai"]' in workspace
    assert "kuaiiot" not in workspace
    assert "kuaireport" not in workspace

    assert (REPO / "riveredge-backend/src/apps/kuaiiot/edge-agent/agent.py").is_file()
    backend_manifest = (REPO / "riveredge-backend/src/apps/kuaiiot/manifest.json").read_text(encoding="utf-8")
    frontend_manifest = (REPO / "riveredge-frontend/src/apps/kuaiiot/manifest.json").read_text(encoding="utf-8")
    assert '"code": "kuaiiot"' in backend_manifest
    assert '"code": "kuaiiot"' in frontend_manifest
