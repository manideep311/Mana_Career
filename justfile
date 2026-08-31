set shell := ["bash", "-uc"]

install:
    cd backend && uv sync
    cd frontend && pnpm install

lint:
    cd backend && uv run ruff check . && uv run lint-imports
    cd frontend && pnpm lint

typecheck:
    cd backend && uv run mypy app
    cd frontend && pnpm exec tsc --noEmit

test:
    cd backend && uv run pytest
    cd frontend && pnpm test run

ci: lint typecheck test

up:
    docker compose up --build -d

down:
    docker compose down -v

migrate:
    cd backend && uv run alembic upgrade head

smoke:
    ./scripts/smoke.sh
