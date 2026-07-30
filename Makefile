# Extracted Artana Evidence Platform Makefile

DEFAULT_VENV := $(if $(wildcard venv/bin/python3),venv,$(if $(wildcard .venv/bin/python3),.venv,venv))
VENV ?= $(DEFAULT_VENV)
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
COVERAGE_MIN ?= 86
EVIDENCE_SELECTION_REQUIRED_MAINLINE_COMMIT ?= d23b1dea194d7fc6f116de84738fdf720c536a71

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
	 services/artana_evidence_db/graph_workflow/actor_context.py \
	 services/artana_evidence_db/graph_workflow/policy.py \
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

# Contract exports import the service package to read its live schema. Without
# this, the editable install resolves the import to whichever checkout was
# `pip install -e`d, so running these from a git worktree silently exports the
# OTHER tree's contract -- and --check then passes against code you did not write.
SERVICE_PYTHONPATH := PYTHONPATH="$(CURDIR)/services"

GRAPH_SERVICE_TYPE_EXCLUDE := artana_evidence_db/(tests|alembic)/
ARTANA_EVIDENCE_API_TYPE_EXCLUDE := artana_evidence_api/(tests|alembic)/

GRAPH_SERVICE_TEST_PATHS := \
	 tests/e2e/graph_service \
	 services/artana_evidence_db/tests/unit \
	 services/artana_evidence_db/tests/integration \
	 tests/unit/database/test_023_graph_external_fk_decoupling_contract.py

ARTANA_EVIDENCE_API_LINT_PATHS := \
 services/artana_evidence_api \
 scripts/run_evidence_selection_expert_study_gate.py \
 scripts/run_evidence_selection_review_calibration_gate.py \
 scripts/build_evidence_selection_shadow_review_packet.py \
 scripts/build_evidence_selection_expert_pilot_packets.py \
 scripts/import_evidence_selection_expert_pilot_reviews.py \
 scripts/build_evidence_selection_shadow_review_source_inputs.py \
 scripts/build_evidence_selection_shadow_review_study_batch_manifest.py \
 scripts/build_evidence_selection_shadow_review_study_batch.py \
 scripts/build_evidence_selection_shadow_review_study_artifacts.py \
 scripts/build_evidence_selection_source_exports.py \
 scripts/build_evidence_selection_expert_study_bundle.py \
 scripts/generate_evidence_selection_semantic_baseline.py \
 scripts/validate_evidence_selection_semantic_benchmark_v2.py \
 scripts/run_evidence_selection_semantic_agent_evaluation.py \
 scripts/run_evidence_selection_semantic_model_comparison.py \
 scripts/ci/validate_agent_output_boundaries.py \
 scripts/export_artana_evidence_api_openapi.py \
 scripts/validate_artana_evidence_api_service_boundary.py \
 scripts/validation \
 tests

ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS := \
 --show-error-codes

GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS := \
 --show-error-codes

ARTANA_EVIDENCE_API_TEST_PATHS := \
	 tests/e2e/artana_evidence_api \
	 services/artana_evidence_api/tests/integration \
	 services/artana_evidence_api/tests/unit \
	 tests/unit/database/test_artana_evidence_api_alembic_migration_regressions.py \
	 tests/unit/test_finite_source_unit_audit.py \
	 tests/unit/test_nary_claim_evaluation.py \
	 tests/unit/test_nary_claim_runner.py \
	 tests/unit/test_run_evidence_selection_expert_study_gate.py \
	 tests/unit/test_run_evidence_selection_review_calibration_gate.py \
	 tests/unit/test_agent_output_boundary_validator.py \
	 tests/unit/test_bionlp_claim_event_import.py \
	 tests/unit/test_nary_claim_comparison.py \
	 tests/unit/test_nary_claim_fixture.py \
	 tests/unit/test_nary_claim_matching.py \
	 tests/unit/test_nary_claim_operational.py \
	 tests/unit/test_nary_claim_scoring.py \
	 tests/unit/test_restricted_corpus_text.py \
	 tests/unit/test_restricted_corpus_scan.py \
	 tests/unit/test_typing_any_ban.py \
	 tests/unit/test_governance_invariants.py

