import importlib.util
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "src"
_PATHS = _SRC / "core/services/integration/kingdee_cosmic_paths.py"
_spec = importlib.util.spec_from_file_location("kingdee_cosmic_paths_mod", _PATHS)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
normalize = _mod.normalize_kingdee_cosmic_api_path
strip_base = _mod.strip_kingdee_cosmic_ierp_suffix_from_base


def test_strip_ierp_suffix_from_base():
    assert strip_base("https://tenant.kdgalaxy.com/ierp") == "https://tenant.kdgalaxy.com"
    assert strip_base("https://tenant.kdgalaxy.com") == "https://tenant.kdgalaxy.com"


def test_cosmic_url_no_double_ierp():
    base = strip_base("https://tenant.kdgalaxy.com/ierp")
    path = normalize("ierp/kapi/sys/bd_material/query")
    url = f"{base}/{path.lstrip('/')}"
    assert url == "https://tenant.kdgalaxy.com/ierp/kapi/sys/bd_material/query"


def test_normalize_sys_query_adds_ierp_prefix():
    assert normalize("kapi/sys/bd_material/query") == "ierp/kapi/sys/bd_material/query"
    assert normalize("ierp/kapi/sys/bd_material/query") == "ierp/kapi/sys/bd_material/query"


def test_rewrite_saved_supplier_sys_query_to_batch_query():
    rewrite = _mod.rewrite_basedata_sys_query_path
    assert rewrite("kapi/sys/bd_supplier/query") == "kapi/v2/basedata/bd_supplier/query"
    assert rewrite("kapi/v2/basedata/bd_supplier/batchQuery") == "kapi/v2/basedata/bd_supplier/batchQuery"
    assert rewrite("kapi/sys/bd_customer/query") == "kapi/v2/basedata/bd_customer/batchQuery"
    assert rewrite("kapi/sys/bd_warehouse/query") == "kapi/v2/sbd/bd_warehouse/getList"


def test_normalize_cosmic_openapi_endpoint_fixes_v2_prefix():
    norm = _mod.normalize_cosmic_openapi_endpoint
    assert norm("v2/basedata/bd_supplier/query") == "kapi/v2/basedata/bd_supplier/query"
    assert norm("kapi/v2/basedata/b") == "kapi/v2/basedata/bd_supplier/query"


def test_is_kingdee_cosmic_supplier_query_path_excludes_group_and_custom():
    """裸子串 bd_supplier 会误伤 suppliergroup / pbdfl；须按路径段判断。"""
    is_sup = _mod.is_kingdee_cosmic_supplier_query_path
    assert is_sup("kapi/v2/basedata/bd_supplier/query") is True
    assert is_sup("kapi/v2/basedata/bd_supplier/batchQuery") is True
    assert is_sup("kapi/v2/basedata/b") is True
    assert is_sup("kapi/v2/basedata/bd_suppliergroup/query") is False
    assert is_sup("kapi/v2/basedata/bd_suppliercommon/batchQuery") is False
    assert is_sup("api/v2/k6s3/basedata/bd_supplier/pbdfl/query") is False
    assert is_sup("kapi/v2/fd81/basedata/bd_supplier/getsupplier") is False
    assert is_sup("kapi/v2/basedata/bd_address/query") is False


def test_supplier_group_query_requires_star_markers_when_empty():
    from core.services.integration.kingdee_cosmic_api_presets import (
        kingdee_supplier_group_api_upgrade_fields,
        supplier_group_preset_needs_upgrade,
    )

    path = "kapi/v2/basedata/bd_suppliergroup/query"
    assert supplier_group_preset_needs_upgrade(path, "POST", {"data": {}, "pageNo": 1, "pageSize": 100})
    assert supplier_group_preset_needs_upgrade(
        path, "POST", {"data": {"number": "", "name": ""}, "pageNo": 1, "pageSize": 100}
    )
    assert not supplier_group_preset_needs_upgrade(
        path,
        "POST",
        {"data": {"number": "*", "name": "*"}, "pageNo": 1, "pageSize": 1000},
    )
    fields = kingdee_supplier_group_api_upgrade_fields()
    assert fields["request_body"]["data"]["number"] == "*"
    assert fields["request_body"]["data"]["name"] == "*"


