from apps.kuaizhizao.services.mobile_workbench import (
    MOBILE_WORKBENCH_BADGE_PENDING_ONLY_KEYS,
    _open_badge_count,
    apply_workbench_badge_counts,
)


def test_open_badge_count_pending_only_skips_in_progress():
    triple = {"overdue": 0, "pending": 2, "in_progress": 9}
    assert _open_badge_count(triple) == 11
    assert _open_badge_count(triple, pending_only=True) == 2


def test_apply_workbench_badge_purchase_requisition_pending_only():
    sections = [
        {
            "key": "common",
            "title": "",
            "entries": [
                {
                    "key": "purchase-requisitions",
                    "label": "采购申请",
                    "route": "/docs/purchase-requisitions",
                    "icon": "app",
                    "_badge_keys": ["purchase_requisition"],
                }
            ],
        }
    ]
    counts = {"purchase_requisition": {"overdue": 0, "pending": 0, "in_progress": 9}}
    out = apply_workbench_badge_counts(
        sections,
        counts,
        pending_only_keys=MOBILE_WORKBENCH_BADGE_PENDING_ONLY_KEYS,
    )
    assert out[0]["entries"][0]["badge_count"] == 0
