"""SSRF guard. Deliberately self-contained (no dependency on the main
agentos package) since this service deploys independently, on different
infrastructure, from the main AgentOS app."""

import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_url(url):
    """Only http(s), and the host must not resolve to a private, loopback,
    link-local or otherwise internal address - this worker runs on cloud
    infrastructure of its own, so an unguarded fetch could reach that
    provider's internal metadata endpoints just as easily as the main
    app's fetch_url could reach its host's."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        for info in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False
