import json

from agentos.llm import chat
from agentos.memory import default_memory
from agentos.planner import make_plan
from agentos.registry import get_agent
import agentos.agents  # noqa: F401  (registers built-in agents)

VERIFY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "satisfied": {"type": "boolean"},
                "feedback": {
                    "type": "string",
                    "description": "If not satisfied: what is missing or wrong, "
                                   "as an instruction for fixing the final output.",
                },
            },
            "required": ["satisfied", "feedback"],
            "additionalProperties": False,
        },
    },
}


class Kernel:
    """The AgentOS kernel: plan -> schedule agents -> verify -> deliver.

    `run` is a generator that yields progress events, so every frontend
    (CLI, Streamlit, API) renders the same stream:
      {"type": "plan", "steps": [...], "session_id": ...}
      {"type": "step_start", "index", "agent", "instruction"}
      {"type": "step_result", "index", "agent", "output"}
      {"type": "verify", "satisfied": bool, "feedback": str}
      {"type": "done", "output": str}
    """

    def __init__(self, memory=None):
        self.memory = memory or default_memory

    def run(self, user_input, energy_level="Medium", session_id=None):
        if session_id is None:
            session_id = self.memory.create_session(user_input)
        history = self.memory.get_messages(session_id, limit=8)

        def emit(event):
            self.memory.log_event(session_id, event)
            return event

        steps = make_plan(user_input, energy_level, history=history)
        yield emit({"type": "plan", "steps": steps, "session_id": session_id})

        outputs = {}
        for i, step in enumerate(steps):
            for event in self._run_step(i, step, steps, outputs):
                yield emit(event)

        final = outputs.get(len(steps) - 1, "")
        verdict = self._verify(user_input, steps, outputs)
        yield emit({"type": "verify", **verdict})

        if not verdict["satisfied"] and steps:
            # One revision round: the final step's agent fixes its output.
            last = len(steps) - 1
            revision = {
                "agent": steps[last]["agent"],
                "instruction": (
                    f"{steps[last]['instruction']}\n\n"
                    f"Your previous attempt was reviewed. Fix this feedback and "
                    f"produce the corrected final result:\n{verdict['feedback']}\n\n"
                    f"Previous attempt:\n{final}"
                ),
                "depends_on": steps[last]["depends_on"],
            }
            for event in self._run_step(last, revision, steps, outputs):
                yield emit(event)
            final = outputs.get(last, final)

        self.memory.add_message(session_id, "user", user_input)
        self.memory.add_message(session_id, "assistant", str(final))
        yield emit({"type": "done", "output": final, "session_id": session_id})

    def _run_step(self, i, step, steps, outputs):
        agent = get_agent(step["agent"])
        if agent is None:
            outputs[i] = f"No agent named '{step['agent']}'."
            yield {"type": "step_result", "index": i,
                   "agent": step["agent"], "output": outputs[i]}
            return

        yield {"type": "step_start", "index": i,
               "agent": agent.spec.name, "instruction": step["instruction"]}

        context = "\n\n".join(
            f"[Output of step {dep + 1} ({steps[dep]['agent']})]:\n{outputs[dep]}"
            for dep in step.get("depends_on", [])
            if dep in outputs
        )
        try:
            outputs[i] = agent.run(step["instruction"], context)
        except Exception as e:
            outputs[i] = f"Step failed: {e}"

        yield {"type": "step_result", "index": i,
               "agent": agent.spec.name, "output": outputs[i]}

    def _verify(self, user_input, steps, outputs):
        """Ask the LLM whether the outputs actually satisfy the request."""
        try:
            results = "\n\n".join(
                f"Step {i + 1} ({step['agent']}): {str(outputs.get(i, ''))[:1500]}"
                for i, step in enumerate(steps)
            )
            response = chat(
                messages=[
                    {"role": "system", "content":
                        "You are the quality verifier of a multi-agent system. "
                        "Judge whether the step outputs, taken together, satisfy "
                        "the user's request. Be pragmatic: minor style issues are "
                        "fine, missing or wrong content is not."},
                    {"role": "user", "content":
                        f"User request: {user_input}\n\nStep outputs:\n{results}"},
                ],
                response_format=VERIFY_RESPONSE_FORMAT,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"satisfied": True, "feedback": f"(verifier unavailable: {e})"}
