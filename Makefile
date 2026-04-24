# Extracted Artana Evidence Platform Makefile

VENV ?= venv
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip3
USE_PYTHON := $(if $(wildcard $(PYTHON)),$(PYTHON),python3)
USE_PYTHON_ABS := $(if $(findstring /,$(USE_PYTHON)),$(abspath $(USE_PYTHON)),$(USE_PYTHON))
ALEMBIC_BIN := $(if $(wildcard $(VENV)/bin/alembic),$(VENV)/bin/alembic,alembic)
BOOTSTRAP_PYTHON := $(strip $(shell command -v python3.13 || command -v python3))

POSTGRES_ENV_FILE := .env.postgres
POSTGRES_ENV_TEMPLATE := .env.postgres.example
POSTGRES_COMPOSE_FILE := docker-compose.postgres.yml
POSTGRES_SERVICE := postgres
POSTGRES_COMPOSE := docker compose --env-file $(POSTGRES_ENV_FILE) -f $(POSTGRES_COMPOSE_FILE)
POSTGRES_ACTIVE_FLAG := .postgres-active

GRAPH_SERVICE_PORT ?= 8090
ARTANA_EVIDENCE_API_PORT ?= 8091

BACKEND_DEV_JWT_SECRET ?= artana-platform-backend-jwt-secret-for-development-2026-01
BACKEND_DEV_JWT_ISSUER ?= artana-platform
ARTANA_EVIDENCE_API_BOOTSTRAP_KEY ?= artana-evidence-api-bootstrap-key-for-development-2026-03
AUTH_ALLOW_TEST_AUTH_HEADERS ?= 1
BACKEND_DEV_ENV := AUTH_JWT_SECRET=$(BACKEND_DEV_JWT_SECRET) GRAPH_JWT_SECRET=$(BACKEND_DEV_JWT_SECRET) GRAPH_JWT_ISSUER=$(BACKEND_DEV_JWT_ISSUER) ARTANA_EVIDENCE_API_BOOTSTRAP_KEY=$(ARTANA_EVIDENCE_API_BOOTSTRAP_KEY) AUTH_ALLOW_TEST_AUTH_HEADERS=$(AUTH_ALLOW_TEST_AUTH_HEADERS)

GRAPH_SERVICE_LINT_PATHS := \
 services/artana_evidence_db/ai_full_mode_models.py \
 services/artana_evidence_db/ai_full_mode_persistence_models.py \
 services/artana_evidence_db/ai_full_mode_service.py \
 services/artana_evidence_db/decision_confidence.py \
 services/artana_evidence_db/workflow_models.py \
 services/artana_evidence_db/workflow_persistence_models.py \
	 services/artana_evidence_db/graph_workflow_service.py \
	 services/artana_evidence_db/kernel_entity_errors.py \
	 services/artana_evidence_db/entity_service.py \
	 services/artana_evidence_db/kernel_entity_models.py \
	 services/artana_evidence_db/entity_repository.py \
	 services/artana_evidence_db/governance.py \
	 services/artana_evidence_db/governance_ports.py \
	 services/artana_evidence_db/_dictionary_relation_types.py \
	 services/artana_evidence_db/alembic \
	 services/artana_evidence_db/__main__.py \
 services/artana_evidence_db/config.py \
 services/artana_evidence_db/database.py \
 services/artana_evidence_db/manage.py \
 services/artana_evidence_db/graph_api_schemas/ai_full_mode_schemas.py \
 services/artana_evidence_db/graph_api_schemas/workflow_schemas.py \
 services/artana_evidence_db/tests \
 services/artana_evidence_db/routers/ai_full_mode.py \
 services/artana_evidence_db/routers/workflows.py \
 services/artana_evidence_db/routers/claims.py \
	 services/artana_evidence_db/routers/entities.py \
	 services/artana_evidence_db/routers/relations.py \
	 scripts/export_graph_openapi.py \
	 tests/e2e/graph_service/test_user_flows.py

GRAPH_SERVICE_TYPE_PATHS := \
 services/artana_evidence_db \
 scripts/export_graph_openapi.py
GRAPH_SERVICE_TYPE_EXCLUDE := services/artana_evidence_db/(tests|alembic)/
ARTANA_EVIDENCE_API_TYPE_EXCLUDE := artana_evidence_api/(tests|alembic)/

GRAPH_SERVICE_TEST_PATHS := \
	 tests/e2e/graph_service \
	 services/artana_evidence_db/tests/unit \
	 services/artana_evidence_db/tests/integration

