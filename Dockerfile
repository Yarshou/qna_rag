FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8 AS builder

ENV POETRY_VERSION=2.3.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /qna_rag

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root


FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/qna_rag/.venv/bin:${PATH}"

WORKDIR /qna_rag

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=builder /qna_rag/.venv /qna_rag/.venv
COPY app ./app
COPY knowledge ./knowledge

RUN mkdir -p /qna_rag/app/data \
    && chmod -R a+rX /qna_rag/app /qna_rag/knowledge \
    && chown -R app:app /qna_rag

USER app

EXPOSE 8000

CMD exec gunicorn app.config.app:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers "${APP_WORKERS:-1}" \
    --timeout 120
