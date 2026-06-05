.PHONY: install test run

install:
	uv sync

test:
	uv run pytest tests/ -v

run:
	uv run uvicorn pii_proxy.main:app --host 0.0.0.0 --port 8001
