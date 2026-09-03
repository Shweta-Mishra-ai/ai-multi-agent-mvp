"""AgentOS HTTP API — the same kernel event stream over the network.

    python cli.py serve            # or: uvicorn api:app --host 0.0.0.0

    GET  /health    -> liveness probe for load balancers / orchestrators
    GET  /diagnostics -> real self-check: live LLM call, real search, real
                       DB write, reporting the true error for each
    GET  /agents    -> registered agents and their tools
    POST /run       -> run a request; streams NDJSON events as they happen
    POST /execute   -> execute action(s) previously returned in an
                       approval_required event, exactly as previewed
    POST /internal/check-followups -> send/skip due email follow-ups;
                       machine-to-machine only, see agentos/followup.py
    GET  /auth/google/login, /auth/google/callback -> optional "Sign in
                       with Google" issuing an API key automatically
    GET  /auth/instagram/login, /auth/instagram/callback,
         /auth/linkedin/login, /auth/linkedin/callback -> optional social
                       posting: connects ONE Instagram/LinkedIn account
                       for the whole deployment, like SMTP

Authentication: create API keys with `python cli.py keys create <name>`,
or (if configured) let users self-serve one via GET /auth/google/login.
Once at least one (non-revoked) key exists, /run and /execute require
'Authorization: Bearer <key>' and each key gets its own rate-limit budget.
Before any key is ever created, the API runs unauthenticated ("open
mode") sharing a single global budget - fine for solo/local use, but a
public deployment should create keys for real users.
"""

import hmac
import html
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agentos
import agentos.agents  # noqa: F401  (registers built-in agents)
from agentos import config, followup, monitoring, oauth, social_instagram, social_linkedin
from agentos.kernel import Kernel
from agentos.memory import default_memory
from agentos.registry import all_specs

log = logging.getLogger("agentos.api")
monitoring.init()

# Where the built web UI lives. Overridable so a container can serve a
# build from elsewhere (and so tests can point at an empty directory to
# exercise the "no build present" path).
_FRONTEND_DIST = Path(
    os.getenv("AGENTOS_FRONTEND_DIST")
    or Path(__file__).parent / "frontend" / "dist"
)


def _frontend_dist_exists():
    return (_FRONTEND_DIST / "index.html").is_file()

app = FastAPI(
    title="AgentOS API",
    version=agentos.__version__,
    description="Multi-agent orchestration: plan → agents → tools → verify.",
)

# AgentOS is designed to be embeddable in other products (see README), so
# CORS is open by default; restrict it by setting a comma-separated
# AGENTOS_CORS_ORIGINS if this API should only ever be called from one
# specific frontend origin.
_cors_origins = os.getenv("AGENTOS_CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_origins == "*" else _cors_origins.split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_identity(authorization: Optional[str]):
    """Returns None in open mode (no keys ever created), or the verified
    identity dict {"id", "name", "can_execute"}. Raises 401 for a missing/
    invalid/revoked key once at least one key exists."""
    if not default_memory.any_api_keys_exist():
        return None  # open mode: nobody has set up keys yet

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="This deployment requires an API key: pass "
                   "'Authorization: Bearer <key>'.",
        )
    identity = default_memory.verify_api_key(authorization[len("Bearer "):].strip())
    if identity is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
    return identity


def get_api_key_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """FastAPI dependency for /run: resolves the caller's identity for
    rate limiting and enforces auth once at least one API key exists."""
    identity = _resolve_identity(authorization)
    return identity["id"] if identity else None


def get_executable_api_key_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """FastAPI dependency for /execute: same as get_api_key_id, but also
    enforces the key's can_execute scope - a restricted key (created with
    `keys create <name> --no-execute`) can preview irreversible actions
    via /run but is never allowed to actually execute them."""
    identity = _resolve_identity(authorization)
    if identity and not identity["can_execute"]:
        raise HTTPException(
            status_code=403,
            detail="This API key is restricted to preview-only access and "
                   "cannot execute approved actions.",
        )
    return identity["id"] if identity else None


