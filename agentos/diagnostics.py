"""Runtime self-check: what is actually working on THIS deployment, right now.

Different from `cli.py doctor`, which only reports whether environment
variables are present. This actually exercises each dependency - makes a
real LLM call, runs a real search, writes to the real database - because
"the variable is set" and "the thing works" are very different claims,
and the gap between them is exactly where a deployment silently produces
useless output instead of failing.

Never raises and never leaks secrets: every check returns ok/detail, and
keys are reported only as present/absent.
"""

import os
import time

from agentos.log import get_logger

log = get_logger("agentos.diagnostics")

# Written once per process start. If a check reads back a DIFFERENT boot
# id than the one this process wrote, storage survived a restart; if the
# row is missing entirely on a later boot, storage is ephemeral.
BOOT_ID = str(time.time())
_STORAGE_KEY = "__diagnostics_boot__"


def _check_llm():
    """A real (tiny) completion - the only way to tell a working provider
    from a wrong model name, a bad key, or a base_url pointing at a
    provider that doesn't serve this model."""
    from agentos import llm

    base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1 (default)"
    detail = f"model={llm.MODEL} via {base_url}"
    if not os.getenv("OPENAI_API_KEY"):
        return {"ok": False, "detail": f"OPENAI_API_KEY is not set ({detail})"}
    try:
        llm.chat([{"role": "user", "content": "Reply with the single word: ok"}])
        return {"ok": True, "detail": detail}
    except Exception as e:
        return {"ok": False, "detail": f"{detail} - call failed: {type(e).__name__}: {e}"}


def _check_search():
    """Runs a real query. This is the check that most often explains a
    'the answers are vague and generic' complaint: when no provider is
    reachable the research agent has no sources to work from."""
    from agentos.tools.web import SEARCH_FAILED_PREFIX, web_search

    configured = [name for name, env in (("Tavily", "TAVILY_API_KEY"),
                                        ("Brave", "BRAVE_API_KEY"))
                 if os.getenv(env)]
    try:
        result = web_search("what is the current year")
    except Exception as e:
        return {"ok": False, "detail": f"search raised {type(e).__name__}: {e}"}

    configured_note = ", ".join(configured) or (
        "none - falling back to keyless DuckDuckGo, which cloud hosts "
        "like Render usually block")
    if result.startswith(SEARCH_FAILED_PREFIX):
        return {
            "ok": False,
            "detail": (f"no provider returned results (configured: "
                      f"{configured_note}). Research answers will be refused "
                      f"rather than guessed - set TAVILY_API_KEY (free at "
                      f"tavily.com) or BRAVE_API_KEY to fix."),
        }
    return {"ok": True, "detail": f"working (configured: {configured_note})"}


def _check_storage():
    """Detects the free-tier trap: a container filesystem that resets on
    every restart/sleep, which silently deletes scheduled follow-ups,
    connected social accounts, saved memory and issued API keys."""
    from agentos.memory import default_memory

    try:
        previous = default_memory.recall(_STORAGE_KEY, scope="default").get(_STORAGE_KEY)
        default_memory.remember(_STORAGE_KEY, BOOT_ID, scope="default")
    except Exception as e:
        return {"ok": False, "detail": f"database unusable: {type(e).__name__}: {e}"}

    path = default_memory.db_path
    if previous is None:
        return {"ok": True, "detail": (
            f"writable at {path}, but nothing was stored before this boot - "
            f"if this still says the same after a restart, storage is "
            f"ephemeral and scheduled follow-ups / connected accounts will "
            f"not survive")}
    if previous == BOOT_ID:
        return {"ok": True, "detail": f"writable at {path} (same process)"}
    return {"ok": True, "detail": f"persistent at {path} - survived a restart"}


def _check_tools():
    from agentos.tools import TOOLS

    return {"ok": bool(TOOLS), "detail": f"{len(TOOLS)} tools registered"}


def _check_optional():
    """Optional integrations - reported as info, never as failures, since
    a deployment that doesn't use them is perfectly healthy."""
    return {
        "smtp": bool(os.getenv("SMTP_HOST")),
        "imap_reply_detection": bool(os.getenv("IMAP_HOST")),
        "email_followup_cron": bool(os.getenv("FOLLOWUP_CRON_SECRET")),
        "google_signin": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "instagram": bool(os.getenv("META_APP_ID")),
        "linkedin": bool(os.getenv("LINKEDIN_CLIENT_ID")),
    }


CHECKS = (
    ("llm", _check_llm),
    ("search", _check_search),
    ("storage", _check_storage),
    ("tools", _check_tools),
)


def run_diagnostics():
    """Runs every check. A check that blows up is reported as failed
    rather than taking the endpoint down with it - a diagnostics tool
    that itself 500s is worse than useless."""
    checks = {}
    for name, fn in CHECKS:
        try:
            checks[name] = fn()
        except Exception as e:
            log.warning("diagnostic %s raised: %s", name, e)
            checks[name] = {"ok": False, "detail": f"check crashed: {type(e).__name__}: {e}"}

    return {
        "healthy": all(c["ok"] for c in checks.values()),
        "checks": checks,
        "optional": _check_optional(),
    }
