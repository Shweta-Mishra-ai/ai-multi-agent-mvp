"""Per-run metrics: LLM calls, tokens, tool calls, duration, estimated cost.
Thread-safe (steps run in parallel) and propagated via contextvars."""

import contextvars
import threading
import time

# Default price estimate (gpt-4o-mini, USD per token). Override per deployment.
PRICE_IN = 0.15 / 1_000_000
PRICE_OUT = 0.60 / 1_000_000


class RunMetrics:
    def __init__(self):
        self.started = time.time()
        self.llm_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.tool_calls = 0
        self._lock = threading.Lock()

    def record_llm(self, usage):
        with self._lock:
            self.llm_calls += 1
            if usage is not None:
                self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

    def record_tool(self):
        with self._lock:
            self.tool_calls += 1

    def snapshot(self):
        cost = self.prompt_tokens * PRICE_IN + self.completion_tokens * PRICE_OUT
        return {
            "duration_s": round(time.time() - self.started, 1),
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "tokens": self.prompt_tokens + self.completion_tokens,
            "est_cost_usd": round(cost, 5),
        }


_current = contextvars.ContextVar("agentos_metrics", default=None)


def start_run():
    metrics = RunMetrics()
    _current.set(metrics)
    return metrics


def record_llm(response):
    metrics = _current.get()
    if metrics:
        metrics.record_llm(getattr(response, "usage", None))


def record_tool():
    metrics = _current.get()
    if metrics:
        metrics.record_tool()
