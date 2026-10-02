# Two stages: build the dashboard with Node, then install the Python package
# (with the dashboard inside it) on a slim Python image.

FROM node:22-slim AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# The dashboard reads brand.json and the demo fixtures from the Python package.
COPY src/issueradar/brand.json /build/src/issueradar/brand.json
COPY src/issueradar/demo/fixtures/demo.json /build/src/issueradar/demo/fixtures/demo.json
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FIRSTPR_DB_URL=sqlite:////data/firstpr.sqlite
WORKDIR /app
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
COPY --from=web /build/web/dist ./src/issueradar/web
RUN pip install . \
    && useradd --create-home --uid 10001 radar \
    && mkdir /data \
    && chown radar /data
USER radar
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)"
# 0.0.0.0 inside the container; publish the port to 127.0.0.1 on the host (see compose file).
CMD ["firstpr", "serve", "--host", "0.0.0.0", "--port", "8765"]