ARTANA_EVIDENCE_API_LINT_PATHS := \
 services/artana_evidence_api \
 scripts/export_artana_evidence_api_openapi.py \
 scripts/validate_artana_evidence_api_service_boundary.py \
 tests/e2e/artana_evidence_api

ARTANA_EVIDENCE_API_MYPY_FLAGS := \
 --show-error-codes \
 --follow-imports=skip \
 --disable-error-code no-any-unimported \
 --disable-error-code no-any-return \
 --disable-error-code misc \
 --disable-error-code untyped-decorator \
 --disable-error-code no-untyped-def \
 --disable-error-code arg-type \
 --disable-error-code attr-defined \
 --disable-error-code assignment \
 --disable-error-code unreachable \
 --disable-error-code has-type

ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS := \
 --show-error-codes

GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS := \
 --show-error-codes \
 --no-warn-unused-configs \
 --disable-error-code no-any-unimported \
 --disable-error-code no-any-return \
 --disable-error-code misc \
 --disable-error-code untyped-decorator

ARTANA_EVIDENCE_API_TEST_PATHS := \
 tests/e2e/artana_evidence_api \
 services/artana_evidence_api/tests/integration \
 services/artana_evidence_api/tests/unit

GRAPH_ALEMBIC_CONFIG := services/artana_evidence_db/alembic.ini
GRAPH_SERVICE_OPENAPI_OUTPUT := services/artana_evidence_db/openapi.json
ARTANA_EVIDENCE_API_OPENAPI_OUTPUT := services/artana_evidence_api/openapi.json
GRAPH_SERVICE_TS_TYPES_OUTPUT := services/artana_evidence_db/artana-evidence-db.generated.ts

define ensure_postgres_env
@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then \
 if [ -f "$(POSTGRES_ENV_TEMPLATE)" ]; then \
  cp "$(POSTGRES_ENV_TEMPLATE)" "$(POSTGRES_ENV_FILE)"; \
  echo "Created $(POSTGRES_ENV_FILE) from template."; \
 else \
  echo "Missing $(POSTGRES_ENV_TEMPLATE). Cannot create $(POSTGRES_ENV_FILE)."; \
  exit 1; \
 fi \
fi
endef

define run_with_postgres_env
$(call ensure_postgres_env)
@echo "Using Postgres env ($(POSTGRES_ENV_FILE))"
@/bin/bash -lc 'set -a; source "$(POSTGRES_ENV_FILE)"; set +a; $(1)'
endef

define check_venv
@if [ ! -x "$(PYTHON)" ]; then \
 echo "Local Python environment is not ready."; \
 echo "Create and install it with:"; \
 echo "  make install-dev"; \
 exit 1; \
fi
endef

.PHONY: help venv install-dev docker-postgres-up docker-postgres-down docker-postgres-destroy docker-postgres-logs docker-postgres-status postgres-wait graph-db-wait graph-db-migrate artana-evidence-api-db-wait artana-evidence-api-db-migrate init-artana-schema setup-postgres graph-service-openapi graph-service-client-types graph-service-sync-contracts graph-service-contract-check graph-service-boundary-check artana-evidence-api-openapi artana-evidence-api-contract-check artana-evidence-api-boundary-check graph-phase6-release-check graph-service-lint graph-service-type-check graph-service-type-check-strict-imports graph-service-test graph-service-checks artana-evidence-api-lint artana-evidence-api-type-check artana-evidence-api-type-check-strict-imports artana-evidence-api-test artana-evidence-api-service-checks type-hardening-baseline run-graph-service run-artana-evidence-api-service run-all

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_.-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-32s %s\n", $$1, $$2}'

venv: ## Create the local virtual environment
	@if [ -x "$(PYTHON)" ]; then echo "Virtual environment already exists at $(VENV)"; exit 0; fi
	@if [ -z "$(BOOTSTRAP_PYTHON)" ]; then echo "Python 3.13+ is required."; exit 1; fi
	$(BOOTSTRAP_PYTHON) -m venv $(VENV)

install-dev: venv ## Install runtime and development dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -e .[dev]
	$(PIP) install -r services/artana_evidence_db/requirements.txt
	$(PIP) install -r services/artana_evidence_api/requirements.txt
	$(PIP) install aiosqlite

docker-postgres-up: ## Start the local Postgres container
	$(call ensure_postgres_env)
	$(POSTGRES_COMPOSE) up -d
	@touch "$(POSTGRES_ACTIVE_FLAG)"

docker-postgres-down: ## Stop the local Postgres container
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then echo "No $(POSTGRES_ENV_FILE) found; nothing to stop."; exit 0; fi
	$(POSTGRES_COMPOSE) down && rm -f "$(POSTGRES_ACTIVE_FLAG)" || true

