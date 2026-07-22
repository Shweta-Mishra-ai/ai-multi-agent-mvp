# 🧠 AgentOS — Multi-Agent Orchestration System

An **agentic OS**: a kernel that plans work, schedules specialized AI agents,
gives them real-world tools, verifies the result, and remembers everything —
controllable from a **React web app**, the **CLI**, or the **HTTP API**, all
three running on the same core. The web app is a real production build
(React + TypeScript + Tailwind), served by the API itself as one deployable
service — no separate frontend server, no CORS setup needed.

```
                ┌────────────────────────────────────────────┐
   React UI ───►│                 KERNEL                     │
                │  plan → schedule agents → verify → deliver │
   CLI ────────►│                                            │
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
- **Frontend-agnostic kernel** — the kernel emits an event stream; the React
  UI and the CLI are both thin renderers over the exact same events coming
  from the HTTP API
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
  bucket) and **per-key scopes** (a `--no-execute` restricted key can
  preview irreversible actions but never actually execute them), keys
  stored only as a salted hash with constant-time verification (a leaked
  DB backup can't be used to impersonate a key), SSRF guard with
  per-redirect-hop re-validation and a response size cap (agents cannot
  fetch internal/private network addresses, including via a redirect
  chain), tool-argument schema validation, path-traversal-safe
  workspace, safe (AST-based) calculator, secrets only via environment
- **Optional "Sign in with Google"** — users can self-serve an API key at
  `/auth/google/login` instead of an operator manually creating one for
  everybody; see the OAuth section below (**requires setup only the
  operator can do**, and its full round trip is untested against
  Google's real servers - see the honesty note there)
- **Multi-tenant isolation** — workspace files and long-term memory are
  scoped per caller (their API key, or a shared "default" scope in
  open-mode/local use), and a caller can never resume a conversation
  session that belongs to a different caller, even by guessing its id
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
- **Health & diagnostics** — `/health` endpoint for load balancers,
  `python cli.py doctor` to validate a deployment's configuration, and
  `python scripts/smoke_test.py <url>` to verify a live deployment
  actually works right after deploying (not just that it started)
- **Tested + CI** — pytest suite (kernel orchestration, parallelism, failure
  propagation, security guards, concurrent-load isolation, API) runs on
  every push via GitHub Actions, gated at 80% coverage (currently ~92%,
  104+ tests)
- **Data retention** — `python cli.py prune` deletes old events/messages/
  metrics so the database doesn't grow unbounded under daily use
- **Semantic memory (optional)** — `remember`/`recall` compute an
  embedding for each saved fact when the configured provider supports it,
  so `recall` can find a fact even with no literal wording overlap with
  the search query; falls back to plain substring search automatically
  (and fast - it gives up after one failed attempt per process, not on
  every call) for providers without an embeddings endpoint (e.g. Groq)
- **Optional error monitoring** — set `SENTRY_DSN` to send unhandled and
  notable handled exceptions (planner failures, step crashes, storage
  errors) to Sentry; a true no-op with zero overhead when unset

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
python cli.py keys create "intern" --no-execute  # restricted: can preview, never execute
python cli.py keys list     # list keys (never shows the secret again)
python cli.py keys revoke <id>          # revoke a key immediately
python cli.py doctor        # validate the deployment configuration
python cli.py serve         # HTTP API - AND the web UI, once it's built (below)
```

### 🖥️ Web UI (React + TypeScript + Tailwind)

```bash
cd frontend
npm install
npm run build          # -> frontend/dist, served automatically by `cli.py serve`
```

