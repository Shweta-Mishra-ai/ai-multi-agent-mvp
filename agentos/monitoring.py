"""Optional error monitoring/alerting.

Set SENTRY_DSN to send unhandled and handled-but-notable exceptions to
Sentry (or any Sentry-compatible ingestion endpoint). Requires
`pip install sentry-sdk` - deliberately NOT a hard dependency in
requirements.txt, so a deployment that doesn't want monitoring stays
lean. Without SENTRY_DSN set (or without the package installed), every
function here is a safe no-op - AgentOS behaves exactly as if this
module didn't exist.
"""

import logging
import os

log = logging.getLogger("agentos.monitoring")

_initialized = False


def init():
    """Call once at process startup (api.py, cli.py). Idempotent."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk

        import agentos

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("AGENTOS_ENV", "production"),
            release=f"agentos@{agentos.__version__}",
            # Tracing/profiling cost money on most Sentry plans and aren't
            # needed for error alerting - default off, opt in explicitly.
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")),
        )
    except ImportError:
        log.warning(
            "SENTRY_DSN is set but the 'sentry-sdk' package isn't "
            "installed - run 'pip install sentry-sdk' to enable it. "
            "Continuing without error monitoring.")
    except Exception as e:
        log.warning("Sentry initialization failed, continuing without "
                   "it: %s", e)


def capture_exception(exc):
    """Report an exception that was already handled (logged, degraded
    gracefully) but is still worth surfacing to monitoring - e.g. a
    planner failure or a step that crashed. A no-op if monitoring isn't
    configured, so call sites never need to check is_enabled() first."""
    if not os.getenv("SENTRY_DSN"):
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        pass  # monitoring itself must never be the thing that breaks a run


def is_enabled():
    return bool(os.getenv("SENTRY_DSN"))
