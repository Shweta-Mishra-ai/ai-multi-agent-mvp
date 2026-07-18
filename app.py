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
                if status is not None:
                    status.update(
                        label=f"Step {event['index'] + 1}: {event['agent']} agent ✅",
                        state="complete",
                    )
                    with status:
                        st.write(event["output"])
                    status = None
            elif event["type"] == "verify":
                if event["satisfied"]:
                    st.caption("✔ Verifier: output satisfies the request")
                else:
                    st.warning(f"Verifier requested a revision: {event['feedback']}")
            elif event["type"] == "done":
                final_output = event["output"]

        if final_output is not None:
            st.success("Result")
            st.write(final_output)