Then just `python cli.py serve` and open `http://localhost:8000` — the API
serves the built UI at `/` and its own routes at `/health`, `/agents`,
`/run`, etc., all from one process. No `frontend/dist`? The API still runs
fine, it just has no `/` route (a 404 there is expected, not a bug — the
API's own paths and `/docs` still work).

For frontend development with hot reload, run the API separately and point
Vite's dev server at it:

```bash
python cli.py serve                    # terminal 1: API on :8000
python cli.py ui                       # terminal 2: Vite dev server on :5173, proxies to :8000
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
product can embed AgentOS. Interactive docs are auto-generated at `/docs`
(Swagger UI) and `/openapi.json` on any running instance.

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

On Render, manage keys via the service's **Shell** tab
(`python cli.py keys create "..."`) since there's no key-creation HTTP
endpoint by design — exposing key creation over the network would let
anyone mint their own key.

### Deploying to Render (one click)

In Render: **New → Blueprint → select the repo → pick the
`claude/multi-agent-orchestration-xk52e1` branch**. `render.yaml`
configures **one service** — the Dockerfile builds the React frontend
(Node, build-time only) and copies the static output into the same image
that runs the Python API, so a single container serves both the web app
(at `/`) and the API (at `/health`, `/agents`, `/run`, etc.).

You'll be prompted for `OPENAI_API_KEY`; if using Groq/Gemini instead of
OpenAI, also fill in `OPENAI_BASE_URL` and `AGENTOS_MODEL` in the
dashboard after the first deploy. The build takes a few minutes longer
than before (it now compiles the frontend too); Render gives you one URL
when ready — open it directly, that's the app.

### ✅ Launch checklist

1. `python cli.py doctor` locally - confirm `OPENAI_API_KEY` and provider
   settings are right before deploying
2. Deploy the Render blueprint (above)
3. Create at least one API key if this will be public: open the
   service's **Shell** tab on Render and run
   `python cli.py keys create "some name"` — once any key exists, both
   the API and the web UI (which calls the API to do anything) require
   one, so this is your actual "make it private" switch
4. Verify the live deployment actually works:
   `python scripts/smoke_test.py https://your-app-url.onrender.com`
   (add `--key ak_...` if you created one)
5. Schedule `python cli.py prune` periodically (e.g. a weekly Render cron
   job) so the database doesn't grow unbounded under daily use

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

### 🔐 Optional: "Sign in with Google"

Lets a user self-serve an API key at `GET /auth/google/login` instead of
an operator running `cli.py keys create` for every person. **This needs
real setup only the deployment operator can do, and has NOT been tested
against Google's real servers in development** (there's no real Google
OAuth Client ID or public HTTPS callback URL available there) - the
request/response handling (CSRF state, token exchange, error paths) is
covered by tests using mocked HTTP responses, but treat the live flow as
unverified until you've tried it yourself.

Setup:
1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials),
   create an **OAuth 2.0 Client ID** (application type: Web application).
2. Add an **authorized redirect URI**: `https://<your-api-domain>/auth/google/callback`
3. Set three env vars on the service: `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` (the exact URL from
   step 2 - it's required explicitly rather than auto-detected, since a
   reverse proxy like Render's can make requests appear to arrive over
   `http://` even though the public URL is `https://`).
4. Visit `https://<your-api-domain>/auth/google/login` - after signing
   in, the page shows a freshly issued API key (shown once). Logging in
   again issues a new key and revokes the previous one for that account.

Leave `GOOGLE_CLIENT_ID` unset and these routes 404 - the API behaves
exactly as if this feature didn't exist.

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
  identity.py      # ambient caller identity for multi-tenant isolation
  embeddings.py    # optional semantic embeddings for long-term memory
  monitoring.py    # optional Sentry error monitoring (no-op if unset)
  oauth.py         # optional "Sign in with Google" login flow
  log.py           # structured logging
  agents/
    base.py        # generic tool-loop agent (arg validation, output caps)
    builtin.py     # task / research / email / code / writer
  tools/           # the "syscalls": web, files, mail, system, memory
                   #   (workspace files & memory scoped per caller)
cli.py             # Typer + Rich CLI (run, chat, agents, history, stats,
                   #   prune, keys create/list/revoke, doctor, serve, ui)
api.py             # FastAPI HTTP API (NDJSON event stream) + serves the
                   #   built frontend/dist at "/" if present
frontend/          # React + TypeScript + Tailwind web UI (Vite)
  src/
    api.ts         # fetch helpers + NDJSON streaming parser for /run
    runReducer.ts  # event-stream -> UI state (mirrors the kernel's event types)
    types.ts       # TypeScript types matching the API's event/response shapes
    components/    # Sidebar, RequestForm, RunView, ApprovalPanel, etc.
  dist/            # production build output (gitignored; `npm run build`)
scripts/
  smoke_test.py    # post-deploy check: hits a live URL's /health, /agents, /run
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

- Session/conversation history in the web UI (resume a past run, browse
  `cli.py history` visually)
- Additional OAuth providers beyond Google (GitHub, Microsoft)
- Per-tenant quotas beyond rate limiting (e.g. workspace disk quotas)
- Scheduled / recurring runs
- Postgres backend option for horizontal scaling

---

## 📄 License

All rights reserved — see [`LICENSE`](LICENSE). This is proprietary
software; no copying, modification, or redistribution without permission.
