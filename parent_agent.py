from agents.task_agent import TaskAgent
from agents.research_agent import ResearchAgent
from agents.email_agent import EmailAgent
from planner import make_plan


class ParentAgent:
    """Orchestrator: plans the request with an LLM, then executes each step
    with the right agent, passing earlier outputs as context to later steps.

    `handle` is a generator that yields progress events so the UI can show
    the plan and each step's result as they happen:
      {"type": "plan", "steps": [...]}
      {"type": "step_start", "index": i, "agent": name, "instruction": ...}
      {"type": "step_result", "index": i, "agent": name, "output": ...}
    """

    def __init__(self):
        self.agents = {
            agent.name: agent
            for agent in (TaskAgent(), ResearchAgent(), EmailAgent())
        }

    def handle(self, user_input, energy_level):
        steps = make_plan(user_input, energy_level)
        yield {"type": "plan", "steps": steps}

        outputs = {}
        for i, step in enumerate(steps):
            agent = self.agents.get(step["agent"])
            if agent is None:
                outputs[i] = f"No agent named '{step['agent']}'."
                yield {
                    "type": "step_result",
                    "index": i,
                    "agent": step["agent"],
                    "output": outputs[i],
                }
                continue

            yield {
                "type": "step_start",
                "index": i,
                "agent": agent.name,
                "instruction": step["instruction"],
            }

            context = "\n\n".join(
                f"[Output of step {dep + 1} ({steps[dep]['agent']})]:\n{outputs[dep]}"
                for dep in step.get("depends_on", [])
                if dep in outputs
            )
            try:
                outputs[i] = agent.run(step["instruction"], context)
            except Exception as e:
                outputs[i] = f"Step failed: {e}"

            yield {
                "type": "step_result",
                "index": i,
                "agent": agent.name,
                "output": outputs[i],
            }
