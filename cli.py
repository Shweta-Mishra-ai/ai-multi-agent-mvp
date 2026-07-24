"""AgentOS command-line interface.

    python cli.py run "research AI agent frameworks and write a report"
    python cli.py chat                 # interactive session with memory
    python cli.py agents               # list registered agents and tools
    python cli.py history              # recent sessions
    python cli.py serve                # HTTP API + web UI (if built)
    python cli.py ui                   # React frontend in dev mode (hot reload)
"""

import os
import subprocess
import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from agentos import monitoring

monitoring.init()

app = typer.Typer(add_completion=False, help="AgentOS — multi-agent orchestration")
console = Console()

keys_app = typer.Typer(add_completion=False, help="Manage API keys for the HTTP API")
app.add_typer(keys_app, name="keys")


def _render_events(events):
    final = None
    approval_needed = False
    pending_actions = []
    for event in events:
        kind = event["type"]
        if kind == "plan":
            table = Table(title="📋 Plan", show_lines=False)
            table.add_column("#", style="dim", width=3)
            table.add_column("Agent", style="cyan")
            table.add_column("Instruction")
            for i, step in enumerate(event["steps"], 1):
                table.add_row(str(i), step["agent"], step["instruction"])
            console.print(table)
        elif kind == "step_start":
            console.print(
                f"[dim]▶ step {event['index'] + 1}:[/dim] "
                f"[cyan]{event['agent']}[/cyan] agent working..."
            )
        elif kind == "step_result":
            status = event.get("status", "ok")
            style = {"ok": "green", "failed": "red", "skipped": "yellow"}[status]
            console.print(Panel(
                Markdown(str(event["output"])),
                title=f"step {event['index'] + 1} · {event['agent']}"
                      + ("" if status == "ok" else f" · {status}"),
                border_style=style,
            ))
        elif kind == "verify":
            if event["satisfied"]:
                console.print("[green]✔ verifier: output satisfies the request[/green]")
            else:
                console.print(
                    f"[yellow]✎ verifier requested a revision:[/yellow] "
                    f"{event['feedback']}"
                )
        elif kind == "approval_required":
            approval_needed = True
            pending_actions = event["actions"]
            lines = "\n".join(
                f"• {a['tool']}({', '.join(f'{k}={v!r}' for k, v in a['args'].items())})"
                for a in event["actions"]
            )
            console.print(Panel(
                f"These real-world actions were prepared but NOT executed:\n\n{lines}",
                title="⚠ approval required", border_style="yellow",
            ))
        elif kind == "error":
            console.print(Panel(str(event["message"]), title="error",
                                border_style="red"))
        elif kind == "metrics":
            console.print(
                f"[dim]⏱ {event['duration_s']}s · {event['llm_calls']} LLM calls · "
                f"{event['tool_calls']} tool calls · {event['tokens']} tokens · "
                f"~${event['est_cost_usd']}[/dim]"
            )
        elif kind == "done":
            final = event["output"]
    return {"final": final, "approval_needed": approval_needed,
            "pending_actions": pending_actions}


def _execute_approved(pending_actions):
    """Execute exactly the previewed actions - no re-planning, no re-running
    any agent, so what gets executed is guaranteed to match what was shown."""
    from agentos.kernel import Kernel

    for result in Kernel().execute_approved(pending_actions):
        console.print(Panel(str(result["result"]),
                            title=f"executed: {result['tool']}",
                            border_style="green"))


@app.command()
def run(
    request: str = typer.Argument(..., help="What you want AgentOS to do"),
    energy: str = typer.Option("Medium", help="Low / Medium / High"),
    approve: bool = typer.Option(
        False, "--approve",
        help="Execute real-world actions (e.g. actually send email)"),
):
    """Run one request through the kernel and print the result."""
    from agentos.kernel import Kernel

    outcome = _render_events(Kernel().run(request, energy, approve=approve))
    if outcome["approval_needed"]:
        if sys.stdin.isatty() and typer.confirm(
                "Approve and execute exactly the action(s) previewed above?"):
            _execute_approved(outcome["pending_actions"])
        else:
            console.print("[yellow]Re-run with --approve to execute "
                          "the pending actions.[/yellow]")


