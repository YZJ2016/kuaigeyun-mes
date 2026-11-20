"""采购入库苍穹撤销绑定解析。"""

from apps.kuaiconnect.services.document_push.kingdee_purchase_receipt_revoke_service import (
    _action_apis_from_targets,
)


def test_action_apis_from_targets_merges_rows():
    targets = [
        {
            "target_profile": "kingdee_im_purinbill",
            "action_apis": {"confirm": "uuid-add", "withdraw": "uuid-unaudit"},
        },
        {
            "target_profile": "kingdee_im_purinbill",
            "action_apis": {"unsubmit": "uuid-unsubmit", "delete": "uuid-delete"},
        },
    ]
    merged = _action_apis_from_targets(targets)
    assert merged["confirm"] == "uuid-add"
    assert merged["withdraw"] == "uuid-unaudit"
    assert merged["unsubmit"] == "uuid-unsubmit"
    assert merged["delete"] == "uuid-delete"

