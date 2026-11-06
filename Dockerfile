# One container runs both parts of QueryWise: the Express API (which also serves the React UI)
# and the Python generation service, which listens only on localhost inside the container.

# ---- 1. Build the React UI ----
FROM node:24-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- 2. Install the API's production packages ----
FROM node:24-slim AS api
WORKDIR /app/api
COPY api/package.json api/package-lock.json ./
RUN npm ci --omit=dev

# ---- 3. Final image: Python, plus the Node runtime copied in ----
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GEN_SERVICE_URL=http://127.0.0.1:8000 \
    SERVE_WEB=true \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    NODE_OPTIONS=--max-old-space-size=128

RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY gen-service/requirements.txt gen-service/requirements.txt
RUN pip install -r gen-service/requirements.txt

# Download the embedding model while building, so a waking container only loads it from disk.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/gen-service/.model_cache')"

COPY db/ db/
COPY gen-service/ gen-service/
COPY api/package.json api/
COPY api/src/ api/src/
COPY --from=api /app/api/node_modules api/node_modules
COPY --from=web /app/web/dist web/dist
COPY start.sh ./
RUN chmod +x start.sh

CMD ["./start.sh"]