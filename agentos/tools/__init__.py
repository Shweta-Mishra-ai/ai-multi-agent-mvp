"""Tool registry: the "syscalls" of AgentOS.

Register a tool with the @tool decorator; give an agent access by listing
the tool's name in its AgentSpec. Tools are plain python functions.
"""

TOOLS = {}


def tool(description, parameters=None):
    def decorator(fn):
        TOOLS[fn.__name__] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": description,
                    "parameters": parameters
                    or {"type": "object", "properties": {}, "required": []},
                },
            },
        }
        return fn

    return decorator


def resolve(names):
    """Return (schemas, {name: fn}) for the given tool names."""
    schemas, fns = [], {}
    for name in names:
        entry = TOOLS.get(name)
        if entry:
            schemas.append(entry["schema"])
            fns[name] = entry["fn"]
    return schemas, fns


# Importing the modules registers their tools.
from agentos.tools import system, files, web, mail, memtools  # noqa: E402,F401
