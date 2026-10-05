# The platform worker. Build from the repository root:
#   docker build -f apps/worker/Dockerfile -t firstpr-worker .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# The engine (the firstpr package, built from packages/core), the shared platform
# code, and the worker itself.
COPY pyproject.toml README.md LICENSE CHANGELOG.md /app/
COPY packages /app/packages
COPY apps/worker /app/apps/worker
RUN pip install /app /app/packages/platform /app/apps/worker \
    && useradd --create-home --uid 10001 firstpr

USER firstpr
CMD ["arq", "firstpr_worker.main.WorkerSettings"]
