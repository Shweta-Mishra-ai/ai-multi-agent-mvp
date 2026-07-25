import json

import pytest

from tests.conftest import fake_response, fake_tool_call
from agentos.security import is_safe_url, validate_request
from agentos.tools import TOOLS


def test_calculator_is_safe():
    assert TOOLS["calculate"]["fn"](expression="12 * (3 + 4)") == 84
    with pytest.raises(ValueError):
        TOOLS["calculate"]["fn"](expression="__import__('os').system('id')")


def test_workspace_blocks_traversal_and_size():
    TOOLS["write_file"]["fn"](name="a.md", content="hello")
    assert TOOLS["read_file"]["fn"](name="a.md") == "hello"
    with pytest.raises(ValueError):
        TOOLS["read_file"]["fn"](name="../../etc/passwd")
    refused = TOOLS["write_file"]["fn"](name="big.txt", content="x" * 500_000)
    assert "Refused" in refused


def test_ssrf_guard_blocks_internal_addresses():
    assert not is_safe_url("http://127.0.0.1/admin")
    assert not is_safe_url("http://10.0.0.5/")
    assert not is_safe_url("http://192.168.1.1/")
    assert not is_safe_url("http://169.254.169.254/latest/meta-data")
    assert not is_safe_url("ftp://example.com/x")
    assert not is_safe_url("not a url")


def test_fetch_url_refuses_unsafe_targets():
    out = TOOLS["fetch_url"]["fn"](url="http://127.0.0.1:8080/secrets")
    assert "Blocked" in out


def test_validate_request():
    assert validate_request("") is not None
    assert validate_request(None) is not None
    assert validate_request("x" * 5000) is not None
    assert validate_request("normal request") is None


def test_email_draft_mode_without_smtp(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    out = TOOLS["send_email"]["fn"](to="a@b.co", subject="hi", body="test")
    assert "NOT sent" in out


def test_agent_validates_tool_arguments(patch_llm):
    state = {"calls": 0}

    def fake_chat(messages, tools=None, response_format=None):
        state["calls"] += 1
        if state["calls"] == 1:
            # missing required "expression" + an unknown argument
            return fake_response(tool_calls=[
                fake_tool_call("calculate", {"bogus": 1})])
        return fake_response(content=messages[-1]["content"])

    patch_llm(fake_chat)
    from agentos.registry import get_agent
    import agentos.agents  # noqa: F401

    result = get_agent("task").run("compute")
    assert "missing required argument" in result


def test_agent_recovers_from_hallucinated_tool_name(patch_llm):
    """Regression test for a real failure seen with Groq's
    openai/gpt-oss-120b: the model calls a plausible-but-wrong tool name
    (e.g. 'web_fetch' instead of the registered 'fetch_url') despite the
    exact name being in the tools schema, and the provider rejects the
    whole request server-side (400 tool_use_failed) before any tool_calls
    message is ever returned. Since the attempted call is echoed back in
    `failed_generation`, and its arguments unambiguously match exactly one
    registered tool ('calculate' takes 'expression'; no other task-agent
    tool does), the agent should run that tool instead of failing the step."""
    import httpx
    from openai import BadRequestError

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(400, request=request)
    hallucination = BadRequestError(
        "Tool call validation failed",
        response=response,
        body={
            "code": "tool_use_failed",
            "failed_generation": json.dumps(
                {"name": "compute_math", "arguments": {"expression": "2+2"}}),
        },
    )

    state = {"calls": 0}

    def fake_chat(messages, tools=None, response_format=None):
        state["calls"] += 1
        if state["calls"] == 1:
            raise hallucination
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        assert tool_messages and tool_messages[-1]["content"] == "4"
        return fake_response(content="done")

    patch_llm(fake_chat)
    from agentos.registry import get_agent
    import agentos.agents  # noqa: F401

    assert get_agent("task").run("what is 2+2") == "done"
