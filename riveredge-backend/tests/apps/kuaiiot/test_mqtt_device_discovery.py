"""MQTT 现场设备发现测试。"""

from apps.kuaiiot.services.mqtt_device_discovery import extract_devices_from_payload


def test_extract_sanyi_devices():
    payload = {
        "workshop": {"name": "三易自动化车间", "code": "001"},
        "line": {"name": "一号产线", "code": "cx_001"},
        "devices": [
            {
                "device_id": "f73d622c-0748-4b98-b839-337ad77aa0ee",
                "device_name": "观测机",
                "variables": [{"variable_code": "jdl", "value": 77}],
            },
            {
                "device_id": "03cbcccf-d762-44b6-889c-567ef0caf55d",
                "device_name": "焊锡机",
                "variables": [],
            },
        ],
    }
    items = extract_devices_from_payload(payload)
    assert len(items) == 2
    assert items[0]["device_name"] == "观测机"
    assert items[1]["external_device_id"] == "03cbcccf-d762-44b6-889c-567ef0caf55d"
    assert items[0]["line_name"] == "一号产线"


def test_extract_devices_without_variables_key():
    payload = {
        "devices": [
            {"device_id": "aaa-bbb", "device_name": "上料机"},
        ]
    }
    items = extract_devices_from_payload(payload)
    assert items[0]["device_name"] == "上料机"
    assert items[0]["external_device_id"] == "aaa-bbb"


def test_extract_from_truncated_preview_wrapper():
    preview = (
        '{"timestamp": "2026-10-04 15:43:09", "workshop": {"name": "三易自动化车间"}, '
        '"line": {"name": "一号产线"}, "devices": ['
        '{"device_id": "f73d622c-0748-4b98-b839-337ad77aa0ee", "device_name": "预测机", '
        '"device_key": "预测机_f73d622c-0748-4b98-b839-337ad77aa0ee", "variables": ['
    )
    items = extract_devices_from_payload({"truncated": True, "preview": preview})
    assert any(item["device_name"] == "预测机" for item in items)
    assert items[0]["external_device_id"] == "f73d622c-0748-4b98-b839-337ad77aa0ee"


def test_extract_from_truncated_compact_devices():
    payload = {
        "truncated": True,
        "preview": "{",
        "devices": [
            {"device_id": "aaa", "device_name": "上料机"},
            {"device_id": "bbb", "device_name": "焊锡机"},
        ],
    }
    items = extract_devices_from_payload(payload)
    assert [item["device_name"] for item in items] == ["上料机", "焊锡机"]
