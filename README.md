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
                 │ code       │ │ files     │ │ (SQLite)  │
                 │ writer     │ │ calc, now │ │           │
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

## 💻 CLI usage

```bash
pip install -r requirements.txt
cp .env.example .env        # add your OPENAI_API_KEY

python cli.py run "research the top 3 CRM tools and draft a comparison email"
python cli.py chat          # interactive session with memory
python cli.py agents        # list registered agents and their tools
python cli.py history       # recent sessions from persistent memory
python cli.py ui            # launch the Streamlit web frontend
```

---

## ➕ Adding a new agent (one registration call)

```python
# agentos/agents/builtin.py
register(AgentSpec(
    name="translator",
    description="Translates text between languages.",
    system_prompt="You are a professional translator...",
    tools=["now"],            # any tools from the registry
))
```

The planner discovers it automatically — no other changes needed.
New tools are one `@tool` decorator in `agentos/tools/`.

---

## 📦 Project layout

```
agentos/
  kernel.py        # orchestrator: plan → execute → verify, event stream
  planner.py       # LLM planner (structured output, learns agents from registry)
  registry.py      # AgentSpec registration & discovery
  memory.py        # SQLite: sessions, messages, events, key-value memory
  llm.py           # provider-agnostic LLM client
  agents/
    base.py        # generic tool-loop agent
    builtin.py     # task / research / email / code / writer
  tools/           # the "syscalls": web, files, mail, system, memory
cli.py             # Typer + Rich CLI (run, chat, agents, history, ui)
app.py             # Streamlit frontend over the same kernel
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

- Parallel execution of independent plan steps
- Human-in-the-loop approval gates for irreversible actions
- HTTP API frontend (same event stream) + scheduled/recurring runs
- Vector memory for semantic recall
- Evals: golden test set for planner routing quality
