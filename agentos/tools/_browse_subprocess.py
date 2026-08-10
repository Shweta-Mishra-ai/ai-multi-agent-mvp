"""Standalone entry point run as a subprocess by browse_and_accomplish
(agentos/tools/browser.py) - never imported directly.

Uses browser-use (an LLM-driven browser automation agent: it looks at the
page, decides an action - click, type, navigate - and repeats) instead of
a single page load like render_page, for tasks that genuinely need
interaction (searching a box, filling a form, clicking through a flow).
Runs in its own OS process for the same reason render_page's subprocess
does: an OOM kill here only ends this one browse task, not the whole API
server, given Render's free tier is 512MB RAM total.

Usage: python -m agentos.tools._browse_subprocess <task> [start_url]
Prints one JSON line to stdout: {"result": ...} on success, or
{"error": ...} on failure. Never raises.
"""

import asyncio
import json
import os
import sys

MAX_RESULT_CHARS = 8000
MAX_STEPS = 15

# Same rationale as render_page's LAUNCH_ARGS: minimize Chromium's own
# memory footprint on a 512MB-RAM host. chromium_sandbox=False is
# browser-use's dedicated field for what render_page passes as the raw
# --no-sandbox flag.
EXTRA_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--mute-audio",
    "--disable-extensions",
]

# Off by default: this project's other integrations (fetch_url, render_page,
# find_freelance_jobs) never phone home to anything but the target URL and
# the configured LLM provider - browser-use's own analytics shouldn't be an
# exception just because it ships one.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")


def _emit(payload):
    print(json.dumps(payload), flush=True)


async def _run(task, start_url):
    from browser_use import Agent, BrowserProfile, ChatOpenAI

    llm = ChatOpenAI(
        model=os.getenv("AGENTOS_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
    profile = BrowserProfile(
        headless=True, chromium_sandbox=False, args=EXTRA_ARGS)

    full_task = f"Starting at {start_url}: {task}" if start_url else task
    agent = Agent(task=full_task, llm=llm, browser_profile=profile)
    history = await agent.run(max_steps=MAX_STEPS)
    return history.final_result() or (
        "The browsing task finished without a clear final result "
        f"after {MAX_STEPS} steps.")


def main():
    if len(sys.argv) < 2:
        _emit({"error": "usage: _browse_subprocess.py <task> [start_url]"})
        return

    task = sys.argv[1]
    start_url = sys.argv[2] if len(sys.argv) > 2 else ""

    try:
        result = asyncio.run(_run(task, start_url))
    except Exception as e:
        _emit({"error": str(e)})
        return

    _emit({"result": str(result)[:MAX_RESULT_CHARS]})


if __name__ == "__main__":
    main()
