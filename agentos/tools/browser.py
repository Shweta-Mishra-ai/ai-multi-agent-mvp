import os

import requests

from agentos.tools import tool


@tool(
    "Render a JavaScript-heavy web page with a real headless browser and "
    "return its visible text - use this instead of fetch_url when a page "
    "needs JavaScript to show its content (e.g. a single-page app or a "
    "listing page that loads results dynamically). This cannot log into "
    "authenticated/private pages - there are no credentials available.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def render_page(url):
    worker_url = os.getenv("BROWSER_WORKER_URL")
    worker_token = os.getenv("BROWSER_WORKER_TOKEN")
    if not worker_url or not worker_token:
        return ("Browser rendering is not configured on this deployment "
                "(BROWSER_WORKER_URL / BROWSER_WORKER_TOKEN not set - see "
                "browser-worker/README.md to deploy and configure it).")

    try:
        r = requests.post(
            f"{worker_url.rstrip('/')}/render",
            json={"url": url},
            headers={"Authorization": f"Bearer {worker_token}"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        detail = e.response.text
        try:
            detail = e.response.json().get("detail", detail)
        except ValueError:
            pass
        return f"Browser render failed: {detail}"
    except Exception as e:
        return f"Browser worker unavailable: {e}"

    title = data.get("title", "")
    text = data.get("text", "")
    return f"{title}\n\n{text}".strip()
