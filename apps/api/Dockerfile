# The platform API. Build from the repository root:
#   docker build -f apps/api/Dockerfile -t firstpr-api .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY packages/platform /app/packages/platform
COPY apps/api /app/apps/api
RUN pip install /app/packages/platform /app/apps/api \
    && useradd --create-home --uid 10001 firstpr

USER firstpr
EXPOSE 8000
# Apply database migrations, then start the API.
CMD ["sh", "-c", "python -m firstpr_platform.migrate && exec uvicorn --factory firstpr_api.main:create_app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
