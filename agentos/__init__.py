"""AgentOS — a small agentic operating system.

Kernel   = plans, schedules and verifies work across agents
Agents   = specialized LLM workers registered in a central registry
Tools    = the "syscalls" agents use to act on the real world
Memory   = persistent sessions, conversation history, key-value store and
           API keys, all scoped per caller for multi-tenant isolation

Frontends (CLI, Streamlit, HTTP API) all talk to the same Kernel.
"""

__version__ = "1.0.0"
