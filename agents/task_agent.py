from agents.base_agent import BaseAgent


class TaskAgent(BaseAgent):
    name = "task"
    system_prompt = """You are a task planning AI.
Break the user's goal into small, clear, actionable steps.
Keep it simple and structured.
If context from previous steps is provided, build your plan on top of it."""
