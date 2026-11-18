FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_PATH=/opt/models

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download the embedding model at build time so containers start fast and work offline.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBEDDING_MODEL}')"

COPY app ./app
COPY data ./data

RUN useradd --system --uid 10001 --home-dir /app appuser \
    && mkdir -p /app/storage/claims /app/storage/chroma \
    && chown -R appuser:appuser /app/storage /opt/models

# From here on the model is cached: never reach out to the network for it.
ENV HF_HUB_OFFLINE=1 \
    CLAIMS_FILE_PATH=/app/storage/claims/mock_claims.json \
    CHROMA_PATH=/app/storage/chroma

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request as u,sys; sys.exit(0 if u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8000/api/v1/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
