# SSRF-safe web_fetch (SHIP-340, P5.3)

Status: ready-for-agent
Source: Linear SHIP-340, milestone "Phase 5: Tooling"
Branch: `contactsagarbera/ship-340-p53-ssrf-safe-web_fetch` (stacked on `contactsagarbera/ship-339-p52-confined-file-tools`)

## Problem Statement

The agent needs to read web pages, but a fetch tool that follows any URL lets a prompt-injected model reach internal services, cloud metadata endpoints (169.254.169.254) and localhost, or follow a redirect from a public host to a private one.

## Solution

`june.tooling` gains a `web_fetch` Tool (Risk `medium`) that fetches an http(s) URL with strict network limits. Every hop (the first request and each redirect) is validated before connecting: scheme, port, and every resolved address must be public. Redirects are followed manually, at most a few hops. Size and time are capped. The returned text is marked as untrusted data.

## User Stories

1. As the model, I want `web_fetch(url)` to return a page's text, so I can read the web.
2. As an operator, I want only `http` and `https` URLs, so `file:`, `ftp:` and similar are refused.
3. As an operator, I want URLs carrying credentials (`user:pass@host`) refused.
4. As an operator, I want hosts that resolve to loopback, private (RFC 1918), link-local (including cloud metadata 169.254.169.254), unspecified, multicast, reserved or unique-local addresses refused, for IPv4 and IPv6, including IPv4-mapped IPv6 and literal-IP and decimal/octal/hex-encoded IP hosts.
5. As an operator, I want a hostname refused when any of its resolved addresses is non-public.
6. As an operator, I want the connection made to the address that was validated, so DNS rebinding between check and connect cannot reach a private address.
7. As an operator, I want redirects followed manually, each hop re-validated by stories 2 to 6, with a hop limit (named constant, 5).
8. As an operator, I want a redirect to a non-http(s) scheme or a private host refused.
9. As an operator, I want a total time limit and a response size limit (named constants, 15 s and 1 MiB), enforced while streaming, so a slow or huge response cannot hang or exhaust memory.
10. As an operator, I want non-text content types (not `text/*`, JSON, XML) refused, so binary data never reaches the model.
11. As an operator, I want a non-2xx final status to raise `ToolError` naming the status.
12. As the model, I want the result framed as untrusted external data (a fixed header line naming the final URL), so the loop and Gates treat it as data not instructions.
13. As an operator, I want every refusal to raise `ToolError` that names the reason without echoing response bodies.
14. As an operator, I want `web_fetch` rated `medium` Risk and registered in composition.

## Implementation Decisions

- `tooling/adapters/web_fetch.py` (httpx is allowed in adapters only; contract 5). `WebFetchTool(client_factory=..., resolver=..., limits)`: the resolver (hostname to addresses) and HTTP transport are injectable so tests use no network.
- Address policy as a small pure function `is_public_address(ip) -> bool` using `ipaddress` (`is_global` plus explicit rejection of IPv4-mapped private), unit-tested exhaustively.
- Connect to the validated IP while sending the original `Host` header and SNI/cert verification for the hostname (custom httpx transport or per-hop request to the IP with `extensions={"sni_hostname": host}`).
- Redirects: httpx `follow_redirects=False`; the tool reads `Location`, resolves it against the current URL, and loops.
- Env/proxy settings ignored (`trust_env=False`) so a proxy cannot bypass the check.
- Untrusted framing: result text starts with `[untrusted web content from <url>]`.
- Glossary: add **Web fetch** [tooling] (and **Untrusted content** if not defined). New ADR only if a decision contradicts an existing one.

## Testing Decisions

- Pure tests for `is_public_address` and URL validation; the tool through an injected fake resolver and `httpx.MockTransport`: redirect chains (public to private refused), rebinding (resolver returns private on second call), size and time limits, content types, status codes.
- No real network in tests. Prior art: `tests/unit/test_file_tools.py`, `tests/unit/test_llm_openai_adapter.py`.
- `make check` passes; `june.tooling` coverage at least 80%.

## Out of Scope

Robots.txt, caching, HTML-to-text extraction beyond returning decoded text, authentication, POST/other verbs, JavaScript rendering, an allowlist of domains.

## Further Notes

Linear: SHIP-340. Stacked on SHIP-339 (PR #26).
