"""Optional Instagram posting via the Meta Graph API.

Fully optional: leave META_APP_ID unset and nothing here is reachable.

HONESTY NOTE, same as agentos/oauth.py: this needs a real Meta Developer
app (Business type, Instagram Graph API product added), a real Instagram
Business or Creator account linked to a Facebook Page, and a real public
HTTPS callback URL - none of which exist in a development sandbox. The
request-shaping logic here is unit-tested against mocked HTTP responses;
the full round trip has NOT been exercised against Meta's real servers.
See the README's social posting section for the operator setup this
requires before it can be used for real.

Posting requires a publicly reachable image URL (Meta's Content Publishing
API fetches the image itself - it does not accept a file upload), so
post_to_instagram (agentos/tools/social.py) takes an existing image URL
rather than this app hosting one itself.
"""

import os
import time
from urllib.parse import quote

import requests

from agentos.oauth_state import OAuthStates

GRAPH_API = "https://graph.facebook.com/v21.0"
AUTHORIZE_URL = "https://www.facebook.com/v21.0/dialog/oauth"
SCOPES = "instagram_basic,instagram_content_publish,pages_show_list,business_management"

states = OAuthStates()


def is_configured():
    return bool(os.getenv("META_APP_ID") and os.getenv("META_APP_SECRET"))


def build_authorize_url(redirect_uri):
    state = states.issue()
    params = {
        "client_id": os.getenv("META_APP_ID"),
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": SCOPES,
        "response_type": "code",
    }
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def consume_state(state):
    return states.consume(state)


def exchange_code_for_account(code, redirect_uri):
    """Authorization code -> (long_lived_token, instagram_business_account_id,
    expires_at). Raises on any failure - callers must catch this and
    return a clean error response. Three round trips, unavoidable with
    Meta's API: code -> short-lived token -> long-lived token, then
    Pages -> the Page's linked Instagram Business Account."""
    token_response = requests.get(f"{GRAPH_API}/oauth/access_token", params={
        "client_id": os.getenv("META_APP_ID"),
        "client_secret": os.getenv("META_APP_SECRET"),
        "redirect_uri": redirect_uri,
        "code": code,
    }, timeout=15)
    token_response.raise_for_status()
    short_lived_token = token_response.json()["access_token"]

    exchange_response = requests.get(f"{GRAPH_API}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": os.getenv("META_APP_ID"),
        "client_secret": os.getenv("META_APP_SECRET"),
        "fb_exchange_token": short_lived_token,
    }, timeout=15)
    exchange_response.raise_for_status()
    long_lived = exchange_response.json()
    access_token = long_lived["access_token"]
    expires_at = time.time() + long_lived.get("expires_in", 60 * 86400)

    pages_response = requests.get(f"{GRAPH_API}/me/accounts", params={
        "access_token": access_token,
    }, timeout=15)
    pages_response.raise_for_status()
    pages = pages_response.json().get("data", [])
    if not pages:
        raise ValueError(
            "No Facebook Page found for this account - Instagram posting "
            "requires a Business/Creator Instagram account linked to a "
            "Facebook Page you manage.")

    for page in pages:
        page_info = requests.get(f"{GRAPH_API}/{page['id']}", params={
            "fields": "instagram_business_account",
            "access_token": access_token,
        }, timeout=15).json()
        ig_account = page_info.get("instagram_business_account")
        if ig_account:
            return access_token, ig_account["id"], expires_at

    raise ValueError(
        "None of your Facebook Pages have a linked Instagram Business "
        "account - link one in Meta Business Suite first.")


def publish_photo(access_token, ig_account_id, image_url, caption):
    """Two-step per Meta's Content Publishing API: create a media
    container, then publish it. Raises on failure."""
    container_response = requests.post(
        f"{GRAPH_API}/{ig_account_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": access_token},
        timeout=30,
    )
    container_response.raise_for_status()
    creation_id = container_response.json()["id"]

    publish_response = requests.post(
        f"{GRAPH_API}/{ig_account_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    publish_response.raise_for_status()
    return publish_response.json()["id"]
