"""Central configuration. Every limit is tunable via environment variables,
so operators can adjust behavior without touching code."""

import os


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# LLM resilience
LLM_TIMEOUT = _int("AGENTOS_LLM_TIMEOUT", 60)          # seconds per LLM call
LLM_RETRIES = _int("AGENTOS_LLM_RETRIES", 3)           # automatic retries (429/5xx)

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