def test_customer_group_and_address_and_project_upgrades():
    from core.services.integration.kingdee_cosmic_api_presets import (
        address_query_preset_needs_upgrade,
        customer_group_preset_needs_upgrade,
        kingdee_address_query_api_upgrade_fields,
        kingdee_customer_group_api_upgrade_fields,
        kingdee_project_getlist_api_upgrade_fields,
        project_getlist_preset_needs_upgrade,
    )

    cg = "kapi/v2/basedata/bd_customergroup/query"
    assert customer_group_preset_needs_upgrade(
        cg, "POST", {"data": {"id": "", "number": ""}, "pageNo": 1, "pageSize": 100}
    )
    assert not customer_group_preset_needs_upgrade(
        cg, "POST", {"data": {"number": "*", "name": "*"}, "pageNo": 1, "pageSize": 100}
    )
    assert kingdee_customer_group_api_upgrade_fields()["request_body"]["data"]["number"] == "*"

    addr = "kapi/v2/basedata/bd_address/query"
    assert address_query_preset_needs_upgrade(addr, "POST", {"data": {}, "pageNo": 1, "pageSize": 100})
    assert not address_query_preset_needs_upgrade(
        "kapi/v2/basedata/bd_address/queryAddress", "POST", {"data": {}}
    )
    assert kingdee_address_query_api_upgrade_fields()["request_body"]["data"]["supplierid"] == "*"

    proj = "kapi/v2/basedata/bd_project/getList"
    assert project_getlist_preset_needs_upgrade(proj, "POST", {"data": {}})
    assert kingdee_project_getlist_api_upgrade_fields()["request_body"]["data"]["useorg_number"] == "*"


def test_strip_blank_filters_from_v2_query_data():
    strip = _mod.strip_blank_filters_from_v2_query_data
    url = "https://x/kapi/v2/basedata/bd_multimeasureunit/batchQuery"
    out = strip(
        url,
        {
            "data": {"id": "", "materialid_id": "", "status": "C", "tags": []},
            "pageNo": 1,
            "pageSize": 5,
        },
    )
    assert out["data"] == {"status": "C"}
    # 写操作不剥
    write_url = "https://x/kapi/v2/basedata/bd_material/batchAdd"
    body = {"data": [{"id": ""}]}
    assert strip(write_url, body)["data"] == [{"id": ""}]


def test_strip_invalid_base_url_suffix():
    strip = _mod.strip_invalid_kingdee_cosmic_base_url_suffix
    assert (
        strip("https://lzhtech.test.kdgalaxy.com/kapi/v2/basedata/b")
        == "https://lzhtech.test.kdgalaxy.com"
    )


def test_normalize_oauth_path_unchanged():
    assert normalize("kapi/oauth2/getToken") == "kapi/oauth2/getToken"


def test_v2_body_wraps_data_when_missing():
    ensure = _mod.ensure_kingdee_v2_request_body
    url = "https://lzhtech.kdgalaxy.com/kapi/v2/basedata/bd_material/batchQuery"
    assert ensure(url, {}) == {"data": {}, "pageNo": 1, "pageSize": 100}
    assert ensure(url, {"data": {"number": ["A"]}, "pageSize": 20}) == {
        "data": {"number": ["A"]},
        "pageNo": 1,
        "pageSize": 20,
    }
    assert ensure("https://lzhtech.kdgalaxy.com/kapi/oauth2/getToken", {"client_id": "a"}) == {
        "client_id": "a"
    }


def test_v2_query_and_batchequery_also_get_paging():
    ensure = _mod.ensure_kingdee_v2_request_body
    assert ensure("https://x/kapi/v2/sm/sm_salorder/query", {}) == {
        "data": {},
        "pageNo": 1,
        "pageSize": 100,
    }
    assert ensure("https://x/kapi/v2/im/im_mdc_mftfeedorder/batcheQuery", {"data": {}}) == {
        "data": {},
        "pageNo": 1,
        "pageSize": 100,
    }
    # 写操作不塞分页
    assert ensure("https://x/kapi/v2/sm/sm_salorder/batchSubmit", {"data": []}) == {"data": []}