class ExecuteRequest(BaseModel):
    actions: list[dict[str, Any]] = Field(min_length=1, max_length=20)


class RunRequest(BaseModel):
    request: str = Field(min_length=1, max_length=config.MAX_INPUT_CHARS)
    energy: str = Field(default="Medium", pattern="^(Low|Medium|High)$")
    session_id: Optional[str] = Field(default=None, max_length=32)
    approve: bool = Field(
        default=False,
        description="Execute real-world actions (e.g. send email). When "
                    "false, such actions are returned as previews in an "
                    "approval_required event.")


@app.get("/health")
def health():
    """Liveness probe, and enough build detail to tell at a glance WHICH
    code a deployment is actually running - a stale deploy otherwise
    looks identical to a broken one from the outside."""
    return {
        "status": "ok",
        "version": agentos.__version__,
        # Render sets RENDER_GIT_COMMIT automatically; harmless elsewhere.
        "commit": (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT")
                   or "unknown")[:12],
        "web_ui_built": _frontend_dist_exists(),
    }


@app.get("/diagnostics")
def diagnostics():
    """What is ACTUALLY working on this deployment: makes a real LLM call,
    runs a real search, writes to the real database, and reports the true
    error for anything that fails.

    Unauthenticated on purpose - it's the tool you need precisely when
    the deployment is misbehaving (possibly including auth itself), and
    it never returns secrets: keys are reported only as present/absent."""
    from agentos import diagnostics as diag

    return diag.run_diagnostics()


@app.get("/agents")
def agents():
    return [
        {"name": s.name, "description": s.description, "tools": s.tools}
        for s in all_specs()
    ]


@app.post("/run")
def run(body: RunRequest, api_key_id: Optional[str] = Depends(get_api_key_id)):
    def stream():
        try:
            for event in Kernel().run(body.request, body.energy,
                                      session_id=body.session_id,
                                      approve=body.approve,
                                      api_key_id=api_key_id):
                yield json.dumps(event, default=str) + "\n"
        except Exception as e:
            # Without this, an unexpected error mid-stream would truncate
            # the NDJSON response with no terminal event, leaving the
            # client to guess whether the run finished or died.
            log.exception("unhandled error while streaming a run")
            monitoring.capture_exception(e)
            yield json.dumps({"type": "error", "message": f"Internal error: {e}"},
                             default=str) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/execute")
def execute(body: ExecuteRequest,
           api_key_id: Optional[str] = Depends(get_executable_api_key_id)):
    """Execute action(s) previously returned in a /run approval_required
    event, using their exact recorded arguments. This never re-runs the
    plan or any agent, so the action executed is guaranteed to match
    what was previewed - re-running a full plan would ask the LLM to
    regenerate its output, which is non-deterministic and could execute
    something different from what the caller reviewed and approved."""
    try:
        return Kernel().execute_approved(body.actions, api_key_id=api_key_id)
    except Exception as e:
        log.exception("unhandled error executing approved actions")
        monitoring.capture_exception(e)
        return JSONResponse(status_code=500, content={"message": f"Internal error: {e}"})


@app.post("/internal/check-followups")
def check_followups(x_cron_secret: Optional[str] = Header(None)):
    """Triggered by a scheduled GitHub Actions workflow (see
    .github/workflows/email-followup-cron.yml) - not for interactive use.
    Guarded by a dedicated shared secret rather than the general API-key
    system, since this is a machine-to-machine trigger with no caller
    identity of its own, the same shape as the (now in-process) browser
    worker's token used earlier."""
    secret = os.getenv("FOLLOWUP_CRON_SECRET")
    if not secret:
        raise HTTPException(
            status_code=404,
            detail="Email follow-up automation is not configured on this deployment.")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, secret):
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret.")

    try:
        return followup.check_due_followups()
    except Exception as e:
        log.exception("unhandled error checking follow-ups")
        monitoring.capture_exception(e)
        return JSONResponse(status_code=500, content={"message": f"Internal error: {e}"})


