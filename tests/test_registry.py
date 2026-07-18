import agentos.agents  # noqa: F401
from agentos.registry import all_specs, get_agent
from agentos.tools import TOOLS


def test_every_registered_agent_is_instantiable():
    specs = all_specs()
    assert {s.name for s in specs} >= {
        "task", "research", "email", "code", "writer", "analyst", "translator",
    }
    for spec in specs:
        agent = get_agent(spec.name)
        assert agent is not None
        # every declared tool must exist in the tool registry
        for tool_name in spec.tools:
            assert tool_name in TOOLS, (
                f"agent '{spec.name}' declares unknown tool '{tool_name}'")
        # resolved schemas must match the declared tools
        resolved = {s["function"]["name"] for s in agent.tool_schemas}
        assert resolved == set(spec.tools)


def test_unknown_agent_returns_none():
    assert get_agent("does-not-exist") is None