def test_v2_inventory_params_body_not_wrapped_as_data():
    ensure = _mod.ensure_kingdee_v2_request_body
    body = {"params": {"org": "100"}, "pageNo": 1, "pageSize": 100}
    assert ensure("https://x/kapi/v2/im/getInventoryDetail", body) == body
    assert ensure(
        "https://x/kapi/v2/im/getInventoryAvbQty", {"params": {"org": "100"}}
    ) == {
        "params": {"org": "100"},
        "pageNo": 1,
        "pageSize": 100,
    }
    assert ensure("https://x/kapi/v2/im/getInventorySum", {"params": {"org": "100"}}) == {
        "params": {"org": "100"},
        "pageNo": 1,
        "pageSize": 100,
    }
    # 旧错误包法应还原
    assert ensure(
        "https://x/kapi/v2/im/getInventoryDetail",
        {"data": {"params": {"org": "100"}}, "pageNo": 1, "pageSize": 100},
    ) == {"params": {"org": "100"}, "pageNo": 1, "pageSize": 100}


def test_inventory_avb_qty_fills_params_org_from_connector_when_placeholder():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {"org_number": "ORG-88"},
        "https://x/kapi/v2/im/getInventoryAvbQty",
        "POST",
        {},
        {
            "params": {"org": "<库存组织编码，如 100>"},
            "pageNo": 1,
            "pageSize": 200,
        },
    )
    assert method == "POST"
    assert url.endswith("/im/getInventoryAvbQty")
    assert body["params"]["org"] == "ORG-88"
    assert body["pageSize"] == 200


def test_warehouse_list_query_rewrites_to_getlist_and_injects_org():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {"org_number": "BU-00001"},
        "https://x/kapi/v2/basedata/bd_warehouse/query",
        "GET",
        {},
        {"data": {}, "pageNo": 1, "pageSize": 1000},
    )
    assert method == "POST"
    assert url.endswith("/sbd/bd_warehouse/getList")
    assert body == {
        "data": {"createorg_number": "BU-00001"},
        "pageNo": 1,
        "pageSize": 1000,
    }


def test_warehouse_batchquery_rewrites_to_getlist_without_inventing_org():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {},
        "https://x/kapi/v2/basedata/bd_warehouse/batchQuery",
        "POST",
        {},
        {"data": {}, "pageNo": 1, "pageSize": 1000},
    )
    assert method == "POST"
    assert url.endswith("/sbd/bd_warehouse/getList")
    assert body["data"] == {}
    assert body["pageSize"] == 1000


def test_warehouse_getlist_keeps_body_createorg_when_connector_org_missing():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {},
        "https://x/kapi/v2/sbd/bd_warehouse/getList",
        "POST",
        {},
        {"data": {"createorg_number": "ORG01"}, "pageNo": 1, "pageSize": 1000},
    )
    assert method == "POST"
    assert url.endswith("/sbd/bd_warehouse/getList")
    assert body["data"]["createorg_number"] == "ORG01"
    assert body["pageSize"] == 1000


def test_warehouse_getlist_prefers_connector_org_over_preset_example():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {"org_number": "BU-00001"},
        "https://x/kapi/v2/sbd/bd_warehouse/getList",
        "POST",
        {},
        {"data": {"createorg_number": "BU-00000"}, "pageNo": 1, "pageSize": 1000},
    )
    assert method == "POST"
    assert url.endswith("/sbd/bd_warehouse/getList")
    assert body["data"]["createorg_number"] == "BU-00001"


