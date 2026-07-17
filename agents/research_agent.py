from agents.base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    name = "research"
    system_prompt = """You are a research assistant.
Give a concise, well-organized summary with key bullet points about the topic.
If context from previous steps is provided, use it to focus your research."""
