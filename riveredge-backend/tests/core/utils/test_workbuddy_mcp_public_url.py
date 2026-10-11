"""WorkBuddy MCP 公网地址规范化。"""

import pytest
from fastapi import HTTPException

from core.utils.workbuddy_mcp_public_url import (
    normalize_workbuddy_mcp_public_url,
    parse_workbuddy_mcp_public_host,
)


def test_normalize_from_domain():
    assert normalize_workbuddy_mcp_public_url("kuaigeyun.com") == "https://kuaigeyun.com/mcp"


def test_normalize_from_full_url():
    assert normalize_workbuddy_mcp_public_url("https://kuaigeyun.com/mcp") == "https://kuaigeyun.com/mcp"


def test_parse_host_from_stored():
    assert parse_workbuddy_mcp_public_host("https://kuaigeyun.com/mcp") == "kuaigeyun.com"


def test_reject_custom_path():
    with pytest.raises(HTTPException) as exc:
        normalize_workbuddy_mcp_public_url("https://evil.com/other")
    assert "路径" in str(exc.value.detail)
