set shell := ["bash", "-c"]

PORT := env("PORT", "8000")

configure:
	poetry run pre-commit install

install:
	poetry install --with dev

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

server:
	poetry run uvicorn app.server:app --host 0.0.0.0 --port {{PORT}}

worker:
	poetry run python -m app.worker

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps
