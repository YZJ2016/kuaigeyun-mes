import importlib.util
from pathlib import Path

_path = (
    Path(__file__).resolve().parents[3]
    / "src/core/services/im/im_module_notify_ref.py"
)
_spec = importlib.util.spec_from_file_location("im_module_notify_ref", _path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
resolve_module_notify_ref_id = _mod.resolve_module_notify_ref_id


def test_operation_completed_ref_id_shared_across_recipients():
    variables = {
        "work_order_id": "42",
        "completed_operation_name": "下料",
        "next_operation_name": "热处理",
    }
    a = resolve_module_notify_ref_id(
        message_log_uuid="uuid-a",
        business_document="work_order",
        business_action="operation_completed",
        variables=variables,
    )
    b = resolve_module_notify_ref_id(
        message_log_uuid="uuid-b",
        business_document="work_order",
        business_action="operation_completed",
        variables=variables,
    )
    assert a == b
    assert a == "work_order:operation_completed:42:下料:热处理"


def test_falls_back_to_message_log_uuid_without_business_key():
    ref = resolve_module_notify_ref_id(message_log_uuid="only-this")
    assert ref == "only-this"
