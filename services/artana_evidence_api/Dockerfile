FROM python:3.13.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONPATH=/app \
    ARTANA_EVIDENCE_API_SERVICE_HOST=0.0.0.0 \
    ARTANA_EVIDENCE_API_SERVICE_PORT=8080 \
    ARTANA_EVIDENCE_API_SERVICE_RELOAD=0

RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system artana \
    && useradd --system --gid artana --create-home artana

WORKDIR /app

COPY services/artana_evidence_api/requirements.txt /tmp/artana_evidence_api_requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/artana_evidence_api_requirements.txt

COPY services/artana_evidence_api/requirements-dev.txt /tmp/artana_evidence_api_requirements_dev.txt
COPY services/artana_evidence_api ./artana_evidence_api

FROM base AS test

COPY services/artana_evidence_api/Dockerfile ./services/artana_evidence_api/Dockerfile
COPY services/artana_evidence_api/requirements.txt ./services/artana_evidence_api/requirements.txt
COPY services/artana_evidence_api/requirements-dev.txt ./services/artana_evidence_api/requirements-dev.txt
COPY services/artana_evidence_db/openapi.json ./services/artana_evidence_db/openapi.json
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
    && pip install -r /tmp/artana_evidence_api_requirements_dev.txt

CMD ["pytest", "artana_evidence_api/tests/unit", "artana_evidence_api/tests/integration", "-q"]

FROM base AS runtime

RUN rm -rf /app/artana_evidence_api/tests \
    && find /app -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /app -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.db' \) -delete

RUN chown -R artana:artana /app

USER artana

EXPOSE 8080

CMD ["python", "-m", "artana_evidence_api"]
