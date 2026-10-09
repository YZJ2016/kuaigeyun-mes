from apps.kuaiplm.constants.rd_project_system_archive import SYSTEM_ARCHIVE_TOTAL_COUNT
from apps.kuaiplm.utils.system_archive_capabilities import compute_system_archive_capabilities


def test_capabilities_empty():
    caps = compute_system_archive_capabilities(None)
    assert not caps["checklist_ready"]


def test_capabilities_progression():
    summary = {
        "total": SYSTEM_ARCHIVE_TOTAL_COUNT,
        "filled": 0,
        "missing_marked": 0,
        "complete": False,
        "all_accepted": False,
    }
    caps = compute_system_archive_capabilities(summary)
    assert caps["checklist_ready"]
    assert not caps["upload_link_started"]

    summary["filled"] = 3
    caps = compute_system_archive_capabilities(summary)
    assert caps["upload_link_started"]

    summary["filled"] = SYSTEM_ARCHIVE_TOTAL_COUNT
    summary["complete"] = True
    caps = compute_system_archive_capabilities(summary)
    assert caps["checklist_complete"]

    summary["all_accepted"] = True
    caps = compute_system_archive_capabilities(summary)
    assert caps["all_accepted"]
