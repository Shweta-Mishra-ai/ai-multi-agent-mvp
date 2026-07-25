"""Circuit breaker for LLM calls.

Without this, a provider outage means every single request still pays
the full cost of AGENTOS_LLM_RETRIES retries plus AGENTOS_LLM_TIMEOUT
seconds per attempt before failing - under real concurrent load (as
demonstrated in production load testing) that pile-up ties up every
worker thread for the full timeout duration on every request.

After enough consecutive failures, the circuit "opens" and calls fail
immediately with a clear message for a cooldown period, then allows one
trial call through ("half-open") to check if the provider has recovered.
"""

import threading
import time

from agentos import config


class CircuitOpenError(Exception):
    """Raised instead of attempting a call while the circuit is open."""


class CircuitBreaker:
    def __init__(self, failure_threshold, reset_after):
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = None

    def before_call(self):
        with self._lock:
            if self._opened_at is None:
                return
            if time.time() - self._opened_at < self.reset_after:
                remaining = round(self.reset_after - (time.time() - self._opened_at))
                raise CircuitOpenError(
                    f"LLM provider appears to be unavailable ("
                    f"{self._failures} consecutive failures) - "
                    f"retrying in ~{max(remaining, 1)}s")
            # Cooldown elapsed: half-open - let exactly one call through to
            # probe whether the provider has recovered.
            self._opened_at = None
            self._failures = 0

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self):
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold and self._opened_at is None:
                self._opened_at = time.time()

    def snapshot(self):
        with self._lock:
            return {
                "open": self._opened_at is not None,
                "consecutive_failures": self._failures,
            }


# Process-global: "is the LLM provider currently healthy" is a property of
# the upstream service, not of any individual request.
breaker = CircuitBreaker(
    failure_threshold=config.CIRCUIT_FAILURE_THRESHOLD,
    reset_after=config.CIRCUIT_RESET_SECONDS,
)
