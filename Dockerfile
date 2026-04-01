FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm

WORKDIR /app

RUN groupadd --gid 1000 matcher && \
    useradd --uid 1000 --gid matcher --shell /bin/bash --create-home matcher

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY alembic.ini ./
COPY migrations ./migrations
COPY configs ./configs

RUN chown -R matcher:matcher /app
USER matcher

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "matcher.main:app", "--host", "0.0.0.0", "--port", "8000"]
