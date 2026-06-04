FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_lg
COPY . .
ENV REMOTE_LLM_BASE_URL=http://host.docker.internal:8000/v1
EXPOSE 8001
CMD ["uvicorn", "pii_proxy.main:app", "--host", "0.0.0.0", "--port", "8001"]
