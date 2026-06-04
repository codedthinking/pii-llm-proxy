.PHONY: install test run

install:
	uv pip install -r requirements.txt
	python -m spacy download en_core_web_lg

test:
	uv run pytest tests/ -v

run:
	uv run uvicorn pii_proxy.main:app --host 0.0.0.0 --port 8001
