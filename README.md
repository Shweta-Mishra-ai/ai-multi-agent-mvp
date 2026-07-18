# 🧠 AgentOS — Multi-Agent Orchestration System

An **agentic OS**: a kernel that plans work, schedules specialized AI agents,
gives them real-world tools, verifies the result, and remembers everything —
controllable from the **CLI** or a **web UI**, both running on the same core.

```
                ┌────────────────────────────────────────────┐
   CLI ────────►│                 KERNEL                     │
                │  plan → schedule agents → verify → deliver │
   Web UI ─────►│                                            │
                └───────┬──────────────┬───────────┬─────────┘
                        │              │           │
                 ┌──────▼─────┐ ┌──────▼────┐ ┌────▼──────┐
                 │   AGENTS   │ │   TOOLS   │ │  MEMORY   │
                 │ task       │ │ web_search│ │ sessions  │
                 │ research   │ │ fetch_url │ │ history   │
                 │ email      │ │ send_email│ │ key-value │
                 │ code       │ │ files     │ │ metrics   │
                 │ writer     │ │ calc, now │ │ (SQLite)  │
                 │ analyst    │ │ memory    │ │           │
                 │ translator │ │           │ │           │
                 └────────────┘ └───────────┘ └───────────┘
```

---

## 🚀 What makes this real orchestration

- **LLM Planner** — turns any request into a 1–5 step plan (structured JSON),
  assigning each step to the best agent, with dependencies between steps
- **Tool-using agents** — every agent runs an agentic loop: call the LLM,
  execute tools, feed results back, repeat until done
- **Real-world tools** — live web search, page fetching, file workspace,
  email sending (SMTP), calculator, date/time, long-term memory
- **Context passing** — later steps receive earlier steps' outputs
  ("research X **then** email a summary" actually chains)
- **Verification loop** — a verifier LLM judges whether the outputs satisfy
  the request; if not, the responsible agent gets one revision round
- **Persistent memory** — SQLite sessions, conversation history for
  follow-ups, and a key-value store agents can read/write across sessions
- **Frontend-agnostic kernel** — the kernel emits an event stream; CLI and
  Streamlit are thin renderers over the same events (an HTTP API would be too)
- **Provider-agnostic** — works with any OpenAI-compatible endpoint
  (OpenAI, Ollama, vLLM…) via `OPENAI_BASE_URL` + `AGENTOS_MODEL`

---

## 🛡️ Production hardening

- **Resilient LLM calls** — timeouts and automatic retries with backoff on
  rate limits and transient errors (configurable)
- **Load handling** — independent plan steps run **in parallel** (bounded
  worker pool); SQLite in WAL mode with busy timeouts for concurrent access
- **Failure isolation** — a failed step never crashes the run; dependent
  steps are explicitly skipped and the user gets a clear partial-result report
- **Budgets** — hard per-run deadline, max steps, max tool turns, and
  request-size limits protect latency and cost
- **Security** — input validation, per-deployment rate limiting, SSRF guard
  (agents cannot fetch internal/private network addresses), tool-argument
  schema validation, path-traversal-safe workspace, safe (AST-based)
  calculator, secrets only via environment
- **Observability** — structured logging, and per-run metrics (duration,
  LLM calls, tool calls, tokens, estimated cost) persisted and aggregated
  via `python cli.py stats`
- **Health & diagnostics** — `/health` endpoint for load balancers and
  `python cli.py doctor` to validate a deployment's configuration
- **Tested + CI** — pytest suite (kernel orchestration, parallelism, failure
  propagation, security guards, API) runs on every push via GitHub Actions

---

## 💻 CLI usage

```bash
pip install -r requirements.txt
cp .env.example .env        # add your OPENAI_API_KEY

python cli.py run "research the top 3 CRM tools and draft a comparison email"
python cli.py chat          # interactive session with memory
python cli.py agents        # list registered agents and their tools
python cli.py history       # recent sessions from persistent memory
python cli.py stats         # aggregated run metrics (tokens, cost, duration)
python cli.py doctor        # validate the deployment configuration
python cli.py serve         # HTTP API (FastAPI) on :8000
python cli.py ui            # launch the Streamlit web frontend
```

