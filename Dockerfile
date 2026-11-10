# Stage 1: the website
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: the server. poppler-utils gives pdftotext, which the DPR import needs.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY rules ./rules
COPY data/catalog.db ./data/catalog.db
RUN uv sync --frozen --no-dev   # editable, so the code finds rules/ and data/ next to src/
COPY --from=web /web/dist ./web/dist
CMD ["uv", "run", "--no-sync", "gatorpath-web"]
