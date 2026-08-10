import json
import subprocess
import sys
import threading

from agentos.tools import tool

RENDER_TIMEOUT_S = 25
BROWSE_TIMEOUT_S = 90

# Shared across both tools: two headless Chromium instances competing for
# Render's 512MB RAM is a much likelier OOM than one ever is, regardless of
# which tool launched it.
_browser_slot = threading.Semaphore(1)


@tool(
    "Render a JavaScript-heavy web page with a real headless browser and "
    "return its visible text - use this instead of fetch_url when a page "
    "needs JavaScript to show its content (e.g. a single-page app or a "
    "listing page that loads results dynamically). This cannot log into "
    "authenticated/private pages - there are no credentials available. "
    "Slower and heavier than fetch_url, so only use it when fetch_url's "
    "result looks empty or useless.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def render_page(url):
    with _browser_slot:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "agentos.tools._render_subprocess", url],
                capture_output=True, text=True, timeout=RENDER_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return f"Rendering {url} timed out after {RENDER_TIMEOUT_S}s."

    output = (result.stdout or "").strip()
    if not output:
        stderr = (result.stderr or "").strip()
        return (f"Browser rendering failed (exit {result.returncode}): "
                f"{stderr[-500:] or 'no output - the process may have run out of memory'}")

    try:
        data = json.loads(output.splitlines()[-1])
    except (ValueError, IndexError):
        return f"Browser rendering failed: unexpected output ({output[-500:]})"

    if "error" in data:
        return f"Browser render failed: {data['error']}"

    title = data.get("title", "")
    text = data.get("text", "")
    return f"{title}\n\n{text}".strip()


@tool(
    "Accomplish a task that needs REAL interaction with a web page - "
    "searching a box, clicking links/buttons, filling and submitting a "
    "form, navigating through multiple steps - using a real headless "
    "browser driven step by step by an LLM. Much slower and more "
    "expensive than fetch_url/render_page, so only use it when the task "
    "genuinely requires clicking or typing, not just reading a page. "
    "Cannot log into authenticated/private pages - there are no "
    "credentials available.",
    {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "what to accomplish, in plain language "
                               "(e.g. 'search for React developer jobs "
                               "and list the first 5 with links')",
            },
            "start_url": {
                "type": "string",
                "description": "the page to start from",
            },
        },
        "required": ["task", "start_url"],
    },
)
def browse_and_accomplish(task, start_url):
    with _browser_slot:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "agentos.tools._browse_subprocess",
                 task, start_url],
                capture_output=True, text=True, timeout=BROWSE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return f"Browsing task timed out after {BROWSE_TIMEOUT_S}s."

    output = (result.stdout or "").strip()
    if not output:
        stderr = (result.stderr or "").strip()
        return (f"Browsing task failed (exit {result.returncode}): "
                f"{stderr[-500:] or 'no output - the process may have run out of memory'}")

    try:
        data = json.loads(output.splitlines()[-1])
    except (ValueError, IndexError):
        return f"Browsing task failed: unexpected output ({output[-500:]})"

    if "error" in data:
        return f"Browsing task failed: {data['error']}"

    return str(data.get("result", "")).strip()
