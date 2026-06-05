import json
import logging
import uuid

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from .config import settings
from .pii import SYSTEM_NOTICE, get_anonymizer
from .session import SessionStore

logger = logging.getLogger("pii_proxy")
logging.basicConfig(level=logging.DEBUG)

app = FastAPI(title="PII Sanitizing LLM Proxy")
store = SessionStore()

# Headers that must not be forwarded between client and upstream.
_HOP_BY_HOP = frozenset({
    "host", "connection", "keep-alive", "transfer-encoding",
    "te", "trailer", "upgrade", "content-length",
})


def _forward_headers(raw_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Build upstream headers by forwarding everything except hop-by-hop.

    If the client doesn't send an Authorization header, injects the
    configured upstream_api_key as a Bearer token (if set).
    """
    out: dict[str, str] = {}
    for name_b, value_b in raw_headers:
        name = name_b.decode("latin-1").lower()
        if name in _HOP_BY_HOP:
            continue
        out[name] = value_b.decode("latin-1")
    if "authorization" not in out and settings.upstream_api_key:
        out["authorization"] = f"Bearer {settings.upstream_api_key}"
    return out


def _resolve_conversation_id(headers: dict[str, str]) -> str:
    return headers.get("x-conversation-id", str(uuid.uuid4()))


def _sanitize_messages_in_place(body: dict, session) -> None:
    """Walk messages and sanitize text content in place."""
    anonymizer = get_anonymizer()
    messages = body.get("messages")
    if not messages:
        return
    for msg in messages:
        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            msg["content"] = anonymizer.sanitize(content, session)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                    part["text"] = anonymizer.sanitize(part["text"], session)


def _inject_system_notice(body: dict, session) -> None:
    """Prepend system notice about synthetic PII if not already injected."""
    if not settings.inject_system_notice or session.system_notice_injected:
        return
    messages = body.get("messages", [])
    if messages and messages[0].get("role") == "system":
        first = messages[0]
        if isinstance(first.get("content"), str):
            first["content"] = SYSTEM_NOTICE + "\n\n" + first["content"]
        else:
            first["content"] = SYSTEM_NOTICE
    else:
        messages.insert(0, {"role": "system", "content": SYSTEM_NOTICE})
    session.system_notice_injected = True


async def _forward_non_streaming(
    body: dict, headers: dict[str, str], path: str,
) -> Response:
    """Forward request and return the complete response."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.upstream_base_url}/{path}",
            content=json.dumps(body, ensure_ascii=False).encode(),
            headers=headers,
        )
    return resp.status_code, resp.text, resp.headers


