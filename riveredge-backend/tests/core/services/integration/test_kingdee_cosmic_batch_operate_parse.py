"""苍穹 im batch operate 响应解析与幂等文案。"""

import importlib.util
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "src"
_PATH = _SRC / "core/services/integration/kingdee_cosmic_response_status.py"
_spec = importlib.util.spec_from_file_location("kingdee_cosmic_response_status_mod", _PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

extract = _mod.extract_cosmic_response_status
idempotent = _mod.is_im_operate_idempotent_message
is_unsubmit_404 = _mod.is_cosmic_batch_unsubmit_http_404


def test_batch_unaudit_status_true_without_success_count_still_ok():
    payload = {
        "status": True,
        "data": {
            "totalCount": "1",
            "successCount": "0",
            "failCount": "0",
            "result": [{"billno": "PR-001"}],
        },
    }
    ok, _ = extract(payload, im_batch_operate=True)
    assert ok is True


def test_batch_submit_still_fails_when_success_count_zero():
    payload = {
        "status": True,
        "data": {"totalCount": "1", "successCount": "0", "failCount": "0"},
    }
    ok, _ = extract(payload, im_batch_operate=False)
    assert ok is False


def test_idempotent_unaudit_when_already_unaudited():
    assert idempotent("单据处于未审核状态，不能重复反审核", "withdraw") is True


def test_idempotent_unsubmit_when_already_draft():
    assert idempotent("当前单据为暂存状态，无法撤销提交", "unsubmit") is True


def test_idempotent_unaudit_kingdee_not_audited_state():
    assert idempotent("单据非审核态，不能反审核。", "withdraw") is True


def test_unsubmit_http_404_detect():
    msg = (
        "金蝶苍穹接口返回 HTTP 404（苍穹采购入库单批量撤销提交 "
        "kapi/v2/im/im_purinbill/batchUnSubmit）"
    )
    assert is_unsubmit_404(Exception(msg)) is True
