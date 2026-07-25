import json
from types import SimpleNamespace

from openai import BadRequestError

from agentos import config, telemetry
from agentos import tools as toolbox
from agentos.llm import chat


class Agent:
    """Generic tool-loop agent: calls the LLM, executes requested tools,
    feeds results back, and repeats until it produces a final answer.
    Behavior comes entirely from the AgentSpec (prompt + tool list).

    Hardening: tool arguments are validated against the tool's schema
    (unknown arguments dropped, missing required arguments rejected),
    tool outputs are size-capped, and the loop is turn-bounded."""

    def __init__(self, spec):
        self.spec = spec
        self.max_turns = config.MAX_TOOL_TURNS
        self.tool_schemas, self.tool_fns, self.approval_tools = \
            toolbox.resolve(spec.tools)
        self._schemas_by_name = {
            s["function"]["name"]: s["function"] for s in self.tool_schemas
        }

    def run(self, task, context=""):
        user_content = task
        if context:
            user_content = f"{task}\n\nContext from previous steps:\n{context}"

        messages = [
            {"role": "system", "content": self.spec.system_prompt},
            {"role": "user", "content": user_content},
        ]

        for _ in range(self.max_turns):
            try:
                response = chat(messages, tools=self.tool_schemas or None)
            except BadRequestError as e:
                recovered = self._recover_hallucinated_tool_call(e)
                if recovered is None:
                    raise
                messages.append(recovered["assistant_message"])
                messages.append(recovered["tool_message"])
                continue
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
        telemetry.record_tool()
        try:
            args = json.loads(call.function.arguments or "{}")
            if not isinstance(args, dict):
                return "Tool error: arguments must be an object"
            args = self._validate_args(call.function.name, args)
            if (call.function.name in self.approval_tools
                    and not telemetry.approvals_granted()):
                telemetry.record_pending(
                    {"tool": call.function.name, "args": args})
                return (
                    "ACTION NOT EXECUTED: this action requires the user's "
                    "approval first. Show the user a full preview of exactly "
                    "what would be done, and tell them to approve and run "
                    "again to execute it."
                )
            return str(fn(**args))[:config.MAX_TOOL_OUTPUT_CHARS]
        except Exception as e:
            return f"Tool error: {e}"

    def _recover_hallucinated_tool_call(self, exc):
        """Some models (observed with Groq's openai/gpt-oss-120b) occasionally
        invent a plausible-but-wrong tool name (e.g. 'web_fetch' instead of
        the registered 'fetch_url') despite the exact name being given in
        the tools schema. The provider then rejects the whole request
        server-side (400 tool_use_failed) before we ever see a tool_calls
        message to correct - but it echoes the attempted call back in
        `failed_generation`, which is enough to recover: if exactly one
        registered tool's required arguments match what was attempted,
        run that tool instead of failing the whole step."""
        body = getattr(exc, "body", None)
        if not isinstance(body, dict) or body.get("code") != "tool_use_failed":
            return None
        try:
            attempted = json.loads(body.get("failed_generation") or "")
            arguments = attempted["arguments"]
            if not isinstance(arguments, dict):
                return None
        except (TypeError, ValueError, KeyError):
            return None

        matches = [
            name for name, schema in self._schemas_by_name.items()
            if set(schema.get("parameters", {}).get("required", [])) == set(arguments)
        ]
        if len(matches) != 1:
            return None
        resolved_name = matches[0]

        call_id = f"recovered_{resolved_name}"
        arguments_json = json.dumps(arguments)
        call = SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(name=resolved_name, arguments=arguments_json),
        )
        return {
            "assistant_message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": resolved_name, "arguments": arguments_json},
                }],
            },
            "tool_message": {
                "role": "tool",
                "tool_call_id": call_id,
                "content": self._execute_tool(call),
            },
        }

    def _validate_args(self, tool_name, args):
        params = self._schemas_by_name.get(tool_name, {}).get("parameters", {})
        properties = params.get("properties", {})
        args = {k: v for k, v in args.items() if k in properties}
        missing = [k for k in params.get("required", []) if k not in args]
        if missing:
            raise ValueError(f"missing required argument(s): {', '.join(missing)}")
        return args
