import requests
import pytest
import requests_mock
from brixel.client import BrixelClient
from brixel.models import create_task
from brixel.exceptions import BrixelAPIError, BrixelConnectionError

API_KEY = "fake-api-key"
ENDPOINT = "http://mocked-api.local/generate_plan"

@pytest.fixture
def brixel_client():
    client = BrixelClient(api_key=API_KEY)
    client.api_base_url = "http://mocked-api.local"
    return client

@pytest.fixture
def agent():
    task = create_task(
        name="SummariseText",
        description="Summarise text in 200 words.",
        inputs=[{"name": "text", "type": "string", "description": "The text to summarise", "required": True}],
        output={"type": "string", "description": "The summary"}
    )
    return {"name": "Summarisation Agent", "description": "Agent specialised in summarisation", "tasks": [task]}

def test_generate_plan_success(brixel_client, agent, requests_mock):
    mock_response = {"plan": {"id": "1234", "steps": []}}
    requests_mock.post(ENDPOINT, json=mock_response, status_code=200)

    result = brixel_client.generate_plan("Resume this", agents=[agent])
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


def test_execute_plan_local_subplan(brixel_client, requests_mock, agent):
    plan = {
        "plan_id": "abc123",
        "sub_plans": [
            {
                "id": 0,
                "agent": {
                    "id": "test",
                    "type": "local",
                    "options": {}
                },
                "plan": [
                    {
                        "name": "_assign",
                        "index": 0,
                        "output": "result",
                        "inputs": {
                            "value": "5"
                        }
                    },
                    {
                        "name": "_return",
                        "index": 1,
                        "inputs": {
                            "value": "result"
                        }
                    }
                ]
            }
        ]
    }

    result = brixel_client.execute_plan(plan)
    assert result is None


def test_execute_plan_hosted_subplan(brixel_client, requests_mock, agent):
    plan_id = "xyz456"
    sub_id = 1
    plan = {
        "plan_id": plan_id,
        "sub_plans": [
            {
                "id": sub_id,
                "agent": {
                    "id": "hosted-agent",
                    "type": "hosted"
                }
            }
        ]
    }

    response_data = {"message": "done!"}

    requests_mock.post(
        f"http://mocked-api.local/{plan_id}/sub_plan/{sub_id}/execute",
        json=response_data
    )

    result = brixel_client.execute_plan(plan)

    assert result is None


def test_execute_plan_with_multiple_subplans(brixel_client, requests_mock, agent):
    plan = {
        "plan_id": "plan789",
        "sub_plans": [
            {
                "id": 0,
                "agent": {"id": "local-agent", "type": "local"},
                "plan": [
                    {"name": "_assign", "index": 0, "output": "x", "inputs": {"value": "42"}},
                    {"name": "_return", "index": 1, "inputs": {"value": "x"}}
                ]
            },
            {
                "id": 1,
                "agent": {"id": "hosted-agent", "type": "hosted"},
            }
        ]
    }

    requests_mock.post(
        "http://mocked-api.local/plan789/sub_plan/1/execute",
        json={"status": "ok"}
    )

    result = brixel_client.execute_plan(plan)

    assert result is None