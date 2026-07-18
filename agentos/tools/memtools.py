from agentos.memory import default_memory
from agentos.tools import tool


@tool(
    "Save a fact to long-term memory so it survives across sessions "
    "(e.g. user preferences, recurring context).",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "short label for the fact"},
            "value": {"type": "string", "description": "the fact to remember"},
        },
        "required": ["key", "value"],
    },
)
def remember(key, value):
    default_memory.remember(key, value)
    return f"Remembered '{key}'."


@tool(
    "Search long-term memory for saved facts. Empty query returns recent facts.",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": [],
    },
)
def recall(query=""):
    facts = default_memory.recall(query)
    if not facts:
        return "No matching facts in memory."
    return "\n".join(f"- {k}: {v}" for k, v in facts.items())
