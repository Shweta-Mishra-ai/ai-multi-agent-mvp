from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

MODEL = "gpt-4o-mini"


def chat(messages, tools=None, response_format=None):
    kwargs = {
        "model": MODEL,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format

    return client.chat.completions.create(**kwargs)
