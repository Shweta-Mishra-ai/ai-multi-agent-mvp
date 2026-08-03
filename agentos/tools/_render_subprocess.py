"""Standalone entry point run as a subprocess by render_page (agentos/
tools/browser.py) - never imported directly.

Headless Chromium runs here, in its own OS process, rather than inline in
the API server. Render's free tier gives the whole app only 512MB RAM, so
a page that makes Chromium balloon in memory can get OOM-killed - isolating
it in a subprocess means only this one render dies when that happens,
instead of the kernel killing the API server process and taking down every
in-flight request.

Usage: python -m agentos.tools._render_subprocess <url>
Prints one JSON line to stdout: {"title": ..., "text": ...} on success,
or {"error": ...} on failure. Never raises - a subprocess that also
crashes on error would defeat the point of isolating the crash risk here.
"""

import json
import sys

from agentos.security import is_safe_url

MAX_TEXT_CHARS = 8000
NAV_TIMEOUT_MS = 15000

# Reduce Chromium's own memory/process footprint as much as possible -
# every one of these matters on a 512MB-RAM host.
LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--single-process",
    "--no-zygote",
    "--disable-extensions",
    "--mute-audio",
]


def _emit(payload):
    print(json.dumps(payload), flush=True)


def main():
    if len(sys.argv) != 2:
        _emit({"error": "usage: _render_subprocess.py <url>"})
        return

    url = sys.argv[1]
    if not is_safe_url(url):
        _emit({"error": f"{url} is not a safe public http(s) URL "
                        "(internal/private addresses are not allowed)."})
        return

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(args=LAUNCH_ARGS)
            try:
                page = browser.new_page()
                page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
                page.goto(url, wait_until="networkidle")
                # the page may have redirected - re-check the URL it
                # actually landed on, same reason fetch_url re-checks
                # every redirect hop instead of trusting the original one
                if not is_safe_url(page.url):
                    _emit({"error": f"Redirected to {page.url}, which is "
                                    "not a safe public address."})
                    return
                title = page.title()
                text = page.inner_text("body")
            finally:
                browser.close()
    except Exception as e:
        _emit({"error": str(e)})
        return

    _emit({"title": title, "text": text[:MAX_TEXT_CHARS]})


if __name__ == "__main__":
    main()
