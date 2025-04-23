import json
import requests
import pytest # type: ignore
from brixel.client import BrixelClient
from brixel.models import create_agent, create_task
from brixel.exceptions import BrixelAPIError, BrixelConnectionError

API_KEY = "fake-api-key"
ENDPOINT = "http://mocked-api.local/generate"

@pytest.fixture
def brixel_client():
    return BrixelClient(api_key=API_KEY, endpoint=ENDPOINT)

@pytest.fixture
def agent():
    task = create_task(
        name="SummariseText",
        description="Summarise text in 200 words.",
        inputs=[{"name": "text", "type": "string", "description": "The text to summarise", "required": True}],
        output={"type": "string", "description": "The summary"}
    )
    return create_agent("Summarisation Agent", "Agent specialised in summarisation", [task])

def test_generate_plan_success(brixel_client, agent, requests_mock):
    mock_response = {"plan": {"id": "1234", "steps": []}}
    requests_mock.post(ENDPOINT, json=mock_response, status_code=200)

    result = brixel_client.generate_plan("résume moi ça", agents=[agent])
    assert "plan" in result
    assert result["plan"]["id"] == "1234"

def test_generate_plan_http_error(brixel_client, agent, requests_mock):
    requests_mock.post(ENDPOINT, status_code=400, json={"error": "Bad Request"})

    with pytest.raises(BrixelAPIError) as exc:
        brixel_client.generate_plan("message", agents=[agent])
    assert "Bad Request" in str(exc.value)

def test_generate_plan_timeout(brixel_client, agent, requests_mock):
    requests_mock.post(ENDPOINT, exc=requests.exceptions.Timeout)

    with pytest.raises(BrixelConnectionError) as exc:
        brixel_client.generate_plan("message", agents=[agent])
    assert "Connexion timeout" in str(exc.value)

def test_generate_plan_connection_error(brixel_client, agent, requests_mock):
    requests_mock.post(ENDPOINT, exc=requests.exceptions.ConnectionError)

    with pytest.raises(BrixelConnectionError):
        brixel_client.generate_plan("message", agents=[agent])


def test_execute_plan_streaming(brixel_client, agent, requests_mock):
    # Simule un flux de données avec des lignes JSON séparées
    streaming_data = '\n'.join([
        json.dumps({"step": 1, "message": "Plan started"}),
        json.dumps({"step": 2, "message": "Running task"}),
        json.dumps({"step": 3, "message": "Plan completed"})
    ])

    requests_mock.post(ENDPOINT, content=streaming_data.encode("utf-8"))

    stream = brixel_client.execute_plan(
        message="stream test",
        agents=[agent],
        stream=True
    )

    results = list(stream)

    assert len(results) == 3
    assert results[0]["step"] == 1
    assert results[-1]["message"] == "Plan completed"

def test_execute_plan_non_streaming(brixel_client, agent, requests_mock):
    mock_json = {
        "status": "completed",
        "steps": [
            {"step": 1, "message": "Started"},
            {"step": 2, "message": "Finished"}
        ]
    }

    requests_mock.post(ENDPOINT, json=mock_json, status_code=200)

    result = brixel_client.execute_plan(
        message="non-stream test",
        agents=[agent],
        stream=False
    )

    assert result["status"] == "completed"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["message"] == "Started"

def test_execute_plan_full_structure(brixel_client, agent, requests_mock):
    # Exemple simplifié du plan que tu as partagé
    mock_plan = {
        "plan_id": "004cae7f-6498-4fe6-8d79-f3ee94c8020f",
        "sub_plans": [
            {
                "id": 0,
                "agent": {
                    "id": "42f7a263-d4d0-4437-9272-a0907563e330",
                    "type": "hosted"
                },
                "status": "complete",
                "plan": [
                    {"title": "Web search", "name": "web_search_with_serper_dev", "index": 0},
                    {"title": "Return results", "name": "_return", "index": 1}
                ]
            }
        ],
        "metrics": {
            "plans_generated": 1,
            "generation_time": 5.2,
            "steps": 2
        }
    }

    requests_mock.post(ENDPOINT, json=mock_plan, status_code=200)

    result = brixel_client.execute_plan(
        message="Structure test",
        agents=[agent],
        stream=False
    )

    assert "plan_id" in result
    assert result["plan_id"] == "004cae7f-6498-4fe6-8d79-f3ee94c8020f"

    assert "sub_plans" in result
    assert len(result["sub_plans"]) == 1

    plan = result["sub_plans"][0]["plan"]
    assert isinstance(plan, list)
    assert plan[0]["name"] == "web_search_with_serper_dev"
    assert result["metrics"]["plans_generated"] == 1