LIVE_ENDPOINT_CONTRACT_TEST_PATH := tests/e2e/artana_evidence_api/test_live_endpoint_contract.py
LIVE_EXTERNAL_API_TEST_PATH := services/artana_evidence_api/tests/integration/test_research_init_live_pipeline.py

COVERAGE_TEST_PATHS := \
	 $(GRAPH_SERVICE_TEST_PATHS) \
	 $(ARTANA_EVIDENCE_API_TEST_PATHS)

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

.PHONY: help all venv install-dev docker-postgres-up docker-postgres-down docker-postgres-destroy docker-postgres-logs docker-postgres-status postgres-wait graph-db-wait graph-db-migrate artana-evidence-api-db-wait artana-evidence-api-db-migrate init-artana-schema setup-postgres graph-service-openapi graph-service-client-types graph-service-sync-contracts graph-service-contract-check graph-service-boundary-check artana-evidence-api-openapi artana-evidence-api-contract-check artana-evidence-api-boundary-check agent-output-boundary-check graph-phase6-release-check architecture-size-check architecture-structure-check restricted-corpus-digest-check restricted-corpus-scan restricted-corpus-digests typing-any-check graph-service-lint graph-service-type-check graph-service-type-check-strict-imports graph-service-test graph-service-static-checks-core graph-service-static-checks graph-service-checks artana-evidence-api-lint artana-evidence-api-type-check artana-evidence-api-type-check-strict-imports artana-evidence-api-test evidence-selection-semantic-baseline-check evidence-selection-semantic-benchmark-v2-check evidence-selection-semantic-model-comparison coverage-check relation-feasibility-quality-gate artana-evidence-api-static-checks-core artana-evidence-api-static-checks artana-evidence-api-service-checks service-checks live-endpoint-contract-check live-external-api-check live-agent-relation-feasibility-check live-service-checks type-hardening-baseline run-graph-service run-artana-evidence-api-service run-artana-evidence-api-worker run-all

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_.-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-32s %s\n", $$1, $$2}'

all: service-checks ## Run the full CI-safe quality gate

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
	$(SERVICE_PYTHONPATH) $(USE_PYTHON) scripts/export_graph_openapi.py --output $(GRAPH_SERVICE_OPENAPI_OUTPUT)

graph-service-client-types: ## Generate graph service TypeScript contract types
	$(call check_venv)
	$(SERVICE_PYTHONPATH) $(USE_PYTHON) scripts/generate_ts_types.py --module artana_evidence_db.service_contracts --output $(GRAPH_SERVICE_TS_TYPES_OUTPUT)

graph-service-sync-contracts: ## Regenerate graph service OpenAPI and types
	@$(MAKE) -s graph-service-openapi
	@$(MAKE) -s graph-service-client-types

graph-service-contract-check: ## Verify graph service OpenAPI and types are current
	$(call check_venv)
	$(SERVICE_PYTHONPATH) $(USE_PYTHON) scripts/export_graph_openapi.py --output $(GRAPH_SERVICE_OPENAPI_OUTPUT) --check
	$(SERVICE_PYTHONPATH) $(USE_PYTHON) scripts/generate_ts_types.py --module artana_evidence_db.service_contracts --output $(GRAPH_SERVICE_TS_TYPES_OUTPUT) --check

graph-service-boundary-check: ## Validate graph service standalone boundary rules
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_graph_service_boundary.py

artana-evidence-api-openapi: ## Export evidence API OpenAPI
	$(call check_venv)
	$(SERVICE_PYTHONPATH) $(USE_PYTHON) scripts/export_artana_evidence_api_openapi.py --output $(ARTANA_EVIDENCE_API_OPENAPI_OUTPUT)

