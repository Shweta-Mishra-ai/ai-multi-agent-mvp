import os
import re

import requests

from agentos.tools import tool


# Returned when every search provider failed. Deliberately does NOT tell
# the agent to answer from its own knowledge: doing that produced
# confident, generic, made-up articles that looked identical to real
# researched answers, with nothing anywhere telling the user the search
# never actually happened. Failing loudly is worth more than a fluent
# guess.
SEARCH_FAILED_PREFIX = "SEARCH_FAILED"


def _search_tavily(query):
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return None  # not configured - try the next provider
    r = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": 5},
        timeout=20,
    )
    r.raise_for_status()
    return [
        (x["title"], x["url"], x.get("content", "")[:300])
        for x in r.json().get("results", [])
    ]


def _search_brave(query):
    key = os.getenv("BRAVE_API_KEY")
    if not key:
        return None
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 5},
        headers={"Accept": "application/json", "X-Subscription-Token": key},
        timeout=20,
    )
    r.raise_for_status()
    return [
        (x.get("title", ""), x.get("url", ""), x.get("description", "")[:300])
        for x in r.json().get("web", {}).get("results", [])
    ]


def _search_ddgs(query):
    """No API key, but it scrapes DuckDuckGo/Startpage - which routinely
    block datacenter IPs, so this fails on most cloud hosts (Render
    included). Kept as a last resort for local use, not relied on."""
    from ddgs import DDGS

    return [(x["title"], x["href"], x["body"][:300])
            for x in DDGS().text(query, max_results=5)]


SEARCH_PROVIDERS = (
    ("Tavily", _search_tavily),
    ("Brave", _search_brave),
    ("DuckDuckGo", _search_ddgs),
)


@tool(
    "Search the web and return the top results (title, url, snippet).",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def web_search(query):
    """Tries each configured provider in turn. A provider that isn't
    configured is skipped; one that errors is recorded and the next is
    tried - previously a failing Tavily call returned immediately without
    ever falling back."""
    errors = []
    for name, provider in SEARCH_PROVIDERS:
        try:
            results = provider(query)
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue
        if results is None:
            continue  # provider not configured
        if results:
            return "\n\n".join(f"{t}\n{u}\n{s}" for t, u, s in results)
        errors.append(f"{name}: no results")

    detail = "; ".join(errors) or "no search provider is configured"
    return (
        f"{SEARCH_FAILED_PREFIX}: the web search did not run ({detail}). "
        "You have NO search results. Do not write an answer from your own "
        "knowledge and do not invent sources - tell the user plainly that "
        "web search is unavailable on this deployment and that setting "
        "TAVILY_API_KEY (free tier at tavily.com) or BRAVE_API_KEY fixes it."
    )


MAX_FETCH_BYTES = 2_000_000  # cap response body read to bound memory use
MAX_REDIRECTS = 5


@tool(
    "Fetch a web page and return its text content.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def fetch_url(url):
    from agentos.security import is_safe_url

    # Redirects are followed manually (not via requests' allow_redirects=True)
    # and every hop is re-validated - otherwise a public URL that 302s to an
    # internal address (e.g. cloud metadata) would bypass the SSRF guard.
    next_url = url
    for _ in range(MAX_REDIRECTS + 1):
        if not is_safe_url(next_url):
            return (f"Blocked: {next_url} is not a safe public http(s) URL "
                    "(internal/private addresses are not allowed).")
        try:
            r = requests.get(next_url, timeout=20,
                             headers={"User-Agent": "AgentOS/0.2"},
                             allow_redirects=False, stream=True)
        except Exception as e:
            return f"Could not fetch {next_url}: {e}"

        if r.is_redirect or r.is_permanent_redirect:
            location = r.headers.get("location")
            r.close()
            if not location:
                return f"Could not fetch {next_url}: redirect with no location"
            next_url = requests.compat.urljoin(next_url, location)
            continue

        try:
            r.raise_for_status()
            body = b""
            for chunk in r.iter_content(chunk_size=65536):
                body += chunk
                if len(body) > MAX_FETCH_BYTES:
                    break
            text = body.decode(r.encoding or "utf-8", errors="replace")
            text = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", text)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:6000] or "(page has no readable text)"
        except Exception as e:
            return f"Could not fetch {next_url}: {e}"
        finally:
            r.close()

    return f"Could not fetch {url}: too many redirects"
