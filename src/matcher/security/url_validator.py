"""URL validation utilities to prevent SSRF attacks."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Blocked IP ranges: loopback, link-local, private, metadata endpoints
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # Private
    ipaddress.ip_network("172.16.0.0/12"),  # Private
    ipaddress.ip_network("192.168.0.0/16"),  # Private
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),  # "This" network
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Allowed URL schemes
_ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(ValueError):
    """Raised when a URL targets a blocked network or uses a forbidden scheme."""

    pass


def validate_url_safe(url: str, *, allow_http: bool = False) -> str:
    """Validate that a URL is safe for server-side requests (anti-SSRF).

    Args:
        url: The URL to validate.
        allow_http: If True, allows both http and https. If False, only https.

    Returns:
        The validated URL string.

    Raises:
        SSRFError: If the URL is unsafe.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFError(f"Invalid URL: {e}")

    # Scheme check
    allowed = _ALLOWED_SCHEMES if allow_http else {"https"}
    if parsed.scheme not in allowed:
        raise SSRFError(
            f"URL scheme '{parsed.scheme}' is not allowed. Allowed: {', '.join(sorted(allowed))}"
        )

    # Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no hostname")

    # Block common bypass patterns
    if hostname in ("localhost", "0.0.0.0", "[::]", "[::1]"):
        raise SSRFError(f"Hostname '{hostname}' resolves to a blocked address")

    # Resolve hostname to IP and check against blocked ranges
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise SSRFError(f"Cannot resolve hostname: {hostname}")

    for family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFError(f"Invalid IP address resolved: {ip_str}")

        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise SSRFError(f"URL resolves to blocked address {ip} (network {network})")

    return url