artana-evidence-api-contract-check: ## Verify evidence API OpenAPI is current
	$(call check_venv)
	$(SERVICE_PYTHONPATH) $(USE_PYTHON) scripts/export_artana_evidence_api_openapi.py --output $(ARTANA_EVIDENCE_API_OPENAPI_OUTPUT) --check

artana-evidence-api-boundary-check: ## Validate evidence API service boundary rules
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_artana_evidence_api_service_boundary.py

graph-phase6-release-check: ## Validate graph-service release-boundary policy
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_graph_phase6_release_contract.py

architecture-size-check: ## Enforce per-file architecture size budget
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_architecture_size.py

architecture-structure-check: ## Enforce package structure and sprawl guardrails
	$(call check_venv)
	$(USE_PYTHON) scripts/validate_architecture_structure.py

# Two halves, because the thorough check needs a corpus we are not allowed to
# commit. This half runs anywhere and catches restricted runs we have already
# removed coming back; it is blind to corpus text nobody has removed before.
# No check_venv: this is stdlib only, and it has to be runnable in a CI job
# that installs nothing. A guard that runs everywhere is worth more than one
# that shares a bootstrap with the gates it is meant to outlive.
restricted-corpus-digest-check: ## Catch re-introduced restricted corpus text (offline)
	PYTHONPATH="$(CURDIR)" $(USE_PYTHON) scripts/validation/check_restricted_corpus_digests.py

# The other half: every tracked file against every corpus document. Needs the
# corpus fetched, so it cannot be in service-checks. Run it before landing
# anything corpus-derived.
restricted-corpus-scan: ## Scan every tracked file against the corpus (needs the corpus)
	$(call check_venv)
	PYTHONPATH="$(CURDIR)" $(USE_PYTHON) scripts/validation/check_restricted_corpus_text.py

restricted-corpus-digests: ## Rebuild the committed digest set (needs the corpus)
	$(call check_venv)
	PYTHONPATH="$(CURDIR)" $(USE_PYTHON) scripts/validation/build_restricted_corpus_digests.py

# ruff has no rule for `fixture: dict[str, Any] = load(...)` -- ANN401 covers
# parameters and returns, not locals -- and until this branch `tests/unit/` was
# outside every ruff path anyway, so nothing opened those files at all. Seven
# `Any` annotations reached HEAD through that pair of holes and a hand sweep
# missed four of them. No check_venv and stdlib only, for the same reason as
# the corpus digest check above: it has to be runnable in a CI job that
# installs nothing.
typing-any-check: ## Enforce the AGENTS.md ban on `Any` in guarded trees
	PYTHONPATH="$(CURDIR)" $(USE_PYTHON) scripts/ci/check_typing_any_ban.py

graph-service-lint: ## Run ruff on graph service paths
	$(call check_venv)
	$(USE_PYTHON) -m ruff check $(GRAPH_SERVICE_LINT_PATHS)

graph-service-type-check: ## Run mypy on graph service paths
	$(call check_venv)
	cd services && $(USE_PYTHON_ABS) -m mypy -p artana_evidence_db --exclude '$(GRAPH_SERVICE_TYPE_EXCLUDE)' --no-warn-unused-configs $(GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/export_graph_openapi.py --no-warn-unused-configs $(GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS)

graph-service-type-check-strict-imports: ## Exploratory graph mypy check without skipped imports
	$(call check_venv)
	@$(MAKE) -s graph-service-type-check

graph-service-test: ## Run graph service tests against isolated Postgres
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/run_isolated_postgres_tests.py $(GRAPH_SERVICE_TEST_PATHS) -q)

graph-service-static-checks-core: ## Run graph service static gates except repo-wide size check
	@$(MAKE) -s graph-service-lint
	@$(MAKE) -s graph-service-type-check
	@$(MAKE) -s graph-service-boundary-check
	@$(MAKE) -s graph-service-contract-check
	@$(MAKE) -s graph-phase6-release-check

