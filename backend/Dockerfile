FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_LINK_MODE=copy
# Apply Debian security fixes published since the base image was built (the
# image scan in CI fails on fixable HIGH/CRITICAL findings).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app

FROM base AS dev
# Dependency layer (cached until pyproject/lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS prod
# No download cache in the shipped image: it only adds size.
ENV UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1
# Dependency layer only — no project, no dev group (cached until pyproject/lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
# The local embedding model (EMBEDDINGS_PROVIDER=local, about 67 MB) ships in
# the image: a cold start reads it from disk, and HF_HUB_OFFLINE below stops
# any attempt to fetch it at run time.
ARG LOCAL_EMBED_MODEL=BAAI/bge-small-en-v1.5
ENV FASTEMBED_CACHE_PATH=/opt/models
RUN /app/.venv/bin/python -c "import sys; from fastembed import TextEmbedding; TextEmbedding(sys.argv[1])" "$LOCAL_EMBED_MODEL"
# App source
COPY . .
RUN useradd --system --uid 10001 app && mkdir -p /app/var/files && chown -R app /app /opt/models
USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app ENV=prod HF_HUB_OFFLINE=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
