"""Network policy for `web_fetch`: which URLs and which addresses may be contacted.

Pure functions, no I/O. A URL passes `parse_fetch_url` only if it is a plain http(s) URL without
credentials, to an allowed port, whose host is a hostname or a canonical IP literal. Hosts written
as encoded IPs (decimal, hex, octal, short forms) are refused outright because resolvers and HTTP
clients disagree about how to read them. Whether an address is safe to contact is decided
separately by `is_public_address`, applied to every address a host resolves to.
"""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from june.shared.errors import ToolError

ALLOWED_SCHEMES = {"http": 80, "https": 443}
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
_NUMERIC_LABEL = re.compile(r"0x[0-9a-f]*|[0-9]+")
_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f\\]")
_IPV4_COMPATIBLE = ipaddress.IPv6Network("::/96")
_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")
_LOW_32_BITS = 0xFFFFFFFF

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class FetchTarget:
    """A validated request target; the host is not resolved yet."""

    scheme: str
    host: str
    port: int
    path_and_query: str

    @property
    def host_header(self) -> str:
        """Value for the Host header: bracketed IPv6, port only when not the scheme default."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        if self.port == ALLOWED_SCHEMES[self.scheme]:
            return host
        return f"{host}:{self.port}"


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 address wraps (mapped, 6to4, NAT64), if any."""
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & _LOW_32_BITS)
    return None


def _is_public(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip in _IPV4_COMPATIBLE:
            return False
        embedded = _embedded_ipv4(ip)
        if embedded is not None:
            return _is_public(embedded)
    return ip.is_global and not ip.is_multicast


def is_public_address(address: str) -> bool:
    """True only for a globally routable unicast address; anything unparseable is refused."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return _is_public(ip)


def _refuse(reason: str) -> ToolError:
    return ToolError(f"web_fetch: {reason}")


def _canonical_host(raw_host: str | None) -> str:
    """Lower-cased host, refusing empty, non-ASCII, scoped and encoded-IP hosts."""
    if not raw_host:
        raise _refuse("invalid URL: missing host")
    host = raw_host.lower().rstrip(".")
    if not host.isascii() or "%" in host:
        raise _refuse("invalid host")
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise _refuse("invalid host") from exc
        return host
    if all(_NUMERIC_LABEL.fullmatch(label) for label in host.split(".")):
        try:
            ipaddress.IPv4Address(host)
        except ValueError as exc:
            raise _refuse("host is an encoded IP address") from exc
    return host


def parse_fetch_url(url: str) -> FetchTarget:
    """Validate `url` and split it into a `FetchTarget`, or raise `ToolError`."""
    if not url.strip() or _FORBIDDEN_CHARS.search(url):
        raise _refuse("invalid URL")
    try:
        parts = urlsplit(url)
        port = parts.port
        username, password, raw_host = parts.username, parts.password, parts.hostname
    except ValueError as exc:
        raise _refuse("invalid URL") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise _refuse("only http and https URLs are allowed")
    if username is not None or password is not None or "@" in parts.netloc:
        raise _refuse("URLs with credentials are not allowed")
    host = _canonical_host(raw_host)
    effective_port = ALLOWED_SCHEMES[scheme] if port is None else port
    if effective_port not in ALLOWED_PORTS:
        raise _refuse(f"port {effective_port} is not allowed")
    path = parts.path or "/"
    path_and_query = f"{path}?{parts.query}" if parts.query else path
    return FetchTarget(scheme, host, effective_port, path_and_query)
