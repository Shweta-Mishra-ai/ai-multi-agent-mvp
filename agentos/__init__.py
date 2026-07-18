"""AgentOS — a small agentic operating system.

Kernel   = plans, schedules and verifies work across agents
Agents   = specialized LLM workers registered in a central registry
Tools    = the "syscalls" agents use to act on the real world
Memory   = persistent sessions, conversation history and key-value store

Frontends (CLI, Streamlit, future API) all talk to the same Kernel.
"""

__version__ = "0.2.0"
