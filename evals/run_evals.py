"""Live planner-routing evals against the golden set.

Runs the real LLM planner on each golden request and checks that every
expected agent appears in the produced plan. Requires a real
OPENAI_API_KEY (this is the one place a real key is used in automation).

    python evals/run_evals.py            # exits 1 if accuracy < PASS_RATE
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS_RATE = float(os.getenv("AGENTOS_EVAL_PASS_RATE", "0.8"))
GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden.jsonl")


def main():
    import agentos.agents  # noqa: F401
    from agentos.planner import make_plan

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    passed = 0
    for case in cases:
        steps = make_plan(case["request"], "Medium")
        planned = [s["agent"] for s in steps]
        ok = all(agent in planned for agent in case["expect_agents"])
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] expected {case['expect_agents']} got {planned}  "
              f"<- {case['request'][:60]}")

    accuracy = passed / len(cases)
    print(f"\nRouting accuracy: {passed}/{len(cases)} = {accuracy:.0%} "
          f"(required: {PASS_RATE:.0%})")
    if accuracy < PASS_RATE:
        sys.exit(1)


if __name__ == "__main__":
    main()