graph-service-static-checks: ## Run graph service gates except tests
	@$(MAKE) -s graph-service-static-checks-core
	@$(MAKE) -s architecture-size-check
	@$(MAKE) -s architecture-structure-check

graph-service-checks: ## Run graph service gates
	@$(MAKE) -s graph-service-static-checks
	@$(MAKE) -s graph-service-test

artana-evidence-api-lint: ## Run ruff on evidence API paths
	$(call check_venv)
	$(USE_PYTHON) -m ruff check $(ARTANA_EVIDENCE_API_LINT_PATHS)

artana-evidence-api-type-check: ## Run strict mypy on evidence API package
	$(call check_venv)
	cd services && $(USE_PYTHON_ABS) -m mypy -p artana_evidence_api --exclude '$(ARTANA_EVIDENCE_API_TYPE_EXCLUDE)' --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/run_evidence_selection_expert_study_gate.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/run_evidence_selection_review_calibration_gate.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_shadow_review_packet.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_expert_pilot_packets.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/import_evidence_selection_expert_pilot_reviews.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_shadow_review_source_inputs.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_shadow_review_study_batch_manifest.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_shadow_review_study_batch.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_shadow_review_study_artifacts.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_source_exports.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/build_evidence_selection_expert_study_bundle.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/generate_evidence_selection_semantic_baseline.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/validate_evidence_selection_semantic_benchmark_v2.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/run_evidence_selection_semantic_agent_evaluation.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/run_evidence_selection_semantic_model_comparison.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/run_finite_source_unit_audit.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)
	cd services && $(USE_PYTHON_ABS) -m mypy ../scripts/ci/validate_agent_output_boundaries.py --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)

artana-evidence-api-type-check-strict-imports: ## Explicit strict-import evidence API mypy gate
	$(call check_venv)
	@$(MAKE) -s artana-evidence-api-type-check

type-hardening-baseline: ## Capture strict-import mypy baselines under tmp/type-hardening
	$(call check_venv)
	@mkdir -p tmp/type-hardening
	@/bin/bash -lc 'set +e; cd services && "$(USE_PYTHON_ABS)" -m mypy -p artana_evidence_api --exclude "$(ARTANA_EVIDENCE_API_TYPE_EXCLUDE)" --no-warn-unused-configs $(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS) > ../tmp/type-hardening/evidence-api-runtime-strict-imports.txt 2>&1; status=$$?; cd ..; "$(USE_PYTHON)" scripts/summarize_mypy_errors.py tmp/type-hardening/evidence-api-runtime-strict-imports.txt --label evidence-api-runtime-strict-imports --output tmp/type-hardening/evidence-api-runtime-strict-imports-summary.md; echo "Evidence API runtime strict-import mypy exit: $$status"; cat tmp/type-hardening/evidence-api-runtime-strict-imports-summary.md'
	@/bin/bash -lc 'set +e; cd services && "$(USE_PYTHON_ABS)" -m mypy -p artana_evidence_db --exclude "$(GRAPH_SERVICE_TYPE_EXCLUDE)" --no-warn-unused-configs $(GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS) > ../tmp/type-hardening/graph-service-strict-imports.txt 2>&1; status=$$?; cd ..; "$(USE_PYTHON)" scripts/summarize_mypy_errors.py tmp/type-hardening/graph-service-strict-imports.txt --label graph-service-strict-imports --output tmp/type-hardening/graph-service-strict-imports-summary.md; echo "Graph service strict-import mypy exit: $$status"; cat tmp/type-hardening/graph-service-strict-imports-summary.md'

artana-evidence-api-test: ## Run evidence API tests against isolated Postgres
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/run_isolated_postgres_tests.py $(ARTANA_EVIDENCE_API_TEST_PATHS) -q)

