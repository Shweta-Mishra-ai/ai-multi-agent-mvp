import os
import re

import requests

from agentos.tools import tool


@tool(
    "Search the web and return the top results (title, url, snippet).",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def web_search(query):
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": 5},
                timeout=20,
            )
            r.raise_for_status()
            return "\n\n".join(
                f"{x['title']}\n{x['url']}\n{x.get('content', '')[:300]}"
                for x in r.json().get("results", [])
            ) or "No results."
        except Exception as e:
            return f"Tavily search failed: {e}"

    try:
        from ddgs import DDGS

        results = DDGS().text(query, max_results=5)
        return "\n\n".join(
            f"{x['title']}\n{x['href']}\n{x['body'][:300]}" for x in results
        ) or "No results."
    except Exception as e:
        return (
            f"Web search unavailable ({e}). "
            "Answer from your own knowledge and say the information may be outdated."
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
