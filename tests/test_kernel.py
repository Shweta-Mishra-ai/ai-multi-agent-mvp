import json
import time

from tests.conftest import fake_response, fake_tool_call, make_plan_json


def _satisfied_verdict(messages=None, **_):
    return fake_response(content=json.dumps({"satisfied": True, "feedback": ""}))


def test_chain_passes_context_between_steps(patch_llm):
    plan = make_plan_json([
        {"agent": "research", "instruction": "Research CRMs", "depends_on": []},
        {"agent": "email", "instruction": "Draft email", "depends_on": [0]},
    ])

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            name = response_format["json_schema"]["name"]
            if name == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        user = messages[-1]["content"]
        if "Context from previous steps" in user:
            return fake_response(content="EMAIL built on: " + user[-60:])
        return fake_response(content="RESEARCH OUTPUT")

    patch_llm(fake_chat)
    from agentos.kernel import Kernel

    events = list(Kernel().run("research CRMs and email my manager"))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "plan" and kinds[-2:] == ["done", "metrics"]
    results = {e["index"]: e for e in events if e["type"] == "step_result"}
    assert results[0]["output"] == "RESEARCH OUTPUT"
    assert "RESEARCH OUTPUT" in results[1]["output"]
    assert all(e["status"] == "ok" for e in results.values())


def test_parallel_independent_steps(patch_llm):
    plan = make_plan_json([
        {"agent": "research", "instruction": "A", "depends_on": []},
        {"agent": "writer", "instruction": "B", "depends_on": []},
    ])
    running = {"now": 0, "max": 0}

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        time.sleep(0.3)
        running["now"] -= 1
        return fake_response(content="OUT")

    patch_llm(fake_chat)
    from agentos.kernel import Kernel

    events = list(Kernel().run("do A and B"))
    results = [e for e in events if e["type"] == "step_result"]
    assert len(results) == 2 and all(e["status"] == "ok" for e in results)
    assert running["max"] == 2  # both agent steps overlapped


def test_failed_dependency_skips_dependent_step(patch_llm):
    plan = make_plan_json([
        {"agent": "research", "instruction": "A", "depends_on": []},
        {"agent": "email", "instruction": "B", "depends_on": [0]},
    ])

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        raise RuntimeError("provider exploded")

    patch_llm(fake_chat)
    from agentos.kernel import Kernel

    events = list(Kernel().run("do A then B"))
    results = {e["index"]: e for e in events if e["type"] == "step_result"}
    assert results[0]["status"] == "failed"
    assert results[1]["status"] == "skipped"
    done = [e for e in events if e["type"] == "done"][0]
    assert "could not be fully completed" in done["output"]


def test_revision_round_on_unsatisfied_verdict(patch_llm):
    plan = make_plan_json(
        [{"agent": "writer", "instruction": "Write intro", "depends_on": []}])
    state = {"verdicts": 0}

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            state["verdicts"] += 1
            return fake_response(content=json.dumps(
                {"satisfied": False, "feedback": "too short"}))
        user = messages[-1]["content"]
        if "too short" in user:
            return fake_response(content="REVISED LONGER OUTPUT")
        return fake_response(content="short")

    patch_llm(fake_chat)
    from agentos.kernel import Kernel

    events = list(Kernel().run("write an intro"))
    done = [e for e in events if e["type"] == "done"][0]
    assert done["output"] == "REVISED LONGER OUTPUT"


def test_input_validation_rejects_empty_and_huge(patch_llm):
    patch_llm(lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM call")))
    from agentos.kernel import Kernel

    events = list(Kernel().run("   "))
    assert events == [events[0]] and events[0]["type"] == "error"

    events = list(Kernel().run("x" * 10_000))
    assert events[0]["type"] == "error" and "too long" in events[0]["message"]


def test_metrics_emitted_and_persisted(patch_llm):
    plan = make_plan_json(
        [{"agent": "task", "instruction": "plan it", "depends_on": []}])

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        return fake_response(content="OK")

    patch_llm(fake_chat)
    from agentos.kernel import Kernel
    from agentos.memory import default_memory

    events = list(Kernel().run("plan my day"))
    metrics = [e for e in events if e["type"] == "metrics"][0]
    assert metrics["llm_calls"] >= 2 and metrics["tokens"] > 0
    assert default_memory.recent_metrics(1)
