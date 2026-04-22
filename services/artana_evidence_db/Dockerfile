FROM python:3.13.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONPATH=/app \
    GRAPH_SERVICE_HOST=0.0.0.0 \
    GRAPH_SERVICE_PORT=8080 \
    GRAPH_SERVICE_RELOAD=0

# Pull latest Debian security patches at build time so Trivy container
# scans pick up upstream OpenSSL/libssl fixes (e.g. CVE-2026-28390)
# without waiting for the python:slim tag to be rebuilt downstream.
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system artana \
    && useradd --system --gid artana --create-home artana

WORKDIR /app

COPY services/artana_evidence_db/requirements.txt /tmp/artana_evidence_db_requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/artana_evidence_db_requirements.txt

COPY services/artana_evidence_db ./artana_evidence_db
COPY src ./src

FROM base AS test

COPY services/artana_evidence_db/requirements-dev.txt /tmp/artana_evidence_db_requirements_dev.txt
COPY services/artana_evidence_db/Dockerfile ./services/artana_evidence_db/Dockerfile
COPY services/artana_evidence_db/requirements.txt ./services/artana_evidence_db/requirements.txt
COPY services/artana_evidence_db/requirements-dev.txt ./services/artana_evidence_db/requirements-dev.txt
COPY .dockerignore ./.dockerignore
COPY AGENTS.md ./AGENTS.md
COPY README.md ./README.md
COPY Makefile ./Makefile
COPY architecture_overrides.json ./architecture_overrides.json
COPY pytest.ini ./pytest.ini
COPY docker-compose.postgres.yml ./docker-compose.postgres.yml
COPY .env.postgres.example ./.env.postgres.example
COPY docs ./docs
COPY scripts ./scripts

RUN mkdir -p /app/venv/bin \
    && ln -sf /usr/local/bin/alembic /app/venv/bin/alembic \
    && pip install -r /tmp/artana_evidence_db_requirements_dev.txt

CMD ["pytest", "artana_evidence_db/tests/unit", "-q"]

FROM base AS runtime

RUN rm -rf /app/artana_evidence_db/tests

RUN chown -R artana:artana /app

USER artana

EXPOSE 8080

CMD ["python", "-m", "artana_evidence_db"]
