import httpx
import pytest
from web_fetch_support import (
    PUBLIC,
    fetch,
    make_tool,
    text_response,
)

from june.shared.errors import ToolError
from june.tooling.adapters.web_fetch import WebFetchTool, default_client

pytestmark = pytest.mark.unit


def test_definition_and_risk():
    tool = WebFetchTool()

    assert tool.definition.name == "web_fetch"
    assert tool.risk == "medium"
    assert tool.definition.parameters["required"] == ["url"]
    assert tool.definition.parameters["additionalProperties"] is False


async def test_returns_page_text_framed_as_untrusted():
    tool = make_tool(lambda request: text_response("<p>hi</p>"), {"example.com": [PUBLIC]})

    result = await fetch(tool, "https://example.com/page")

    assert result == "[untrusted web content from https://example.com/page]\n<p>hi</p>"


async def test_connects_to_the_validated_ip_with_original_host_and_sni():
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers["host"], request.extensions["sni_hostname"]))
        return text_response()

    await fetch(make_tool(handler, {"example.com": [PUBLIC]}), "https://example.com/")

    assert seen == [(PUBLIC, "example.com", "example.com")]


async def test_ipv6_address_is_connected_to_directly():
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return text_response()

    tool = make_tool(handler, {"example.com": ["2606:4700:4700::1111"]})

    await fetch(tool, "https://example.com/")

    assert seen == ["2606:4700:4700::1111"]


async def test_public_ip_literal_skips_the_resolver():
    tool = make_tool(lambda r: text_response(), {})

    result = await fetch(tool, f"http://{PUBLIC}/")

    assert result.endswith("hello")


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
async def test_non_2xx_final_status_names_the_status(status):
    tool = make_tool(lambda r: text_response("secret error body", status=status))

    with pytest.raises(ToolError, match=f"status {status}") as caught:
        await fetch(tool)

    assert "secret error body" not in str(caught.value)


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/html; charset=utf-8",
        "application/json",
        "application/xml",
        "application/ld+json",
        "application/atom+xml",
        "application/xhtml+xml",
    ],
)
async def test_text_like_content_types_are_accepted(content_type):
    tool = make_tool(lambda r: text_response("ok", content_type=content_type))

    assert (await fetch(tool)).endswith("ok")


@pytest.mark.parametrize(
    "content_type", ["image/png", "application/octet-stream", "application/pdf", "video/mp4", ""]
)
async def test_other_content_types_are_refused(content_type):
    tool = make_tool(lambda r: text_response("BINARY", content_type=content_type))

    with pytest.raises(ToolError, match="content type") as caught:
        await fetch(tool)

    assert "BINARY" not in str(caught.value)


async def test_transport_errors_become_tool_errors_without_details():
    def handler(request):
        raise httpx.ReadError("secret internal detail")

    tool = make_tool(handler)

    with pytest.raises(ToolError, match="request failed") as caught:
        await fetch(tool)

    assert "secret" not in str(caught.value)


async def test_charset_is_honoured():
    def handler(request):
        return httpx.Response(
            200,
            content="café".encode("latin-1"),
            headers={"content-type": "text/plain; charset=latin-1"},
        )

    assert (await fetch(make_tool(handler))).endswith("café")


async def test_unknown_charset_falls_back_to_utf8_with_replacement():
    def handler(request):
        return httpx.Response(
            200, content=b"ok\xff", headers={"content-type": "text/plain; charset=nope"}
        )

    assert (await fetch(make_tool(handler))).endswith("ok�")


@pytest.mark.parametrize("arguments", [{}, {"url": 5}, {"url": None}])
async def test_url_argument_must_be_a_string(arguments):
    with pytest.raises(ToolError, match="'url' must be a string"):
        await WebFetchTool().run(arguments)


async def test_request_is_a_plain_get_without_cookies_or_auth():
    seen = []

    def handler(request):
        seen.append(request)
        return text_response()

    await fetch(make_tool(handler))

    assert seen[0].method == "GET"
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers


def test_default_client_ignores_proxy_environment_and_never_follows_redirects(monkeypatch):
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.invalid:3128")

    client = default_client()

    assert client._mounts == {}
    assert client._trust_env is False
    assert client.follow_redirects is False
