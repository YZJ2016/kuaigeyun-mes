"""仓储单据与金蝶对齐红灯（纯规则）。"""

from apps.kuaizhizao.services.warehouse_kingdee_alignment import (
    _summary_mentions_document,
    classify_push_log,
    inventory_pull_block_reason,
)


def test_document_mention_does_not_match_longer_id():
    summary = "sales_delivery/33 → kingdee action=withdraw"
    assert _summary_mentions_document(summary, "sales_delivery", 33)
    assert not _summary_mentions_document(summary, "sales_delivery", 3)


def test_classify_push_and_withdraw():
    assert classify_push_log("sales_delivery/33 → kingdee action=withdraw bill_no=X") == "withdraw"
    assert classify_push_log("sales_delivery/33 → kingdee_im_saloutbill bill_no=X") == "push"
    assert classify_push_log("other_outbound/32 → kingdee action=submit_audit") == "push"


def test_block_posted_without_relation():
    reason = inventory_pull_block_reason(
        label="其他出库",
        code="QTCK1",
        posted=True,
        has_relation=False,
        push_enabled=True,
        last_kind=None,
        last_status=None,
    )
    assert reason and "尚未关联" in reason


def test_block_local_withdraw_kingdee_failed():
    reason = inventory_pull_block_reason(
        label="销售出库",
        code="XSFH1",
        posted=False,
        has_relation=True,
        push_enabled=True,
        last_kind="withdraw",
        last_status="failed",
    )
    assert reason and "金蝶撤回失败" in reason


def test_no_block_when_push_disabled_or_aligned():
    assert (
        inventory_pull_block_reason(
            label="销售出库",
            code="X",
            posted=True,
            has_relation=False,
            push_enabled=False,
            last_kind=None,
            last_status=None,
        )
        is None
    )
    assert (
        inventory_pull_block_reason(
            label="销售出库",
            code="X",
            posted=True,
            has_relation=True,
            push_enabled=True,
            last_kind="push",
            last_status="success",
        )
        is None
    )
