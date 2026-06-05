import json

import httpx
import litellm

from .client import LlmClient


class LitellmClient(LlmClient):
    """LLM client using litellm for chat completions.

    Uses litellm.acompletion() for chat (supports 100+ providers).
    Falls back to httpx for embeddings and passthrough endpoints.
    """

    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def chat_completion(
        self, request: dict, auth_header: str | None = None
    ) -> tuple[int, str]:
        api_key = None
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header[len("Bearer "):]

        try:
            response = await litellm.acompletion(
                api_base=self.base_url,
                api_key=api_key,
                **request,
            )
            return 200, response.model_dump_json()
        except litellm.exceptions.APIStatusError as e:
            return e.status_code, json.dumps({"error": str(e)})
        except Exception as e:
            return 502, json.dumps({"error": f"Failed to reach upstream LLM: {e}"})

    async def embeddings(
        self, request: dict, auth_header: str | None = None
    ) -> tuple[int, bytes]:
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                json=request,
                headers=headers,
            )
        return resp.status_code, resp.content

    async def passthrough(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
    ) -> tuple[int, bytes]:
        url = f"{self.base_url}/{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.request(
                method=method,
                url=url,
                content=body if body else None,
                headers=headers,
            )
        return resp.status_code, resp.content