@app.get("/auth/google/login")
def google_login():
    """Redirects to Google's consent screen. Requires GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI to be configured - see
    the README's OAuth section for the Google Cloud Console setup this
    depends on (which only the deployment operator can do)."""
    if not oauth.is_configured():
        raise HTTPException(
            status_code=404,
            detail="Google sign-in is not configured on this deployment.")
    redirect_uri = config.GOOGLE_REDIRECT_URI
    if not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_REDIRECT_URI is not set on this deployment.")
    return RedirectResponse(oauth.build_authorize_url(redirect_uri))


@app.get("/auth/google/callback")
def google_callback(code: Optional[str] = None, state: Optional[str] = None,
                    error: Optional[str] = None):
    """Exchanges the authorization code for a verified email, then issues
    (or reissues - see upsert_google_key) an API key for that account."""
    if error:
        raise HTTPException(status_code=400,
                            detail=f"Google sign-in failed: {error}")
    if not code or not state or not oauth.consume_state(state):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired sign-in attempt - please try again.")
    try:
        email = oauth.exchange_code_for_email(code, config.GOOGLE_REDIRECT_URI)
    except Exception as e:
        log.warning("Google OAuth exchange failed: %s", e)
        monitoring.capture_exception(e)
        raise HTTPException(status_code=502, detail="Could not verify Google sign-in.")

    key_id, plaintext = default_memory.upsert_google_key(email)
    safe_email = html.escape(email)
    safe_key = html.escape(plaintext)
    return HTMLResponse(f"""
        <h2>Signed in as {safe_email}</h2>
        <p>Your API key (shown once — copy it now, it can't be shown again):</p>
        <pre style="background:#eee;padding:1em;word-wrap:break-word;">{safe_key}</pre>
        <p>Use it as a header: <code>Authorization: Bearer {safe_key}</code></p>
    """)


@app.get("/auth/instagram/login")
def instagram_login():
    """Redirects to Meta's consent screen. Requires META_APP_ID,
    META_APP_SECRET and META_REDIRECT_URI - see the README's social
    posting section for the Meta Developer app setup this depends on.
    Connects ONE Instagram account for this whole deployment (like SMTP),
    not a separate account per API key."""
    if not social_instagram.is_configured():
        raise HTTPException(
            status_code=404,
            detail="Instagram posting is not configured on this deployment.")
    redirect_uri = config.META_REDIRECT_URI
    if not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="META_REDIRECT_URI is not set on this deployment.")
    return RedirectResponse(social_instagram.build_authorize_url(redirect_uri))


@app.get("/auth/instagram/callback")
def instagram_callback(code: Optional[str] = None, state: Optional[str] = None,
                       error: Optional[str] = None):
    """Exchanges the authorization code for a long-lived token tied to
    the linked Instagram Business account, then stores it for posting."""
    if error:
        raise HTTPException(status_code=400,
                            detail=f"Instagram connect failed: {error}")
    if not code or not state or not social_instagram.consume_state(state):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired connect attempt - please try again.")
    try:
        access_token, ig_account_id, expires_at = social_instagram.exchange_code_for_account(
            code, config.META_REDIRECT_URI)
    except Exception as e:
        log.warning("Instagram OAuth exchange failed: %s", e)
        monitoring.capture_exception(e)
        raise HTTPException(status_code=502, detail="Could not connect Instagram.")

    default_memory.save_social_token(
        "default", "instagram", access_token, ig_account_id, expires_at)
    return HTMLResponse(
        "<h2>Instagram connected</h2>"
        "<p>Agents on this deployment can now post to Instagram when you approve it.</p>")