@app.command()
def chat(energy: str = typer.Option("Medium", help="Low / Medium / High")):
    """Interactive session: follow-ups share memory and context."""
    from agentos.kernel import Kernel

    kernel = Kernel()
    session_id = None
    console.print("[bold]AgentOS chat[/bold] — type 'exit' to quit\n")
    while True:
        try:
            user_input = console.input("[bold cyan]you ›[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in {"exit", "quit"}:
            break

        approval_needed = False
        pending_actions = []
        for event in kernel.run(user_input, energy, session_id=session_id):
            if event["type"] == "plan":
                session_id = event["session_id"]
                agents = " → ".join(s["agent"] for s in event["steps"])
                console.print(f"[dim]plan: {agents}[/dim]")
            elif event["type"] == "step_start":
                console.print(f"[dim]  {event['agent']} working...[/dim]")
            elif event["type"] == "approval_required":
                approval_needed = True
                pending_actions = event["actions"]
            elif event["type"] == "error":
                console.print(Panel(str(event["message"]), border_style="red"))
            elif event["type"] == "done":
                console.print(Panel(Markdown(str(event["output"])),
                                    border_style="green"))
        if approval_needed and typer.confirm(
                "⚠ Real-world actions await approval. Approve and execute "
                "exactly what was previewed?"):
            _execute_approved(pending_actions)
    console.print("[dim]bye[/dim]")


@app.command()
def agents():
    """List registered agents and their tools."""
    import agentos.agents  # noqa: F401
    from agentos.registry import all_specs

    table = Table(title="Registered agents")
    table.add_column("Agent", style="cyan")
    table.add_column("Purpose")
    table.add_column("Tools", style="magenta")
    for spec in all_specs():
        table.add_row(spec.name, spec.description, ", ".join(spec.tools) or "—")
    console.print(table)


@app.command()
def history(limit: int = typer.Option(10, help="How many sessions to show")):
    """Show recent sessions from persistent memory."""
    from agentos.memory import default_memory

    table = Table(title="Recent sessions")
    table.add_column("When", style="dim")
    table.add_column("Session", style="cyan")
    table.add_column("Request")
    for s in default_memory.recent_sessions(limit):
        when = datetime.fromtimestamp(s["created_at"]).strftime("%d %b %H:%M")
        table.add_row(when, s["id"], s["title"])
    console.print(table)


@app.command()
def ui():
    """Launch the React frontend in dev mode (hot reload) against a
    locally running `cli.py serve` on :8000. For production, the
    frontend is already served BY `cli.py serve` - build it first with
    `cd frontend && npm run build`, no separate process needed."""
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
    if not os.path.isdir(os.path.join(frontend_dir, "node_modules")):
        console.print("[dim]Installing frontend dependencies (first run only)...[/dim]")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
    subprocess.run(["npm", "run", "dev"], cwd=frontend_dir)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address"),
    port: int = typer.Option(8000, help="Port"),
):
    """Launch the HTTP API - and the web UI too, if frontend/dist has
    been built (`cd frontend && npm run build`), served from the same
    origin at '/'."""
    import uvicorn

    uvicorn.run("api:app", host=host, port=port)


@app.command()
def stats(limit: int = typer.Option(100, help="How many recent runs to aggregate")):
    """Aggregate metrics of recent runs: duration, tokens, estimated cost."""
    from agentos.memory import default_memory

    rows = default_memory.recent_metrics(limit)
    if not rows:
        console.print("[dim]No runs recorded yet.[/dim]")
        return
    runs = len(rows)
    table = Table(title=f"Last {runs} runs")
    table.add_column("Metric")
    table.add_column("Total", justify="right")
    table.add_column("Avg / run", justify="right")
    for key, label in [("duration_s", "duration (s)"), ("llm_calls", "LLM calls"),
                       ("tool_calls", "tool calls"), ("tokens", "tokens"),
                       ("est_cost_usd", "est. cost ($)")]:
        total = sum(r.get(key, 0) for r in rows)
        table.add_row(label, f"{round(total, 4)}", f"{round(total / runs, 4)}")
    console.print(table)


@app.command()
def prune(days: int = typer.Option(30, help="Delete records older than this many days")):
    """Delete old events/messages/metrics so the database doesn't grow
    unbounded under daily use. Safe to run anytime (e.g. a weekly cron)."""
    from agentos.memory import default_memory

    result = default_memory.prune(older_than_days=days)
    table = Table(title=f"Pruned records older than {days} days")
    table.add_column("Table")
    table.add_column("Deleted", justify="right")
    for k, v in result.items():
        table.add_row(k, str(v))
    console.print(table)


