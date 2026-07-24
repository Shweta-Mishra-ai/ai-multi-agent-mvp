import os

from agentos import config, identity
from agentos.tools import tool


def _workspace():
    # Scoped per caller (API key, or "default" in open-mode/local use) so
    # different callers' files never collide or become visible to each
    # other - each gets their own subdirectory automatically.
    base = os.getenv("AGENTOS_WORKSPACE", "workspace")
    return os.path.join(base, identity.scope())


def _safe_path(name):
    workspace = _workspace()
    os.makedirs(workspace, exist_ok=True)
    path = os.path.realpath(os.path.join(workspace, name))
    root = os.path.realpath(workspace)
    if not path.startswith(root + os.sep):
        raise ValueError("path escapes the workspace")
    return path


@tool("List all files in your workspace.")
def list_files():
    workspace = _workspace()
    os.makedirs(workspace, exist_ok=True)
    files = []
    for dirpath, _, names in os.walk(workspace):
        for n in names:
            files.append(os.path.relpath(os.path.join(dirpath, n), workspace))
    return "\n".join(sorted(files)) or "(workspace is empty)"


@tool(
    "Read a file from the shared workspace.",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
def read_file(name):
    with open(_safe_path(name), encoding="utf-8") as f:
        return f.read()[:8000]


@tool(
    "Write content to a file in the shared workspace (creates or overwrites).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["name", "content"],
    },
)
def write_file(name, content):
    if len(content.encode("utf-8")) > config.MAX_FILE_BYTES:
        return (f"Refused: content exceeds the {config.MAX_FILE_BYTES} byte "
                "workspace file limit. Split it into smaller files.")
    path = _safe_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} characters to {name}"
