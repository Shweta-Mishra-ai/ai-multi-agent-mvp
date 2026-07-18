"""Direct unit tests for the generic tool-loop Agent (agentos/agents/base.py)."""

from tests.conftest import fake_response, fake_tool_call

from agentos import config
from agentos.agents.base import Agent
from agentos.registry import AgentSpec
from agentos.tools import tool


def make_agent(tools=()):
    return Agent(AgentSpec(
        name="probe",
        description="test agent",
        system_prompt="You are a test agent.",
        tools=list(tools),
    ))


def test_answers_directly_without_tools(patch_llm):
    def fake_chat(messages, tools=None, response_format=None):
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a test agent."
        assert tools is None  # agent has no tools -> none sent to the LLM
        return fake_response(content="direct answer")

    patch_llm(fake_chat)
    assert make_agent().run("hello") == "direct answer"


def test_context_is_included_in_user_message(patch_llm):
    def fake_chat(messages, tools=None, response_format=None):
        user = messages[-1]["content"]
        assert "the task" in user and "PREVIOUS OUTPUT" in user
        return fake_response(content="ok")

    patch_llm(fake_chat)
    assert make_agent().run("the task", context="PREVIOUS OUTPUT") == "ok"


def test_tool_loop_executes_tool_and_feeds_result_back(patch_llm):
    state = {"calls": 0}

    def fake_chat(messages, tools=None, response_format=None):
        state["calls"] += 1
        if state["calls"] == 1:
            assert any(t["function"]["name"] == "calculate" for t in tools)
            return fake_response(tool_calls=[
                fake_tool_call("calculate", {"expression": "6 * 7"})])
        assert messages[-1]["role"] == "tool"
        return fake_response(content=f"the answer is {messages[-1]['content']}")

    patch_llm(fake_chat)
    assert make_agent(["calculate"]).run("what is 6*7?") == "the answer is 42"


def test_unknown_tool_is_reported_not_crashed(patch_llm):
    state = {"calls": 0}

    def fake_chat(messages, tools=None, response_format=None):
        state["calls"] += 1
        if state["calls"] == 1:
            return fake_response(tool_calls=[fake_tool_call("no_such_tool", {})])
        return fake_response(content=messages[-1]["content"])

    patch_llm(fake_chat)
    result = make_agent(["calculate"]).run("go")
    assert "Unknown tool: no_such_tool" in result


def test_malformed_tool_arguments_return_tool_error(patch_llm):
    state = {"calls": 0}

    def fake_chat(messages, tools=None, response_format=None):
        state["calls"] += 1
        if state["calls"] == 1:
            call = fake_tool_call("calculate", {})
            call.function.arguments = "{not valid json"
            return fake_response(tool_calls=[call])
        return fake_response(content=messages[-1]["content"])

    patch_llm(fake_chat)
    assert "Tool error" in make_agent(["calculate"]).run("go")


def test_loop_is_bounded_by_max_turns(patch_llm):
    state = {"calls": 0}

    def fake_chat(messages, tools=None, response_format=None):
        state["calls"] += 1
        return fake_response(tool_calls=[
            fake_tool_call("calculate", {"expression": "1+1"})])

    patch_llm(fake_chat)
    result = make_agent(["calculate"]).run("loop forever")
    assert "maximum number of tool turns" in result
    assert state["calls"] == config.MAX_TOOL_TURNS  # never exceeds the budget


def test_huge_tool_output_is_truncated(patch_llm):
    @tool("returns a huge string")
    def _huge_probe_tool():
        return "x" * (config.MAX_TOOL_OUTPUT_CHARS * 3)

    state = {"calls": 0, "tool_msg_len": None}

    def fake_chat(messages, tools=None, response_format=None):
        state["calls"] += 1
        if state["calls"] == 1:
            return fake_response(tool_calls=[fake_tool_call("_huge_probe_tool", {})])
        state["tool_msg_len"] = len(messages[-1]["content"])
        return fake_response(content="done")

    patch_llm(fake_chat)
    assert make_agent(["_huge_probe_tool"]).run("go") == "done"
    assert state["tool_msg_len"] == config.MAX_TOOL_OUTPUT_CHARS
