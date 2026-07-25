"""Ambient identity of the current caller, for multi-tenant isolation.

Set once at the start of Kernel.run() and read deep inside tool functions
(workspace files, long-term memory) without threading an explicit
parameter through every agent/tool call. Uses the same contextvars +
copy_context() pattern already used by telemetry and approval gates, so
it propagates correctly into the kernel's parallel-step worker threads.
"""

import contextvars

_current_caller = contextvars.ContextVar("agentos_caller", default=None)


def set_caller(api_key_id):
    _current_caller.set(api_key_id)


def current_caller():
    return _current_caller.get()


def scope():
    """A storage-safe scope identifier for the current caller: the API key
    id when authenticated, or a fixed "default" bucket for open-mode/local
    use (so a single-user deployment behaves exactly as before)."""
    caller = current_caller()
    return caller if caller else "default"
