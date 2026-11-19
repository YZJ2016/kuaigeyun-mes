"""仓储苍穹出站：Save 接口样例头字段解析。"""

import importlib.util
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "src"
_PATH = _SRC / "core/services/integration/kingdee_warehouse_document_push_config.py"
_spec = importlib.util.spec_from_file_location("kingdee_warehouse_push_cfg_mod", _PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_header_row_from_save_api_body = _mod._header_row_from_save_api_body
_apply_entry_fallback_fields = _mod._apply_entry_fallback_fields
purinbill_save_sample_has_real_codes = _mod.purinbill_save_sample_has_real_codes
read_kingdee_push_workflow_bool = _mod.read_kingdee_push_workflow_bool
finalize_kingdee_warehouse_im_push_config = _mod.finalize_kingdee_warehouse_im_push_config
merge_warehouse_kingdee_push_config = _mod.merge_warehouse_kingdee_push_config


def test_header_row_unwraps_data_dict_purinbill_add():
    body = {
        "data": {
            "billtype_number": "im_PurInBill_STD_BT_S",
            "biztype_number": "110",
            "invscheme_number": "110",
            "billentry": [
                {
                    "linetype_number": "010",
                    "invstatus_number": "110",
                    "invtype_number": "110",
                }
            ],
        }
    }
    row = _header_row_from_save_api_body(body)
    assert row is not None
    assert row["billtype_number"] == "im_PurInBill_STD_BT_S"
    assert row["biztype_number"] == "110"


def test_header_row_unwraps_data_list_salout_batch_add():
    body = {
        "data_list": [
            {
                "billtype_number": "im_SalOutBill_STD_BT_S",
                "biztype_number": "210",
                "billentry": [{"linetype_number": "010"}],
            }
        ]
    }
    row = _header_row_from_save_api_body(body)
    assert row is not None
    assert row["billtype_number"] == "im_SalOutBill_STD_BT_S"


def test_header_row_skips_replace_via_entry_fallback():
    out: dict = {}
    row = {
        "billtype_number": "im_PurInBill_STD_BT_S",
        "billentry": [
            {
                "linetype_number": "REPLACE_LINETYPE",
                "invstatus_number": "110",
                "invtype_number": "110",
            }
        ],
    }
    _apply_entry_fallback_fields(out, row)
    assert out.get("linetype_number") is None
    assert out["invstatus_number"] == "110"
    assert out["invtype_number"] == "110"


def test_purinbill_sample_with_real_billtype_is_kept():
    body = {
        "data": {
            "billtype_number": "im_PurInBill_STD_BT_S",
            "biztype_number": "110",
            "billentry": [{"linetype_number": "010", "invstatus_number": "110"}],
        }
    }
    assert purinbill_save_sample_has_real_codes(body) is True


def test_purinbill_replace_placeholder_sample_is_not_real():
    body = {
        "data": {
            "billtype_number": "REPLACE_BILLTYPE",
            "biztype_number": "REPLACE_BIZTYPE",
            "invscheme_number": "REPLACE_INVSCHEME",
            "billentry": [
                {
                    "invstatus_number": "REPLACE_INVSTATUS",
                    "invtype_number": "REPLACE_INVTYPE",
                    "linetype_number": "REPLACE_LINETYPE",
                }
            ],
        }
    }
    assert purinbill_save_sample_has_real_codes(body) is False


def test_read_kingdee_push_workflow_bool_null_means_default_true():
    cfg = {"submit_after_save": None, "audit_after_save": None}
    assert read_kingdee_push_workflow_bool(cfg, "submit_after_save", default=True) is True
    assert read_kingdee_push_workflow_bool(cfg, "audit_after_save", default=True) is True
    assert read_kingdee_push_workflow_bool(cfg, "submit_after_save", default=False) is False


def test_read_kingdee_push_workflow_bool_explicit_false():
    cfg = {"submit_after_save": False}
    assert read_kingdee_push_workflow_bool(cfg, "submit_after_save", default=True) is False


def test_finalize_im_push_config_sets_salout_defaults():
    out = finalize_kingdee_warehouse_im_push_config(
        {},
        default_submit_path="kapi/v2/im/im_saloutbill/batchSubmit",
        default_audit_path="kapi/v2/im/im_saloutbill/batchAudit",
        default_body_wrap="data_list",
    )
    assert out["submit_after_save"] is True
    assert out["body_wrap"] == "data_list"
    assert "batchSubmit" in out["submit_path"]


def test_strip_std_other_outbill_for_production_picking():
    is_std = _mod.is_standard_other_outbill_billtype
    strip = _mod.strip_mismatched_std_document_types
    assert is_std("im_OtherOutBill_STD_BT_S")
    assert not is_std("im_otheroutbill_BT")
    out = strip(
        {
            "billtype_number": "im_OtherOutBill_STD_BT_S",
            "biztype_number": "355",
        },
        expected_related_document="production_picking",
    )
    assert "billtype_number" not in out
    assert out["biztype_number"] == "355"


validate_im_operate_api_path = _mod.validate_im_operate_api_path


def test_validate_im_operate_rejects_add2_path():
    import pytest
    from infra.exceptions.exceptions import BusinessLogicError

    with pytest.raises(BusinessLogicError, match="batchUnaudit"):
        validate_im_operate_api_path(
            "kapi/v2/fd81/im/im_purinbill/add2",
            "withdraw",
        )


def test_validate_im_operate_accepts_batch_unaudit():
    validate_im_operate_api_path(
        "kapi/v2/im/im_purinbill/batchUnaudit",
        "withdraw",
    )
