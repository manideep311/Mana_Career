FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_LINK_MODE=copy
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
ENV UV_COMPILE_BYTECODE=1
# Dependency layer only — no project, no dev group (cached until pyproject/lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
# App source
COPY . .
RUN useradd --system --uid 10001 app && chown -R app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app ENV=prod
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
