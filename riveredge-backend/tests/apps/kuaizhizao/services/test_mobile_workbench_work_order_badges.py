"""工作台「我的工单」与「全部工单」须用不同 badge_key，禁止共用全量计数。"""

import json
from pathlib import Path

import pytest

from apps.kuaizhizao.models.work_order_operation import work_order_ids_assigned_to_worker

_MANIFEST = Path(__file__).resolve().parents[4] / "src" / "apps" / "kuaizhizao" / "manifest.json"


def _workshop_entries() -> list[dict]:
    data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    sections = data["mobile_workbench"]["scopes"]["workshop"]["sections"]
    entries: list[dict] = []
    for section in sections:
        entries.extend(section.get("entries") or [])
    return entries


def test_manifest_my_work_orders_badge_is_not_all_work_orders():
    by_key = {e["key"]: e for e in _workshop_entries()}
    assert by_key["my-work-orders"]["badge_key"] == "my_work_order"
    assert by_key["work-orders"]["badge_key"] == "work_order"


@pytest.mark.asyncio
async def test_assigned_worker_ids_empty_without_worker():
    assert await work_order_ids_assigned_to_worker(tenant_id=1, worker_id=0) == set()
