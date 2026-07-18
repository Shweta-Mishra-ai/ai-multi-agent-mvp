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


@tool(
    "Fetch a web page and return its text content.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def fetch_url(url):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "AgentOS/0.2"})
        r.raise_for_status()
        text = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", r.text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000] or "(page has no readable text)"
    except Exception as e:
        return f"Could not fetch {url}: {e}"
