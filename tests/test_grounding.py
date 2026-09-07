"""Anti-fabrication contract, pinned at both places it leaked.

Background: hardening web_search to fail honestly was not enough. A plan
like "research X -> write it up" still produced an invented document,
because two things downstream of the research step did not know about
the failure:

  1. the writer agent, whose prompt only said "ground your writing in the
     context" and so happily wrote from the model's own memory, and
  2. the verifier, whose prompt said "missing content is not fine" - so
     it demanded a "complete" answer, triggering a revision round that
     forced the agents to invent even more.

These tests assert the prompt contract at both points. They cannot prove
a live model obeys it - only that the instruction is actually present and
reaches every agent, which is the part regressions silently break.
"""

from unittest.mock import patch

from agentos.agents.base import GROUNDING_RULE
from agentos.registry import all_specs, get_agent
from tests.conftest import fake_response


def _flat(text):
    """Collapse wrapping so assertions test the wording, not where the
    source happens to break lines."""
    return " ".join(text.split()).lower()


def _system_prompt_seen_by(agent_name, patch_llm):
    """Run an agent with a stubbed LLM and capture the system prompt it
    actually sent - the real assembled one, not the raw AgentSpec."""
    seen = {}

    def fake_chat(messages, tools=None, response_format=None):
        seen["system"] = messages[0]["content"]
        return fake_response(content="done")

    patch_llm(fake_chat)
    get_agent(agent_name).run("any task")
    return seen["system"]


def test_every_registered_agent_receives_the_grounding_rule(patch_llm):
    """Applied centrally in Agent.run, so a newly added agent cannot
    forget it - which is exactly how the writer agent slipped through."""
    for spec in all_specs():
        prompt = _system_prompt_seen_by(spec.name, patch_llm)
        assert GROUNDING_RULE.strip() in prompt, f"{spec.name} missing grounding rule"


def test_writer_specifically_is_covered(patch_llm):
    """The agent that actually produced the invented document."""
    prompt = _flat(_system_prompt_seen_by("writer", patch_llm))
    assert "search_failed" in prompt
    assert "do not fill the gap from your own knowledge" in prompt


def test_grounding_rule_forbids_the_specific_failure_modes():
    rule = _flat(GROUNDING_RULE)
    assert "never invent facts, sources, urls, product names" in rule
    # It must also say an honest short answer is a correct outcome, or the
    # model treats refusing as failing the task and pads it out anyway.
    assert "correct and complete" in rule


def test_grounding_rule_survives_the_agents_own_instructions(patch_llm):
    """It is appended after the spec prompt and says it overrides, so an
    agent told to 'always produce a full report' still can't fabricate."""
    prompt = _system_prompt_seen_by("writer", patch_llm)
    assert prompt.index(GROUNDING_RULE.strip()) > prompt.index("professional writer")
    assert "overrides any instruction above" in prompt


def test_verifier_treats_an_honest_failure_as_satisfying(patch_llm):
    """The revision loop is what turned a short honest answer into 2000
    words of invented comparison - the verifier must not demand that."""
    from agentos.kernel import Kernel

    seen = {}

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            seen["system"] = messages[0]["content"]
        return fake_response(content='{"satisfied": true, "feedback": ""}')

    patch_llm(fake_chat)
    Kernel()._verify("compare X and Y", [{"agent": "research", "instruction": "x"}], {0: "SEARCH_FAILED"})

    system = seen["system"].lower()
    assert "search_failed" in system
    assert "is satisfying" in system
    assert "never ask for missing information" in system


def test_verifier_still_rejects_genuinely_wrong_output(patch_llm):
    """The honest-failure carve-out must not turn the verifier into a
    rubber stamp for everything else."""
    from agentos.kernel import Kernel

    seen = {}

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            seen["system"] = messages[0]["content"]
        return fake_response(content='{"satisfied": false, "feedback": "wrong"}')

    patch_llm(fake_chat)
    verdict = Kernel()._verify("do X", [{"agent": "task", "instruction": "x"}], {0: "nonsense"})

    assert "missing or wrong content is not" in seen["system"]
    assert verdict["satisfied"] is False


def test_verify_failure_still_degrades_to_satisfied():
    """Unchanged safety net: a verifier outage must not block a run."""
    from agentos.kernel import Kernel

    with patch("agentos.kernel.chat", side_effect=Exception("provider down")):
        verdict = Kernel()._verify("do X", [{"agent": "task", "instruction": "x"}], {0: "out"})
    assert verdict["satisfied"] is True
