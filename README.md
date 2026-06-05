# PII LLM Proxy

A transparent reverse proxy that sits between your AI client and any OpenAI-compatible LLM provider. It sanitizes personally identifiable information (PII) in outgoing requests and restores original values in responses. The proxy is invisible to both the client and the upstream provider — it preserves all headers, body fields, streaming, auth, and model selection.

## How it works

1. Client sends a chat completion request to the proxy
2. Proxy detects PII (names, emails, phones, SSNs, credit cards, IBANs, dates) and replaces each with a consistent fake value using Faker
3. Sanitized request is forwarded to the upstream LLM provider
4. LLM response flows back through the proxy, which restores all fake values to originals
5. Client receives the response with real PII intact

Replacement is consistent within a session: the same real value always maps to the same fake value. This preserves coherence across multi-turn conversations.

Streaming is supported natively — SSE chunks flow through with buffered desanitization that handles fake values spanning chunk boundaries.

## Setup

Requires Python 3.13+.

```bash
# Install dependencies
uv sync

# Configure
cp .env.example .env
# Edit .env with your upstream URL and API key

# Run
make run
```

The proxy starts on `http://localhost:8001`.

### Configuration

Set these in `.env` or as environment variables:

| Variable | Default | Description |
|---|---|---|
| `UPSTREAM_BASE_URL` | `https://openrouter.ai/api/v1` | Base URL of the upstream LLM provider |
| `UPSTREAM_API_KEY` | (none) | Fallback API key for upstream, used when the client doesn't send an Authorization header |
| `SESSION_TTL_SECONDS` | `3600` | How long PII mappings are kept per conversation |
| `INJECT_SYSTEM_NOTICE` | `true` | Prepend a system message warning the LLM that values are synthetic |
| `PII_DETECTOR_BACKEND` | `regex` | PII detection algorithm (`regex`) |

### Authentication

The proxy passes the client's `Authorization` header through to the upstream provider. If the client sends no auth, the proxy injects `UPSTREAM_API_KEY` as a Bearer token. This lets you either:

- **Client-managed keys**: each client sends their own API key, proxy forwards it
- **Proxy-managed key**: configure `UPSTREAM_API_KEY` in `.env`, clients don't need to know the upstream key

## Using with OpenCode

Copy [`opencode.example.json`](opencode.example.json) to `opencode.json` in your project and adjust the model list as needed:

```json
{
  "provider": {
    "pii-proxy": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "PII Proxy",
      "options": {
        "baseURL": "http://localhost:8001/v1"
      },
      "models": {
        "minimax/minimax-m3": {
          "name": "Minimax M3 (PII Proxy)"
        },
        "xiaomi/mimo-v2.5": {
          "name": "Xiaomi MiMo v2.5 (PII Proxy)"
        },
        "moonshotai/kimi-k2.6": {
          "name": "Kimi K2.6 (PII Proxy)"
        },
        "google/gemma-4-26b-a4b-it:free": {
          "name": "Gemma 4 26B free (PII Proxy)"
        },
        "qwen/qwen3-235b-a22b-2507": {
          "name": "Qwen3 235B (PII Proxy)"
        },
        "deepseek/deepseek-v4-flash": {
          "name": "DeepSeek V4 Flash (PII Proxy)"
        },
        "anthropic/claude-sonnet-latest": {
          "name": "Claude Sonnet latest (PII Proxy)"
        },
        "openai/gpt-5.5": {
          "name": "GPT-5.5 (PII Proxy)"
        }
      }
    }
  }
}
```

Then run `/connect` in OpenCode, select "Other", enter `pii-proxy` as the provider ID, and supply your upstream API key (e.g., your OpenRouter key). Or set `UPSTREAM_API_KEY` in the proxy's `.env` and skip client-side auth.

Model IDs follow whatever naming the upstream provider uses. For OpenRouter, that is `provider/model` (e.g., `anthropic/claude-sonnet-latest`). The proxy does not interpret model names — it forwards them as-is. OpenCode does not auto-discover models from custom providers, so you must list them explicitly in `opencode.json`.

## Using with other AI SDK clients

Any client that supports OpenAI-compatible providers works. Point `baseURL` at `http://localhost:8001/v1` and use it like any other provider. The proxy is fully transparent: streaming, tool calls, function calling, vision — everything passes through.

## PII detection

The default `regex` detector finds:

- **Names** — runs of 2+ capitalized words where at least one is in a dictionary of ~4000 common names. Notable public figures (~44k from Wikipedia) are not masked.
- **Email addresses**
- **Phone numbers** — US and international formats
- **US Social Security Numbers**
- **Credit card numbers**
- **IBAN codes**
- **Dates** — YYYY-MM-DD and DD-MM-YYYY formats

The detector is pluggable via the `PiiDetector` abstract class in `pii_proxy/pii/detector.py`.

## Development

```bash
# Run tests
make test

# Run the proxy
make run
```

## Project structure

```
pii_proxy/
    main.py            # FastAPI reverse proxy
    config.py          # Settings from .env
    session.py         # Per-conversation PII mapping state
    sanitizer.py       # Thin wrapper (backward compat)
    desanitizer.py     # Thin wrapper (backward compat)
    pii/
        detector.py        # PiiDetector ABC, PiiEntity dataclass
        anonymizer.py      # PiiAnonymizer (Faker replacement, session mapping)
        regex_detector.py  # Regex + name-dictionary detector
        data/
            names.txt          # ~4000 common names
            notable_people.txt # ~44k public figures (not masked)
```

## License

MIT
