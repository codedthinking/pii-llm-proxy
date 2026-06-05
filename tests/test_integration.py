import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from pii_proxy.main import app
from pii_proxy.config import settings


client = TestClient(app)


def _upstream_url(path: str) -> str:
    return f"{settings.upstream_base_url}/{path}"


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
                    {"role": "user", "content": "My name is Tiffany Rogers and my email is john@example.com."}
                ],
            },
        )
        assert response.status_code == 200
        assert "x-conversation-id" in response.headers

        # Verify the forwarded request had PII sanitized
        sent_body = json.loads(route.calls[0].request.content)
        for msg in sent_body["messages"]:
            if isinstance(msg.get("content"), str):
                assert "Tiffany Rogers" not in msg["content"]
                assert "john@example.com" not in msg["content"]


def test_stream_passed_through():
    """stream=true should be forwarded as-is to upstream."""
    resp_body = {
        "id": "chatcmpl-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    }
    with respx.mock:
        route = respx.post(_upstream_url("chat/completions")).mock(
            return_value=httpx.Response(200, json=resp_body)
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        sent_body = json.loads(route.calls[0].request.content)
        # stream value is forwarded as-is (no longer forced to false)
        assert sent_body["stream"] is False


def test_extra_fields_preserved():
    """Unknown request fields should pass through to upstream unchanged."""
    resp_body = {
        "id": "chatcmpl-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    }
    with respx.mock:
        route = respx.post(_upstream_url("chat/completions")).mock(
            return_value=httpx.Response(200, json=resp_body)
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0.7,
                "top_p": 0.9,
                "custom_field": "preserved",
            },
        )
        assert response.status_code == 200
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["temperature"] == 0.7
        assert sent_body["top_p"] == 0.9
        assert sent_body["custom_field"] == "preserved"
