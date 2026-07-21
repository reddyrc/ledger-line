# syntax=docker/dockerfile:1

# ---- Frontend build ----
FROM node:22-bookworm-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm install
COPY web/ ./
# Same-origin API when UI is served by FastAPI
ENV VITE_API_URL=/api/v1
RUN npm run build

# ---- Runtime ----
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DATABASE_PATH=/data/finance.db \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src ./src
COPY --from=web-build /web/dist ./web/dist

# Mount a Railway Volume at /data to persist the SQLite cache (do not use Docker VOLUME)

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn finance_app.main:app --host 0.0.0.0 --port ${PORT}"]