@app.get("/auth/linkedin/login")
def linkedin_login():
    """Redirects to LinkedIn's consent screen. Requires LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET and LINKEDIN_REDIRECT_URI - see the README's
    social posting section for the LinkedIn Developer app setup this
    depends on. Connects ONE LinkedIn profile for this whole deployment
    (like SMTP), not a separate account per API key."""
    if not social_linkedin.is_configured():
        raise HTTPException(
            status_code=404,
            detail="LinkedIn posting is not configured on this deployment.")
    redirect_uri = config.LINKEDIN_REDIRECT_URI
    if not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="LINKEDIN_REDIRECT_URI is not set on this deployment.")
    return RedirectResponse(social_linkedin.build_authorize_url(redirect_uri))


@app.get("/auth/linkedin/callback")
def linkedin_callback(code: Optional[str] = None, state: Optional[str] = None,
                      error: Optional[str] = None):
    """Exchanges the authorization code for a token tied to the signed-in
    member's own profile, then stores it for posting."""
    if error:
        raise HTTPException(status_code=400,
                            detail=f"LinkedIn connect failed: {error}")
    if not code or not state or not social_linkedin.consume_state(state):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired connect attempt - please try again.")
    try:
        access_token, member_urn, expires_at = social_linkedin.exchange_code_for_member(
            code, config.LINKEDIN_REDIRECT_URI)
    except Exception as e:
        log.warning("LinkedIn OAuth exchange failed: %s", e)
        monitoring.capture_exception(e)
        raise HTTPException(status_code=502, detail="Could not connect LinkedIn.")

    default_memory.save_social_token(
        "default", "linkedin", access_token, member_urn, expires_at)
    return HTMLResponse(
        "<h2>LinkedIn connected</h2>"
        "<p>Agents on this deployment can now post to LinkedIn when you approve it.</p>")


# Serve the built React frontend (frontend/dist) at "/", if present. This
# is registered LAST so it never shadows the API routes above (Starlette
# matches routes in registration order) - and only if the build actually
# exists, so running the API without ever building the frontend (e.g.
# the test suite, or local API-only development) still works rather than
# raising at import time.
if _frontend_dist_exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
else:
    log.warning("frontend/dist not found - serving API only (run "
                "`npm run build` in frontend/ to enable the web UI)")

    @app.get("/", include_in_schema=False)
    def missing_frontend():
        """Explain the situation instead of returning a bare 404.

        A plain `{"detail": "Not Found"}` here is indistinguishable from a
        crashed app, a wrong URL, or a stale deployment - which is exactly
        the confusion this page exists to prevent. It states what's
        actually true: the API is healthy, the web UI just isn't in this
        build."""
        commit = (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT")
                  or "unknown")[:12]
        return HTMLResponse(status_code=503, content=f"""
            <html><head><title>AgentOS - web UI not built</title></head>
            <body style="font-family:system-ui;max-width:40em;margin:4em auto;
                         padding:0 1em;line-height:1.6;">
            <h1>AgentOS API is running &mdash; the web UI isn't in this build</h1>
            <p>The backend is healthy (try
               <a href="/health">/health</a>,
               <a href="/agents">/agents</a>, or
               <a href="/docs">/docs</a>), but no
               <code>frontend/dist</code> was found, so there's nothing to
               serve here.</p>
            <p>Running version <code>{html.escape(agentos.__version__)}</code>,
               commit <code>{html.escape(commit)}</code>.</p>
            <h2>Fix it</h2>
            <ul>
              <li><b>Deployed (Docker/Render):</b> the image's Node build
                  stage didn't produce a build, or the running deploy
                  predates the web UI. Redeploy the latest commit with
                  the build cache cleared, and check the build log for
                  <code>npm run build</code>.</li>
              <li><b>Local:</b> run <code>cd frontend && npm install &&
                  npm run build</code>, then restart the server.</li>
            </ul>
            </body></html>
        """)