---

## 🌐 HTTP API & deployment

```bash
python cli.py serve                       # dev
docker compose up --build                 # production container (+ volume for data)

curl localhost:8000/health
curl localhost:8000/agents
curl -N -X POST localhost:8000/run \
     -H 'content-type: application/json' \
     -d '{"request": "research AI agent frameworks and write a report"}'
# → streams NDJSON events: plan, step_start, step_result, verify, done, metrics
```

The API streams the exact same event protocol as the CLI and web UI, so any
product can embed AgentOS.

### Deploying to Render (one click)

Push this repo, then in Render: **New → Blueprint → select the repo** —
`render.yaml` configures the service. You'll be prompted for secrets.

### 🔑 Which keys go where

| Where | Key | Required? | Purpose |
|---|---|---|---|
| **Render** (dashboard → Environment) | `OPENAI_API_KEY` | ✅ yes | the only key AgentOS needs to run |
| Render | `TAVILY_API_KEY` | optional | stronger web search (free tier at tavily.com) |
| Render | `SMTP_HOST/PORT/USER/PASSWORD/FROM` | optional | real email sending (else safe draft-only mode) |
| **GitHub Actions** | — | ❌ none | CI runs the test suite with a **mocked** LLM (`OPENAI_API_KEY: test` is a dummy value already in the workflow) — no real key, no cost, nothing to configure |

Add a GitHub secret (repo **Settings → Secrets and variables → Actions**)
only if you later add live-LLM eval jobs to CI. Never commit keys to git —
`.env` is gitignored and `render.yaml` marks secrets `sync: false`.

---

## ➕ Adding a new agent (one registration call)

```python
# agentos/agents/builtin.py
register(AgentSpec(
    name="social",
    description="Writes social media posts tuned per platform.",
    system_prompt="You are a social media expert...",
    tools=["web_search", "now"],   # any tools from the registry
))
```

The planner discovers it automatically — no other changes needed.
New tools are one `@tool` decorator in `agentos/tools/`.

---

## 📦 Project layout

```
agentos/
  kernel.py        # orchestrator: validate → plan → parallel execute → verify
  planner.py       # LLM planner (structured output, learns agents from registry)
  registry.py      # AgentSpec registration & discovery
  memory.py        # SQLite (WAL): sessions, messages, events, metrics, kv memory
  llm.py           # provider-agnostic LLM client (timeouts + retries)
  config.py        # every limit tunable via environment variables
  security.py      # input validation, rate limiting, SSRF guard
  telemetry.py     # per-run metrics: tokens, tool calls, est. cost
  log.py           # structured logging
  agents/
    base.py        # generic tool-loop agent (arg validation, output caps)
    builtin.py     # task / research / email / code / writer
  tools/           # the "syscalls": web, files, mail, system, memory
cli.py             # Typer + Rich CLI (run, chat, agents, history, stats, doctor, serve, ui)
api.py             # FastAPI HTTP API (NDJSON event stream)
app.py             # Streamlit frontend over the same kernel
tests/             # pytest suite (mocked LLM) — runs in CI on every push
```

---

## ⚙️ Configuration

All optional settings live in `.env` (see `.env.example`): custom model or
provider, Tavily API key for stronger web search, SMTP credentials to let the
email agent actually send, and storage paths.

Without SMTP configured the email agent safely returns drafts only.
Without search access the research agent answers from model knowledge and
says so explicitly.

---

## 🔮 Roadmap

- Human-in-the-loop approval gates for irreversible actions
- API authentication (keys/OAuth) + multi-tenant isolation
- Scheduled / recurring runs
- Vector memory for semantic recall
- Evals: golden test set for planner routing quality
- Postgres backend option for horizontal scaling
