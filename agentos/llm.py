import os

from dotenv import load_dotenv
from openai import OpenAI

from agentos import config, telemetry

load_dotenv()

# Works with any OpenAI-compatible endpoint (OpenAI, Ollama, vLLM, ...):
# set OPENAI_BASE_URL and AGENTOS_MODEL to switch providers without code changes.
# Timeouts and automatic retries (rate limits, transient 5xx) are built in.
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
    timeout=config.LLM_TIMEOUT,
    max_retries=config.LLM_RETRIES,
)

MODEL = os.getenv("AGENTOS_MODEL", "gpt-4o-mini")


def chat(messages, tools=None, response_format=None):
    kwargs = {"model": MODEL, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    response = client.chat.completions.create(**kwargs)
    telemetry.record_llm(response)
    return response
