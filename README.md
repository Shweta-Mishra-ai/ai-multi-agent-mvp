
# AI Multi-Agent Task Management System

This project is a working MVP built as part of an AI Engineer technical challenge.

It demonstrates a **Parent–Child multi-agent architecture** where a central Parent Agent orchestrates multiple specialized AI agents to perform different tasks based on user intent and energy level.

---

## 🚀 Features

- LLM-powered Planner that turns a request into a multi-step plan (structured JSON output)
- Parent Agent that orchestrates the plan: runs each step with the right agent and passes earlier outputs as context to later steps
- Task Planning Agent (LLM-powered)
- Research Agent (LLM-powered)
- Email Writing Agent (LLM-powered)
- Shared agent base class with a tool-calling loop, ready for real tools (web search, email sending, calendar)
- Energy level influences planning (low energy → fewer, simpler steps)
- Streamlit UI with live per-step progress
- Cloud-deployed (no local setup required)

---

## 🧠 Architecture Overview

User → Streamlit UI → Parent Agent  
Parent Agent → Planner (LLM) → Multi-step plan  
Parent Agent → Step 1 Agent → output → Step 2 Agent (with step 1 output as context) → …  
Each Agent → LLM (+ tools) → Result → Parent Agent → User

Example: *"Research the top 3 CRM tools and email a comparison to my manager"*
becomes a 2-step plan — the Research Agent runs first, and the Email Agent
writes the email using the research output as context.

---

## ⚙️ Tech Stack

- Python
- Streamlit
- OpenAI API
- Modular Agent Architecture

---

## 🧪 How It Works

1. User enters a task and selects energy level
2. The Planner (LLM with structured output) produces a plan of 1–4 steps, each assigned to an agent, with dependencies between steps
3. The Parent Agent executes the steps in order, feeding each step's output into the steps that depend on it
4. Each agent runs a tool-calling loop (currently no tools registered, so it resolves in one LLM call) and returns its result
5. The plan and every step's output are shown live in the UI

---

## 🌍 Deployment

The app is deployed using **Streamlit Community Cloud** (free tier).

---

## 🔮 Future Improvements

- Add real tools: web search for the Research Agent, actual email sending (with user confirmation)
- Add memory and context persistence
- Add calendar integration
- Add interrupt handling agent
- Add a verification pass: Parent Agent checks the outputs satisfy the request and retries failed steps

---

## 📌 Note

This MVP focuses on **clarity, architecture, and applied AI**, not production-scale complexity.
