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
- **Security** — API key authentication with **per-key rate limiting**
  (each caller gets an independent budget instead of sharing one global
  bucket), keys stored only as a salted hash with constant-time
  verification (a leaked DB backup can't be used to impersonate a key),
  SSRF guard with per-redirect-hop re-validation and a response size cap
  (agents cannot fetch internal/private network addresses, including via
  a redirect chain), tool-argument schema validation, path-traversal-safe
  workspace, safe (AST-based) calculator, secrets only via environment
- **Circuit breaker** — after repeated consecutive LLM failures (a
  provider outage), calls fail instantly with a clear message for a
  cooldown period instead of every request separately paying the full
  retry-and-timeout cost, which would otherwise pile up and tie up every
  worker thread during an outage
- **Observability** — structured logging, and per-run metrics (duration,
  LLM calls, tool calls, tokens, estimated cost) persisted and aggregated
  via `python cli.py stats`
- **Human-in-the-loop approval gates** — irreversible actions (like actually
  sending an email) are never executed silently: the agent prepares a full
  preview, the run emits an `approval_required` event, and approving
  executes **exactly the previewed tool call** directly (CLI/web UI
  confirm, or `POST /execute`) rather than re-running the whole plan —
  re-running would ask the LLM to regenerate its output, which is
  non-deterministic and could execute something different from what was
  reviewed, as well as doubling LLM cost
- **Live evals** — a golden routing test set (`evals/`) measures planner
  accuracy against the real LLM; run locally or via the manual `Evals`
  GitHub Actions workflow
- **Health & diagnostics** — `/health` endpoint for load balancers and
  `python cli.py doctor` to validate a deployment's configuration
- **Tested + CI** — pytest suite (kernel orchestration, parallelism, failure
  propagation, security guards, concurrent-load isolation, API) runs on
  every push via GitHub Actions, gated at 80% coverage (currently ~89%)
- **Data retention** — `python cli.py prune` deletes old events/messages/
  metrics so the database doesn't grow unbounded under daily use

---

## 💻 CLI usage

```bash
pip install -r requirements.txt
cp .env.example .env        # add an API key (see below if you don't have one)

python cli.py run "research the top 3 CRM tools and draft a comparison email"
python cli.py run "email the report to boss@x.com" --approve   # allow real actions
python cli.py chat          # interactive session with memory
python cli.py agents        # list registered agents and their tools
python cli.py history       # recent sessions from persistent memory
python cli.py stats         # aggregated run metrics (tokens, cost, duration)
python cli.py prune         # delete old records (e.g. a weekly cron)
python cli.py keys create "some user"   # issue an API key (see Security below)
python cli.py keys list     # list keys (never shows the secret again)
python cli.py keys revoke <id>          # revoke a key immediately
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
# → streams NDJSON events: plan, step_start, step_result, verify, done,
#   approval_required (if an irreversible action was blocked), metrics

# If a run's events include approval_required, execute exactly that
# preview (never re-runs the plan/agents):
curl -X POST localhost:8000/execute \
     -H 'content-type: application/json' \
     -d '{"actions": [{"tool": "send_email", "args": {...}}]}'
```

The API streams the exact same event protocol as the CLI and web UI, so any
product can embed AgentOS.

### 🔐 Authentication & per-user rate limits

Fresh installs run **open mode**: `/run` and `/execute` work with no
`Authorization` header, sharing one global rate-limit budget — fine for
solo/local use. The moment you create your first API key, the API
**permanently** requires a key on every `/run`/`/execute` call (even if
that key is later revoked — revoking is for rotating out a compromised
key, not for reopening the API to the public).

```bash
python cli.py keys create "acme-corp"     # shown ONCE - store it now
# → ak_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

curl -X POST localhost:8000/run \
     -H 'content-type: application/json' \
     -H 'Authorization: Bearer ak_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' \
     -d '{"request": "..."}'
```

Give each real user/team their own key (`cli.py keys create "their name"`)
so **one key's traffic never exhausts another's budget** — the opposite of
a single shared bucket, where one very active user could starve everyone
else. Keys are stored as a salted hash (never in plaintext) with
constant-time comparison; `cli.py keys list` shows metadata only, never
the secret itself. `/health` and `/agents` never require a key.

On Render, manage keys via the **Shell** tab on the `agentos-api`
service (`python cli.py keys create "..."`) since there's no key-creation
HTTP endpoint by design — exposing key creation over the network would
let anyone mint their own key.

### Deploying to Render (one click)

In Render: **New → Blueprint → select the repo → pick the
`claude/multi-agent-orchestration-xk52e1` branch**. `render.yaml`
configures **two services** from the same code:

- **`agentos-ui`** — a clickable website (Streamlit). This is what most
  people want: open the URL Render gives you, type a request, click
  "Run AgentOS".
- **`agentos-api`** — the HTTP API, for integrating AgentOS into another
  app or script.

You'll be prompted once for `OPENAI_API_KEY` (shared by both services);
if using Groq/Gemini instead of OpenAI, also fill in `OPENAI_BASE_URL`
and `AGENTOS_MODEL` in the group's dashboard settings after the first
deploy. Each service takes a few minutes to build; Render gives each one
its own URL when ready.

### 🔑 Which keys go where

| Where | Key | Required? | Purpose |
|---|---|---|---|
| **Render** (dashboard → Environment) | `OPENAI_API_KEY` | ✅ yes | the only key AgentOS needs to run |
| Render | `TAVILY_API_KEY` | optional | stronger web search (free tier at tavily.com) |
| Render | `SMTP_HOST/PORT/USER/PASSWORD/FROM` | optional | real email sending (else safe draft-only mode) |
| **GitHub Actions** (CI) | — | ❌ none | CI runs the test suite with a **mocked** LLM (`OPENAI_API_KEY: test` is a dummy value already in the workflow) — no real key, no cost, nothing to configure |
| GitHub Actions (**Evals**, manual) | `OPENAI_API_KEY` secret | optional | the `Evals` workflow runs the golden routing set against the real LLM; add the secret in repo **Settings → Secrets and variables → Actions**, then trigger it from the Actions tab |

Never commit keys to git — `.env` is gitignored and `render.yaml` marks
secrets `sync: false`.

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
  memory.py        # SQLite (WAL): sessions, messages, events, metrics,
                   #   kv memory, API keys (hashed) - schema auto-migrates
  llm.py           # provider-agnostic LLM client (timeouts, retries, circuit breaker)
  circuit_breaker.py  # fails fast during a sustained LLM provider outage
  config.py        # every limit tunable via environment variables
  security.py      # input validation, per-key rate limiting, SSRF guard
  telemetry.py     # per-run metrics: tokens, tool calls, est. cost
  log.py           # structured logging
  agents/
    base.py        # generic tool-loop agent (arg validation, output caps)
    builtin.py     # task / research / email / code / writer
  tools/           # the "syscalls": web, files, mail, system, memory
cli.py             # Typer + Rich CLI (run, chat, agents, history, stats,
                   #   prune, keys create/list/revoke, doctor, serve, ui)
api.py             # FastAPI HTTP API (NDJSON event stream)
app.py             # Streamlit frontend over the same kernel
tests/             # pytest suite (mocked LLM) — runs in CI on every push
```

---

## ⚙️ Configuration

All optional settings live in `.env` (see `.env.example`): custom model or
provider, Tavily API key for stronger web search, SMTP credentials to let the
email agent actually send, and storage paths.

### No OpenAI key? Run AgentOS for free

AgentOS works with **any OpenAI-compatible provider** — just set
`OPENAI_BASE_URL` + `AGENTOS_MODEL` in `.env` (exact copy-paste configs are
in `.env.example`):

| Provider | Cost | Get a key |
|---|---|---|
| **Groq** (recommended: fast, generous free tier) | free, no card | console.groq.com/keys |
| **Google Gemini** | free tier, no card | aistudio.google.com/apikey |
| **Ollama** (runs on your own machine) | 100% free, no key at all | ollama.com |

Note: the planner and verifier use structured JSON output. Groq and Gemini
support it; if a provider doesn't, AgentOS degrades gracefully (single-step
plans, verifier skipped) instead of crashing.

Without SMTP configured the email agent safely returns drafts only.
Without search access the research agent answers from model knowledge and
says so explicitly.

---

## 🔮 Roadmap

- OAuth / SSO in addition to API keys, and per-key scopes (e.g. read-only,
  no-approval-gate-bypass)
- Scheduled / recurring runs
- Vector memory for semantic recall
- Postgres backend option for horizontal scaling