docker-postgres-destroy: ## Stop Postgres and remove volumes
	@if [ ! -f "$(POSTGRES_ENV_FILE)" ]; then echo "No $(POSTGRES_ENV_FILE) found; nothing to destroy."; exit 0; fi
	$(POSTGRES_COMPOSE) down -v && rm -f "$(POSTGRES_ACTIVE_FLAG)" || true

docker-postgres-logs: ## Tail Postgres logs
	$(call ensure_postgres_env)
	$(POSTGRES_COMPOSE) logs -f $(POSTGRES_SERVICE)

docker-postgres-status: ## Show Postgres container status
	$(call ensure_postgres_env)
	$(POSTGRES_COMPOSE) ps

postgres-wait: ## Wait until Postgres is ready
	$(call check_venv)
	$(call ensure_postgres_env)
	@if [ -z "$$($(POSTGRES_COMPOSE) ps -q $(POSTGRES_SERVICE))" ]; then \
		if /bin/bash -lc 'set -a; source "$(POSTGRES_ENV_FILE)"; set +a; $(USE_PYTHON) scripts/wait_for_postgres.py >/dev/null 2>&1'; then \
			echo "Detected reachable Postgres at DATABASE_URL; using existing instance."; \
		else \
			$(POSTGRES_COMPOSE) up -d $(POSTGRES_SERVICE); \
			touch "$(POSTGRES_ACTIVE_FLAG)"; \
		fi; \
	fi
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/wait_for_postgres.py)

graph-db-wait: ## Wait for the graph service database
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,PYTHONPATH="$(CURDIR)/services" GRAPH_DATABASE_URL="$$DATABASE_URL" $(USE_PYTHON) -m artana_evidence_db.manage wait-db)

graph-db-migrate: ## Run graph service migrations
	@$(MAKE) -s graph-db-wait
	$(call run_with_postgres_env,PYTHONPATH="$(CURDIR)/services" GRAPH_DATABASE_URL="$$DATABASE_URL" $(USE_PYTHON) -m artana_evidence_db.manage migrate)

artana-evidence-api-db-wait: ## Wait for the evidence API database
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,PYTHONPATH="$(CURDIR)/services" ARTANA_EVIDENCE_API_DATABASE_URL="$$DATABASE_URL" $(USE_PYTHON) -m artana_evidence_api.manage wait-db)

artana-evidence-api-db-migrate: ## Run evidence API migrations
	@$(MAKE) -s artana-evidence-api-db-wait
	$(call run_with_postgres_env,PYTHONPATH="$(CURDIR)/services" ARTANA_EVIDENCE_API_DATABASE_URL="$$DATABASE_URL" $(USE_PYTHON) -m artana_evidence_api.manage migrate)

init-artana-schema: ## Initialize the artana schema
	$(call check_venv)
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/init_artana_schema.py)

setup-postgres: ## Start Postgres and apply required schemas/migrations
	@$(MAKE) -s postgres-wait
	@$(MAKE) -s graph-db-migrate
	@$(MAKE) -s init-artana-schema
	@$(MAKE) -s artana-evidence-api-db-migrate

graph-service-openapi: ## Export graph service OpenAPI
	$(call check_venv)
	$(USE_PYTHON) scripts/export_graph_openapi.py --output $(GRAPH_SERVICE_OPENAPI_OUTPUT)

graph-service-client-types: ## Generate graph service TypeScript contract types
	$(call check_venv)
	$(USE_PYTHON) scripts/generate_ts_types.py --module artana_evidence_db.service_contracts --output $(GRAPH_SERVICE_TS_TYPES_OUTPUT)

graph-service-sync-contracts: ## Regenerate graph service OpenAPI and types
	@$(MAKE) -s graph-service-openapi
	@$(MAKE) -s graph-service-client-types

graph-service-contract-check: ## Verify graph service OpenAPI and types are current
	$(call check_venv)
	$(USE_PYTHON) scripts/export_graph_openapi.py --output $(GRAPH_SERVICE_OPENAPI_OUTPUT) --check
	$(USE_PYTHON) scripts/generate_ts_types.py --module artana_evidence_db.service_contracts --output $(GRAPH_SERVICE_TS_TYPES_OUTPUT) --check

graph-service-boundary-check: ## Validate graph service standalone boundary rules
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_graph_service_boundary.py

artana-evidence-api-openapi: ## Export evidence API OpenAPI
	$(call check_venv)
	$(USE_PYTHON) scripts/export_artana_evidence_api_openapi.py --output $(ARTANA_EVIDENCE_API_OPENAPI_OUTPUT)

