"""AgentOS browser worker: renders a page with a real headless browser
and returns its visible text.

This exists for one specific gap in the main AgentOS app: fetch_url does
a plain HTTP GET and strips tags, which returns nothing useful for
JavaScript-rendered pages (single-page apps, client-side-rendered
listings, etc). This service actually launches Chromium, lets the page's
JS run, and returns what a real browser would show.

It deliberately does NOT attempt to log into authenticated sites - there
are no credentials here, and handling that per-site (2FA, CAPTCHAs,
session cookies) is a much larger problem this worker does not solve.

Run standalone: uvicorn app:app --host 0.0.0.0 --port 7860
Requires WORKER_API_KEY to be set - every request must send it as
'Authorization: Bearer <WORKER_API_KEY>', since this runs on a public
URL and unauthenticated use would let anyone spend your compute.
"""

import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field

from security import is_safe_url

MAX_TEXT_CHARS = 8000
NAV_TIMEOUT_MS = 20000

app = FastAPI(title="AgentOS Browser Worker")


class RenderRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


def _check_auth(authorization: Optional[str]):
    token = os.getenv("WORKER_API_KEY")
    if not token:
        raise HTTPException(
            status_code=500,
            detail="WORKER_API_KEY is not configured on this worker.")
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401,
                            detail="Invalid or missing worker token.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/render")
def render(body: RenderRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not is_safe_url(body.url):
        raise HTTPException(
            status_code=422,
            detail=f"{body.url} is not a safe public http(s) URL "
                   "(internal/private addresses are not allowed).")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
                page.goto(body.url, wait_until="networkidle")
                # the page may have redirected - re-check the URL it
                # actually landed on, the same reason fetch_url re-checks
                # every redirect hop instead of trusting the original one
                if not is_safe_url(page.url):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Redirected to {page.url}, which is not a "
                               "safe public address.")
                title = page.title()
                text = page.inner_text("body")
            finally:
                browser.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Could not render {body.url}: {e}")

    return {"title": title, "text": text[:MAX_TEXT_CHARS]}
