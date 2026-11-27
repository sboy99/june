import httpx
import pytest
from web_fetch_support import (
    OTHER_PUBLIC,
    PUBLIC,
    fetch,
    make_tool,
    redirect,
    text_response,
)

from june.shared.errors import ToolError
from june.tooling.adapters.web_fetch import WebFetchTool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:7f00:1]/",
        "http://[fe80::1]/",
        "http://2130706433/",
        "http://0x7f.0.0.1/",
        "http://017700000001/",
        "file:///etc/passwd",
        "https://user:pw@example.com/",
    ],
)
async def test_unsafe_urls_are_refused_without_any_request(url):
    calls = []
    tool = make_tool(lambda r: calls.append(r) or text_response(), {})

    with pytest.raises(ToolError, match="web_fetch"):
        await fetch(tool, url)

    assert calls == []


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.5"],
        ["169.254.169.254"],
        ["::1"],
        ["::ffff:10.0.0.1"],
        [PUBLIC, "192.168.1.1"],
        [],
    ],
)
async def test_host_resolving_to_any_non_public_address_is_refused(addresses):
    calls = []
    tool = make_tool(lambda r: calls.append(r) or text_response(), {"a.example": addresses})

    with pytest.raises(ToolError, match="web_fetch"):
        await fetch(tool)

    assert calls == []


async def test_resolver_failure_is_a_tool_error():
    async def failing(host, port):
        raise OSError("boom")

    tool = WebFetchTool(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(text_response)),
        resolver=failing,
    )

    with pytest.raises(ToolError, match="could not resolve"):
        await fetch(tool)


async def test_follows_a_redirect_and_revalidates_each_hop():
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers["host"], request.url.path))
        if request.headers["host"] == "a.example":
            return redirect("https://b.example/final")
        return text_response("done")

    tool = make_tool(handler, {"a.example": [PUBLIC], "b.example": [OTHER_PUBLIC]})

    result = await fetch(tool, "https://a.example/start")

    assert seen == [(PUBLIC, "a.example", "/start"), (OTHER_PUBLIC, "b.example", "/final")]
    assert result == "[untrusted web content from https://b.example/final]\ndone"


async def test_relative_redirect_is_resolved_against_the_current_url():
    def handler(request):
        if request.url.path == "/old":
            return redirect("/new?x=1", status=301)
        return text_response(request.url.query.decode())

    result = await fetch(make_tool(handler), "http://a.example/old")

    assert result.endswith("x=1")


@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://2130706433/",
        "file:///etc/passwd",
        "ftp://example.com/",
        "http://user:pw@b.example/",
        "http://internal.example/",
    ],
)
async def test_redirect_to_unsafe_target_is_refused(location):
    requests = []

    def handler(request):
        requests.append(request.headers["host"])
        return redirect(location)

    tool = make_tool(handler, {"a.example": [PUBLIC], "internal.example": ["10.0.0.9"]})

    with pytest.raises(ToolError, match="web_fetch"):
        await fetch(tool)

    assert requests == ["a.example"]


async def test_dns_rebinding_between_hops_is_caught():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.headers["host"] == "a.example":
            return redirect("http://rebind.example/")
        return redirect("http://rebind.example/again")

    tool = make_tool(
        handler,
        {"a.example": [PUBLIC], "rebind.example": [[OTHER_PUBLIC], ["127.0.0.1"]]},
    )

    with pytest.raises(ToolError, match="non-public"):
        await fetch(tool)

    assert hosts == [PUBLIC, OTHER_PUBLIC]


async def test_the_validated_address_is_the_one_connected_to_with_a_single_lookup():
    hosts = []
    lookups = []

    async def resolver(host, port):
        lookups.append(host)
        return [PUBLIC]

    def handler(request):
        hosts.append(request.url.host)
        return text_response()

    tool = WebFetchTool(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=resolver,
    )

    await fetch(tool)

    assert hosts == [PUBLIC]
    assert lookups == ["a.example"]