def test_outbound_replace_org_placeholders_from_connector():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {"org_number": "BU-00001"},
        "https://x/kapi/v2/im/im_purinbill/add",
        "POST",
        {},
        {
            "data": {
                "org_number": "REPLACE_ORG",
                "bizorg_number": "REPLACE_ORG",
                "billentry": [{"entrysettleorg_number": "REPLACE_ORG"}],
            }
        },
    )
    assert method == "POST"
    assert body["data"]["org_number"] == "BU-00001"
    assert body["data"]["bizorg_number"] == "BU-00001"
    assert body["data"]["billentry"][0]["entrysettleorg_number"] == "BU-00001"


def test_warehouse_query_with_number_keeps_basedata_query_and_injects_param():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {"org_number": "BU-00000"},
        "https://x/kapi/v2/basedata/bd_warehouse/query",
        "GET",
        {"number": "CK01"},
        {},
    )
    assert method == "GET"
    assert url.endswith("/bd_warehouse/query")
    assert params["createorg_number"] == "BU-00000"
    assert params["number"] == "CK01"


def test_warehouse_getlist_fills_missing_createorg_from_connector():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    method, url, params, body = prepare(
        {"org_number": "BU-00001"},
        "https://x/kapi/v2/sbd/bd_warehouse/getList",
        "POST",
        {},
        {"data": {}, "pageNo": 1, "pageSize": 1000},
    )
    assert url.endswith("/sbd/bd_warehouse/getList")
    assert body["data"]["createorg_number"] == "BU-00001"


def test_project_row_by_select_reads_nested_group_and_baseunit():
    project = _mod.project_row_by_select
    row = {
        "number": "M001",
        "name": "螺丝",
        "modelnum": "M8",
        "baseunit": {"number": "kg", "name": "KG"},
        "group": {"number": "G01", "name": "紧固件"},
    }
    select = (
        "number,name,modelnum,baseunit.number,baseunit.name,group.number,group.name"
    ).split(",")
    out = project(row, select)
    assert out["number"] == "M001"
    assert out["name"] == "螺丝"
    assert out["modelnum"] == "M8"
    assert out["baseunit_number"] == "kg"
    assert out["baseunit_name"] == "KG"
    assert out["group_number"] == "G01"
    assert out["group_name"] == "紧固件"
    # 不得把 baseunit.number 误匹配成物料 number 后丢掉嵌套
    assert out.get("baseunit") is None


def test_material_batchquery_strips_blank_checkbox_filters():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    _, _, _, body = prepare(
        {"org_number": "BU-00001"},
        "https://x/kapi/v2/basedata/bd_material/batchQuery",
        "POST",
        {},
        {
            "data": {
                "id": "",
                "number": "",
                "status": "C",
                "createorg_number": 100,
                "start_createtime": "",
            },
            "pageNo": 1,
            "pageSize": 1000,
        },
    )
    assert body["data"] == {"status": "C"}


def test_material_group_batchquery_strips_createorg_and_blank_filters():
    """物料分类 batchQuery 与物料同契约：剥离 createorg 与空筛选项。"""
    prepare = _mod.prepare_kingdee_cosmic_outbound
    _, _, _, body = prepare(
        {"org_number": "100"},
        "https://x/kapi/v2/basedata/bd_materialgroup/batchQuery",
        "POST",
        {},
        {
            "data": {
                "id": "",
                "number": "",
                "status": "C",
                "createorg_number": 100,
                "start_createtime": "",
            },
            "pageNo": 1,
            "pageSize": 1000,
        },
    )
    assert body["data"] == {"status": "C"}


def test_material_batchquery_strips_createorg_from_top_level_and_params():
    prepare = _mod.prepare_kingdee_cosmic_outbound
    _, _, params, body = prepare(
        {"org_number": "BU-00001"},
        "https://x/kapi/v2/basedata/bd_material/batchQuery",
        "POST",
        {"createorg_number": "BU-00001", "select": "number"},
        {
            "createorg_number": "BU-00001",
            "data": {"createorg_number": ["BU-00001"]},
            "pageNo": 1,
            "pageSize": 100,
            "select": "number",
        },
    )
    assert "createorg_number" not in params
    assert "createorg_number" not in body
    assert "createorg_number" not in body.get("data", {})
