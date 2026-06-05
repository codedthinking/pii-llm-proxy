import json
import logging
import uuid

from fastapi import FastAPI, Request, Response

from .config import settings
from .llm import get_client
from .models import ChatCompletionRequest, ContentPart
from .pii import SYSTEM_NOTICE, get_anonymizer
from .session import SessionStore

logger = logging.getLogger("pii_proxy")
logging.basicConfig(level=logging.DEBUG)

app = FastAPI(title="PII Sanitizing LLM Proxy")
store = SessionStore()


def _get_auth_header(headers_dict: dict[str, str]) -> str | None:
    """Return auth header from client request, falling back to configured API key."""
    if "authorization" in headers_dict:
        return headers_dict["authorization"]
    if settings.openrouter_api_key:
        return f"Bearer {settings.openrouter_api_key}"
    return None


def _resolve_conversation_id(request_headers: dict[str, str], body: ChatCompletionRequest) -> tuple[str, bool]:
    """Return (conversation_id, is_new)."""
    cid = request_headers.get("x-conversation-id")
    if cid:
        return cid, False
    if body.messages and body.messages[-1].tool_call_id:
        return body.messages[-1].tool_call_id, False
    return str(uuid.uuid4()), True


def _sanitize_message_content(content: str | list[ContentPart] | None, session) -> str | list[ContentPart] | None:
    anonymizer = get_anonymizer()
    if content is None:
        return None
    if isinstance(content, str):
        return anonymizer.sanitize(content, session)
    sanitized_parts = []
    for part in content:
        if part.type == "text" and part.text is not None:
            new_part = part.model_copy(update={"text": anonymizer.sanitize(part.text, session)})
            sanitized_parts.append(new_part)
        else:
            sanitized_parts.append(part)
    return sanitized_parts


def _sanitize_request(body: ChatCompletionRequest, session) -> ChatCompletionRequest:
    sanitized_messages = []
    for msg in body.messages:
        new_content = _sanitize_message_content(msg.content, session)
        sanitized_messages.append(msg.model_copy(update={"content": new_content}))

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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    raw_body = await request.json()
    try:
        body = ChatCompletionRequest.model_validate(raw_body)
    except Exception as e:
        return Response(content=str(e), status_code=422)

    client_wants_stream = body.stream
    if client_wants_stream:
        body = body.model_copy(update={"stream": False})

    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    conversation_id, is_new = _resolve_conversation_id(headers_dict, body)
    session = store.get_or_create(conversation_id)

    try:
        sanitized_body = _sanitize_request(body, session)
    except Exception:
        logger.exception("PII sanitization failed")
        return Response(
            content='{"error": "PII sanitization failed"}',
            status_code=500,
            media_type="application/json",
        )

    sanitized_dict = sanitized_body.model_dump(exclude_none=True)
    logger.debug("Sanitized request: %s", sanitized_dict)

    auth = _get_auth_header(headers_dict)
    llm = get_client()

    try:
        status_code, raw_text = await llm.chat_completion(sanitized_dict, auth)
    except Exception as e:
        logger.error("Upstream request failed: %s", e)
        return Response(
            content='{"error": "Failed to reach upstream LLM"}',
            status_code=502,
            media_type="application/json",
        )

    if status_code != 200:
        logger.error("Upstream returned %d: %s", status_code, raw_text[:500])
        return Response(
            content=raw_text,
            status_code=status_code,
            media_type="application/json",
        )

    logger.debug("Upstream response: %s", raw_text[:500])
    anonymizer = get_anonymizer()
    desanitized_text = anonymizer.desanitize(raw_text, session)
    logger.debug("Desanitized response: %s", desanitized_text[:500])

    response_headers = {"X-Conversation-ID": conversation_id}

    if client_wants_stream:
        resp_data = json.loads(desanitized_text)
        chunk = {
            "id": resp_data.get("id", ""),
            "object": "chat.completion.chunk",
            "created": resp_data.get("created", 0),
            "model": resp_data.get("model", ""),
        }
        for key in ("provider", "system_fingerprint", "service_tier"):
            if key in resp_data:
                chunk[key] = resp_data[key]
        chunk["choices"] = []
        for choice in resp_data.get("choices", []):
            msg = choice.get("message", {})
            chunk_choice = {
                "index": choice.get("index", 0),
                "delta": msg,
                "finish_reason": choice.get("finish_reason"),
            }
            for key in choice:
                if key not in ("index", "message", "finish_reason"):
                    chunk_choice[key] = choice[key]
            chunk["choices"].append(chunk_choice)
        if "usage" in resp_data:
            chunk["usage"] = resp_data["usage"]
        chunk_json = json.dumps(chunk, ensure_ascii=False)
        sse_body = f"data: {chunk_json}\n\ndata: [DONE]\n\n"
        return Response(
            content=sse_body,
            status_code=200,
            media_type="text/event-stream",
            headers=response_headers,
        )

    return Response(
        content=desanitized_text,
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

    anonymizer = get_anonymizer()
    if "input" in raw_body:
        inp = raw_body["input"]
        if isinstance(inp, str):
            raw_body["input"] = anonymizer.sanitize(inp, session)
        elif isinstance(inp, list):
            raw_body["input"] = [
                anonymizer.sanitize(item, session) if isinstance(item, str) else item
                for item in inp
            ]

    auth = _get_auth_header(headers_dict)
    llm = get_client()

    try:
        status_code, content = await llm.embeddings(raw_body, auth)
    except Exception:
        return Response(content='{"error": "Failed to reach upstream LLM"}', status_code=502, media_type="application/json")

    return Response(content=content, status_code=status_code, media_type="application/json")


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def passthrough(request: Request, path: str):
    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    forward_headers = {"Content-Type": headers_dict.get("content-type", "application/json")}
    auth = _get_auth_header(headers_dict)
    if auth:
        forward_headers["Authorization"] = auth

    body = await request.body()
    llm = get_client()

    try:
        status_code, content = await llm.passthrough(
            method=request.method,
            path=path,
            body=body if body else None,
            headers=forward_headers,
        )
    except Exception:
        return Response(content='{"error": "Failed to reach upstream"}', status_code=502, media_type="application/json")

    return Response(content=content, status_code=status_code, media_type="application/json")
