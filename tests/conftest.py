import json
import os
import sys
import tempfile
import types

_tmp = tempfile.mkdtemp(prefix="agentos-test-")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ["AGENTOS_DB"] = os.path.join(_tmp, "test.db")
os.environ["AGENTOS_WORKSPACE"] = os.path.join(_tmp, "workspace")
os.environ["AGENTOS_RATE_LIMIT_PER_MIN"] = "1000"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


def fake_response(content=None, tool_calls=None):
    message = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=message)],
        usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def fake_tool_call(name, arguments, call_id="c1"):
    return types.SimpleNamespace(
        id=call_id,
        function=types.SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def make_plan_json(steps):
    return json.dumps({"steps": steps})


@pytest.fixture(autouse=True)
def _reset_caller_identity():
    """Guarantee agentos.identity's ambient caller contextvar never leaks
    between tests, even if a test fails partway through before reaching
    its own cleanup (a manual identity.set_caller(None) at the end of a
    test body would not run if an assertion above it raises)."""
    from agentos import identity

    yield
    identity.set_caller(None)


@pytest.fixture
def patch_llm(monkeypatch):
    """Patch the LLM everywhere it's imported; pass a callable chat stub."""

    def _apply(fake_chat):
        import agentos.agents.base as base_mod
        import agentos.kernel as kernel_mod
        import agentos.llm as llm_mod
        import agentos.planner as planner_mod
        from agentos import telemetry

        def wrapped(*args, **kwargs):
            # mirror the real chat(): record telemetry for every LLM call
            response = fake_chat(*args, **kwargs)
            telemetry.record_llm(response)
            return response

        for mod in (llm_mod, planner_mod, kernel_mod, base_mod):
            monkeypatch.setattr(mod, "chat", wrapped)

    return _apply
