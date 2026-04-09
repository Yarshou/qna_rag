FROM python:3.13.12-slim AS builder

ENV POETRY_VERSION=2.3.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /qna_rag

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root


FROM python:3.13.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/qna_rag/.venv/bin:${PATH}"

WORKDIR /qna_rag

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=builder /qna_rag/.venv /qna_rag/.venv
COPY app ./app
COPY knowledge ./knowledge

RUN mkdir -p /qna_rag/app/data && chown -R app:app /qna_rag

USER app

EXPOSE 8000

CMD ["uvicorn", "app.config.app:app", "--host", "0.0.0.0", "--port", "8000"]
