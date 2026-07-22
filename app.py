import streamlit as st

from agentos.kernel import Kernel
from agentos.registry import all_specs

st.set_page_config(page_title="AgentOS", layout="centered")

st.title("🧠 AgentOS")
st.caption("Multi-agent orchestration: plan → agents → tools → verify. "
           "Also available from the CLI: `python cli.py run \"...\"`")

with st.sidebar:
    st.subheader("Registered agents")
    for spec in all_specs():
        st.markdown(f"**{spec.name}** — {spec.description}")
        if spec.tools:
            st.caption("tools: " + ", ".join(spec.tools))

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "pending_actions" not in st.session_state:
    st.session_state.pending_actions = []

user_input = st.text_area(
    "What do you want to do?",
    placeholder="e.g. Research the top 3 CRM tools, write a comparison report, "
                "and draft an email to my manager"
)
energy = st.selectbox("Your current energy level", ["Low", "Medium", "High"])
approve = st.checkbox(
    "Allow real-world actions (e.g. actually send email)",
    help="Off = actions like sending email are prepared as previews only. "
         "Tick this and run again to execute them.",
)

if st.button("Run AgentOS"):
    if user_input.strip() == "":
        st.warning("Please enter a task.")
    else:
        kernel = Kernel()
        # Keyed by step index (not a single shared variable): independent
        # steps run in parallel, so a second step's step_start can arrive
        # before the first step's step_result - a single shared widget
        # reference would have the second step's start overwrite the
        # reference to the first step's box, misattributing its result.
        status_by_index = {}
        final_output = None
        st.session_state.pending_actions = []

        for event in kernel.run(user_input, energy,
                                session_id=st.session_state.session_id,
                                approve=approve):
            if event["type"] == "plan":
                st.session_state.session_id = event["session_id"]
                with st.expander("📋 Plan", expanded=True):
                    for i, step in enumerate(event["steps"], 1):
                        st.markdown(f"**{i}. {step['agent']}** — {step['instruction']}")
            elif event["type"] == "step_start":
                status_by_index[event["index"]] = st.status(
                    f"Step {event['index'] + 1}: {event['agent']} agent working...",
                    state="running",
                )
            elif event["type"] == "step_result":
                step_status = event.get("status", "ok")
                status = status_by_index.get(event["index"])
                if status is not None:
                    icon = {"ok": "✅", "failed": "❌", "skipped": "⏭️"}[step_status]
                    status.update(
                        label=f"Step {event['index'] + 1}: {event['agent']} agent {icon}",
                        state="complete" if step_status == "ok" else "error",
                    )
                    with status:
                        st.write(event["output"])
                elif step_status != "ok":
                    st.warning(f"Step {event['index'] + 1} ({event['agent']}): "
                               f"{event['output']}")
            elif event["type"] == "verify":
                if event["satisfied"]:
                    st.caption("✔ Verifier: output satisfies the request")
                else:
                    st.warning(f"Verifier requested a revision: {event['feedback']}")
            elif event["type"] == "approval_required":
                st.session_state.pending_actions = event["actions"]
                actions = ", ".join(a["tool"] for a in event["actions"])
                st.warning(
                    f"⚠ Prepared but NOT executed: {actions}. Review the "
                    "preview above, then use the button below to approve "
                    "and execute exactly what was previewed."
                )
            elif event["type"] == "error":
                st.error(event["message"])
            elif event["type"] == "metrics":
                st.caption(
                    f"⏱ {event['duration_s']}s · {event['llm_calls']} LLM calls · "
                    f"{event['tool_calls']} tool calls · {event['tokens']} tokens · "
                    f"~${event['est_cost_usd']}"
                )
            elif event["type"] == "done":
                final_output = event["output"]

        if final_output is not None:
            st.success("Result")
            st.write(final_output)

if st.session_state.pending_actions:
    st.divider()
    st.warning(f"{len(st.session_state.pending_actions)} action(s) awaiting approval.")
    if st.button("✅ Approve & execute exactly what was previewed"):
        # Executes the exact recorded tool calls directly - never re-runs
        # the plan/agents, so what gets executed always matches the preview.
        for result in Kernel().execute_approved(st.session_state.pending_actions):
            st.success(f"Executed {result['tool']}")
            st.write(result["result"])
        st.session_state.pending_actions = []
