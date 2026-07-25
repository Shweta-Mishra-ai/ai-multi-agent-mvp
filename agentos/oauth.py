"""Optional "Sign in with Google" login for the HTTP API.

An ALTERNATIVE to `cli.py keys create`: instead of an operator manually
minting a key for every user, a person can sign in with their Google
account at /auth/google/login and get an API key issued automatically,
tied to their Google email so a repeat login finds the same identity
(the key itself rotates each login - see upsert_google_key in memory.py
for why a stored key can never be shown again after creation).

Fully optional: leave GOOGLE_CLIENT_ID unset and the API works exactly
as it did before (CLI-issued keys only, no /auth/* routes reachable).

HONESTY NOTE: this flow needs a real Google Cloud OAuth 2.0 Client ID/
secret and a real public HTTPS callback URL, neither of which exist in
a development sandbox. The logic here (state/CSRF handling, token
exchange, error handling) is unit-tested against mocked HTTP responses,
but the full round trip has NOT been exercised against Google's real
servers. See the README's OAuth section for the operator setup steps
required before this can be used for real.
"""

import os
import secrets
import time
from urllib.parse import quote

import requests

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_STATE_TTL = 600  # seconds a login attempt's CSRF state stays valid
_pending_states = {}  # state -> issued_at (in-memory: single-use, short-lived)


def is_configured():
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def _prune_expired_states():
    cutoff = time.time() - _STATE_TTL
    for s, issued_at in list(_pending_states.items()):
        if issued_at < cutoff:
            _pending_states.pop(s, None)


def build_authorize_url(redirect_uri):
    """Start a login: returns the URL to send the user's browser to."""
    _prune_expired_states()
    state = secrets.token_urlsafe(24)
    _pending_states[state] = time.time()
    params = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


def consume_state(state):
    """True exactly once for a state issued by build_authorize_url within
    its TTL - prevents CSRF and replaying the same callback twice."""
    _prune_expired_states()
    return _pending_states.pop(state, None) is not None


def exchange_code_for_email(code, redirect_uri):
    """Exchange an authorization code for the signed-in user's verified
    email. Raises on any failure (network, invalid code, unverified
    email) - callers must catch this and return a clean error response."""
    token_response = requests.post(GOOGLE_TOKEN_URL, data={
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]

    userinfo_response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    userinfo_response.raise_for_status()
    userinfo = userinfo_response.json()

    email = userinfo.get("email")
    if not email or not userinfo.get("email_verified"):
        raise ValueError("Google account has no verified email")
    return email
