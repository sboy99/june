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

DEFAULT_PORTS = {"http": 80, "https": 443}
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
_NUMERIC_LABEL = re.compile(r"0x[0-9a-f]*|[0-9]+")
_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f\\]")
_IPV4_COMPATIBLE = ipaddress.IPv6Network("::/96")
_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")
_LOW_32_BITS = 0xFFFFFFFF
_MAX_LABEL_LENGTH = 63
_MAX_HOST_LENGTH = 253
# Explicit denylist on top of `is_global`, so the verdict does not depend on the Python patch level.
_DENIED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "100.64.0.0/10",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "240.0.0.0/4",
        "100::/64",
        "2001:db8::/32",
        "64:ff9b:1::/48",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
    )
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class FetchTarget:
    """A validated request target; the host is not resolved yet."""

    scheme: str
    host: str
    port: int
    path_and_query: str

    def connect_url(self, address: str) -> str:
        """URL that connects to the validated `address` instead of resolving the host again."""
        host = f"[{address}]" if ":" in address else address
        return f"{self.scheme}://{host}:{self.port}{self.path_and_query}"

    @property
    def host_header(self) -> str:
        """Value for the Host header: bracketed IPv6, port only when not the scheme default."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        if self.port == DEFAULT_PORTS[self.scheme]:
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
    if any(ip in network for network in _DENIED_NETWORKS):
        return False
    return ip.is_global and not ip.is_multicast


def is_public_address(address: str) -> bool:
    """True only for a globally routable unicast address; anything unparseable is refused."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return _is_public(ip)


def refuse(reason: str) -> ToolError:
    """The `ToolError` every `web_fetch` refusal is raised as."""
    return ToolError(f"web_fetch: {reason}")


def _check_label_lengths(host: str) -> None:
    labels = host.split(".")
    if len(host) > _MAX_HOST_LENGTH or not all(
        0 < len(label) <= _MAX_LABEL_LENGTH for label in labels
    ):
        raise refuse("invalid host")


def _canonical_host(raw_host: str | None) -> str:
    """Lower-cased host, refusing empty, non-ASCII, scoped and encoded-IP hosts."""
    if not raw_host:
        raise refuse("invalid URL: missing host")
    host = raw_host.lower().removesuffix(".")
    if not host:
        raise refuse("invalid URL: missing host")
    if not host.isascii() or "%" in host:
        raise refuse("invalid host")
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise refuse("invalid host") from exc
        return host
    _check_label_lengths(host)
    if all(_NUMERIC_LABEL.fullmatch(label) for label in host.split(".")):
        try:
            ipaddress.IPv4Address(host)
        except ValueError as exc:
            raise refuse("host is an encoded IP address") from exc
    return host


def parse_fetch_url(url: str) -> FetchTarget:
    """Validate `url` and split it into a `FetchTarget`, or raise `ToolError`."""
    if not url.strip() or _FORBIDDEN_CHARS.search(url):
        raise refuse("invalid URL")
    try:
        parts = urlsplit(url)
        port = parts.port
        username, password, raw_host = parts.username, parts.password, parts.hostname
    except ValueError as exc:
        raise refuse("invalid URL") from exc
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise refuse("only http and https URLs are allowed")
    if username is not None or password is not None or "@" in parts.netloc:
        raise refuse("URLs with credentials are not allowed")
    host = _canonical_host(raw_host)
    effective_port = DEFAULT_PORTS[scheme] if port is None else port
    if effective_port not in ALLOWED_PORTS:
        raise refuse(f"port {effective_port} is not allowed")
    path = parts.path or "/"
    path_and_query = f"{path}?{parts.query}" if parts.query else path
    return FetchTarget(scheme, host, effective_port, path_and_query)
