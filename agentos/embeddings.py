"""Optional semantic embeddings for long-term memory (memory.py's
recall()). Not every OpenAI-compatible provider supports an embeddings
endpoint - notably Groq's free, chat-only API does not. Every function
here degrades to returning None on any failure, so recall() falls back
to its existing substring search automatically and transparently;
nothing breaks for a deployment using a provider without embeddings
support, it just doesn't get the semantic-ranking upgrade.
"""

import logging
import math

from agentos import config
from agentos.llm import client

log = logging.getLogger("agentos.embeddings")

# Whether embeddings are known to be unavailable for the configured
# provider (Groq et al don't have this endpoint at all). Set on the first
# failure and never reset for the rest of the process - unlike a general
# LLM outage (handled by the circuit breaker, which does reset, since
# that's usually transient), "this provider has no embeddings endpoint"
# is a static fact about the deployment's config that won't change
# without a restart. Without this, every remember() call would retry and
# wait out the full timeout again, adding several real seconds of
# latency to a tool call that should be near-instant.
_unavailable = False


def embed(text):
    """Return a list[float] embedding for text, or None if embeddings
    aren't available (provider doesn't support the endpoint, network
    error, etc.) - logged at debug level since this is an expected,
    common, non-error condition for several supported providers."""
    global _unavailable
    if _unavailable or not text or not text.strip():
        return None
    try:
        # Short timeout, no retries: this is a "nice to have" enhancement,
        # not core functionality - it must never make a tool call feel
        # slow while we find out whether the provider supports it.
        response = client.with_options(timeout=8, max_retries=0).embeddings.create(
            model=config.EMBEDDING_MODEL, input=text[:8000])
        return response.data[0].embedding
    except Exception as e:
        log.debug("embeddings unavailable, recall will use substring "
                 "search instead (won't retry again this process): %s", e)
        _unavailable = True
        return None


def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