coverage-check: ## Enforce service coverage threshold
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,$(USE_PYTHON) scripts/run_isolated_postgres_tests.py $(COVERAGE_TEST_PATHS) -W "ignore:unclosed database in <sqlite3.Connection object:ResourceWarning" --cov=services --cov-report=term-missing --cov-report=xml --cov-fail-under=$(COVERAGE_MIN) -q)

relation-feasibility-quality-gate: ## Run relation feasibility quality regression tests
	$(call check_venv)
	PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) -m pytest tests/unit/test_relation_feasibility_audit.py tests/unit/test_relation_feasibility_readiness_gate.py tests/unit/test_relation_feasibility_model_comparison.py tests/unit/test_relation_feasibility_fixture_validation.py tests/unit/test_generate_relation_feasibility_summary.py -q

evidence-selection-semantic-baseline-check: ## Verify the frozen semantic baseline reports
	$(call check_venv)
	PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) scripts/generate_evidence_selection_semantic_baseline.py --fixture scripts/validation/evidence_selection/fixtures/semantic_relevance_failure_corpus_v1.json --predictions scripts/validation/evidence_selection/fixtures/semantic_relevance_live_baseline_predictions_v1.json --generated-at 2026-07-11T00:00:00Z --json-output docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json --markdown-output docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.md --check

evidence-selection-semantic-benchmark-v2-check: ## Verify benchmark v2 integrity and reports
	$(call check_venv)
	PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) scripts/validate_evidence_selection_semantic_benchmark_v2.py --fixture scripts/validation/evidence_selection/fixtures/semantic_relevance_benchmark_v2.json --predictions scripts/validation/evidence_selection/fixtures/semantic_relevance_live_baseline_predictions_v1.json --generated-at 2026-07-13T00:00:00Z --json-output docs/validation/reports/2026-07-13-pr151-semantic-benchmark-v2.json --markdown-output docs/validation/reports/2026-07-13-pr151-semantic-benchmark-v2.md --check

agent-output-boundary-check: ## Validate registered agent output schema boundaries
	$(call check_venv)
	PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) scripts/ci/validate_agent_output_boundaries.py --check-report docs/validation/reports/2026-07-11-pr-semantic-pr3-agent-output-registry.json

evidence-selection-semantic-agent-evaluation: ## Run PR 2 live-agent semantic quality gate
	$(call check_venv)
	@test -n "$(EVALUATED_COMMIT)" || (echo "EVALUATED_COMMIT is required" >&2; exit 2)
	$(call run_with_postgres_env,PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) scripts/run_evidence_selection_semantic_agent_evaluation.py --fixture scripts/validation/evidence_selection/fixtures/semantic_relevance_failure_corpus_v1.json --baseline-report docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json --evaluated-commit "$(EVALUATED_COMMIT)" --generated-at "$${GENERATED_AT:-$$(date -u +%Y-%m-%dT%H:%M:%SZ)}" --json-output docs/validation/reports/pr-semantic-pr2-agent-selector-evaluation.json --markdown-output docs/validation/reports/pr-semantic-pr2-agent-selector-evaluation.md)

evidence-selection-semantic-model-comparison: ## Run PR 6 repeated source-locked model A/B proof
	$(call check_venv)
	@test -n "$(EVALUATED_COMMIT)" || (echo "EVALUATED_COMMIT is required" >&2; exit 2)
	@test -n "$(CANDIDATE_MODEL)" || (echo "CANDIDATE_MODEL is required" >&2; exit 2)
	@test -n "$(COMPARISON_OUTPUT_DIR)" || (echo "COMPARISON_OUTPUT_DIR is required" >&2; exit 2)
	$(call run_with_postgres_env,PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) scripts/run_evidence_selection_semantic_model_comparison.py --fixture scripts/validation/evidence_selection/fixtures/semantic_relevance_failure_corpus_v1.json --benchmark-fixture scripts/validation/evidence_selection/fixtures/semantic_relevance_benchmark_v2.json --baseline-report docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json --evaluated-commit "$(EVALUATED_COMMIT)" --trusted-mainline-ref "$(or $(TRUSTED_MAINLINE_REF),origin/main)" --required-mainline-commit "$(EVIDENCE_SELECTION_REQUIRED_MAINLINE_COMMIT)" $(if $(CURRENT_MODEL),--current-model "$(CURRENT_MODEL)",) --candidate-model "$(CANDIDATE_MODEL)" --generated-at "$${GENERATED_AT:-$$(date -u +%Y-%m-%dT%H:%M:%SZ)}" --output-dir "$(COMPARISON_OUTPUT_DIR)")

