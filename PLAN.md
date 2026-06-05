# Refactor: Transparent OpenAI-compatible reverse proxy

## Context

The proxy should behave as a transparent OpenAI-compatible provider — the only thing it does is sanitize PII on the way in and desanitize on the way out. Everything else passes through untouched: auth headers, model field, streaming, response format, error codes, all body fields.

Currently the proxy makes several opinionated choices that break transparency:
1. **Forces `stream=False` upstream** then fake-converts to SSE — breaks real streaming, adds latency
2. **Parses requests into Pydantic models** then re-serializes with `model_dump(exclude_none=True)` — can drop fields
3. **Has LlmClient ABC with litellm backend** — unnecessary abstraction for a reverse proxy
4. **Falls back to configured API key** — proxy shouldn't inject auth, just forward what the client sends
5. **Has separate endpoint handlers** for chat/embeddings/passthrough — should be one transparent proxy

The goal: configure this as a provider in opencode.ai or any AI SDK client via `@ai-sdk/openai-compatible` with `baseURL` pointing at the proxy. Auth, model, streaming — all controlled by the client.

## Design

### Pure reverse proxy with httpx

Replace the multi-endpoint, multi-backend architecture with a single transparent reverse proxy:

1. **One catch-all endpoint**: `/{path:path}` — forwards everything to `{upstream_base_url}/{path}`
2. **Chat completions gets special treatment**: parse just enough JSON to find message text → sanitize → re-serialize → forward
3. **All headers forwarded** transparently (Authorization, Content-Type, Accept, etc.) — proxy adds nothing
4. **Streaming handled natively**: if client sends `stream: true`, forward `stream: true` upstream and pipe SSE chunks back, desanitizing each chunk's text content as it flows through

### Streaming desanitization

The hard part. Fake values (e.g. "Sarah Johnson") may span SSE chunk boundaries. Solution: **buffered desanitization**.

For each streaming response:
1. Parse SSE `data:` lines, extract `choices[].delta.content` text
2. Accumulate raw text in a buffer
3. The "settled" prefix is `buffer[:-max_fake_len]` — no fake value can start in the settled region and extend beyond it
4. Desanitize only the settled prefix, emit the delta since last emission
5. On `finish_reason` or `[DONE]`, flush and desanitize the remainder

This adds latency of ~20-30 characters (max fake value length), negligible for streaming UX.

### Request sanitization without Pydantic

Work directly with raw JSON dicts to avoid any field loss:
- Parse request body as `dict`
- Walk `messages[].content` (string or list of content parts) → sanitize text in place
- Re-serialize and forward

### What to remove

- `pii_proxy/llm/` package entirely (client ABC, httpx_client, litellm_client)
- `litellm` dependency
- `pii_proxy/models.py` (Pydantic request/response models — no longer needed for proxy)
- `llm_client_backend` config setting
- `openrouter_api_key` config setting (auth is the client's responsibility)
- The fake SSE conversion code in main.py
- Separate embeddings endpoint (handled by generic passthrough)

### What to keep

- `pii_proxy/pii/` package (detector, anonymizer) — unchanged
- `pii_proxy/session.py` — unchanged
- `pii_proxy/config.py` — simplified (just `upstream_base_url`, `session_ttl_seconds`, `inject_system_notice`)
- `sanitizer.py` / `desanitizer.py` thin wrappers — keep for backward compat of tests

## File changes

```
pii_proxy/
    config.py          # simplify: upstream_base_url, session_ttl, inject_system_notice
    main.py            # rewrite: transparent reverse proxy with streaming support
    models.py          # delete (or keep minimal if tests import from it)
    sanitizer.py       # keep (thin wrapper)
    desanitizer.py     # keep (thin wrapper)
    session.py         # unchanged
    pii/               # unchanged
    llm/               # delete entirely
```

## New main.py structure

```python
# Pseudocode
@app.api_route("/v1/chat/completions", methods=["POST"])
async def chat_completions(request: Request):
    raw_body = await request.json()
    session = get_or_create_session(request.headers)
    sanitize_messages_in_place(raw_body, session)
    inject_system_notice(raw_body, session)

    is_streaming = raw_body.get("stream", False)

    if is_streaming:
        return StreamingResponse(
            stream_with_desanitization(raw_body, session, request.headers),
            media_type="text/event-stream"
        )
    else:
        status, text = await forward_and_receive(raw_body, request.headers)
        desanitized = anonymizer.desanitize(text, session)
        return Response(content=desanitized, status_code=status)

@app.api_route("/v1/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def passthrough(request: Request):
    # Pure byte-level passthrough, no PII processing
    ...
```

## Updated tests

- `test_stream_forced_to_false` → replace with `test_stream_passed_through` (verify stream=true is forwarded as-is and SSE is returned)
- Add test for streaming desanitization (mock upstream returns SSE chunks with fake values, verify client receives real values)
- Existing sanitization/desanitization unit tests unchanged

## Verification

- `make test` passes
- Configure in opencode: `baseURL: http://localhost:8001/v1`, send requests with any model, verify transparent passthrough
- Test streaming: send `stream: true`, verify real SSE chunks flow through with PII restored
