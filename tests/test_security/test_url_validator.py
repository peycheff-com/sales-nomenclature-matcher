"""Tests for SSRF-safe URL validator."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from matcher.security.url_validator import SSRFError, validate_url_safe


def _fake_getaddrinfo_public(host, port, *args, **kwargs):
    """Return a fake public IP for any hostname resolution."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port or 443))
    ]


def _fake_getaddrinfo_for(ip: str):
    """Return a factory that resolves any hostname to the given IP."""

    def _resolver(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 443))]

    return _resolver


class TestURLValidator:
    def test_blocks_localhost(self):
        """localhost and 127.0.0.1 must be rejected."""
        with pytest.raises(SSRFError):
            validate_url_safe("https://localhost/path", allow_http=True)

        fake = _fake_getaddrinfo_for("127.0.0.1")
        with patch("matcher.security.url_validator.socket.getaddrinfo", fake):
            with pytest.raises(SSRFError, match="blocked"):
                validate_url_safe("https://sneaky-host.example.com")

    def test_blocks_private_ranges(self):
        """Private RFC1918 ranges (10.x, 172.16.x, 192.168.x) must be blocked."""
        private_ips = ["10.0.0.1", "192.168.1.1", "172.16.0.1"]
        for ip in private_ips:
            with patch(
                "matcher.security.url_validator.socket.getaddrinfo",
                _fake_getaddrinfo_for(ip),
            ):
                with pytest.raises(SSRFError, match="blocked"):
                    validate_url_safe("https://some-host.example.com", allow_http=False)

    def test_blocks_link_local(self):
        """Cloud metadata endpoint (169.254.169.254) must be blocked."""
        with patch(
            "matcher.security.url_validator.socket.getaddrinfo",
            _fake_getaddrinfo_for("169.254.169.254"),
        ):
            with pytest.raises(SSRFError, match="blocked"):
                validate_url_safe("https://metadata.example.com", allow_http=False)

    def test_blocks_zero(self):
        """0.0.0.0 must be rejected."""
        with pytest.raises(SSRFError):
            validate_url_safe("https://0.0.0.0/something", allow_http=True)

    def test_allows_public_https(self):
        """A public HTTPS URL that resolves to a public IP should be allowed."""
        with patch(
            "matcher.security.url_validator.socket.getaddrinfo",
            _fake_getaddrinfo_public,
        ):
            result = validate_url_safe("https://example.com")
            assert result == "https://example.com"

    def test_rejects_http_without_flag(self):
        """HTTP URLs should be rejected when allow_http is False (default)."""
        with patch(
            "matcher.security.url_validator.socket.getaddrinfo",
            _fake_getaddrinfo_public,
        ):
            with pytest.raises(SSRFError, match="scheme"):
                validate_url_safe("http://example.com")

    def test_allows_http_with_flag(self):
        """HTTP URLs should be allowed when allow_http=True."""
        with patch(
            "matcher.security.url_validator.socket.getaddrinfo",
            _fake_getaddrinfo_public,
        ):
            result = validate_url_safe("http://example.com", allow_http=True)
            assert result == "http://example.com"

    def test_rejects_no_hostname(self):
        """A URL with no hostname should be rejected."""
        with pytest.raises(SSRFError):
            validate_url_safe("https://")

    def test_rejects_unknown_scheme(self):
        """Non-http(s) schemes such as ftp should be rejected."""
        with pytest.raises(SSRFError, match="scheme"):
            validate_url_safe("ftp://example.com/file.txt")

    def test_wraps_url_parse_errors(self):
        """Parser failures should surface as SSRF validation errors."""
        with patch("matcher.security.url_validator.urlparse", side_effect=ValueError("broken")):
            with pytest.raises(SSRFError, match="Invalid URL: broken"):
                validate_url_safe("https://example.com")

    def test_rejects_unresolvable_hostname(self):
        """DNS failures should be rejected instead of silently allowing the URL."""
        with patch(
            "matcher.security.url_validator.socket.getaddrinfo",
            side_effect=socket.gaierror("not found"),
        ):
            with pytest.raises(SSRFError, match="Cannot resolve hostname"):
                validate_url_safe("https://missing.example.com")

    def test_rejects_invalid_resolved_ip_address(self):
        """Unexpected resolver output should be treated as unsafe."""
        def resolver(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("not-an-ip", port))
            ]

        with patch("matcher.security.url_validator.socket.getaddrinfo", resolver):
            with pytest.raises(SSRFError, match="Invalid IP address resolved"):
                validate_url_safe("https://weird.example.com")
