"""AgentOS HTTP API — the same kernel event stream over the network.

    python cli.py serve            # or: uvicorn api:app --host 0.0.0.0

    GET  /health    -> liveness probe for load balancers / orchestrators
    GET  /agents    -> registered agents and their tools
    POST /run       -> run a request; streams NDJSON events as they happen
    POST /execute   -> execute action(s) previously returned in an
                       approval_required event, exactly as previewed
    GET  /auth/google/login, /auth/google/callback -> optional "Sign in
                       with Google" issuing an API key automatically

Authentication: create API keys with `python cli.py keys create <name>`,
or (if configured) let users self-serve one via GET /auth/google/login.
Once at least one (non-revoked) key exists, /run and /execute require
'Authorization: Bearer <key>' and each key gets its own rate-limit budget.
Before any key is ever created, the API runs unauthenticated ("open
mode") sharing a single global budget - fine for solo/local use, but a
public deployment should create keys for real users.
"""

import html
import json
import logging
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

import agentos
import agentos.agents  # noqa: F401  (registers built-in agents)
from agentos import config, monitoring, oauth
from agentos.kernel import Kernel
from agentos.memory import default_memory
from agentos.registry import all_specs

log = logging.getLogger("agentos.api")
monitoring.init()

app = FastAPI(
    title="AgentOS API",
    version=agentos.__version__,
    description="Multi-agent orchestration: plan → agents → tools → verify.",
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
    return {"status": "ok", "version": agentos.__version__}


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
