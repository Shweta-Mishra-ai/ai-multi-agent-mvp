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

user_input = st.text_area(
    "What do you want to do?",
    placeholder="e.g. Research the top 3 CRM tools, write a comparison report, "
                "and draft an email to my manager"
)
energy = st.selectbox("Your current energy level", ["Low", "Medium", "High"])

if st.button("Run AgentOS"):
    if user_input.strip() == "":
        st.warning("Please enter a task.")
    else:
        kernel = Kernel()
        status = None
        final_output = None

        for event in kernel.run(user_input, energy,
                                session_id=st.session_state.session_id):
            if event["type"] == "plan":
                st.session_state.session_id = event["session_id"]
                with st.expander("📋 Plan", expanded=True):
                    for i, step in enumerate(event["steps"], 1):
                        st.markdown(f"**{i}. {step['agent']}** — {step['instruction']}")
            elif event["type"] == "step_start":
                status = st.status(
                    f"Step {event['index'] + 1}: {event['agent']} agent working...",
                    state="running",
                )
            elif event["type"] == "step_result":
                step_status = event.get("status", "ok")
                if status is not None:
                    icon = {"ok": "✅", "failed": "❌", "skipped": "⏭️"}[step_status]
                    status.update(
                        label=f"Step {event['index'] + 1}: {event['agent']} agent {icon}",
                        state="complete" if step_status == "ok" else "error",
                    )
                    with status:
                        st.write(event["output"])
                    status = None
                elif step_status != "ok":
                    st.warning(f"Step {event['index'] + 1} ({event['agent']}): "
                               f"{event['output']}")
            elif event["type"] == "verify":
                if event["satisfied"]:
                    st.caption("✔ Verifier: output satisfies the request")
                else:
                    st.warning(f"Verifier requested a revision: {event['feedback']}")
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
