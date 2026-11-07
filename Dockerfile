# Runs the API (and the CLI) with the models cached in the image's own volume.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    RFP_STATE_DIR=/data/var \
    RFP_TRACES_DIR=/data/traces \
    RFP_MODEL_CACHE_DIR=/data/models \
    RFP_DATA_DIR=/data/bids \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

WORKDIR /app

# Dependencies first, so source edits do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY config ./config
COPY src ./src
RUN uv sync --frozen --no-dev

VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["uv", "run", "--no-sync", "rfp"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