artana-evidence-api-contract-check: ## Verify evidence API OpenAPI is current
	$(call check_venv)
	$(USE_PYTHON) scripts/export_artana_evidence_api_openapi.py --output $(ARTANA_EVIDENCE_API_OPENAPI_OUTPUT) --check

artana-evidence-api-boundary-check: ## Validate evidence API service boundary rules
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_artana_evidence_api_service_boundary.py

graph-phase6-release-check: ## Validate graph-service release-boundary policy
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_graph_phase6_release_contract.py

graph-service-lint: ## Run ruff on graph service paths
	$(call check_venv)
	$(USE_PYTHON) -m ruff check $(GRAPH_SERVICE_LINT_PATHS)

graph-service-type-check: ## Run mypy on graph service paths
	$(call check_venv)
	$(USE_PYTHON) -m mypy $(GRAPH_SERVICE_TYPE_PATHS) --exclude '$(GRAPH_SERVICE_TYPE_EXCLUDE)' --show-error-codes --no-warn-unused-configs --follow-imports=skip --disable-error-code no-any-unimported --disable-error-code no-any-return --disable-error-code misc --disable-error-code untyped-decorator

graph-service-type-check-strict-imports: ## Exploratory graph mypy check without skipped imports
	$(call check_venv)
	cd services && $(USE_PYTHON_ABS) -m mypy -p artana_evidence_db --exclude 'artana_evidence_db/(tests|alembic)/' $(GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS)

graph-service-test: ## Run graph service tests against isolated Postgres
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/run_isolated_postgres_tests.py $(GRAPH_SERVICE_TEST_PATHS) -q)

graph-service-checks: ## Run graph service gates
	@$(MAKE) -s graph-service-lint
	@$(MAKE) -s graph-service-type-check
	@$(MAKE) -s graph-service-boundary-check
	@$(MAKE) -s graph-service-contract-check
	@$(MAKE) -s graph-phase6-release-check
	@$(MAKE) -s graph-service-test

artana-evidence-api-lint: ## Run ruff on evidence API paths
	$(call check_venv)
	$(USE_PYTHON) -m ruff check $(ARTANA_EVIDENCE_API_LINT_PATHS)

artana-evidence-api-type-check: ## Run mypy on evidence API
	$(call check_venv)
	cd services && $(USE_PYTHON_ABS) -m mypy artana_evidence_api --no-warn-unused-configs $(ARTANA_EVIDENCE_API_MYPY_FLAGS)

artana-evidence-api-type-check-strict-imports: ## Exploratory evidence API runtime mypy check without skipped imports
	$(call check_venv)
	cd services && $(USE_PYTHON_ABS) -m mypy -p artana_evidence_api --exclude '$(ARTANA_EVIDENCE_API_TYPE_EXCLUDE)' --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)

type-hardening-baseline: ## Capture strict-import mypy baselines under tmp/type-hardening
	$(call check_venv)
	@mkdir -p tmp/type-hardening
	@/bin/bash -lc 'set +e; cd services && "$(USE_PYTHON_ABS)" -m mypy -p artana_evidence_api --exclude "$(ARTANA_EVIDENCE_API_TYPE_EXCLUDE)" --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS) > ../tmp/type-hardening/evidence-api-runtime-strict-imports.txt 2>&1; status=$$?; cd ..; "$(USE_PYTHON)" scripts/summarize_mypy_errors.py tmp/type-hardening/evidence-api-runtime-strict-imports.txt --label evidence-api-runtime-strict-imports --output tmp/type-hardening/evidence-api-runtime-strict-imports-summary.md; echo "Evidence API runtime strict-import mypy exit: $$status"; cat tmp/type-hardening/evidence-api-runtime-strict-imports-summary.md'
	@/bin/bash -lc 'set +e; cd services && "$(USE_PYTHON_ABS)" -m mypy -p artana_evidence_db --exclude "artana_evidence_db/(tests|alembic)/" $(GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS) > ../tmp/type-hardening/graph-service-strict-imports.txt 2>&1; status=$$?; cd ..; "$(USE_PYTHON)" scripts/summarize_mypy_errors.py tmp/type-hardening/graph-service-strict-imports.txt --label graph-service-strict-imports --output tmp/type-hardening/graph-service-strict-imports-summary.md; echo "Graph service strict-import mypy exit: $$status"; cat tmp/type-hardening/graph-service-strict-imports-summary.md'

artana-evidence-api-test: ## Run evidence API tests against isolated Postgres
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/run_isolated_postgres_tests.py $(ARTANA_EVIDENCE_API_TEST_PATHS) -q)

