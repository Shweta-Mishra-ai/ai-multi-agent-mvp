"""Input validation, rate limiting and network safety guards."""

import ipaddress
import socket
from urllib.parse import urlparse

from agentos import config


def validate_request(text):
    """Return an error message if the request is invalid, else None."""
    if text is None or not str(text).strip():
        return "Request is empty. Please describe what you want to do."
    if len(text) > config.MAX_INPUT_CHARS:
        return (f"Request too long ({len(text)} characters, "
                f"max {config.MAX_INPUT_CHARS}). Please shorten it.")
    if "\x00" in text:
        return "Request contains invalid characters."
    return None


def check_rate_limit(memory, api_key_id=None):
    """True if this caller is under its runs-per-minute budget.

    Scoped per api_key_id when the caller authenticated with an API key,
    so each key gets its own independent budget instead of every caller
    sharing one global bucket. Unauthenticated/local callers (api_key_id
    is None) share a single bucket - fine for personal/dev use, but a
    public deployment should create API keys (see `cli.py keys create`)
    so real users each get isolated limits."""
    try:
        return memory.runs_in_last_minute(api_key_id) < config.RATE_LIMIT_PER_MIN
    except Exception:
        return True  # never block on a metrics failure


def is_safe_url(url):
    """SSRF guard: only http(s), and the host must not resolve to a private,
    loopback, link-local or otherwise internal address."""
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