async def _stream_with_desanitization(body: dict, session, headers: dict[str, str]):
    """Stream SSE chunks from upstream, desanitizing text content on the fly.

    Uses a buffer to handle fake values that may span chunk boundaries.
    Only emits text that is "settled" — i.e., cannot be part of a partial
    fake value match. Flushes the remainder on stream end.
    """
    anonymizer = get_anonymizer()

    # Accumulated raw content text from all chunks so far
    raw_buffer = ""
    # How many characters of desanitized output we have already emitted
    emitted_len = 0

    def _max_fake_len() -> int:
        if not session.fake_to_real:
            return 0
        return max(len(f) for f in session.fake_to_real)

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.upstream_base_url}/chat/completions",
            content=json.dumps(body, ensure_ascii=False).encode(),
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                # Non-200: read full body and yield as-is
                body_bytes = await resp.aread()
                yield body_bytes
                return

            async for raw_line in resp.aiter_lines():
                if not raw_line.startswith("data: "):
                    # Forward non-data lines (empty lines, comments) as-is
                    yield raw_line + "\n"
                    continue

                payload = raw_line[6:]

                if payload.strip() == "[DONE]":
                    # Flush remaining buffer
                    if raw_buffer:
                        desanitized_full = anonymizer.desanitize(raw_buffer, session)
                        remaining = desanitized_full[emitted_len:]
                        if remaining:
                            # We need to emit a final content chunk with the remaining text.
                            # Reconstruct using the last seen chunk as template.
                            flush_chunk = {
                                "choices": [{"index": 0, "delta": {"content": remaining}}],
                            }
                            yield f"data: {json.dumps(flush_chunk, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    yield raw_line + "\n"
                    continue

                # Extract content delta
                choices = chunk.get("choices", [])
                has_content = False
                is_finished = False
                for choice in choices:
                    delta = choice.get("delta", {})
                    content = delta.get("content")
                    if choice.get("finish_reason"):
                        is_finished = True
                    if content is not None:
                        has_content = True
                        raw_buffer += content

                if not has_content:
                    # Non-content chunk (role, tool_calls, etc.) — forward as-is
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    continue

                # Determine how much we can safely emit
                mfl = _max_fake_len()
                desanitized_full = anonymizer.desanitize(raw_buffer, session)

                if is_finished or mfl == 0:
                    safe_end = len(desanitized_full)
                else:
                    safe_end = max(0, len(desanitized_full) - mfl)

                delta_text = desanitized_full[emitted_len:safe_end]
                emitted_len = safe_end

                if delta_text:
                    # Replace content in the chunk with desanitized delta
                    for choice in chunk.get("choices", []):
                        if "delta" in choice and "content" in choice["delta"]:
                            choice["delta"]["content"] = delta_text
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                elif is_finished:
                    # Flush any remaining
                    remaining = desanitized_full[emitted_len:]
                    if remaining:
                        for choice in chunk.get("choices", []):
                            if "delta" in choice:
                                choice["delta"]["content"] = remaining
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                # If delta_text is empty and not finished, hold back (buffering)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        raw_body = await request.json()
    except Exception:
        return Response(content='{"error": "Invalid JSON"}', status_code=400, media_type="application/json")

    fwd_headers = _forward_headers(request.headers.raw)
    conversation_id = _resolve_conversation_id(
        {k.lower(): v for k, v in request.headers.items()}
    )
    session = store.get_or_create(conversation_id)

    try:
        _sanitize_messages_in_place(raw_body, session)
        _inject_system_notice(raw_body, session)
    except Exception:
        logger.exception("PII sanitization failed")
        return Response(
            content='{"error": "PII sanitization failed"}',
            status_code=500,
            media_type="application/json",
        )

    logger.debug("Sanitized request: %s", json.dumps(raw_body, ensure_ascii=False)[:500])
    response_headers = {"X-Conversation-ID": conversation_id}

    is_streaming = raw_body.get("stream", False)

    if is_streaming:
        return StreamingResponse(
            _stream_with_desanitization(raw_body, session, fwd_headers),
            media_type="text/event-stream",
            headers=response_headers,
        )

    # Non-streaming: forward, desanitize full response, return
    try:
        status_code, raw_text, upstream_headers = await _forward_non_streaming(
            raw_body, fwd_headers, "chat/completions",
        )
    except httpx.RequestError as e:
        logger.error("Upstream request failed: %s", e)
        return Response(
            content='{"error": "Failed to reach upstream LLM"}',
            status_code=502,
            media_type="application/json",
        )

    if status_code != 200:
        return Response(content=raw_text, status_code=status_code, media_type="application/json")

    anonymizer = get_anonymizer()
    desanitized = anonymizer.desanitize(raw_text, session)
    return Response(
        content=desanitized,
        status_code=200,
        media_type="application/json",
        headers=response_headers,
    )


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def passthrough(request: Request, path: str):
    """Pure byte-level passthrough — no PII processing."""
    fwd_headers = _forward_headers(request.headers.raw)
    body = await request.body()
    url = f"{settings.upstream_base_url}/{path}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=url,
                content=body if body else None,
                headers=fwd_headers,
            )
        except httpx.RequestError:
            return Response(
                content='{"error": "Failed to reach upstream"}',
                status_code=502,
                media_type="application/json",
            )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
