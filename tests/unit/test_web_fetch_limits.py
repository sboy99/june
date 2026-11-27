import asyncio
import gzip

import httpx
import pytest
from web_fetch_support import (
    fetch,
    make_tool,
    redirect,
    text_response,
)

from june.shared.errors import ToolError
from june.tooling.adapters.web_fetch import WebFetchLimits

pytestmark = pytest.mark.unit


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
