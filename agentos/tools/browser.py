import json
import subprocess
import sys
import threading

from agentos.tools import tool

RENDER_TIMEOUT_S = 25

# Render's free tier is 512MB RAM total. Two headless Chromium instances
# competing for that at once is a much likelier way to OOM the whole app
# than one ever is - cap concurrent renders to 1 regardless of how many
# agent steps are running in parallel.
_render_slot = threading.Semaphore(1)


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
    with _render_slot:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "agentos.tools._render_subprocess", url],
                capture_output=True, text=True, timeout=RENDER_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return f"Rendering {url} timed out after {RENDER_TIMEOUT_S}s."

    output = (result.stdout or "").strip()
    if not output:
        # negative returncode means the OS killed it by signal (e.g. -9
        # for an OOM kill) rather than the script exiting on its own
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
