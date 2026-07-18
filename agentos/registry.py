"""Agent registry: agents are declared as AgentSpecs and instantiated on demand.

Adding a new agent to AgentOS = one register() call (see agents/builtin.py).
The planner automatically learns about every registered agent.
"""

from dataclasses import dataclass, field


@dataclass
class AgentSpec:
    name: str
    description: str          # shown to the planner: when to use this agent
    system_prompt: str
    tools: list = field(default_factory=list)


_REGISTRY = {}


def register(spec):
    _REGISTRY[spec.name] = spec
    return spec


def get_spec(name):
    return _REGISTRY.get(name)


def all_specs():
    return list(_REGISTRY.values())


def get_agent(name):
    from agentos.agents.base import Agent

    spec = get_spec(name)
    return Agent(spec) if spec else None
