import httpx
import pytest
from web_fetch_support import (
    DNS,
    OTHER_PUBLIC,
    PUBLIC,
    FakeDns,
    fetch,
    make_tool,
    redirect,
    text_response,
)

from june.shared.errors import ToolError
from june.tooling.adapters.net_policy import is_public_address, parse_fetch_url
from june.tooling.adapters.web_fetch import WebFetchTool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    ["http://a..b/", "http://./", "http://a.example../", "http://" + "x" * 64 + ".example/"],
)
def test_empty_or_oversize_labels_are_refused(url):
    with pytest.raises(ToolError, match="web_fetch"):
        parse_fetch_url(url)


def test_a_single_trailing_dot_is_stripped():
    assert parse_fetch_url("http://a.example./").host == "a.example"


@pytest.mark.parametrize(
    "address",
    [
        "fec0::1",
        "192.0.0.1",
        "100.64.0.1",
        "198.18.0.1",
        "240.0.0.1",
        "64:ff9b::7f00:1",
        "64:ff9b::a00:1",
    ],
)
def test_explicit_denylist_ranges_are_refused(address):
    assert is_public_address(address) is False


def test_nat64_wrapping_a_public_address_is_allowed():
    assert is_public_address("64:ff9b::808:808") is True


@pytest.mark.parametrize("error", [UnicodeError("label too long"), OSError("boom")])
async def test_resolver_errors_become_tool_errors(error):
    async def failing(host, port):
        raise error

    tool = WebFetchTool(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(text_response)),
        resolver=failing,
    )

    with pytest.raises(ToolError, match="could not resolve"):
        await fetch(tool)


async def test_https_to_http_redirect_is_refused():
    requests = []

    def handler(request):
        requests.append(request)
        return redirect("http://a.example/plain")

    with pytest.raises(ToolError, match="downgrade"):
        await fetch(make_tool(handler), "https://a.example/")

    assert len(requests) == 1


async def test_http_to_https_redirect_is_followed():
    def handler(request):
        if request.url.scheme == "http":
            return redirect("https://a.example/secure")
        return text_response("secure")

    assert (await fetch(make_tool(handler))).endswith("secure")


async def test_each_hop_uses_a_fresh_client():
    clients = []

    def factory():
        clients.append(1)
        transport = httpx.MockTransport(
            lambda r: redirect("/b") if r.url.path == "/" else text_response()
        )
        return httpx.AsyncClient(transport=transport)

    tool = WebFetchTool(client_factory=factory, resolver=FakeDns(DNS))

    await fetch(tool)

    assert len(clients) == 2


async def test_falls_back_to_the_next_address_when_connecting_fails():
    tried = []

    def handler(request):
        tried.append(request.url.host)
        if request.url.host == PUBLIC:
            raise httpx.ConnectError("refused")
        return text_response("second")

    tool = make_tool(handler, {"a.example": [PUBLIC, OTHER_PUBLIC]})

    assert (await fetch(tool)).endswith("second")
    assert tried == [PUBLIC, OTHER_PUBLIC]


async def test_all_addresses_failing_to_connect_is_a_tool_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    tool = make_tool(handler, {"a.example": [PUBLIC, OTHER_PUBLIC]})

    with pytest.raises(ToolError, match="could not connect"):
        await fetch(tool)


async def test_non_connect_errors_are_not_retried_on_another_address():
    tried = []

    def handler(request):
        tried.append(request.url.host)
        raise httpx.ReadError("reset")

    tool = make_tool(handler, {"a.example": [PUBLIC, OTHER_PUBLIC]})

    with pytest.raises(ToolError, match="request failed"):
        await fetch(tool)

    assert tried == [PUBLIC]


async def test_unvalidated_addresses_are_never_tried_as_fallback():
    tried = []

    def handler(request):
        tried.append(request.url.host)
        raise httpx.ConnectError("refused")

    tool = make_tool(handler, {"a.example": [PUBLIC, "10.0.0.1"]})

    with pytest.raises(ToolError, match="non-public"):
        await fetch(tool)

    assert tried == []


async def test_requests_ask_for_unencoded_bodies():
    seen = []

    def handler(request):
        seen.append(request.headers["accept-encoding"])
        return text_response()

    await fetch(make_tool(handler))

    assert seen == ["identity"]
