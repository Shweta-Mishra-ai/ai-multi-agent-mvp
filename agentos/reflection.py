"""Turns an imperfect run into a reusable lesson, stored through the same
long-term memory agents already read via recall() - the self-improvement
loop is just this module feeding that existing store automatically instead
of only ever being written to by the remember tool."""

import json

from agentos import monitoring
from agentos.llm import chat
from agentos.log import get_logger
from agentos.memory import default_memory

log = get_logger("agentos.reflection")

REFLECT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "lesson",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "has_lesson": {"type": "boolean"},
                "topic": {
                    "type": "string",
                    "description": "short slug for what this lesson is "
                                   "about, e.g. 'freelance-leads'",
                },
                "lesson": {
                    "type": "string",
                    "description": "one or two sentence, generalizable, "
                                   "actionable lesson for similar future "
                                   "requests",
                },
            },
            "required": ["has_lesson", "topic", "lesson"],
            "additionalProperties": False,
        },
    },
}

LESSON_PREFIX = "lesson:"


def reflect_and_remember(user_input, steps, statuses, outputs, verdict, scope):
    """Only fires when something went wrong: a step failed, or the verifier
    asked for a revision. A clean run has nothing to learn from and costs
    nothing extra here - no LLM call, no memory write."""
    failures = [
        f"Step {i + 1} ({steps[i]['agent']}): {str(outputs.get(i, ''))[:500]}"
        for i, s in statuses.items() if s == "failed"
    ]
    revision_note = ""
    if verdict is not None and not verdict.get("satisfied"):
        revision_note = f"\nVerifier's revision feedback: {verdict.get('feedback', '')}"

    if not failures and not revision_note:
        return

    try:
        response = chat(
            messages=[
                {"role": "system", "content": (
                    "You extract reusable lessons from a multi-agent run "
                    "that hit a problem. Given what went wrong, decide: is "
                    "there a short, generalizable lesson worth remembering "
                    "for similar future requests (e.g. 'use tool X instead "
                    "of Y for this kind of task')? If the failure was a "
                    "one-off (network error, rate limit, transient issue) "
                    "with no reusable lesson, say has_lesson: false.")},
                {"role": "user", "content": (
                    f"Request: {user_input}\n\n"
                    "What went wrong:\n" + "\n".join(failures) + revision_note
                )},
            ],
            response_format=REFLECT_RESPONSE_FORMAT,
        )
        result = json.loads(response.choices[0].message.content)
    except Exception as e:
        log.warning("reflection unavailable: %s", e)
        monitoring.capture_exception(e)
        return

    if not result.get("has_lesson"):
        return

    topic = (result.get("topic") or "general").strip()[:60]
    lesson = (result.get("lesson") or "").strip()[:500]
    if topic and lesson:
        default_memory.remember(f"{LESSON_PREFIX}{topic}", lesson, scope=scope)


def relevant_lessons(query, scope, limit=3):
    """Lessons matching the current task, most relevant first - reuses the
    existing recall() (substring + best-effort semantic search) rather than
    a separate lookup path, then narrows to just the lesson: namespace.

    A fresh task's wording rarely shares an exact substring with a past
    lesson, and semantic matching only works when the provider supports
    embeddings (not Groq) - so when topic matching finds nothing, fall
    back to the most recent lessons regardless of topic. A recent lesson
    the agent can judge as relevant or not (its prompt says "apply if
    relevant") beats surfacing none at all."""
    def _lessons(facts):
        return [v for k, v in facts.items() if k.startswith(LESSON_PREFIX)]

    lessons = _lessons(default_memory.recall(query, scope=scope)) if query else []
    if not lessons:
        lessons = _lessons(default_memory.recall("", scope=scope))
    return lessons[:limit]
