MYDIR ?= .

PROJECT_NAME := qna-rag

DEPS_FILES := \
    pyproject.toml \
    poetry.lock

.PHONY: lint-format
lint-format:
	poetry run ruff format
	poetry run ruff check --fix
	poetry run isort .

.PHONY: run
run:
	docker compose --env-file envs/.env -f docker-compose.yml up --build -d

.PHONY: stop
stop:
	docker compose down
