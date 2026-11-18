.PHONY: install dev prod lint format format-check clean check-tools up down logs db db-reset migrate test-db test test-unit test-e2e test-down

check-tools:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "uv no esta instalado. Instalalo aqui: https://docs.astral.sh/uv/getting-started/installation/"; \
		exit 1; \
	fi

install: check-tools
	uv sync

# Aplica las migraciones pendientes y levanta la API (requiere Postgres: `make db`)
dev:
	uv run alembic upgrade head
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 3000

prod:
	uv run alembic upgrade head
	uv run uvicorn app.main:app --host 0.0.0.0 --port 3000

lint:
	uv run ruff check --fix app migrations

format:
	uv run ruff format app migrations

format-check:
	uv run ruff format --check app migrations

clean:
	rm -rf .venv dist .ruff_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

# --- Docker -----------------------------------------------------------------

# Levanta la API (modo dev) y PostgreSQL
up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

# Levanta solo PostgreSQL (para correr la API con `make dev` fuera de Docker)
db:
	docker compose up -d db

# Crea una migración nueva a partir de los modelos (con la API en Docker)
# Uso: make migrate name=agrega_campo_x
migrate:
	docker compose exec api alembic revision --autogenerate -m "$(name)"

# Borra la base de datos (elimina el volumen pgdata)
db-reset:
	docker compose down -v

# --- Tests ------------------------------------------------------------------

test-db:
	docker compose -f docker-compose.test.yml up -d --wait

test-unit:
	uv run pytest -m unit

test-e2e: test-db
	uv run pytest -m e2e

test: test-db
	uv run pytest

test-down:
	docker compose -f docker-compose.test.yml down -v
