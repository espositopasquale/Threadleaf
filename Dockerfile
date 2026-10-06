FROM node:22-bookworm-slim AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="ThreadLeaf" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
ARG INSTALL_LAYOUT=false
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && if [ "$INSTALL_LAYOUT" = "true" ]; then apt-get install -y --no-install-recommends libgl1 libglib2.0-0; fi \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-layout.txt ./
RUN python -m pip install -r requirements.txt \
    && if [ "$INSTALL_LAYOUT" = "true" ]; then python -m pip install -r requirements-layout.txt; fi
COPY threadleaf/ ./threadleaf/
COPY scripts/ ./scripts/
COPY cli.py server.py ingest.py setup.py config.toml system_prompt.txt ./
COPY LICENSE COPYRIGHT README.md ./
COPY --from=web /build/web/public/ ./web/public/
RUN mkdir -p documents db state models
EXPOSE 4321
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "4321"]
