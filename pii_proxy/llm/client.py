from abc import ABC, abstractmethod


class LlmClient(ABC):
    """Abstract interface for LLM API communication.

    Implementations handle the HTTP transport to upstream LLM providers.
    They do NOT handle PII sanitization or desanitization.
    """

    @abstractmethod
    async def chat_completion(
        self, request: dict, auth_header: str | None = None
    ) -> tuple[int, str]:
        """Send a chat completion request.

        Returns (status_code, response_text).
        """
        ...

    @abstractmethod
    async def embeddings(
        self, request: dict, auth_header: str | None = None
    ) -> tuple[int, bytes]:
        """Send an embeddings request.

        Returns (status_code, response_bytes).
        """
        ...

    @abstractmethod
    async def passthrough(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
    ) -> tuple[int, bytes]:
        """Forward an arbitrary request to the upstream provider.

        Returns (status_code, response_bytes).
        """
        ...