@keys_app.command("create")
def keys_create(
    name: str = typer.Argument(..., help="Label for who/what this key is for"),
    no_execute: bool = typer.Option(
        False, "--no-execute",
        help="Restrict this key: it can call /run (research, drafts, "
             "previews) but /execute always refuses it - use for a caller "
             "who should never be able to actually send an email etc."),
):
    """Create a new API key. Once any key exists, the HTTP API requires
    'Authorization: Bearer <key>' on /run and /execute, and this key gets
    its own rate-limit budget separate from every other caller."""
    from agentos.memory import default_memory

    key_id, plaintext = default_memory.create_api_key(name, can_execute=not no_execute)
    scope_note = ("[yellow]restricted: cannot execute approved actions[/yellow]"
                 if no_execute else "full access")
    console.print(Panel(
        f"[bold]{plaintext}[/bold]\n\n"
        f"Scope: {scope_note}\n\n"
        "[yellow]This is shown only once - store it now.[/yellow] "
        "AgentOS keeps only a hash, so it cannot be shown again "
        "(create a new one if it's lost).",
        title=f"API key created (id: {key_id})", border_style="green",
    ))


@keys_app.command("list")
def keys_list():
    """List API keys (never shows the key value itself, only metadata)."""
    from agentos.memory import default_memory

    table = Table(title="API keys")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Created")
    table.add_column("Last used")
    table.add_column("Scope")
    table.add_column("Status")
    for k in default_memory.list_api_keys():
        created = datetime.fromtimestamp(k["created_at"]).strftime("%d %b %H:%M")
        last_used = (datetime.fromtimestamp(k["last_used_at"]).strftime("%d %b %H:%M")
                    if k["last_used_at"] else "never")
        scope = "full" if k["can_execute"] else "[yellow]restricted[/yellow]"
        status = "[red]revoked[/red]" if k["revoked_at"] else "[green]active[/green]"
        table.add_row(k["id"], k["name"], created, last_used, scope, status)
    console.print(table)


@keys_app.command("revoke")
def keys_revoke(key_id: str = typer.Argument(..., help="Key ID from 'keys list'")):
    """Revoke an API key immediately."""
    from agentos.memory import default_memory

    if default_memory.revoke_api_key(key_id):
        console.print(f"[green]Revoked key {key_id}.[/green]")
    else:
        console.print(f"[red]No active key with id {key_id}.[/red]")


@app.command()
def doctor():
    """Check the deployment configuration and report problems."""
    import os

    from dotenv import load_dotenv

    load_dotenv()
    table = Table(title="AgentOS doctor")
    table.add_column("Check")
    table.add_column("Status")

    def row(name, ok, detail=""):
        mark = "[green]✔[/green]" if ok else "[red]✘[/red]"
        table.add_row(name, f"{mark} {detail}".strip())

    row("OPENAI_API_KEY", bool(os.getenv("OPENAI_API_KEY")),
        "" if os.getenv("OPENAI_API_KEY") else "missing — set it in .env")
    row("Model", True, os.getenv("AGENTOS_MODEL", "gpt-4o-mini")
        + (f" via {os.getenv('OPENAI_BASE_URL')}" if os.getenv("OPENAI_BASE_URL") else ""))
    try:
        from agentos.memory import default_memory

        default_memory.recent_sessions(1)
        row("Database", True, default_memory.db_path)
    except Exception as e:
        row("Database", False, str(e))
    try:
        from agentos.tools.files import _safe_path

        probe = _safe_path(".doctor_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        row("Workspace", True, os.getenv("AGENTOS_WORKSPACE", "workspace"))
    except Exception as e:
        row("Workspace", False, str(e))
    row("Web search", True,
        "Tavily" if os.getenv("TAVILY_API_KEY") else "DuckDuckGo fallback")
    row("Email sending", True,
        "SMTP configured" if os.getenv("SMTP_HOST") else "draft-only mode (no SMTP)")
    try:
        from agentos.memory import default_memory

        if default_memory.any_api_keys_exist():
            row("API auth", True, "enabled — /run and /execute require a key")
        else:
            row("API auth", False,
                "open mode — anyone with the URL can call the API; run "
                "'cli.py keys create <name>' before a public deployment")
    except Exception as e:
        row("API auth", False, str(e))
    row("Monitoring", monitoring.is_enabled(),
        "Sentry enabled" if monitoring.is_enabled()
        else "not configured (optional) — set SENTRY_DSN to enable")
    from agentos import oauth

    row("Google sign-in", oauth.is_configured(),
        "configured" if oauth.is_configured()
        else "not configured (optional) — see README's OAuth section")
    if oauth.is_configured() and not os.getenv("GOOGLE_REDIRECT_URI"):
        row("Google sign-in", False,
            "GOOGLE_CLIENT_ID is set but GOOGLE_REDIRECT_URI is missing")
    row("Semantic recall", True,
        f"embedding model: {os.getenv('AGENTOS_EMBEDDING_MODEL', 'text-embedding-3-small')} "
        "(falls back to substring search if the provider doesn't support it)")
    console.print(table)


if __name__ == "__main__":
    app()
