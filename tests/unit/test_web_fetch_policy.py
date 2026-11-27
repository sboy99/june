import pytest

from june.shared.errors import ToolError
from june.tooling.adapters.net_policy import is_public_address, parse_fetch_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "1.1.1.1",
        "93.184.216.34",
        "2606:4700:4700::1111",
        "2001:4860:4860::8888",
        "::ffff:8.8.8.8",
    ],
)
def test_public_addresses_are_allowed(address):
    assert is_public_address(address) is True


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.255.255.254",
        "10.0.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "169.254.0.1",
        "0.0.0.0",
        "100.64.0.1",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "192.0.0.1",
        "198.18.0.1",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd00:ec2::254",
        "ff02::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "::127.0.0.1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::",
        "2002:a9fe:a9fe::",
        "not-an-ip",
        "",
    ],
)
def test_non_public_addresses_are_refused(address):
    assert is_public_address(address) is False


def test_parses_a_plain_https_url():
    target = parse_fetch_url("https://Example.com/a/b?q=1#frag")

    assert (target.scheme, target.host, target.port) == ("https", "example.com", 443)
    assert target.path_and_query == "/a/b?q=1"
    assert target.host_header == "example.com"


def test_parses_http_default_port_and_empty_path():
    target = parse_fetch_url("http://example.com")

    assert (target.scheme, target.port, target.path_and_query) == ("http", 80, "/")


def test_host_header_keeps_a_non_default_allowed_port():
    target = parse_fetch_url("https://example.com:8443/x")

    assert target.port == 8443
    assert target.host_header == "example.com:8443"


def test_ipv6_literal_host_is_unbracketed():
    target = parse_fetch_url("https://[2606:4700:4700::1111]/")

    assert target.host == "2606:4700:4700::1111"
    assert target.host_header == "[2606:4700:4700::1111]"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/",
        "javascript:alert(1)",
        "data:text/plain,hi",
        "//example.com/x",
        "example.com/x",
        "",
        "   ",
    ],
)
def test_non_http_schemes_are_refused(url):
    with pytest.raises(ToolError, match="web_fetch"):
        parse_fetch_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com/",
        "https://user@example.com/",
        "https://:pass@example.com/",
        "https://example.com\\@127.0.0.1/",
        "https://example.com@127.0.0.1/",
    ],
)
def test_credentials_in_the_url_are_refused(url):
    with pytest.raises(ToolError, match="credentials|invalid"):
        parse_fetch_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433/",
        "http://0x7f000001/",
        "http://0x7f.0.0.1/",
        "http://0177.0.0.1/",
        "http://017700000001/",
        "http://127.1/",
        "http://127.0.1/",
        "http://0/",
        "http://0x7f.1/",
        "http://１２７.0.0.1/",
    ],
)
def test_encoded_ip_hosts_are_refused(url):
    with pytest.raises(ToolError, match="encoded|invalid"):
        parse_fetch_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:22/",
        "http://example.com:6379/",
        "http://example.com:0/",
        "http://example.com:99999/",
        "http://example.com:abc/",
    ],
)
def test_ports_outside_the_allowlist_are_refused(url):
    with pytest.raises(ToolError, match="port|invalid"):
        parse_fetch_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://exa mple.com/",
        "http://example.com/\r\nHost: evil",
        "http://example.com/\x00",
        "http://",
        "http:///path",
        "http://[::1/",
        "http://fe80::1%25eth0/",
        "https://[fe80::1%25eth0]/",
    ],
)
def test_malformed_urls_are_refused(url):
    with pytest.raises(ToolError, match="web_fetch"):
        parse_fetch_url(url)


def test_literal_private_ips_parse_but_are_left_to_address_policy():
    assert parse_fetch_url("http://127.0.0.1/").host == "127.0.0.1"
    assert parse_fetch_url("http://[::1]/").host == "::1"
