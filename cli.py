"""AgentOS command-line interface.

    python cli.py run "research AI agent frameworks and write a report"
    python cli.py chat                 # interactive session with memory
    python cli.py agents               # list registered agents and tools
    python cli.py history              # recent sessions
    python cli.py ui                   # launch the Streamlit frontend
"""

import subprocess
import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(add_completion=False, help="AgentOS — multi-agent orchestration")
console = Console()


def _render_events(events):
    final = None
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
            console.print(Panel(
                Markdown(str(event["output"])),
                title=f"step {event['index'] + 1} · {event['agent']}",
                border_style="green",
            ))
        elif kind == "verify":
            if event["satisfied"]:
                console.print("[green]✔ verifier: output satisfies the request[/green]")
            else:
                console.print(
                    f"[yellow]✎ verifier requested a revision:[/yellow] "
                    f"{event['feedback']}"
                )
        elif kind == "done":
            final = event["output"]
    return final


@app.command()
def run(
    request: str = typer.Argument(..., help="What you want AgentOS to do"),
    energy: str = typer.Option("Medium", help="Low / Medium / High"),
):
    """Run one request through the kernel and print the result."""
    from agentos.kernel import Kernel

    _render_events(Kernel().run(request, energy))


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

        events = kernel.run(user_input, energy, session_id=session_id)
        for event in events:
            if event["type"] == "plan":
                session_id = event["session_id"]
                agents = " → ".join(s["agent"] for s in event["steps"])
                console.print(f"[dim]plan: {agents}[/dim]")
            elif event["type"] == "step_start":
                console.print(f"[dim]  {event['agent']} working...[/dim]")
            elif event["type"] == "done":
                console.print(Panel(Markdown(str(event["output"])),
                                    border_style="green"))
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
    """Launch the Streamlit web frontend."""
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])


if __name__ == "__main__":
    app()
