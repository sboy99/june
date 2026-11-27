import asyncio
import gzip

import httpx
import pytest

from june.shared.errors import ToolError
from june.tooling.adapters.web_fetch import WebFetchLimits, WebFetchTool, default_client

pytestmark = pytest.mark.unit

PUBLIC = "93.184.216.34"
OTHER_PUBLIC = "8.8.8.8"
URL = "http://a.example/"
DNS = {"a.example": [PUBLIC]}


class FakeDns:
    """Resolver returning scripted answers per host; a list of lists is consumed per lookup."""

    def __init__(self, answers):
        self._answers = {host: list(addresses) for host, addresses in answers.items()}
        self.lookups = []

    async def __call__(self, host, port):
        self.lookups.append(host)
        answers = self._answers[host]
        return answers.pop(0) if answers and isinstance(answers[0], list) else answers


def make_tool(handler, answers=None, limits=None):
    transport = httpx.MockTransport(handler)

    def factory():
        return httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False)

    dns = FakeDns(DNS if answers is None else answers)
    return WebFetchTool(client_factory=factory, resolver=dns, limits=limits or WebFetchLimits())


def text_response(body="hello", content_type="text/html; charset=utf-8", status=200, headers=None):
    return httpx.Response(
        status, content=body.encode(), headers={"content-type": content_type, **(headers or {})}
    )


def redirect(location, status=302):
    return httpx.Response(status, headers={"location": location})


async def fetch(tool, url=URL):
    return await tool.run({"url": url})


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


async def test_redirect_hop_limit():
    hops = []

    def handler(request):
        hops.append(request.url.path)
        return redirect(f"/{len(hops)}")

    tool = make_tool(handler, limits=WebFetchLimits(max_redirects=3))

    with pytest.raises(ToolError, match="too many redirects"):
        await fetch(tool)

    assert len(hops) == 4


async def test_redirect_without_location_is_refused():
    tool = make_tool(lambda r: httpx.Response(302))

    with pytest.raises(ToolError, match="redirect without a location"):
        await fetch(tool)


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


async def test_declared_oversize_is_refused():
    tool = make_tool(
        lambda r: text_response("x" * 50, headers={"content-length": "50"}),
        limits=WebFetchLimits(max_bytes=10),
    )

    with pytest.raises(ToolError, match="too large"):
        await fetch(tool)


async def test_size_limit_is_enforced_while_streaming_without_content_length():
    pulled = []

    async def body():
        for _ in range(1000):
            pulled.append(1)
            yield b"x" * 10

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=body())

    tool = make_tool(handler, limits=WebFetchLimits(max_bytes=25))

    with pytest.raises(ToolError, match="too large"):
        await fetch(tool)

    assert len(pulled) < 10


async def test_body_exactly_at_the_limit_is_returned():
    tool = make_tool(lambda r: text_response("x" * 10), limits=WebFetchLimits(max_bytes=10))

    assert (await fetch(tool)).endswith("x" * 10)


async def test_compressed_body_is_limited_after_decompression():
    payload = gzip.compress(b"a" * 100_000)

    def handler(request):
        return httpx.Response(
            200, content=payload, headers={"content-type": "text/plain", "content-encoding": "gzip"}
        )

    tool = make_tool(handler, limits=WebFetchLimits(max_bytes=1000))

    with pytest.raises(ToolError, match="too large"):
        await fetch(tool)


async def test_time_limit_is_enforced_on_a_slow_stream():
    async def body():
        yield b"start"
        await asyncio.sleep(5)
        yield b"never"

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=body())

    tool = make_tool(handler, limits=WebFetchLimits(timeout_seconds=0.05))

    with pytest.raises(ToolError, match="timed out"):
        await fetch(tool)


async def test_time_limit_covers_the_whole_redirect_chain():
    async def handler(request):
        await asyncio.sleep(0.03)
        return redirect(request.url.path + "x")

    tool = make_tool(handler, limits=WebFetchLimits(timeout_seconds=0.1, max_redirects=50))

    with pytest.raises(ToolError, match="timed out"):
        await fetch(tool)


async def test_transport_errors_become_tool_errors_without_details():
    def handler(request):
        raise httpx.ConnectError("secret internal detail")

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
