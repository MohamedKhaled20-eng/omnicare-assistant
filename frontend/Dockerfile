FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BACKEND_URL=http://backend:8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py client.py ./

RUN useradd --system --uid 10001 --home-dir /app appuser
USER appuser
EXPOSE 8501

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request as u,sys; sys.exit(0 if u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8501/_stcore/health', timeout=3).status == 200 else 1)"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
