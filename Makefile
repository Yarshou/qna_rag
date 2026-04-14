IMAGE_NAME ?= qna-rag
IMAGE_TAG  ?= latest
APP_MODULE ?= app.config.app:app
HOST ?= 0.0.0.0
PORT ?= 8000
ENV_FILE ?= app/envs/.env

.PHONY: install
install:
	poetry install --with dev

.PHONY: run
run:
	poetry run uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT)

.PHONY: test
test:
	poetry run pytest

.PHONY: lint
lint:
	poetry run ruff check .

.PHONY: format
format:
	poetry run ruff format .
	poetry run isort .

.PHONY: docker-build
docker-build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

.PHONY: docker-build-multiarch
docker-build-multiarch:
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		--tag $(IMAGE_NAME):$(IMAGE_TAG) \
		--push \
		.

.PHONY: docker-run
docker-run:
	docker run --rm --env-file $(ENV_FILE) -p $(PORT):8000 $(IMAGE_NAME):$(IMAGE_TAG)
