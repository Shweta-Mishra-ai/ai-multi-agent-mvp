import json

from llm_client import chat


class BaseAgent:
    """Shared agent loop: call the LLM, execute any requested tools,
    feed results back, and repeat until the agent produces a final answer.

    Subclasses set `name`, `system_prompt`, and optionally register tools
    via `tools` (name -> python function) and `tool_schemas` (OpenAI
    function-calling schemas). Agents without tools behave like a single
    LLM call, but gain tool support without any further changes.
    """

    name = "base"
    system_prompt = "You are a helpful assistant."
    tools = {}
    tool_schemas = []
    max_turns = 5

    def run(self, task, context=""):
        user_content = task
        if context:
            user_content = (
                f"{task}\n\n"
                f"Context from previous steps:\n{context}"
            )

        messages = [
            {"role": "system", "content": self.system_prompt},
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
        fn = self.tools.get(call.function.name)
        if fn is None:
            return f"Unknown tool: {call.function.name}"
        try:
            args = json.loads(call.function.arguments or "{}")
            return str(fn(**args))
        except Exception as e:
            return f"Tool error: {e}"
