import contextvars
import json
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from agentos import config, security, telemetry
from agentos.llm import chat
from agentos.log import get_logger
from agentos.memory import default_memory
from agentos.planner import make_plan
from agentos.registry import get_agent
import agentos.agents  # noqa: F401  (registers built-in agents)

log = get_logger("agentos.kernel")

VERIFY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "satisfied": {"type": "boolean"},
                "feedback": {
                    "type": "string",
                    "description": "If not satisfied: what is missing or wrong, "
                                   "as an instruction for fixing the final output.",
                },
            },
            "required": ["satisfied", "feedback"],
            "additionalProperties": False,
        },
    },
}


class Kernel:
    """The AgentOS kernel: validate -> plan -> schedule agents -> verify -> deliver.

    Production behavior:
    - input validation and per-deployment rate limiting up front
    - independent plan steps run in parallel (bounded worker pool)
    - failed steps don't crash the run; dependent steps are skipped explicitly
    - a global deadline bounds every run
    - a verifier LLM reviews the result and can trigger one revision round
    - every run emits metrics (duration, tokens, est. cost) and is persisted

    `run` yields progress events consumed identically by every frontend:
      plan / step_start / step_result (status: ok|failed|skipped) /
      verify / done / metrics / error
    """

    def __init__(self, memory=None):
        self.memory = memory or default_memory

    def execute_approved(self, actions):
        """Directly execute previously-previewed tool calls with their exact
        recorded arguments - no re-planning and no re-running any agent.

        This guarantees the action actually executed is identical to the one
        the user reviewed: re-running the whole kernel would ask the LLM to
        regenerate its output, which is non-deterministic and could send a
        different email than the one that was previewed, as well as costing
        a second full round of LLM calls just to reach the approval gate."""
        from agentos.tools import TOOLS

        results = []
        for action in actions:
            entry = TOOLS.get(action.get("tool"))
            if entry is None:
                results.append({**action, "result": "Unknown tool"})
                continue
            try:
                result = str(entry["fn"](**action.get("args", {})))[
                    :config.MAX_TOOL_OUTPUT_CHARS]
            except Exception as e:
                result = f"Tool error: {e}"
                log.warning("approved action %s failed: %s", action.get("tool"), e)
            results.append({**action, "result": result})
        return results

    def run(self, user_input, energy_level="Medium", session_id=None,
            approve=False):
        metrics = telemetry.start_run()
        metrics.approved = bool(approve)

        problem = security.validate_request(user_input)
        if problem:
            yield {"type": "error", "message": problem}
            return
        if not security.check_rate_limit(self.memory):
            yield {"type": "error",
                   "message": "Rate limit reached — please wait a minute and try again."}
            return

        try:
            if session_id is None:
                session_id = self.memory.create_session(user_input)
            history = self.memory.get_messages(session_id, limit=8)
        except Exception as e:
            # A transient storage error here must not crash the whole run:
            # degrade to a fresh in-memory-only session (no history) rather
            # than letting the generator raise mid-stream.
            log.warning("memory unavailable, continuing without history: %s", e)
            session_id = session_id or uuid.uuid4().hex[:12]
            history = []

        def emit(event):
            try:
                self.memory.log_event(session_id, event)
            except Exception as e:
                log.warning("could not persist event: %s", e)
            return event

        steps = make_plan(user_input, energy_level, history=history)[:config.MAX_STEPS]
        yield emit({"type": "plan", "steps": steps, "session_id": session_id})

        outputs, statuses = {}, {}
        deadline = time.time() + config.RUN_TIMEOUT
        for event in self._execute(steps, outputs, statuses, deadline):
            yield emit(event)

        last = len(steps) - 1
        final = str(outputs.get(last, ""))

        if statuses.get(last) == "ok":
            verdict = self._verify(user_input, steps, outputs)
            yield emit({"type": "verify", **verdict})
            if not verdict["satisfied"]:
                for event in self._revise(last, steps, outputs, verdict["feedback"]):
                    yield emit(event)
                final = str(outputs.get(last, final))
        else:
            failed = [f"step {i + 1}: {outputs.get(i, '')}"
                      for i, s in statuses.items() if s != "ok"]
            final = ("The run could not be fully completed.\n"
                     + "\n".join(failed))

        pending = metrics.pending_actions()
        if pending:
            yield emit({"type": "approval_required", "actions": pending})

        try:
            self.memory.add_message(session_id, "user", user_input)
            self.memory.add_message(session_id, "assistant", final)
        except Exception as e:
            log.warning("could not persist messages: %s", e)

        yield emit({"type": "done", "output": final, "session_id": session_id})

        snapshot = metrics.snapshot()
        try:
            self.memory.save_metrics(session_id, snapshot)
        except Exception as e:
            log.warning("could not persist metrics: %s", e)
        yield emit({"type": "metrics", **snapshot})

    # --- execution ---

    def _execute(self, steps, outputs, statuses, deadline):
        """Run steps respecting dependencies; independent steps in parallel."""
        pending = set(range(len(steps)))
        pool = ThreadPoolExecutor(max_workers=config.MAX_PARALLEL)
        futures = {}
        try:
            while pending or futures:
                if time.time() > deadline:
                    for i in sorted(pending):
                        statuses[i] = "skipped"
                        outputs[i] = "Skipped: the run reached its time limit."
                        yield self._result_event(i, steps, outputs, statuses)
                    pending.clear()
                    break

                # Skip steps whose dependencies did not succeed.
                for i in sorted(pending):
                    if any(statuses.get(d) in ("failed", "skipped")
                           for d in self._deps(steps, i)):
                        pending.discard(i)
                        statuses[i] = "skipped"
                        outputs[i] = "Skipped: a step it depends on did not succeed."
                        yield self._result_event(i, steps, outputs, statuses)

                # Schedule every step whose dependencies are all satisfied.
                ready = [i for i in sorted(pending)
                         if all(statuses.get(d) == "ok" for d in self._deps(steps, i))]
                for i in ready:
                    pending.discard(i)
                    yield {"type": "step_start", "index": i,
                           "agent": steps[i]["agent"],
                           "instruction": steps[i]["instruction"]}
                    context = self._context_for(i, steps, outputs)
                    ctx = contextvars.copy_context()
                    futures[pool.submit(ctx.run, self._exec_step,
                                        steps[i], context)] = i

                if not futures:
                    if pending:  # circular or invalid dependencies
                        for i in sorted(pending):
                            statuses[i] = "skipped"
                            outputs[i] = "Skipped: unresolvable dependencies in the plan."
                            yield self._result_event(i, steps, outputs, statuses)
                        pending.clear()
                    continue

                done_now, _ = wait(futures, timeout=1.0, return_when=FIRST_COMPLETED)
                for future in done_now:
                    i = futures.pop(future)
                    try:
                        outputs[i] = future.result()
                        statuses[i] = "ok"
                    except Exception as e:
                        outputs[i] = f"Step failed: {e}"
                        statuses[i] = "failed"
                        log.warning("step %s (%s) failed: %s",
                                    i + 1, steps[i]["agent"], e)
                    yield self._result_event(i, steps, outputs, statuses)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _exec_step(self, step, context):
        agent = get_agent(step["agent"])
        if agent is None:
            raise ValueError(f"no agent named '{step['agent']}'")
        return agent.run(step["instruction"], context)

    def _revise(self, last, steps, outputs, feedback):
        """One revision round: the final step's agent fixes its output."""
        instruction = (
            f"{steps[last]['instruction']}\n\n"
            f"Your previous attempt was reviewed. Fix this feedback and "
            f"produce the corrected final result:\n{feedback}\n\n"
            f"Previous attempt:\n{outputs.get(last, '')}"
        )
        yield {"type": "step_start", "index": last,
               "agent": steps[last]["agent"], "instruction": "revision round"}
        try:
            context = self._context_for(last, steps, outputs)
            outputs[last] = self._exec_step(
                {"agent": steps[last]["agent"], "instruction": instruction}, context)
        except Exception as e:
            log.warning("revision failed, keeping previous output: %s", e)
        yield {"type": "step_result", "index": last,
               "agent": steps[last]["agent"],
               "output": outputs.get(last, ""), "status": "ok"}

    # --- helpers ---

    @staticmethod
    def _deps(steps, i):
        return [d for d in steps[i].get("depends_on", [])
                if isinstance(d, int) and 0 <= d < len(steps) and d != i]

    def _context_for(self, i, steps, outputs):
        parts = [
            f"[Output of step {d + 1} ({steps[d]['agent']})]:\n{outputs[d]}"
            for d in self._deps(steps, i) if d in outputs
        ]
        return "\n\n".join(parts)[:config.MAX_CONTEXT_CHARS]

    @staticmethod
    def _result_event(i, steps, outputs, statuses):
        return {"type": "step_result", "index": i, "agent": steps[i]["agent"],
                "output": outputs[i], "status": statuses[i]}

    def _verify(self, user_input, steps, outputs):
        """Ask the LLM whether the outputs actually satisfy the request."""
        try:
            results = "\n\n".join(
                f"Step {i + 1} ({step['agent']}): {str(outputs.get(i, ''))[:1500]}"
                for i, step in enumerate(steps)
            )
            response = chat(
                messages=[
                    {"role": "system", "content":
                        "You are the quality verifier of a multi-agent system. "
                        "Judge whether the step outputs, taken together, satisfy "
                        "the user's request. Be pragmatic: minor style issues are "
                        "fine, missing or wrong content is not. An output that "
                        "shows a prepared action awaiting the user's approval "
                        "(e.g. an email draft pending confirmation) counts as "
                        "satisfying the request."},
                    {"role": "user", "content":
                        f"User request: {user_input}\n\nStep outputs:\n{results}"},
                ],
                response_format=VERIFY_RESPONSE_FORMAT,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            log.warning("verifier unavailable: %s", e)
            return {"satisfied": True, "feedback": f"(verifier unavailable: {e})"}
