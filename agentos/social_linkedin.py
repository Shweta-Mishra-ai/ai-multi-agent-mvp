"""Optional LinkedIn posting (personal profile) via LinkedIn's Posts API.

Fully optional: leave LINKEDIN_CLIENT_ID unset and nothing here is
reachable.

HONESTY NOTE, same as agentos/oauth.py: this needs a real LinkedIn
Developer app with the "Share on LinkedIn" and "Sign In with LinkedIn
using OpenID Connect" products added, and a real public HTTPS callback
URL - neither exists in a development sandbox. The request-shaping logic
here is unit-tested against mocked HTTP responses; the full round trip
has NOT been exercised against LinkedIn's real servers. See the README's
social posting section for the operator setup this requires.

Posts to the connected member's own personal profile (w_member_social
scope) - not a company Page (that's a different scope,
w_organization_social, and a different author URN shape; out of scope
here since this app is built around one person's own use, not managing an
organization's page).
"""

import os
import time
from urllib.parse import quote

import requests

from agentos.oauth_state import OAuthStates

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
API_VERSION = "202601"  # LinkedIn requires a YYYYMM version header on /rest/* calls
SCOPES = "openid profile w_member_social"

states = OAuthStates()


def is_configured():
    return bool(os.getenv("LINKEDIN_CLIENT_ID") and os.getenv("LINKEDIN_CLIENT_SECRET"))


def build_authorize_url(redirect_uri):
    state = states.issue()
    params = {
        "response_type": "code",
        "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": SCOPES,
    }
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def consume_state(state):
    return states.consume(state)


def exchange_code_for_member(code, redirect_uri):
    """Authorization code -> (access_token, member_urn, expires_at).
    Raises on any failure - callers must catch this and return a clean
    error response."""
    token_response = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
        "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET"),
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
    token_response.raise_for_status()
    token_data = token_response.json()
    access_token = token_data["access_token"]
    expires_at = time.time() + token_data.get("expires_in", 60 * 86400)

    userinfo_response = requests.get(
        USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    userinfo_response.raise_for_status()
    member_id = userinfo_response.json()["sub"]
    return access_token, f"urn:li:person:{member_id}", expires_at


def publish_text_post(access_token, author_urn, text):
    """Raises on failure. Returns the new post's URN (from the response
    header LinkedIn's Posts API uses instead of a JSON body)."""
    response = requests.post(
        POSTS_URL,
        json={
            "author": author_urn,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.headers.get("x-restli-id", "")
