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

# On Linux, the kernel's OOM killer sends SIGKILL (signal 9). subprocess
# reports that as returncode -9 - a negative returncode always means
# "killed by a signal", not "exited with an error code" (which would be
# 0-255 and positive). This is the one case worth naming plainly instead
# of the generic "may have run out of memory" guess, because it usually
# IS memory, and headless Chromium is the single heaviest thing this app
# runs on Render's 512MB free tier.
_OOM_HINT = (
    "This was killed by the operating system (signal {sig}) - almost "
    "certainly out of memory. Headless Chromium alone typically needs "
    "300-500MB, which doesn't leave much room on a 512MB-RAM host running "
    "everything else too. If this keeps happening, the free tier is "
    "genuinely too small for browser automation - a paid plan with more "
    "RAM (or a remote browser service instead of local Chromium) is the "
    "real fix, not a code change."
)


def _describe_subprocess_failure(result, label):
    """Turns a dead subprocess into an honest, specific message instead of
    a bare exit code - particularly for OOM, the single most likely
    failure mode on Render's free tier."""
    if result.returncode < 0:
        return (f"{label} (exit {result.returncode}): "
                + _OOM_HINT.format(sig=-result.returncode))
    stderr = (result.stderr or "").strip()
    return (f"{label} (exit {result.returncode}): "
            f"{stderr[-500:] or 'no output - ' + _OOM_HINT.format(sig='unknown')}")


def _run_isolated(module, args, timeout_s):
    """Runs one of the _*_subprocess.py entry points, holding the shared
    browser slot for the subprocess's whole lifetime so at most one
    headless Chromium ever runs at a time. Returns (data, error) - data
    is the parsed {"result"/"title"/"text": ...} dict on success, error
    is a ready-to-return string on any failure."""
    with _browser_slot:
        try:
            result = subprocess.run(
                [sys.executable, "-m", module, *args],
                capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return None, f"timed out after {timeout_s}s."

    output = (result.stdout or "").strip()
    if not output:
        return None, _describe_subprocess_failure(result, "Browser process failed")

    try:
        data = json.loads(output.splitlines()[-1])
    except (ValueError, IndexError):
        return None, f"unexpected output: {output[-500:]}"

    if "error" in data:
        return None, data["error"]
    return data, None


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
    data, error = _run_isolated(
        "agentos.tools._render_subprocess", [url], RENDER_TIMEOUT_S)
    if error:
        return f"Browser rendering failed: {error}"
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
    data, error = _run_isolated(
        "agentos.tools._browse_subprocess", [task, start_url], BROWSE_TIMEOUT_S)
    if error:
        return f"Browsing task failed: {error}"
    return str(data.get("result", "")).strip()
