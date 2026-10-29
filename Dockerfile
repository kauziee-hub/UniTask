# UniTask: one image serving the React app and the FastAPI API from the same origin.
# Build from the repository root:  docker build -t unitask .

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt backend/requirements-aws.txt ./
RUN pip install --no-cache-dir -r requirements-aws.txt
COPY backend/ ./
COPY --from=web /web/dist ./static
RUN useradd --create-home --uid 10001 unitask && mkdir -p /app/uploads && chown -R unitask /app
USER unitask
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1
# Migrations run on startup (RUN_MIGRATIONS=true by default). One worker: jobs run in-process.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
