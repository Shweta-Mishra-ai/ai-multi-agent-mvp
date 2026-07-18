import json

from agentos.llm import chat
from agentos.registry import all_specs

PLAN_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string"},
                            "instruction": {"type": "string"},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        },
                        "required": ["agent", "instruction", "depends_on"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["steps"],
            "additionalProperties": False,
        },
    },
}


def _system_prompt():
    agent_lines = "\n".join(
        f'- "{spec.name}": {spec.description}' for spec in all_specs()
    )
    return f"""You are the planner (kernel scheduler) of AgentOS, a multi-agent system.
Given a user request, produce a step-by-step plan using the available agents.

Available agents:
{agent_lines}

Rules:
- Use between 1 and 5 steps. Most requests need only 1 step.
- Only add multiple steps when the request genuinely requires it
  (e.g. "research X and email a summary" = research step, then email step).
- Each step's instruction must be self-contained and specific.
- Use "depends_on" (a list of earlier step indices, 0-based) when a step
  needs the output of previous steps.
- Only use agent names from the list above.
- The user's energy level is given. For "Low" energy, prefer fewer and
  simpler steps, and keep instructions short and easy to act on.
- If conversation history is given, treat the request as a follow-up and
  plan accordingly."""


def make_plan(user_input, energy_level="Medium", history=None):
    """Turn the user request into a structured multi-step plan.
    Falls back to a single task-agent step if planning fails."""
    user_content = ""
    if history:
        transcript = "\n".join(
            f"{m['role']}: {m['content'][:500]}" for m in history
        )
        user_content += f"Conversation history:\n{transcript}\n\n"
    user_content += (
        f"User energy level: {energy_level}\n"
        f"User request: {user_input}"
    )

    valid_agents = {spec.name for spec in all_specs()}
    try:
        response = chat(
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_content},
            ],
            response_format=PLAN_RESPONSE_FORMAT,
        )
        steps = json.loads(response.choices[0].message.content)["steps"]
        steps = [s for s in steps if s["agent"] in valid_agents]
        if steps:
            return steps[:5]
    except Exception:
        pass

    return [{"agent": "task", "instruction": user_input, "depends_on": []}]