artana-evidence-api-service-checks: ## Run evidence API gates
	@$(MAKE) -s artana-evidence-api-lint
	@$(MAKE) -s artana-evidence-api-type-check
	@$(MAKE) -s artana-evidence-api-boundary-check
	@$(MAKE) -s artana-evidence-api-contract-check
	@$(MAKE) -s artana-evidence-api-test

run-graph-service: ## Run the standalone graph API service locally
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) PYTHONPATH="$(CURDIR)/services" GRAPH_DATABASE_URL="$$DATABASE_URL" GRAPH_SERVICE_HOST=0.0.0.0 GRAPH_SERVICE_PORT=$(GRAPH_SERVICE_PORT) GRAPH_SERVICE_RELOAD=1 $(USE_PYTHON) -m artana_evidence_db)

run-artana-evidence-api-service: ## Run the standalone evidence API locally
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) PYTHONPATH="$(CURDIR)/services" DATABASE_URL="$$DATABASE_URL" ARTANA_EVIDENCE_API_DATABASE_URL="$$DATABASE_URL" GRAPH_API_URL="http://127.0.0.1:$(GRAPH_SERVICE_PORT)" ARTANA_EVIDENCE_API_SERVICE_HOST=0.0.0.0 ARTANA_EVIDENCE_API_SERVICE_PORT=$(ARTANA_EVIDENCE_API_PORT) ARTANA_EVIDENCE_API_SERVICE_RELOAD=1 $(USE_PYTHON) -m artana_evidence_api)

run-all: ## Run Postgres, graph service, and evidence API locally
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	$(call ensure_postgres_env)
	@echo "Using Postgres env ($(POSTGRES_ENV_FILE))"
	@/bin/bash -lc '\
		set -euo pipefail; \
		set -a; source "$(POSTGRES_ENV_FILE)"; set +a; \
		export AUTH_JWT_SECRET="$(BACKEND_DEV_JWT_SECRET)"; \
		export GRAPH_JWT_SECRET="$(BACKEND_DEV_JWT_SECRET)"; \
		export GRAPH_JWT_ISSUER="$(BACKEND_DEV_JWT_ISSUER)"; \
		export ARTANA_EVIDENCE_API_BOOTSTRAP_KEY="$(ARTANA_EVIDENCE_API_BOOTSTRAP_KEY)"; \
		export AUTH_ALLOW_TEST_AUTH_HEADERS="$(AUTH_ALLOW_TEST_AUTH_HEADERS)"; \
		export PYTHONPATH="$(CURDIR)/services"; \
		export GRAPH_DATABASE_URL="$$DATABASE_URL"; \
		export GRAPH_SERVICE_HOST="0.0.0.0"; \
		export GRAPH_SERVICE_PORT="$(GRAPH_SERVICE_PORT)"; \
		export GRAPH_SERVICE_RELOAD="1"; \
		export ARTANA_EVIDENCE_API_DATABASE_URL="$$DATABASE_URL"; \
		export GRAPH_API_URL="http://127.0.0.1:$(GRAPH_SERVICE_PORT)"; \
		export ARTANA_EVIDENCE_API_SERVICE_HOST="0.0.0.0"; \
		export ARTANA_EVIDENCE_API_SERVICE_PORT="$(ARTANA_EVIDENCE_API_PORT)"; \
		export ARTANA_EVIDENCE_API_SERVICE_RELOAD="1"; \
		cleanup() { \
			trap - INT TERM EXIT; \
			[ -n "$${graph_pid:-}" ] && kill "$$graph_pid" 2>/dev/null || true; \
			[ -n "$${api_pid:-}" ] && kill "$$api_pid" 2>/dev/null || true; \
			wait 2>/dev/null || true; \
		}; \
		trap cleanup INT TERM EXIT; \
		echo "Starting graph service on http://127.0.0.1:$(GRAPH_SERVICE_PORT)"; \
		$(USE_PYTHON) -m artana_evidence_db & graph_pid=$$!; \
		echo "Starting evidence API on http://127.0.0.1:$(ARTANA_EVIDENCE_API_PORT)"; \
		$(USE_PYTHON) -m artana_evidence_api & api_pid=$$!; \
		while kill -0 "$$graph_pid" 2>/dev/null && kill -0 "$$api_pid" 2>/dev/null; do sleep 1; done; \
		status=0; \
		if ! kill -0 "$$graph_pid" 2>/dev/null; then wait "$$graph_pid" || status=$$?; echo "Graph service exited."; fi; \
		if ! kill -0 "$$api_pid" 2>/dev/null; then wait "$$api_pid" || status=$$?; echo "Evidence API exited."; fi; \
		exit "$$status"; \
	'
