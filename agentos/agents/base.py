import json

from agentos import tools as toolbox
from agentos.llm import chat


class Agent:
    """Generic tool-loop agent: calls the LLM, executes requested tools,
    feeds results back, and repeats until it produces a final answer.
    Behavior comes entirely from the AgentSpec (prompt + tool list)."""

    max_turns = 8

    def __init__(self, spec):
        self.spec = spec
        self.tool_schemas, self.tool_fns = toolbox.resolve(spec.tools)

    def run(self, task, context=""):
        user_content = task
        if context:
            user_content = f"{task}\n\nContext from previous steps:\n{context}"

        messages = [
            {"role": "system", "content": self.spec.system_prompt},
            {"role": "user", "content": user_content},
        ]

        for _ in range(self.max_turns):
            response = chat(messages, tools=self.tool_schemas or None)
            message = response.choices[0].message

            if not message.tool_calls:
                return message.content

            messages.append(message)
            for call in message.tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": self._execute_tool(call),
                })

        return "Agent stopped: reached the maximum number of tool turns."

    def _execute_tool(self, call):
        fn = self.tool_fns.get(call.function.name)
        if fn is None:
            return f"Unknown tool: {call.function.name}"
        try:
            args = json.loads(call.function.arguments or "{}")
            return str(fn(**args))
        except Exception as e:
            return f"Tool error: {e}"
