# One image: the web app is built in a Node stage, then served by the API with the CLI.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM python:3.12-slim

# OpenCV (used by the OCR engine for scanned pages) needs these two system libraries.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    RFP_STATE_DIR=/data/var \
    RFP_TRACES_DIR=/data/traces \
    RFP_OUTPUTS_DIR=/data/outputs \
    RFP_MODEL_CACHE_DIR=/data/models \
    RFP_DATA_DIR=/data/bids \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

WORKDIR /app

# Dependencies first, so source edits do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY config ./config
COPY src ./src
COPY main.py ./
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

ENTRYPOINT ["uv", "run", "--no-sync", "rfp"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
