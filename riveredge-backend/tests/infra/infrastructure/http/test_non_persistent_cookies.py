import httpx

from infra.infrastructure.http.client import (
    DiscardCookieJar,
    _client_uses_discard_jar,
    init_http_client,
)


def test_discard_cookie_jar_does_not_store_set_cookie():
    jar = DiscardCookieJar()
    cookies = httpx.Cookies(jar)
    request = httpx.Request("POST", "http://erp.example/k3cloud/login")
    response = httpx.Response(
        200,
        headers={"Set-Cookie": "kdservice-sessionid=tenant-a-session; Path=/"},
        request=request,
    )
    cookies.extract_cookies(response)
    assert "kdservice-sessionid" not in cookies
    assert list(cookies.jar) == []


def test_init_http_client_uses_discard_cookie_jar():
    client = init_http_client()
    assert _client_uses_discard_jar(client)
