from agents.base_agent import BaseAgent


class EmailAgent(BaseAgent):
    name = "email"
    system_prompt = """You are a professional email writing assistant.
Write a polite, clear, and professional email for the user's request.
If context from previous steps is provided (e.g. research findings or a plan),
incorporate it into the email body."""
