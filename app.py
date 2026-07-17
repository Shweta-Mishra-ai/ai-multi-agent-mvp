import streamlit as st
from parent_agent import ParentAgent

st.set_page_config(
    page_title="AI Multi-Agent System",
    layout="centered"
)

st.title("🧠 AI Multi-Agent Task Manager")

user_input = st.text_area(
    "What do you want to do?",
    placeholder="e.g. Research the top 3 CRM tools and write an email "
                "to my manager comparing them"
)
energy = st.selectbox(
    "Your current energy level",
    ["Low", "Medium", "High"]
)

if st.button("Run AI"):
    if user_input.strip() == "":
        st.warning("Please enter a task.")
    else:
        agent = ParentAgent()
        status = None
        final_output = None

        with st.spinner("Planning..."):
            events = agent.handle(user_input, energy)
            first_event = next(events)

        if first_event["type"] == "plan":
            with st.expander("📋 Plan", expanded=True):
                for i, step in enumerate(first_event["steps"], 1):
                    st.markdown(f"**{i}. {step['agent']}** — {step['instruction']}")

        for event in events:
            if event["type"] == "step_start":
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
                else:
                    st.error(event["output"])
                final_output = event["output"]

        if final_output is not None:
            st.success("AI Output")
            st.write(final_output)
