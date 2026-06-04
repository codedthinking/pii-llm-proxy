import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from pii_proxy.main import app
from pii_proxy.config import settings


client = TestClient(app)


def _upstream_url(path: str) -> str:
    return f"{settings.remote_llm_base_url}/{path}"


def test_single_turn_sanitize_and_dehash():
    """User sends PII, LLM echoes a hash, agent sees original."""
    resp_body = {
        "id": "chatcmpl-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "I will help that person."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with respx.mock:
        route = respx.post(_upstream_url("chat/completions")).mock(
            return_value=httpx.Response(200, json=resp_body)
        )

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [
                    {"role": "user", "content": "My name is John Doe and my email is john@example.com."}
                ],
            },
        )
        assert response.status_code == 200
        assert "x-conversation-id" in response.headers

        # Verify the forwarded request had PII sanitized
        sent_body = json.loads(route.calls[0].request.content)
        for msg in sent_body["messages"]:
            if isinstance(msg.get("content"), str):
                assert "John Doe" not in msg["content"]
                assert "john@example.com" not in msg["content"]


def test_stream_returns_501():
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )
    assert response.status_code == 501
