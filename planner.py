import json

from llm_client import chat

PLANNER_SYSTEM_PROMPT = """You are the planner of a multi-agent AI system.
Given a user request, produce a step-by-step plan using the available agents.

Available agents:
- "task": breaks a goal into small, clear, actionable steps
- "research": researches a topic and produces a concise summary
- "email": writes a polite, professional email

Rules:
- Use between 1 and 4 steps. Most requests need only 1 step.
- Only add multiple steps when the request genuinely requires it
  (e.g. "research X and email a summary" = research step, then email step).
- Each step's instruction must be self-contained and specific.
- Use "depends_on" (a list of earlier step indices, 0-based) when a step
  needs the output of previous steps.
- The user's energy level is given. For "Low" energy, prefer fewer and
  simpler steps, and keep instructions short and easy to act on.
"""

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
                            "agent": {
                                "type": "string",
                                "enum": ["task", "research", "email"],
                            },
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


def make_plan(user_input, energy_level):
    """Ask the LLM to turn the user request into a structured multi-step plan.

    Falls back to a single task-agent step if planning fails, so the app
    always produces something useful.
    """
    try:
        response = chat(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User energy level: {energy_level}\n"
                        f"User request: {user_input}"
                    ),
                },
            ],
            response_format=PLAN_RESPONSE_FORMAT,
        )
        steps = json.loads(response.choices[0].message.content)["steps"]
        if steps:
            return steps
    except Exception:
        pass

    return [{"agent": "task", "instruction": user_input, "depends_on": []}]
