import httpx

from june.tooling.adapters.web_fetch import WebFetchLimits, WebFetchTool

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
