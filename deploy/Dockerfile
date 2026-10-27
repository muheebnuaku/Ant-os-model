# ANT-OS Ω platform image (API and worker). Build from the repository root:
#   docker build -f deploy/Dockerfile -t antos-api .
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN uv sync --locked --no-dev --package antos-api

FROM python:3.13-slim
RUN useradd --system --uid 10001 antos
WORKDIR /app
COPY --from=build /app /app
COPY profiles ./profiles
ENV PATH="/app/.venv/bin:$PATH" ANTOS_PROFILE_DIR=/app/profiles/africa
USER antos
EXPOSE 8000
CMD ["uvicorn", "antos_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
