import httpx

from .client import LlmClient


class HttpxClient(LlmClient):
    """LLM client using httpx for direct HTTP communication."""

    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def _build_headers(self, auth_header: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        return headers

    async def chat_completion(
        self, request: dict, auth_header: str | None = None
    ) -> tuple[int, str]:
        headers = self._build_headers(auth_header)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=request,
                headers=headers,
            )
        return resp.status_code, resp.text

    async def embeddings(
        self, request: dict, auth_header: str | None = None
    ) -> tuple[int, bytes]:
        headers = self._build_headers(auth_header)
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
