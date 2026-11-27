# ADR 0013: SSRF-safe connection policy for web_fetch

- Status: accepted

## Context
`web_fetch` lets the model request arbitrary URLs. A naive client resolves the host twice (check, then connect), honours proxy environment variables, follows redirects blindly, and can reuse pooled connections, any of which can reach internal addresses.

## Decision
- Resolve the host once, require every resolved address to be public (`is_global` plus an explicit denylist), and connect to the pinned validated IP. The original hostname is sent as the Host header and as the TLS SNI name (httpx `sni_hostname` extension), so certificate verification is against the hostname, not the IP. If connecting to one address fails, the other validated addresses are tried; no other errors are retried.
- `trust_env=False`: proxy settings from the environment are ignored so a proxy cannot bypass the address check.
- Redirects are followed manually, up to a hop limit; each hop is fully re-validated, uses a fresh client (no pooled connection reuse across hostnames), and https to http downgrades are refused.
- Only ports 80, 443, 8080 and 8443 are allowed; credentials in URLs and encoded-IP hosts are refused.
- Requests send `Accept-Encoding: identity`, and the byte cap is enforced on decoded bytes while streaming.

## Consequences
DNS rebinding between check and connect cannot reach private hosts, and a redirect cannot smuggle a request elsewhere. Certificate verification against the hostname relies on httpx's `sni_hostname` extension behaving as documented. The tests use `httpx.MockTransport`, which does not exercise TLS, so that property is not covered by automated tests. A fresh client per hop costs a new connection per hop.

## Alternatives considered
- Validate then let httpx resolve and connect: vulnerable to DNS rebinding.
- A custom transport or resolver hook in httpx: more code and more coupling to httpx internals than pinning the IP in the URL.
- Allow any port: widens access to internal services on public hosts.
