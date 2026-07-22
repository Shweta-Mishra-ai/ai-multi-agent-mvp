"""Central configuration. Every limit is tunable via environment variables,
so operators can adjust behavior without touching code."""

import os


def _int(name, default, minimum=1):
    """Read a positive-int env var, clamped to a sane minimum so a
    misconfigured value (0, negative, non-numeric) can't crash things
    downstream (e.g. ThreadPoolExecutor(max_workers=0) raises ValueError)."""
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else minimum


# LLM resilience
LLM_TIMEOUT = _int("AGENTOS_LLM_TIMEOUT", 60)          # seconds per LLM call
LLM_RETRIES = _int("AGENTOS_LLM_RETRIES", 3, minimum=0)  # automatic retries (429/5xx)

# Run budgets (protect cost and latency)
MAX_STEPS = _int("AGENTOS_MAX_STEPS", 5)
MAX_TOOL_TURNS = _int("AGENTOS_MAX_TOOL_TURNS", 8)
RUN_TIMEOUT = _int("AGENTOS_RUN_TIMEOUT", 300)         # seconds per whole run
MAX_PARALLEL = _int("AGENTOS_MAX_PARALLEL", 3)         # concurrent agent steps

# Validation / size limits
MAX_INPUT_CHARS = _int("AGENTOS_MAX_INPUT_CHARS", 4000)
MAX_TOOL_OUTPUT_CHARS = _int("AGENTOS_MAX_TOOL_OUTPUT_CHARS", 8000)
MAX_CONTEXT_CHARS = _int("AGENTOS_MAX_CONTEXT_CHARS", 12000)
MAX_FILE_BYTES = _int("AGENTOS_MAX_FILE_BYTES", 200_000)

# Abuse protection
RATE_LIMIT_PER_MIN = _int("AGENTOS_RATE_LIMIT_PER_MIN", 10)

# Circuit breaker: fail fast during a sustained LLM provider outage instead
# of every request separately paying the full retry+timeout cost
CIRCUIT_FAILURE_THRESHOLD = _int("AGENTOS_CIRCUIT_FAILURE_THRESHOLD", 5)
CIRCUIT_RESET_SECONDS = _int("AGENTOS_CIRCUIT_RESET_SECONDS", 30)

# Semantic recall: not every OpenAI-compatible provider has an embeddings
# endpoint (e.g. Groq's chat-only API doesn't) - recall() falls back to
# substring search automatically when embeddings are unavailable.
EMBEDDING_MODEL = os.getenv("AGENTOS_EMBEDDING_MODEL", "text-embedding-3-small")

# Optional "Sign in with Google" (see agentos/oauth.py). Set explicitly
# rather than auto-derived from the request, since a reverse proxy (e.g.
# Render terminates TLS in front of the container) can make the request
# appear to arrive over http:// even though the public URL is https://.
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
