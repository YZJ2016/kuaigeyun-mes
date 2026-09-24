"""KU-AI S4 单测：MCP 白名单守卫（KR-D11，services/mcp_guard）。

全部纯函数 + socket.getaddrinfo mock，不需要真实 DNS/数据库。覆盖：
- require_http_transport：仅 http；空值归一 http；stdio/sse/websocket 400
- is_forbidden_sql_tool：黑名单名、*_query 后缀、execute_sql/run_sql 子串、
  空名失败关闭
- parse_allowed_tools：CSV 去空白去重保序
- is_tool_allowed：非黑名单且命中 CSV；空名单/黑名单名拒绝
- require_allowed_tools：空名单 400、SQL 类名 400、合法名单归一化
- require_safe_http_url：仅 http/https、禁 userinfo、禁 localhost/metadata
  主机名、非法端口 400、DNS 不可解析/非 gaierror OSError 400、回环/
  链路本地/组播/云元数据地址 400（含 v4-mapped/v4-compatible IPv6 入径）、
  RFC1918 内网与公网地址放行
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from apps.kuaiai.services.mcp_guard import (
    is_forbidden_sql_tool,
    is_tool_allowed,
    parse_allowed_tools,
    require_allowed_tools,
    require_http_transport,
    require_safe_http_url,
)
from infra.exceptions.exceptions import BusinessLogicError


def _fake_getaddrinfo(mapping):
    """伪造 socket.getaddrinfo：mapping host→IP 列表或异常实例。"""

    def _resolve(host, port, *args, **kwargs):
        value = mapping.get(host)
        if value is None:
            raise socket.gaierror(-2, "Name or service not known")
        if isinstance(value, Exception):
            raise value
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 80)) for ip in value]

    return _resolve


# ------------------------------------------------------------ transport


class TestRequireHttpTransport:
    def test_none_and_blank_normalize_to_http(self):
        assert require_http_transport(None) == "http"
        assert require_http_transport("") == "http"
        assert require_http_transport("   ") == "http"

    def test_http_ok(self):
        assert require_http_transport("http") == "http"
        assert require_http_transport("HTTP") == "http"

    def test_other_transports_400(self):
        for bad in ("stdio", "sse", "websocket", "streamable_http"):
            with pytest.raises(BusinessLogicError) as exc:
                require_http_transport(bad)
            assert exc.value.status_code == 400


# ------------------------------------------------------- SQL 工具名黑名单


class TestIsForbiddenSqlTool:
    def test_blacklist_names(self):
        for name in (
            "execute_sql_query",
            "query_all_tables",
            "execute_sql",
            "sql_query",
            "run_sql",
            "query_database",
            "query_sql",
            "query",
            "list_tables",
            "read_query",
        ):
            assert is_forbidden_sql_tool(name) is True

    def test_query_suffix_and_substring_rules(self):
        assert is_forbidden_sql_tool("custom_order_query") is True  # *_query
        assert is_forbidden_sql_tool("execute_sql_v2") is True  # execute_sql 子串
        assert is_forbidden_sql_tool("my_run_sql_tool") is True  # run_sql 子串
        assert is_forbidden_sql_tool("  Execute_Sql  ") is True  # 大小写/空白归一

    def test_normalization_bypass_variants(self):
        """m3：NFKC + 去空白/_/- 规范化，防双空格/CamelCase/全角同形绕过。"""
        assert is_forbidden_sql_tool("execute  sql") is True  # 双空格
        assert is_forbidden_sql_tool("executeSql") is True  # CamelCase
        assert is_forbidden_sql_tool("run-sql") is True  # 连字符归一
        assert is_forbidden_sql_tool("ｅｘｅｃｕｔｅ＿ｓｑｌ") is True  # 全角同形
        assert is_forbidden_sql_tool("listtables") is True  # 黑名单去 _ 等价
        assert is_forbidden_sql_tool("myquery") is True  # 规范化后 *query 后缀

    def test_empty_name_fails_closed(self):
        assert is_forbidden_sql_tool(None) is True
        assert is_forbidden_sql_tool("") is True
        assert is_forbidden_sql_tool("   ") is True

    def test_normal_names_allowed(self):
        assert is_forbidden_sql_tool("search_knowledge") is False
        assert is_forbidden_sql_tool("query_workorder") is False  # 不以 _query 结尾
        assert is_forbidden_sql_tool("get_weather") is False


# --------------------------------------------------------- allowed_tools


class TestParseAllowedTools:
    def test_csv_strip_dedupe_keep_order(self):
        assert parse_allowed_tools(" a , b ,,a,c ") == ["a", "b", "c"]

    def test_empty_inputs(self):
        assert parse_allowed_tools(None) == []
        assert parse_allowed_tools("") == []
        assert parse_allowed_tools(" , , ") == []


class TestIsToolAllowed:
    def test_member_hit(self):
        assert is_tool_allowed("a,b", "a") is True
        assert is_tool_allowed("a,b", " b ") is True

    def test_not_member_or_empty_list(self):
        assert is_tool_allowed("a,b", "c") is False
        assert is_tool_allowed("", "a") is False
        assert is_tool_allowed(None, "a") is False

    def test_forbidden_name_always_rejected(self):
        assert is_tool_allowed("execute_sql,a", "execute_sql") is False
        assert is_tool_allowed("a", "") is False


class TestRequireAllowedTools:
    def test_empty_400(self):
        for bad in (None, "", " , ,"):
            with pytest.raises(BusinessLogicError) as exc:
                require_allowed_tools(bad)
            assert exc.value.status_code == 400

    def test_sql_tool_name_400(self):
        with pytest.raises(BusinessLogicError) as exc:
            require_allowed_tools("search_knowledge,execute_sql")
        assert exc.value.status_code == 400
        assert "execute_sql" in str(exc.value)

    def test_legal_list_normalized(self):
        assert require_allowed_tools(" a ,b ,,a ") == "a,b"


# --------------------------------------------------------- endpoint URL


class TestRequireSafeHttpUrl:
    def test_happy_path_public_http_https(self):
        dns = _fake_getaddrinfo({"mcp.example.com": ["93.184.216.34"]})
        with patch("socket.getaddrinfo", side_effect=dns):
            assert (
                require_safe_http_url("  http://mcp.example.com/mcp  ")
                == "http://mcp.example.com/mcp"
            )
            assert (
                require_safe_http_url("https://mcp.example.com:8443/sse")
                == "https://mcp.example.com:8443/sse"
            )

    def test_rfc1918_private_allowed(self):
        """内网 RFC1918 段放行（企业内部 MCP server 是合法部署形态）。"""
        dns = _fake_getaddrinfo({"mes-mcp.internal": ["10.20.30.40"]})
        with patch("socket.getaddrinfo", side_effect=dns):
            assert require_safe_http_url("http://mes-mcp.internal/mcp") == (
                "http://mes-mcp.internal/mcp"
            )

    def test_empty_or_no_host_400(self):
        with pytest.raises(BusinessLogicError):
            require_safe_http_url("")
        with pytest.raises(BusinessLogicError):
            require_safe_http_url(None)
        with pytest.raises(BusinessLogicError):
            require_safe_http_url("http://")

    def test_non_http_scheme_400(self):
        for bad in (
            "ftp://mcp.example.com/",
            "file:///etc/passwd",
            "mcp.example.com/mcp",  # 无 scheme
            "ws://mcp.example.com/",
        ):
            with pytest.raises(BusinessLogicError) as exc:
                require_safe_http_url(bad)
            assert exc.value.status_code == 400

    def test_userinfo_400(self):
        with pytest.raises(BusinessLogicError):
            require_safe_http_url("http://user:pass@mcp.example.com/")
        with pytest.raises(BusinessLogicError):
            require_safe_http_url("http://user@mcp.example.com/")

    def test_forbidden_hostnames_400(self):
        for host in (
            "localhost",
            "a.localhost",
            "metadata",
            "metadata.google.internal",
            "metadata.aws.internal",
        ):
            with pytest.raises(BusinessLogicError):
                require_safe_http_url(f"http://{host}/")

    def test_unresolvable_host_400(self):
        with patch(
            "socket.getaddrinfo",
            side_effect=socket.gaierror(-2, "Name or service not known"),
        ):
            with pytest.raises(BusinessLogicError):
                require_safe_http_url("http://no-such-host.invalid/mcp")

    def test_empty_dns_result_400(self):
        with patch("socket.getaddrinfo", return_value=[]):
            with pytest.raises(BusinessLogicError):
                require_safe_http_url("http://mcp.example.com/")

    @pytest.mark.parametrize(
        "bad_ip",
        [
            "127.0.0.1",  # 回环
            "::1",  # v6 回环
            "169.254.169.254",  # 云元数据（链路本地）
            "169.254.1.1",  # 链路本地
            "100.100.100.200",  # 阿里云元数据
            "224.0.0.1",  # 组播
            "0.0.0.0",  # unspecified
        ],
    )
    def test_forbidden_resolved_addresses_400(self, bad_ip):
        dns = _fake_getaddrinfo({"mcp.example.com": [bad_ip]})
        with patch("socket.getaddrinfo", side_effect=dns):
            with pytest.raises(BusinessLogicError) as exc:
                require_safe_http_url("http://mcp.example.com/")
            assert exc.value.status_code == 400

    def test_any_single_forbidden_address_rejects(self):
        """多 A 记录任一命中黑名单即整体拒绝（失败关闭）。"""
        dns = _fake_getaddrinfo(
            {"mcp.example.com": ["93.184.216.34", "169.254.169.254"]}
        )
        with patch("socket.getaddrinfo", side_effect=dns):
            with pytest.raises(BusinessLogicError):
                require_safe_http_url("http://mcp.example.com/")

    def test_ip_literal_host_goes_through_dns_check(self):
        """IP 字面量主机名同样过 getaddrinfo + 地址检查。"""
        dns = _fake_getaddrinfo({"127.0.0.1": ["127.0.0.1"]})
        with patch("socket.getaddrinfo", side_effect=dns):
            with pytest.raises(BusinessLogicError):
                require_safe_http_url("http://127.0.0.1:8080/mcp")

    @pytest.mark.parametrize(
        "bad_ip",
        [
            "::ffff:169.254.169.254",  # v4-mapped 云元数据
            "::ffff:a9fe:a9fe",  # 同上 hex 写法
            "::ffff:7f00:1",  # v4-mapped 回环
            "::ffff:6464:64c8",  # v4-mapped 阿里云元数据 100.100.100.200
            "::127.0.0.1",  # v4-compatible（::/96）回环
        ],
    )
    def test_v6_mapped_or_compat_resolved_addresses_400(self, bad_ip):
        """B1：DNS 返回 v4-mapped/v4-compatible AAAA 地址同样拦截。"""
        dns = _fake_getaddrinfo({"mcp.example.com": [bad_ip]})
        with patch("socket.getaddrinfo", side_effect=dns):
            with pytest.raises(BusinessLogicError) as exc:
                require_safe_http_url("http://mcp.example.com/")
            assert exc.value.status_code == 400

    def test_v6_mapped_literal_host_400(self):
        """B1：v6 字面量主机 [::ffff:x] / [::127.0.0.1] 同样拦截。"""
        for literal in (
            "::ffff:169.254.169.254",
            "::ffff:7f00:1",
            "::127.0.0.1",
        ):
            dns = _fake_getaddrinfo({literal: [literal]})
            with patch("socket.getaddrinfo", side_effect=dns):
                with pytest.raises(BusinessLogicError):
                    require_safe_http_url(f"http://[{literal}]/")

    def test_invalid_port_400(self):
        """m1：非法端口（越界/非数字）归一 400，不冒泡 ValueError 成 500。"""
        for bad in (
            "http://mcp.example.com:99999/",
            "http://mcp.example.com:abc/",
        ):
            with pytest.raises(BusinessLogicError) as exc:
                require_safe_http_url(bad)
            assert exc.value.status_code == 400

    def test_getaddrinfo_non_gaierror_oserror_400(self):
        """m2：getaddrinfo 非 gaierror 的 OSError 同归 400。"""
        with patch(
            "socket.getaddrinfo", side_effect=OSError("network unreachable")
        ):
            with pytest.raises(BusinessLogicError) as exc:
                require_safe_http_url("http://mcp.example.com/")
            assert exc.value.status_code == 400