artana-evidence-api-static-checks-core: ## Run evidence API static gates except repo-wide size check
	@$(MAKE) -s artana-evidence-api-lint
	@$(MAKE) -s artana-evidence-api-type-check
	@$(MAKE) -s artana-evidence-api-boundary-check
	@$(MAKE) -s artana-evidence-api-contract-check
	@$(MAKE) -s agent-output-boundary-check
	@$(MAKE) -s evidence-selection-semantic-baseline-check
	@$(MAKE) -s evidence-selection-semantic-benchmark-v2-check

artana-evidence-api-static-checks: ## Run evidence API gates except tests
	@$(MAKE) -s artana-evidence-api-static-checks-core
	@$(MAKE) -s architecture-size-check
	@$(MAKE) -s architecture-structure-check

artana-evidence-api-service-checks: ## Run evidence API gates
	@$(MAKE) -s artana-evidence-api-static-checks
	@$(MAKE) -s artana-evidence-api-test

service-checks: ## Run all service gates including coverage enforcement
	@$(MAKE) -s graph-service-static-checks-core
	@$(MAKE) -s artana-evidence-api-static-checks-core
	@$(MAKE) -s architecture-size-check
	@$(MAKE) -s architecture-structure-check
	@$(MAKE) -s restricted-corpus-digest-check
	@$(MAKE) -s typing-any-check
	@$(MAKE) -s relation-feasibility-quality-gate
	@$(MAKE) -s coverage-check

live-endpoint-contract-check: ## Run opt-in live endpoint contract against make run-all
	$(call check_venv)
	@if ! curl -fsS "http://127.0.0.1:$(ARTANA_EVIDENCE_API_PORT)/health" >/dev/null; then \
	 echo "Evidence API is not reachable at http://127.0.0.1:$(ARTANA_EVIDENCE_API_PORT)."; \
	 echo "Start the local stack first with: make run-all"; \
	 exit 1; \
	fi
	ARTANA_EVIDENCE_API_BOOTSTRAP_KEY="$(ARTANA_EVIDENCE_API_BOOTSTRAP_KEY)" PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) -m pytest $(LIVE_ENDPOINT_CONTRACT_TEST_PATH) -q -s

live-external-api-check: ## Run opt-in live tests against public external APIs
	$(call check_venv)
	$(call run_with_postgres_env,RUN_LIVE_EXTERNAL_API_TESTS=1 PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) -m pytest $(LIVE_EXTERNAL_API_TEST_PATH) -q -s)

live-agent-relation-feasibility-check: ## Run opt-in strict live-agent relation feasibility audit
	$(call check_venv)
	@$(MAKE) -s postgres-wait
	$(call run_with_postgres_env,PYTHONPATH="$(CURDIR)/services:$(CURDIR)" $(USE_PYTHON) scripts/run_relation_feasibility_audit.py --extractor agent)

live-service-checks: ## Run opt-in live checks; start make run-all separately first
	@$(MAKE) -s live-endpoint-contract-check
	@$(MAKE) -s live-external-api-check
	@$(MAKE) -s live-agent-relation-feasibility-check

