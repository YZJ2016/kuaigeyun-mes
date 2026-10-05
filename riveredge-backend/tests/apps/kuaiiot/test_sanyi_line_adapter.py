"""三易产线 MQTT 报文适配单元测试。"""

from apps.kuaiiot.services.mqtt_subscriber_service import MqttSubscriberService
from apps.kuaiiot.services.sanyi_line_adapter import (
    convert_device_to_tags,
    is_sanyi_line_payload,
    iter_sanyi_device_ingest,
)
from apps.kuaiiot.tag_templates import TAG_TEMPLATES


SAMPLE = {
    "timestamp": "2026-10-04 11:34:11",
    "workshop": {"id": "w1", "name": "三易自动化车间", "code": "001"},
    "line": {"id": "l1", "name": "一号产线", "code": "cx_001"},
    "devices": [
        {
            "device_id": "f73d622c-0748-4b98-b839-337ad77aa0ee",
            "device_name": "预测机",
            "status": "online",
            "exception": "",
            "timestamp": "2026-10-04 11:34:06",
            "variables": [
                {"variable_code": "hgcl", "variable_name": "合格产量", "value": 15713},
                {"variable_code": "jdl", "variable_name": "稼动率", "value": 77},
            ],
        }
    ],
}


class TestSanyiLineAdapter:
    def test_detect_sanyi_payload(self):
        assert is_sanyi_line_payload(SAMPLE) is True
        assert is_sanyi_line_payload({"tags": {"a": 1}}) is False

    def test_convert_device_tags(self):
        tags = convert_device_to_tags(SAMPLE["devices"][0])
        assert tags["online"] is True
        assert tags["hgcl"] == 15713
        assert tags["jdl"] == 77

    def test_iter_devices(self):
        items = iter_sanyi_device_ingest(SAMPLE)
        assert len(items) == 1
        assert items[0]["external_device_id"] == "f73d622c-0748-4b98-b839-337ad77aa0ee"
        assert items[0]["timestamp"] is not None
        assert items[0]["tags"]["hgcl"] == 15713

    def test_resolve_format_auto(self):
        assert MqttSubscriberService._resolve_format("auto", SAMPLE) == "sanyi_line"
        assert MqttSubscriberService._resolve_format("auto", {"tags": {"a": 1}}) == "kuaiiot"
        assert MqttSubscriberService._resolve_format("kuaiiot", SAMPLE) == "kuaiiot"

    def test_builtin_template_exists(self):
        template = TAG_TEMPLATES["sanyi_plc_line"]
        keys = {item["tag_key"] for item in template["tags"]}
        assert "hgcl" in keys
        assert "jdl" in keys
        assert "online" in keys
