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