run-graph-service: ## Run the standalone graph API service locally
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) PYTHONPATH="$(CURDIR)/services" GRAPH_DATABASE_URL="$$DATABASE_URL" GRAPH_SERVICE_HOST=0.0.0.0 GRAPH_SERVICE_PORT=$(GRAPH_SERVICE_PORT) GRAPH_SERVICE_RELOAD=1 $(USE_PYTHON) -m artana_evidence_db)

run-artana-evidence-api-service: ## Run the standalone evidence API locally
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) PYTHONPATH="$(CURDIR)/services" DATABASE_URL="$$DATABASE_URL" ARTANA_EVIDENCE_API_DATABASE_URL="$$DATABASE_URL" GRAPH_API_URL="http://127.0.0.1:$(GRAPH_SERVICE_PORT)" ARTANA_EVIDENCE_API_SERVICE_HOST=0.0.0.0 ARTANA_EVIDENCE_API_SERVICE_PORT=$(ARTANA_EVIDENCE_API_PORT) ARTANA_EVIDENCE_API_SERVICE_RELOAD=1 $(USE_PYTHON) -m artana_evidence_api)

run-artana-evidence-api-worker: ## Run the standalone evidence API queued-run worker locally
	$(call check_venv)
	@$(MAKE) -s setup-postgres
	$(call run_with_postgres_env,$(BACKEND_DEV_ENV) PYTHONPATH="$(CURDIR)/services" DATABASE_URL="$$DATABASE_URL" ARTANA_EVIDENCE_API_DATABASE_URL="$$DATABASE_URL" GRAPH_API_URL="http://127.0.0.1:$(GRAPH_SERVICE_PORT)" AUTH_JWT_SECRET="$(BACKEND_DEV_JWT_SECRET)" GRAPH_JWT_SECRET="$(BACKEND_DEV_JWT_SECRET)" GRAPH_JWT_ISSUER="$(BACKEND_DEV_JWT_ISSUER)" $(USE_PYTHON) -m artana_evidence_api.worker)

run-all: ## Run Postgres, graph service, evidence API, and queued-run worker locally
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
		export ARTANA_EVIDENCE_API_WORKER_POLL_SECONDS="$${ARTANA_EVIDENCE_API_WORKER_POLL_SECONDS:-1}"; \
		cleanup() { \
			trap - INT TERM EXIT; \
			[ -n "$${graph_pid:-}" ] && kill "$$graph_pid" 2>/dev/null || true; \
			[ -n "$${api_pid:-}" ] && kill "$$api_pid" 2>/dev/null || true; \
			[ -n "$${worker_pid:-}" ] && kill "$$worker_pid" 2>/dev/null || true; \
			wait 2>/dev/null || true; \
		}; \
		trap "cleanup; exit 0" INT TERM; \
		trap cleanup EXIT; \
		echo "Starting graph service on http://127.0.0.1:$(GRAPH_SERVICE_PORT)"; \
		$(USE_PYTHON) -m artana_evidence_db & graph_pid=$$!; \
		echo "Starting evidence API on http://127.0.0.1:$(ARTANA_EVIDENCE_API_PORT)"; \
		$(USE_PYTHON) -m artana_evidence_api & api_pid=$$!; \
		echo "Starting evidence API queued-run worker"; \
		$(USE_PYTHON) -m artana_evidence_api.worker & worker_pid=$$!; \
		while kill -0 "$$graph_pid" 2>/dev/null && kill -0 "$$api_pid" 2>/dev/null && kill -0 "$$worker_pid" 2>/dev/null; do sleep 1; done; \
		status=0; \
		if ! kill -0 "$$graph_pid" 2>/dev/null; then wait "$$graph_pid" || status=$$?; echo "Graph service exited."; fi; \
		if ! kill -0 "$$api_pid" 2>/dev/null; then wait "$$api_pid" || status=$$?; echo "Evidence API exited."; fi; \
		if ! kill -0 "$$worker_pid" 2>/dev/null; then wait "$$worker_pid" || status=$$?; echo "Evidence API worker exited."; fi; \
		exit "$$status"; \
	'
