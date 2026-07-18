import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Works with any OpenAI-compatible endpoint (OpenAI, Ollama, vLLM, ...):
# set OPENAI_BASE_URL and AGENTOS_MODEL to switch providers without code changes.
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or None,
)

MODEL = os.getenv("AGENTOS_MODEL", "gpt-4o-mini")


def chat(messages, tools=None, response_format=None):
    kwargs = {"model": MODEL, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    return client.chat.completions.create(**kwargs)
