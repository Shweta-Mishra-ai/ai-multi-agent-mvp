"""Tool registry: the "syscalls" of AgentOS.

Register a tool with the @tool decorator; give an agent access by listing
the tool's name in its AgentSpec. Tools are plain python functions.
"""

TOOLS = {}


def tool(description, parameters=None, requires_approval=False):
    def decorator(fn):
        TOOLS[fn.__name__] = {
            "fn": fn,
            "requires_approval": requires_approval,
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
    """Return (schemas, {name: fn}, {names needing approval}) for the tools."""
    schemas, fns, needs_approval = [], {}, set()
    for name in names:
        entry = TOOLS.get(name)
        if entry:
            schemas.append(entry["schema"])
            fns[name] = entry["fn"]
            if entry.get("requires_approval"):
                needs_approval.add(name)
    return schemas, fns, needs_approval


# Importing the modules registers their tools.
from agentos.tools import system, files, web, mail, memtools  # noqa: E402,F401
