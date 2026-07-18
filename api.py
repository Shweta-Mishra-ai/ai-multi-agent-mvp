"""AgentOS HTTP API — the same kernel event stream over the network.

    python cli.py serve            # or: uvicorn api:app --host 0.0.0.0

    GET  /health   -> liveness probe for load balancers / orchestrators
    GET  /agents   -> registered agents and their tools
    POST /run      -> run a request; streams NDJSON events as they happen
"""

import json
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import agentos
import agentos.agents  # noqa: F401  (registers built-in agents)
from agentos import config
from agentos.kernel import Kernel
from agentos.registry import all_specs

app = FastAPI(
    title="AgentOS API",
    version=agentos.__version__,
    description="Multi-agent orchestration: plan → agents → tools → verify.",
)


class RunRequest(BaseModel):
    request: str = Field(min_length=1, max_length=config.MAX_INPUT_CHARS)
    energy: str = Field(default="Medium", pattern="^(Low|Medium|High)$")
    session_id: Optional[str] = Field(default=None, max_length=32)


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
        for event in Kernel().run(body.request, body.energy,
                                  session_id=body.session_id):
            yield json.dumps(event, default=str) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
