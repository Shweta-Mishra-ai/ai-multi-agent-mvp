import json

from tests.conftest import fake_response, fake_tool_call, make_plan_json

from agentos.registry import AgentSpec, register
from agentos.tools import tool

executed = {"count": 0}


@tool("test-only irreversible action", requires_approval=True)
def _danger_probe():
    executed["count"] += 1
    return "IRREVERSIBLE ACTION DONE"


register(AgentSpec(
    name="dangertest",
    description="test-only agent with an irreversible action",
    system_prompt="You are a test agent.",
    tools=["_danger_probe"],
))


def _fake_chat_factory():
    plan = make_plan_json(
        [{"agent": "dangertest", "instruction": "do the thing", "depends_on": []}])
    state = {"agent_calls": 0}

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        state["agent_calls"] += 1
        if state["agent_calls"] % 2 == 1:
            return fake_response(tool_calls=[fake_tool_call("_danger_probe", {})])
        return fake_response(content=f"result: {messages[-1]['content']}")

    return fake_chat


def test_gated_action_is_blocked_without_approval(patch_llm):
    patch_llm(_fake_chat_factory())
    from agentos.kernel import Kernel

    executed["count"] = 0
    events = list(Kernel().run("do the dangerous thing"))
    kinds = [e["type"] for e in events]

    assert executed["count"] == 0                       # never executed
    assert "approval_required" in kinds
    approval = [e for e in events if e["type"] == "approval_required"][0]
    assert approval["actions"] == [{"tool": "_danger_probe", "args": {}}]
    done = [e for e in events if e["type"] == "done"][0]
    assert "ACTION NOT EXECUTED" in done["output"]


def test_gated_action_executes_with_approval(patch_llm):
    patch_llm(_fake_chat_factory())
    from agentos.kernel import Kernel

    executed["count"] = 0
    events = list(Kernel().run("do the dangerous thing", approve=True))
    kinds = [e["type"] for e in events]

    assert executed["count"] == 1                       # executed exactly once
    assert "approval_required" not in kinds
    done = [e for e in events if e["type"] == "done"][0]
    assert "IRREVERSIBLE ACTION DONE" in done["output"]


def test_send_email_is_approval_gated():
    from agentos.tools import TOOLS

    assert TOOLS["send_email"]["requires_approval"] is True
