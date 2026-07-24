import json

from fastapi.testclient import TestClient

from tests.conftest import fake_response, make_plan_json


def test_health_and_agents():
    from api import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    agents = client.get("/agents").json()
    assert {a["name"] for a in agents} >= {"task", "research", "email", "code", "writer"}


def test_run_streams_events(patch_llm):
    plan = make_plan_json(
        [{"agent": "task", "instruction": "plan it", "depends_on": []}])

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        return fake_response(content="PLANNED")

    patch_llm(fake_chat)
    from api import app

    client = TestClient(app)
    response = client.post("/run", json={"request": "plan my day"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().splitlines()]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "plan" and "done" in kinds and "metrics" in kinds


def test_run_rejects_bad_payload():
    from api import app

    client = TestClient(app)
    assert client.post("/run", json={"request": ""}).status_code == 422
    assert client.post("/run", json={"request": "hi", "energy": "TURBO"}).status_code == 422


def test_execute_endpoint_runs_tool_directly():
    from api import app

    client = TestClient(app)
    r = client.post("/execute", json={
        "actions": [{"tool": "calculate", "args": {"expression": "2+2"}}]})
    assert r.status_code == 200
    assert r.json() == [{"tool": "calculate", "args": {"expression": "2+2"},
                         "result": "4"}]


def test_execute_rejects_empty_actions():
    from api import app

    client = TestClient(app)
    assert client.post("/execute", json={"actions": []}).status_code == 422


def test_run_survives_unexpected_kernel_error():
    """Regression test: an uncaught error used to truncate the NDJSON
    stream with no terminal event. The stream must always end with a
    clear error event instead of silently cutting off."""
    from unittest.mock import patch

    from api import app

    client = TestClient(app)
    with patch("api.Kernel.run", side_effect=RuntimeError("boom")):
        response = client.post("/run", json={"request": "trigger a crash"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().splitlines()]
    assert events[-1]["type"] == "error"
    assert "boom" in events[-1]["message"]


def test_concurrent_requests_do_not_cross_contaminate(patch_llm):
    """Load-handling regression test: fire several /run requests at once
    (simulating concurrent users) and verify each gets back only its own
    plan/output - no telemetry or session bleeding across requests."""
    import threading

    plan_tmpl = lambda word: make_plan_json(  # noqa: E731
        [{"agent": "task", "instruction": f"echo {word}", "depends_on": []}])

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            name = response_format["json_schema"]["name"]
            if name == "plan":
                user = messages[-1]["content"]
                word = user.split("User request: ")[-1].split()[0]
                return fake_response(content=plan_tmpl(word))
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        return fake_response(content=messages[-1]["content"])

    patch_llm(fake_chat)
    from api import app

    client = TestClient(app)
    results = {}
    errors = []

    def worker(n):
        try:
            r = client.post("/run", json={"request": f"unique-{n} do something"})
            events = [json.loads(line) for line in r.text.strip().splitlines()]
            done = [e for e in events if e["type"] == "done"][0]
            results[n] = done["output"]
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors
    assert len(results) == 8
    for n, output in results.items():
        assert f"unique-{n}" in output  # each request got its own result back
