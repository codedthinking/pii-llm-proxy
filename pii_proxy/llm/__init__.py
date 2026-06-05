from ..config import settings
from .client import LlmClient
from .httpx_client import HttpxClient

_client: LlmClient | None = None


def get_client() -> LlmClient:
    """Return the singleton LlmClient instance."""
    global _client
    if _client is None:
        backend = getattr(settings, "llm_client_backend", "httpx")
        if backend == "litellm":
            from .litellm_client import LitellmClient
            _client = LitellmClient(base_url=settings.remote_llm_base_url)
        else:
            _client = HttpxClient(base_url=settings.remote_llm_base_url)
    return _client


__all__ = [
    "LlmClient",
    "HttpxClient",
    "get_client",
]
