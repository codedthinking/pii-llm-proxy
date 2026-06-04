import logging
import uuid

import httpx
from fastapi import FastAPI, Request, Response
from presidio_analyzer import AnalyzerEngine

from .config import settings
from .desanitizer import desanitize_text
from .models import ChatCompletionRequest, ChatCompletionResponse, ContentPart
from .sanitizer import SYSTEM_NOTICE, sanitize_text
from .session import SessionStore

logger = logging.getLogger("pii_proxy")
logging.basicConfig(level=logging.DEBUG)

app = FastAPI(title="PII Sanitizing LLM Proxy")
store = SessionStore()
analyzer = AnalyzerEngine()


def _resolve_conversation_id(request_headers: dict[str, str], body: ChatCompletionRequest) -> tuple[str, bool]:
    """Return (conversation_id, is_new)."""
    cid = request_headers.get("x-conversation-id")
    if cid:
        return cid, False
    # Check last message for tool_call_id
    if body.messages and body.messages[-1].tool_call_id:
        return body.messages[-1].tool_call_id, False
    return str(uuid.uuid4()), True


def _sanitize_message_content(content: str | list[ContentPart] | None, session, ana) -> str | list[ContentPart] | None:
    if content is None:
        return None
    if isinstance(content, str):
        return sanitize_text(content, session, ana)
    # list of content parts
    sanitized_parts = []
    for part in content:
        if part.type == "text" and part.text is not None:
            new_part = part.model_copy(update={"text": sanitize_text(part.text, session, ana)})
            sanitized_parts.append(new_part)
        else:
            sanitized_parts.append(part)
    return sanitized_parts


def _sanitize_request(body: ChatCompletionRequest, session) -> ChatCompletionRequest:
    sanitized_messages = []
    for msg in body.messages:
        if msg.role in ("user", "system", "tool"):
            new_content = _sanitize_message_content(msg.content, session, analyzer)
            sanitized_messages.append(msg.model_copy(update={"content": new_content}))
        else:
            sanitized_messages.append(msg)

    # Inject system notice
    if settings.inject_system_notice and not session.system_notice_injected:
        if sanitized_messages and sanitized_messages[0].role == "system":
            first = sanitized_messages[0]
            if isinstance(first.content, str):
                new_content = SYSTEM_NOTICE + "\n\n" + first.content
            else:
                new_content = SYSTEM_NOTICE
            sanitized_messages[0] = first.model_copy(update={"content": new_content})
        else:
            from .models import Message
            notice_msg = Message(role="system", content=SYSTEM_NOTICE)
            sanitized_messages.insert(0, notice_msg)
        session.system_notice_injected = True

    return body.model_copy(update={"messages": sanitized_messages})


def _desanitize_response(resp: ChatCompletionResponse, session) -> ChatCompletionResponse:
    for choice in resp.choices:
        msg = choice.message
        if msg.content:
            msg.content = desanitize_text(msg.content, session)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tc.function.arguments = desanitize_text(tc.function.arguments, session)
    return resp


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    raw_body = await request.json()
    try:
        body = ChatCompletionRequest.model_validate(raw_body)
    except Exception as e:
        return Response(content=str(e), status_code=422)

    # Force non-streaming — proxy needs full response to dehash
    if body.stream:
        body = body.model_copy(update={"stream": False})

    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    conversation_id, is_new = _resolve_conversation_id(headers_dict, body)
    session = store.get_or_create(conversation_id)

    try:
        sanitized_body = _sanitize_request(body, session)
    except Exception:
        logger.exception("Presidio sanitization failed")
        return Response(
            content='{"error": "PII sanitization failed"}',
            status_code=500,
            media_type="application/json",
        )

    sanitized_dict = sanitized_body.model_dump(exclude_none=True)
    logger.debug("Sanitized request: %s", sanitized_dict)

    # Forward to remote LLM
    forward_headers = {}
    if "authorization" in headers_dict:
        forward_headers["Authorization"] = headers_dict["authorization"]
    forward_headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            upstream_resp = await client.post(
                f"{settings.remote_llm_base_url}/chat/completions",
                json=sanitized_dict,
                headers=forward_headers,
            )
        except httpx.RequestError as e:
            logger.error("Upstream request failed: %s", e)
            return Response(
                content='{"error": "Failed to reach upstream LLM"}',
                status_code=502,
                media_type="application/json",
            )

    if upstream_resp.status_code != 200:
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            media_type="application/json",
        )

    try:
        resp_data = upstream_resp.json()
        completion = ChatCompletionResponse.model_validate(resp_data)
        completion = _desanitize_response(completion, session)
        resp_dict = completion.model_dump(exclude_none=True)
    except Exception:
        logger.exception("Failed to parse/dehash upstream response")
        resp_dict = upstream_resp.json()

    response_headers = {"X-Conversation-ID": conversation_id}
    return Response(
        content=ChatCompletionResponse.model_validate(resp_dict).model_dump_json(),
        status_code=200,
        media_type="application/json",
        headers=response_headers,
    )


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    raw_body = await request.json()
    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    conversation_id = headers_dict.get("x-conversation-id", str(uuid.uuid4()))
    session = store.get_or_create(conversation_id)

    # Sanitize input text
    if "input" in raw_body:
        inp = raw_body["input"]
        if isinstance(inp, str):
            raw_body["input"] = sanitize_text(inp, session, analyzer)
        elif isinstance(inp, list):
            raw_body["input"] = [
                sanitize_text(item, session, analyzer) if isinstance(item, str) else item
                for item in inp
            ]

    forward_headers = {"Content-Type": "application/json"}
    if "authorization" in headers_dict:
        forward_headers["Authorization"] = headers_dict["authorization"]

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            upstream_resp = await client.post(
                f"{settings.remote_llm_base_url}/embeddings",
                json=raw_body,
                headers=forward_headers,
            )
        except httpx.RequestError:
            return Response(content='{"error": "Failed to reach upstream LLM"}', status_code=502, media_type="application/json")

    return Response(content=upstream_resp.content, status_code=upstream_resp.status_code, media_type="application/json")


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def passthrough(request: Request, path: str):
    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    forward_headers = {"Content-Type": headers_dict.get("content-type", "application/json")}
    if "authorization" in headers_dict:
        forward_headers["Authorization"] = headers_dict["authorization"]

    body = await request.body()
    url = f"{settings.remote_llm_base_url}/{path}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            upstream_resp = await client.request(
                method=request.method,
                url=url,
                content=body if body else None,
                headers=forward_headers,
            )
        except httpx.RequestError:
            return Response(content='{"error": "Failed to reach upstream"}', status_code=502, media_type="application/json")

    return Response(content=upstream_resp.content, status_code=upstream_resp.status_code, media_type="application/json")
