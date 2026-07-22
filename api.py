"""AgentOS HTTP API — the same kernel event stream over the network.

    python cli.py serve            # or: uvicorn api:app --host 0.0.0.0

    GET  /health    -> liveness probe for load balancers / orchestrators
    GET  /agents    -> registered agents and their tools
    POST /run       -> run a request; streams NDJSON events as they happen
    POST /execute   -> execute action(s) previously returned in an
                       approval_required event, exactly as previewed
"""

import json
import logging
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import agentos
import agentos.agents  # noqa: F401  (registers built-in agents)
from agentos import config
from agentos.kernel import Kernel
from agentos.registry import all_specs

log = logging.getLogger("agentos.api")

app = FastAPI(
    title="AgentOS API",
    version=agentos.__version__,
    description="Multi-agent orchestration: plan → agents → tools → verify.",
)


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
def run(body: RunRequest):
    def stream():
        try:
            for event in Kernel().run(body.request, body.energy,
                                      session_id=body.session_id,
                                      approve=body.approve):
                yield json.dumps(event, default=str) + "\n"
        except Exception as e:
            # Without this, an unexpected error mid-stream would truncate
            # the NDJSON response with no terminal event, leaving the
            # client to guess whether the run finished or died.
            log.exception("unhandled error while streaming a run")
            yield json.dumps({"type": "error", "message": f"Internal error: {e}"},
                             default=str) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/execute")
def execute(body: ExecuteRequest):
    """Execute action(s) previously returned in a /run approval_required
    event, using their exact recorded arguments. This never re-runs the
    plan or any agent, so the action executed is guaranteed to match
    what was previewed - re-running a full plan would ask the LLM to
    regenerate its output, which is non-deterministic and could execute
    something different from what the caller reviewed and approved."""
    try:
        return Kernel().execute_approved(body.actions)
    except Exception as e:
        log.exception("unhandled error executing approved actions")
        return JSONResponse(status_code=500, content={"message": f"Internal error: {e}"})
