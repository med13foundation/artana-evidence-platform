# Artana Resource Library - AGENTS.md

**A README for AI coding agents working on the Artana Resource Library.**

This document provides essential context and instructions for AI agents building on our domain-agnostic data platform. Complementing the human-facing `README.md`, this file helps agents understand our Clean Architecture, domain requirements, and development workflow.

## 📋 Project Overview

**Artana Resource Library** is a domain-agnostic data platform that ingests, enriches, extracts, and graphs structured knowledge from external sources. The same pipeline, agents, Dictionary, and kernel graph serve biomedical research (MED13, ClinVar, PubMed), sports analytics, CS benchmarking, or any other domain — only the Dictionary content differs. It implements Clean Architecture with:

- **Domain**: Domain-agnostic business logic driven by a universal Dictionary schema engine, plus MED13/biomedical validation as the first domain
- **Architecture**: Service-first Python APIs with the standalone Research Inbox UI, Artana-based AI agents, and a kernel knowledge graph (entities, observations, relations, provenance)
- **Tech Stack**: Python 3.12+, TypeScript, PostgreSQL (with pgvector, RLS, PHI encryption), Clean Architecture patterns, Artana for AI agent orchestration
- **Purpose**: Provide researchers and administrators with reliable, type-safe, evidence-backed data management across any domain

**Key Characteristics:**
- **Domain-Agnostic Design**: The Dictionary is a universal schema engine; agents and pipelines are parameterised by source type, not hardcoded to a single domain
- **Healthcare-Grade Security**: PHI isolation, Row-Level Security, column-level encryption, comprehensive audit logging
- **Next.js-Only UI**: The Dash curation client has been retired; `services/research_inbox` is the canonical authenticated UI
- **Type Safety First**: 100% MyPy compliance, Pydantic validation, strict "Never Any" policy
- **Clean Architecture**: Domain-driven design with clear layer separation
- **Evidence-First AI**: All agent outputs include confidence scores, rationale, and evidence for full auditability

## 🤖 Agent-Specific Instructions

**How AI agents should work with this codebase:**

### Code Generation Guidelines
- **STRICT TYPE SAFETY**: Never use `Any` - always provide proper type annotations
- **Clean Architecture layers**: Domain logic in `src/domain`, application services in `src/application`, API endpoints in `src/routes`, active authenticated UI in `services/research_inbox` (Next.js); `src/presentation` is reserved
- **Pydantic models**: Use Pydantic BaseModel for domain entities and API schemas; use TypedDicts from `src/type_definitions/` for updates, JSON payloads, and API response shapes
- **Type definitions**: Use existing types from `src/type_definitions/` instead of creating new ones
- **Follow biomedical domain rules**: Respect MED13-specific validation and business logic
- **Implement proper error handling**: Use domain-specific exceptions and validation

### Greenfield Default (No Legacy Overhead)
- **Use this mode for new apps/subsystems with no production users**: Implement a single forward-only path
- **Do not add fallback behavior by default**: No fallback branches, compatibility shims, dual reads/writes, or deprecation scaffolding unless explicitly requested
- **Do not add migration/backfill logic by default**: For early-stage work, avoid transition code for old schemas/data unless explicitly requested
- **Prefer direct target architecture**: Build the final intended interfaces and data shapes now; add compatibility work later only when real user/data constraints exist

### Type Management Rules
- **NEVER USE `Any`**: This is a strict requirement - use proper union types, generics, or specific types
- **Use existing types**: Check `src/type_definitions/` for existing TypedDict, Protocol, and union types
- **JSON types**: Use `JSONObject` and `JSONValue` (use `list[JSONValue]` for arrays)
- **External APIs**: Use validation results from `src/type_definitions/external_apis.py`
- **Update operations**: Use TypedDict classes like `GeneUpdate`, `VariantUpdate`, etc.
- **Test fixtures**: Use `tests/test_types/fixtures.py` and `tests/test_types/mocks.py` for typed test data
- **API responses**: Use `APIResponse` and `PaginatedResponse` from `src/type_definitions/common.py`

#### Type Definition Locations
- **Common types**: `src/type_definitions/common.py` (JSON, API responses, pagination)
- **Domain entities**: `src/domain/entities/` (Pydantic models)
- **External APIs**: `src/type_definitions/external_apis.py` (ClinVar, UniProt, etc.)
- **Update types**: `src/type_definitions/common.py` (GeneUpdate, VariantUpdate, etc.)
- **Test types**: `tests/test_types/` (fixtures, mocks, test data)

### File Organization Rules
- **New features**: Follow existing module structure (`/domain`, `/application`, `/infrastructure`)
- **API endpoints**: Add to `/routes` with proper FastAPI router patterns
- **Database changes**: Create Alembic migrations in `/alembic/versions`
- **UI components**: Implement in the active Next.js app (`/services/research_inbox`) with shared typed contracts from the backend
- **AI agents**: Follow the agent architecture pattern (see below)

### AI Agent Development Guidelines

When working with AI agents (Artana-based):

#### Agent Architecture Pattern
```
src/domain/agents/                           # Domain layer
├── contracts/                               # Pydantic models with evidence fields
│   ├── base.py                              # BaseAgentContract (confidence, rationale, evidence)
│   ├── query_generation.py                  # QueryGenerationContract
│   ├── entity_recognition.py                # EntityRecognitionContract
│   ├── extraction.py                        # ExtractionContract
│   ├── graph_connection.py                  # GraphConnectionContract
│   ├── graph_search.py                      # GraphSearchContract
│   ├── content_enrichment.py                # ContentEnrichmentContract
│   └── mapping_judge.py                     # MappingJudgeContract
├── contexts/                                # Pipeline context classes
│   ├── query_generation_context.py
│   ├── entity_recognition_context.py
│   ├── extraction_context.py
│   ├── graph_connection_context.py
│   ├── graph_search_context.py
│   ├── content_enrichment_context.py
│   └── mapping_judge_context.py
└── ports/                                   # Interface definitions (ABC classes)
    ├── query_generation_port.py
    ├── entity_recognition_port.py
    ├── extraction_port.py
    ├── graph_connection_port.py
    ├── graph_search_port.py
    ├── content_enrichment_port.py
    └── mapping_judge_port.py

src/application/agents/services/             # Application layer - orchestration
├── query_generation_service.py
├── entity_recognition_service.py
├── extraction_service.py
├── graph_connection_service.py
├── graph_search_service.py
├── content_enrichment_service.py
└── mapping_judge_service.py

src/infrastructure/llm/                      # Infrastructure - Artana/OpenAI implementation
├── adapters/                                # Port implementations (1 per agent)
├── factories/                               # Agent creation (1 per agent)
├── pipelines/                               # Pipeline definitions by agent & source type
│   ├── entity_recognition_pipelines/
│   │   ├── clinvar_pipeline.py
│   │   └── pubmed_pipeline.py               # Source-type dispatch
│   ├── extraction_pipelines/
│   │   ├── clinvar_pipeline.py
│   │   └── pubmed_pipeline.py
│   └── graph_connection_pipelines/
│       ├── clinvar_pipeline.py
│       └── pubmed_pipeline.py
├── prompts/                                 # System prompts by agent & source type
│   ├── entity_recognition/
│   │   ├── clinvar.py
│   │   └── pubmed.py
│   ├── extraction/
│   │   ├── clinvar.py
│   │   └── pubmed.py
│   └── graph_connection/
│       ├── clinvar.py
│       └── pubmed.py
├── skills/                                  # Skill registry (tool definitions)
└── state/                                   # State backend management
```

#### Implemented Agent Catalog (7 Agents)

| Agent | ISL Layer | Domain Contract | Purpose |
|-------|-----------|-----------------|---------|
| Query Generation | Semantic | `QueryGenerationContract` | Build PubMed Boolean queries from research context |
| Entity Recognition | Identity | `EntityRecognitionContract` | Identify biomedical entities in source records |
| Extraction | Identity | `ExtractionContract` | Extract structured knowledge from documents |
| Graph Connection | Truth | `GraphConnectionContract` | Discover relations between kernel entities |
| Graph Search | Interface | `GraphSearchContract` | Natural-language evidence-backed search over the graph |
| Content Enrichment | Semantic | `ContentEnrichmentContract` | Full-text content acquisition from source documents |
| Mapping Judge | Semantic | `MappingJudgeContract` | Resolve ambiguous dictionary mappings via LLM |

#### Creating New Agents
1. **Define contract** in `src/domain/agents/contracts/` extending `BaseAgentContract`
2. **Define context** in `src/domain/agents/contexts/` extending `BaseAgentContext`
3. **Define port** in `src/domain/agents/ports/` as an ABC class
4. **Create prompt** in `src/infrastructure/llm/prompts/<agent>/` — one file per source type
5. **Create factory** in `src/infrastructure/llm/factories/`
6. **Create pipeline** in `src/infrastructure/llm/pipelines/<agent>_pipelines/` — one per source type
7. **Create adapter** in `src/infrastructure/llm/adapters/` — with `_SUPPORTED_SOURCE_TYPES` set and dispatch dict for pipeline selection
8. **Create service** in `src/application/agents/services/`
9. **Wire DI** in `src/infrastructure/dependency_injection/` and register feature flag if needed
10. **Add routes** in `src/routes/research_spaces/` with Pydantic request/response schemas

#### Source-Type Dispatch Pattern
Agents support multiple domains through source-type dispatch rather than hardcoded logic:

```python
# In adapter — maps source_type to pipeline factory
_PIPELINE_FACTORIES: dict[str, Callable[..., Pipeline]] = {
    "clinvar": create_clinvar_extraction_pipeline,
    "pubmed": create_pubmed_extraction_pipeline,
}

# In adapter — maps source_type to heuristic fallback field mappings
_FALLBACK_FIELDS: dict[str, dict[str, str]] = {
    "clinvar": {"gene_symbol": "gene", "variation": "variant"},
    "pubmed": {"title": "name", "mesh_terms": "keywords"},
}
```

To add a new domain (e.g. sports analytics), create new prompt + pipeline files and add entries to the dispatch dicts — no changes to domain contracts or application services required.

#### Agent Contract Requirements
```python
from src.domain.agents.contracts.base import BaseAgentContract

class MyAgentContract(BaseAgentContract):
    """All contracts must include evidence-first fields."""

    # Inherited from BaseAgentContract:
    # - confidence_score: float (0.0-1.0)
    # - rationale: str
    # - evidence: list[EvidenceItem]

    # Agent-specific fields:
    result: str
    decision: Literal["success", "fallback", "escalate"]
```

#### Feature Flag Convention
All agent-driven and security components are opt-in via environment variables:
- `ARTANA_ENABLE_PHI_ENCRYPTION` — enables column-level PHI encryption
- Agent endpoints are gated by feature flags in the DI layer
- This ensures safe, incremental rollout without affecting existing functionality

#### Type Safety Exception for External AI Runtime Adapters
External runtime adapters can require tightly-scoped `Any` escape hatches. This is a **documented exception** - the files are listed in `scripts/validate_architecture.py` `ALLOWED_ANY_USAGE`. Keep `Any` confined to infrastructure layer only. Domain contracts must be fully typed.

**See:** `docs/artana-kernel/docs/agent_migration.md` for migration/runtime guidance.

### Testing Requirements
- **Unit tests**: Required for all domain logic and services
- **Integration tests**: Required for API endpoints and repository operations
- **Type checking**: All code must pass MyPy strict mode
- **Coverage**: Maintain >85% test coverage for business logic

### Security Considerations

#### Core Principles
- **Never commit PHI**: No protected health information in code or tests
- **Input validation**: All user inputs validated through Pydantic models
- **Authentication**: Use existing auth patterns for new endpoints

#### Row-Level Security (RLS) — Implemented
Database-level access control enforced via PostgreSQL RLS policies on kernel tables (`entities`, `entity_identifiers`, `observations`, `relations`, `provenance`, `relation_evidence`). Session context is injected via `set_config()`:
- `app.current_user_id` — scopes reads/writes to the user's research space
- `app.has_phi_access` — gates access to PHI-sensitive rows
- `app.is_admin` — allows cross-space reads
- `app.bypass_rls` — system-level bypass for migrations/ingestion
- **Key file**: `src/database/session.py` (`set_session_rls_context()`)
- **Migration**: `alembic/versions/016_enable_kernel_rls.py`

#### Column-Level PHI Encryption — Implemented
Application-layer AES-256-GCM encryption with HMAC-SHA256 blind indexing for PHI identifiers. Controlled by feature flag `ARTANA_ENABLE_PHI_ENCRYPTION`:
- **Encryption service**: `src/infrastructure/security/phi_encryption.py`
- **Key management**: `src/infrastructure/security/key_provider.py` (local env vars or GCP Secret Manager)
- **Migration**: `alembic/versions/017_phi_identifier_encryption.py`
- **DI wiring**: `src/infrastructure/dependency_injection/kernel_service_factories.py`

#### Comprehensive Audit Logging — Implemented
Middleware + explicit domain logging for all mutations and reads:
- **Middleware**: `src/middleware/audit_logging.py` — auto-logs `POST/PUT/PATCH/DELETE` plus `phi.read` for GETs
- **API**: `src/routes/admin_routes/audit.py` — query, export (JSON/CSV), retention cleanup
- **Service**: `src/application/services/audit_service.py`
- **Repository**: `src/application/curation/repositories/audit_repository.py`

## 🔧 Build & Development Commands

**Essential commands for AI agents to set up and work with the codebase:**

### Environment Setup
```bash
make setup-dev          # Create Python 3.12 venv + install dependencies
source venv/bin/activate # Activate virtual environment
```

### Artana State Backend
- `ARTANA_STATE_URI` can explicitly set the state store URI. If unset, state URI is derived from `DATABASE_URL` with `search_path=artana,public`.
- Run `make init-artana-schema` (or `make setup-postgres`) to create the `artana` schema before first use.

### Development Servers
```bash
make run-local          # Start FastAPI backend (port 8080)
make run-research-inbox-service # Start Research Inbox (port 3020)
```

### Quality Assurance
```bash
make all                # Full quality gate (format, lint, type-check, tests)
make format            # Black + Ruff formatting
make lint              # Ruff + Flake8 linting
make type-check        # MyPy static analysis
make test              # Pytest execution
make test-cov          # Coverage reporting
```

### Database Operations
```bash
alembic revision --autogenerate -m "Add new table"  # Create migration
alembic upgrade head                                 # Apply migrations
```

## 🏗️ Strong Engineering Architecture

### Clean Architecture Principles
The Artana Resource Library implements a **Clean Architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  FastAPI REST API • Next.js Admin UI • Middleware       │ │
│  │  (audit logging, RLS context injection, CORS)           │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │          Application Services & Use Cases               │ │
│  │  • SourceManagementService  • TemplateService           │ │
│  │  • ValidationService  • IngestionSchedulingService      │ │
│  │  • DictionaryManagementService • AuditService           │ │
│  │  • ResearchQueryService • KernelSearchService           │ │
│  │  • KernelEntityService  • KernelRelationService         │ │
│  │  • KernelObservationService • KernelGraphService        │ │
│  │  ─── AI Agent Application Services ───                  │ │
│  │  • QueryGenerationService  • EntityRecognitionService   │ │
│  │  • ExtractionService  • GraphConnectionService          │ │
│  │  • GraphSearchService • ContentEnrichmentService        │ │
│  │  • MappingJudgeService                                  │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                     Domain Layer                           │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │            Business Logic & Entities                    │ │
│  │  • UserDataSource • SourceTemplate • IngestionJob       │ │
│  │  • KernelEntity • KernelRelation • KernelObservation    │ │
│  │  • DictionaryVariable • DictionaryEntityType            │ │
│  │  • DictionaryRelationType • SourceDocument              │ │
│  │  • ValueSet • ValueSetItem • TransformRegistry          │ │
│  │  • Agent Contracts (7) • Agent Contexts • Agent Ports   │ │
│  │  • Domain Services • Value Objects • Business Rules     │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────┐
│                 Infrastructure Layer                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           External Concerns & Adapters                  │ │
│  │  • SQLAlchemy Repositories • API Clients                │ │
│  │  • Artana Agent Infrastructure (7 agents)               │ │
│  │  • PHI Encryption Service • Key Provider                │ │
│  │  • Kernel Ingestion Pipeline (Map→Normalize→Resolve→    │ │
│  │    Validate→Persist)                                    │ │
│  │  • HybridMapper (Exact + Vector + LLMJudge)             │ │
│  │  • File Storage • External Services                     │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Features
- **Domain-Driven Design (DDD)**: Business logic isolated from technical concerns
- **Dependency Inversion**: Interfaces in domain, implementations in infrastructure
- **SOLID Principles**: Single responsibility, open/closed, Liskov substitution, interface segregation, dependency inversion
- **Hexagonal Architecture**: Ports & adapters pattern for external dependencies
- **CQRS Pattern**: Separate command and query responsibilities where appropriate
- **Intelligence Service Layers (ISL)**: Five conceptual layers — Semantic, Identity, Truth, Governance, Interface — that organise how knowledge flows through agents and the kernel (see `datasources_architecture.md`)

### Platform Architecture (Implemented)
The platform now spans Data Sources, Dictionary, Kernel, AI Agents, Security, and Search:

```
Platform Status: ✅ Core Complete
├── Data Sources (Phases 1-3): Pydantic entities, application services, repos, Next.js UI
├── Dictionary Engine (Phases 1-7): Entity/relation types, value sets, variables,
│   embeddings, constraint schemas, versioning/validity, transform registry
├── Kernel Knowledge Graph: Entities, observations, relations, provenance, review
├── AI Agent System (7 agents): Query Gen, Entity Recognition, Extraction,
│   Graph Connection, Graph Search, Content Enrichment, Mapping Judge
├── Security Hardening: RLS policies, PHI column-level encryption, comprehensive audit
├── Ingestion Pipeline: Map→Normalize→Resolve→Validate→Persist with HybridMapper
└── Search: Unified dictionary search (pgvector + pg_trgm), kernel graph search
```

## 📁 Monorepo Structure & Organization

**Artana uses a monorepo with clear service boundaries:**

```
resource_library/
├── src/                                # Shared Python domain/application code
│   ├── domain/                         # Business logic
│   │   ├── entities/                   # Pydantic domain models
│   │   │   ├── kernel/                 # KernelEntity, KernelRelation, KernelObservation
│   │   │   ├── user_data_source.py     # Data source entities
│   │   │   └── source_document.py      # SourceDocument entity
│   │   ├── services/                   # Domain services
│   │   ├── repositories/               # Repository interfaces (ports)
│   │   ├── ports/                      # Additional port interfaces
│   │   │   ├── graph_query_port.py     # Graph query read operations
│   │   │   └── research_query_port.py  # Interface Layer intent parsing
│   │   └── agents/                     # AI agent domain layer
│   │       ├── contracts/              # 7 output contracts (evidence-first)
│   │       ├── contexts/               # 7 pipeline contexts
│   │       └── ports/                  # 7 agent interface definitions
│   ├── application/                    # Use cases & orchestration
│   │   ├── services/                   # Application layer services
│   │   │   ├── dictionary_management_service.py
│   │   │   ├── audit_service.py
│   │   │   ├── research_query_service.py
│   │   │   └── kernel_*.py             # Kernel CRUD services
│   │   ├── curation/                   # Curation repositories
│   │   │   └── repositories/           # Including audit_repository
│   │   └── agents/services/            # 7 AI agent orchestration services
│   ├── infrastructure/                 # External concerns & adapters
│   │   ├── repositories/              # SQLAlchemy repository implementations
│   │   │   └── kernel/                # Kernel entity/relation/observation repos
│   │   ├── ingestion/                 # Kernel ingestion pipeline
│   │   │   ├── pipeline.py            # Map→Normalize→Resolve→Validate→Persist
│   │   │   └── mapping/              # HybridMapper, ExactMapper, VectorMapper, LLMJudgeMapper
│   │   ├── security/                  # Security infrastructure
│   │   │   ├── phi_encryption.py      # AES-256-GCM PHI encryption
│   │   │   └── key_provider.py        # Local / GCP Secret Manager key providers
│   │   ├── validation/                # External API response validators
│   │   ├── mappers/                   # Data mapping between layers
│   │   ├── factories/                 # Factory classes (ingestion pipeline, etc.)
│   │   ├── scheduling/               # Ingestion scheduling infrastructure
│   │   ├── dependency_injection/      # DI wiring (service factories)
│   │   │   ├── dependencies.py
│   │   │   └── kernel_service_factories.py
│   │   └── llm/                       # Artana-based AI agent infrastructure
│   │       ├── adapters/              # 7 port implementations
│   │       ├── factories/             # 7 agent factories
│   │       ├── pipelines/             # Pipeline definitions by agent & source type
│   │       │   ├── entity_recognition_pipelines/  (clinvar, pubmed)
│   │       │   ├── extraction_pipelines/          (clinvar, pubmed)
│   │       │   └── graph_connection_pipelines/    (clinvar, pubmed)
│   │       ├── prompts/               # System prompts by agent & source type
│   │       │   ├── entity_recognition/  (clinvar, pubmed)
│   │       │   ├── extraction/          (clinvar, pubmed)
│   │       │   └── graph_connection/    (clinvar, pubmed)
│   │       ├── skills/                # Skill registry (tool definitions)
│   │       └── state/                 # State backend management
│   ├── database/                      # Database session, RLS context
│   │   └── session.py                 # set_session_rls_context()
│   ├── middleware/                     # HTTP middleware
│   │   └── audit_logging.py           # Auto audit logging for all mutations
│   ├── models/database/               # SQLAlchemy ORM models
│   │   ├── kernel/                    # Kernel table models
│   │   └── source_document.py
│   ├── routes/                        # API endpoints
│   │   ├── research_spaces/           # Research-space-scoped routes
│   │   │   ├── entity_recognition_routes.py
│   │   │   ├── knowledge_extraction_routes.py
│   │   │   ├── graph_connection_routes.py
│   │   │   ├── kernel_graph_search_routes.py
│   │   │   ├── content_enrichment_routes.py
│   │   │   └── ...
│   │   ├── admin_routes/              # Admin endpoints (audit, templates)
│   │   └── data_discovery/            # PubMed, ClinVar discovery
│   ├── web/                           # Legacy Next.js admin interface
│   └── type_definitions/              # Shared TypedDict, Protocol, union types
├── alembic/versions/                   # Database migrations (001-017+)
├── docs/                               # Documentation
│   ├── latest_plan_path/
│   │   └── datasources_architecture.md # Master architectural roadmap
│   └── artana-kernel/docs/             # AI agent documentation
├── tests/                              # Backend tests
│   ├── unit/                           # Unit tests
│   ├── integration/                    # Integration tests (API, DB)
│   ├── e2e/                            # End-to-end tests
│   └── test_types/                     # Typed fixtures & mocks
├── scripts/                            # Utility scripts (validate_architecture.py)
└── Makefile                            # Build orchestration
```

**Service Boundaries:**
- **FastAPI Backend** (`src/`): Core business logic, kernel graph, dictionary engine, AI agents, security
- **Research Inbox UI** (`services/research_inbox/`): Active authenticated workflow surface
- **Template Catalog**: `/admin/templates` endpoints expose reusable data source templates
- **Research Spaces**: `/research_spaces/{space_id}/` endpoints scope all kernel operations, agent invocations, and search

**Cross-Service Dependencies:**
- The Next.js UI consumes the FastAPI REST API
- Shared TypeScript types generated from Pydantic models
- Common domain entities and business rules

**Database Schema (PostgreSQL):**
- **Kernel tables**: `entities`, `entity_identifiers`, `observations`, `relations`, `relation_evidence`, `provenance` — with RLS policies
- **Dictionary tables**: `dictionary_entity_types`, `dictionary_relation_types`, `dictionary_variables`, `value_sets`, `value_set_items`, `transform_registry` — with pgvector embeddings
- **Data Sources tables**: `user_data_sources`, `source_templates`, `ingestion_jobs`, `source_documents`
- **Audit tables**: `audit_log`
- **Extensions**: `pgvector`, `pg_trgm`
- **Migrations**: Alembic (001 through 017+)

## 🔄 Workflow & CI/CD Instructions

### Commit Message Conventions
**Use conventional commits for automated deployments:**
```bash
feat(api): add data source management endpoints
fix(inbox): resolve table sorting bug in the inbox UI
docs: update API documentation
ci: update deployment configuration
```

### Pull Request Workflow
**Standard PR process for AI-generated changes:**
1. **Branch naming**: `feature/`, `fix/`, `docs/`, `ci/`
2. **PR title**: Follow conventional commit format
3. **PR description**: Include what, why, and testing approach
4. **Required checks**: `make all` must pass
5. **Review**: At least one maintainer review required

### CI/CD Pipeline
**Automated quality gates:**
```bash
# Pre-commit (local)
make all

# CI Pipeline
├── Code formatting (Black, Ruff)
├── Linting (Ruff, Flake8, MyPy)
├── Security scanning (Bandit, Safety)
├── Testing (Pytest with coverage)
└── Deployment (Cloud Run)
```

### Deployment Strategy
**Multi-service independent deployments:**
```bash
# Graph API deployment
gcloud run deploy artana-evidence-db --source services/artana_evidence_db

# Research Inbox deployment
gcloud run deploy artana-research-inbox --source services/research_inbox
```

## 🧪 Testing Instructions

**How AI agents should write and run tests:**

### Test Frameworks & Structure
- **Unit Tests**: `tests/unit/` - Domain logic, services, utilities
- **Integration Tests**: `tests/integration/` - API endpoints, repositories, external services
- **E2E Tests**: `tests/e2e/` - Complete user workflows
- **Type Tests**: MyPy validation for all code

### Test Execution
```bash
# Run specific test types
make test              # All tests
pytest tests/unit/     # Unit tests only
pytest tests/integration/  # Integration tests only
pytest tests/e2e/      # End-to-end tests

# With coverage
make test-cov          # Coverage report
```

### Test Writing Guidelines
- **File naming**: `test_<feature>.py`
- **Test isolation**: Each test independent, no shared state
- **Mock external deps**: Use `tests/test_types/mocks.py` for repositories
- **Type safety**: All test fixtures properly typed
- **Coverage target**: >85% for business logic

### Schema Validation Testing
```python
# Always test Pydantic models
def test_data_source_validation():
    # Test valid data
    source = UserDataSource(
        id=UUID(), owner_id=UUID(),
        name="Test Source", source_type=SourceType.API
    )
    assert source.name == "Test Source"

    # Test invalid data
    with pytest.raises(ValidationError):
        UserDataSource(name="")  # Empty name should fail
```

## 💅 Code Style & Conventions

**Language and formatting standards for AI-generated code:**

### Python Standards
- **Version**: Python 3.12+ required
- **Formatting**: Black with 88-character line length
- **Linting**: Ruff + Flake8 (strict mode, no suppressions)
- **Type Checking**: MyPy strict mode (no `Any` types)

### Naming Conventions
- **Modules**: `snake_case` (e.g., `data_source_service.py`)
- **Classes**: `CamelCase` (e.g., `UserDataSource`, `SourceTemplate`)
- **Functions/Methods**: `snake_case` (e.g., `create_source()`, `validate_config()`)
- **Constants**: `UPPER_CASE` (e.g., `DEFAULT_TIMEOUT = 30`)
- **Variables**: `snake_case` (e.g., `source_config`, `user_permissions`)

### Import Organization
```python
# Standard library imports
from typing import Dict, List, Optional
from uuid import UUID

# Third-party imports
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# Local imports (absolute)
from src.domain.entities.user_data_source import UserDataSource
from src.application.services.source_management_service import SourceManagementService
```

### Docstring Standards
```python
def create_data_source(
    self, request: CreateSourceRequest
) -> UserDataSource:
    """
    Create a new data source with validation.

    Args:
        request: Validated creation request with all required fields

    Returns:
        The newly created UserDataSource entity

    Raises:
        ValueError: If source configuration is invalid
        PermissionError: If user lacks creation permissions
    """
```

### Domain-Specific Patterns
- **Entity Creation**: Always validate through domain services, not direct constructors
- **Error Handling**: Use domain-specific exceptions, not generic ones
- **Validation**: All business rules enforced at domain layer
- **Dependencies**: Use dependency injection, not direct instantiation

## 🛡️ Type Safety Excellence

#### **100% MyPy Compliance - Strict "Never Any" Policy**
The Artana Resource Library implements **100% MyPy compliance** with strict type checking. **Using `Any` is strictly forbidden** - this is a foundational requirement for healthcare software reliability.

#### **Core Type Safety Features**
- **Strict MyPy Configuration**: No `Any` types, comprehensive coverage
- **Pydantic Models**: Runtime type validation with rich error messages
- **Generic Types**: Proper typing for collections and containers
- **Protocol Classes**: Structural typing for interfaces
- **Type Guards**: Runtime type checking functions

#### **Essential Type Management Patterns**

**1. JSON-Compatible Types** (from `src/type_definitions/common.py`):
```python
from src.type_definitions.common import JSONObject, JSONValue

# For JSON data structures
def process_api_response(data: JSONObject) -> JSONValue:
    return data.get("result", [])

# For external API responses
def validate_external_data(raw: dict[str, JSONValue]) -> JSONObject:
    return dict(raw)
```

**2. API Response Types**:
```python
from src.type_definitions.common import APIResponse, PaginatedResponse, JSONObject

# Type-safe API responses
def get_users() -> APIResponse:
    users: list[JSONObject] = [{"id": "user-1", "email": "user@example.com"}]
    return {
        "data": users,
        "total": len(users),
        "page": 1,
        "per_page": 50,
    }

# Paginated responses
def get_paginated_genes(page: int) -> PaginatedResponse:
    genes: list[JSONObject] = [{"id": "gene-1", "symbol": "MED13"}]
    return {
        "items": genes,
        "total": len(genes),
        "page": page,
        "per_page": 50,
        "total_pages": 1,
        "has_next": False,
        "has_prev": False,
    }
```

**3. Update Operations** (from `src/type_definitions/common.py`):
```python
from src.type_definitions.common import GeneUpdate, VariantUpdate

# Type-safe updates
def update_gene(id: str, updates: GeneUpdate) -> Gene:
    # Only allows valid Gene fields
    return gene_service.update(id, updates)

# Example usage:
updates: GeneUpdate = {
    symbol: "MED13",
    name: "Updated name",
    ensembl_id: "ENSG00000108510"
}
```

**4. External API Validation** (from `src/type_definitions/external_apis.py`):
```python
from src.infrastructure.validation.api_response_validator import APIResponseValidator
from src.type_definitions.common import JSONValue
from src.type_definitions.external_apis import (
    ClinVarSearchResponse,
    ClinVarSearchValidationResult,
)

def process_clinvar_data(raw_data: dict[str, JSONValue]) -> ClinVarSearchResponse:
    validation: ClinVarSearchValidationResult = (
        APIResponseValidator.validate_clinvar_search_response(raw_data)
    )
    if not validation["is_valid"] or validation["sanitized_data"] is None:
        raise ValueError(f"Validation failed: {validation['issues']}")
    return validation["sanitized_data"]
```

**5. Typed Test Fixtures** (from `tests/test_types/fixtures.py`):
```python
from tests.test_types.fixtures import create_test_gene, TEST_GENE_MED13
from tests.test_types.mocks import create_mock_gene_service

def test_gene_operations():
    # Typed test data
    test_gene = create_test_gene(
        gene_id="TEST001",
        symbol="TEST",
        name="Test Gene"
    )

    # Type-safe mock service
    service = create_mock_gene_service([test_gene])

    # Full type safety throughout test
    result = service.get_gene_by_symbol("TEST")
    assert result.symbol == "TEST"
```

#### **Common Type Pitfalls to Avoid**

❌ **NEVER DO THIS:**
```python
# Wrong: Using Any
from typing import Any

# Wrong: Using Any
def process_data(data: Any) -> Any:
    return data.get("result")

# Wrong: Plain dict for structured data
def create_user(data: dict[str, Any]) -> User:
    return User(data)

# Wrong: Untyped external API responses
def fetch_clinvar_data(raw_response: Any) -> list[Any]:
    return raw_response.get("esearchresult", {}).get("idlist", [])
```

✅ **DO THIS INSTEAD:**
```python
# Correct: Use proper types
from src.infrastructure.validation.api_response_validator import APIResponseValidator
from src.type_definitions.common import JSONObject, JSONValue
from src.type_definitions.external_apis import (
    ClinVarSearchResponse,
    ClinVarSearchValidationResult,
)

def process_data(data: JSONObject) -> JSONValue:
    return data.get("result")

def create_user(data: UserCreate) -> User:
    return user_service.create(data)

def fetch_clinvar_data(raw_data: JSONValue) -> ClinVarSearchResponse:
    validation: ClinVarSearchValidationResult = (
        APIResponseValidator.validate_clinvar_search_response(raw_data)
    )
    if not validation["is_valid"] or validation["sanitized_data"] is None:
        raise ValueError(f"Invalid response: {validation['issues']}")
    return validation["sanitized_data"]
```

### **Type Safety Benefits**
- **Runtime Safety**: Pydantic validates all input/output at runtime
- **IDE Support**: Full autocomplete and refactoring capabilities
- **Documentation**: Types serve as living documentation
- **Testing**: Type-safe mocks and fixtures reduce test brittleness
- **Maintenance**: Refactoring is safe and reliable
- **Healthcare Compliance**: Prevents data corruption in medical research

#### **Type Safety Resources**
- **Complete patterns**: See `docs/type_examples.md` for comprehensive examples
- **Type definitions**: `src/type_definitions/` - existing types to reuse
- **Test types**: `tests/test_types/` - typed fixtures and mocks
- **Validation**: `src/infrastructure/validation/` - API response validators

## 📋 Development Standards

### Project Structure & Module Organization

See the **Monorepo Structure & Organization** section above for the complete directory tree. Key highlights:

- `src/domain/` — Business logic, entities, repository interfaces, agent contracts/contexts/ports
- `src/application/` — Use case services (15+ including 7 agent services)
- `src/infrastructure/` — SQLAlchemy repos, Artana agents, ingestion pipeline, security, DI
- `src/routes/` — FastAPI endpoints (research spaces, admin, data discovery)
- `src/models/database/` — SQLAlchemy ORM models (kernel, dictionary, data sources)
- `services/research_inbox/` — Active Research Inbox UI
- `alembic/versions/` — Database migrations (001 through 017+)
- `tests/` — Unit, integration, E2E tests with typed fixtures

### Build, Test, and Development Commands
- `make setup-dev`: Clean Python 3.12 virtualenv + dependencies
- `make run-local`: Start FastAPI on port 8080
- `make run-research-inbox-service`: Start Research Inbox on port 3020
- `make all`: Full quality gate (format, lint, type-check, tests)
- `make format`: Black + Ruff formatting
- `make lint`: Ruff + Flake8 linting
- `make type-check`: MyPy static analysis
- `make test`: Pytest execution
- `make test-cov`: Coverage reporting

### Coding Style & Naming Conventions
- **Formatting**: Black with 88 char line length
- **Linting**: Ruff + Flake8 (strict mode, no suppressions)
- **Naming**:
  - `snake_case` for modules, functions, variables
  - `CamelCase` for Pydantic models and classes
  - `UPPER_CASE` for constants
- **Docstrings**: Required for public APIs and complex logic
- **Imports**: Absolute imports, grouped by standard library → third-party → local

### Testing Guidelines
- **Framework**: Pytest with comprehensive fixtures
- **Coverage Target**: >85% with focus on business logic
- **Test Structure**: `tests/test_<feature>.py`
- **Test Types**: Unit, integration, E2E, property-based
- **Mocking**: Type-safe mocks from `tests.types.mocks`
- **Coverage**: `make test-cov` for verification

### Quality Assurance Pipeline
```bash
make all                    # Complete quality gate
├── make format            # Code formatting (Black + Ruff)
├── make lint              # Code quality (Ruff + Flake8)
├── make type-check        # Type safety (MyPy strict)
└── make test              # Test execution (Pytest)
```

### Security & Compliance
- **Static Analysis**: Bandit, Safety, pip-audit
- **Dependency Scanning**: `make security-audit`
- **Secrets Management**: GCP Secret Manager for production
- **Input Validation**: Pydantic models prevent injection attacks
- **Rate Limiting**: Configurable API rate limits
- **CORS Protection**: Properly configured cross-origin policies

## 🚀 Recent Achievements

### Data Sources Module (Phases 1-3 Complete)
- **Domain Modeling**: Full Pydantic entities (`UserDataSource`, `SourceTemplate`, `IngestionJob`, `SourceDocument`) with business rules
- **Application Services**: Clean use case orchestration (`SourceManagementService`, `TemplateService`, `ValidationService`, `IngestionSchedulingService`)
- **Infrastructure**: SQLAlchemy repositories with proper separation
- **UI/UX**: Research Inbox experience with Next.js and modern UI components
- **Quality Assurance**: Type-safe throughout, ready for production

### Autonomous Dictionary Evolution (Phases 1-7 Complete)
- **Phase 1 — Core Schema**: First-class `dictionary_entity_types`, `dictionary_relation_types` tables with provenance
- **Phase 2 — Coded Value Sets**: `value_sets` and `value_set_items` with review workflow
- **Phase 3 — Dictionary Variables**: `dictionary_variables` with type constraints and changelog
- **Phase 4 — Controlled Search + Embeddings**: `pgvector` embeddings, `pg_trgm` trigram indexes, unified search via `DictionaryManagementService`
- **Phase 5 — Constraint Schemas**: Pydantic validation models for variable constraints
- **Phase 6 — Versioning + Validity**: Temporal versioning (`is_active`, `valid_from`, `valid_to`, `superseded_by`) across all dictionary entities
- **Phase 7 — Transform Registry**: Enhanced `transform_registry` for unit conversions and derivations

### Kernel Knowledge Graph — Implemented
- **Entities**: Full CRUD with identifiers, sensitivity levels, research-space scoping
- **Relations**: Typed relations with evidence linking
- **Observations**: Typed observations linked to entities and provenance
- **Provenance**: `created_by`, `source_ref`, `reviewed_by`, `reviewed_at`, `revocation_reason`
- **Review Workflow**: `ACTIVE` → `PENDING_REVIEW` → `REVOKED` status lifecycle
- **Ingestion Pipeline**: `Map → Normalize → Resolve → Validate → Persist` with `HybridMapper` (Exact + Vector + LLMJudge)

### AI Agent System (Artana) — 7 Agents Production Ready
- **Query Generation**: PubMed Boolean query generation from research context
- **Entity Recognition**: Identify biomedical entities in source records (ClinVar + PubMed)
- **Extraction**: Extract structured knowledge from documents (ClinVar + PubMed)
- **Graph Connection**: Discover relations between kernel entities (ClinVar + PubMed)
- **Graph Search**: Natural-language evidence-backed search over the kernel graph
- **Content Enrichment**: Full-text content acquisition from source documents
- **Mapping Judge**: LLM-based resolution for ambiguous dictionary mappings
- **Pattern**: Contract-first, evidence-based, source-type dispatched, feature-flagged
- **Type Safety**: Fully typed domain layer (documented exception for external runtime adapters in infrastructure)

### Security Hardening — Implemented
- **Row-Level Security**: PostgreSQL RLS policies on all kernel tables, context injection via `set_config()`
- **Column-Level Encryption**: AES-256-GCM for PHI identifiers with HMAC-SHA256 blind indexing, feature-flagged
- **Comprehensive Audit Logging**: Middleware auto-logging + explicit domain actions, query/export API, retention cleanup
- **Key Management**: Local env vars or GCP Secret Manager with caching

### Architecture Improvements
- **Clean Architecture**: Proper layer separation implemented across all modules
- **Intelligence Service Layers**: Five conceptual layers (Semantic, Identity, Truth, Governance, Interface) organising knowledge flow
- **Type Safety**: 100% MyPy compliance maintained with strict "Never Any" policy
- **Testing**: Comprehensive test suites with high coverage (unit, integration, migration)
- **CI/CD**: Automated quality gates and security scanning
- **Domain-Agnostic Design**: Source-type dispatch pattern enables multi-domain support without modifying domain contracts

## 📚 Key Documentation References

**🚨 TYPE SAFETY FIRST - Essential Reading:**

- **`docs/type_examples.md`**: **CRITICAL** - Complete type safety patterns, examples, and best practices
- **`src/type_definitions/`**: **Reference** - All existing TypedDict, Protocol, and union types
- **`tests/test_types/`**: **Reference** - Typed test fixtures, mocks, and test data patterns

**Master Architecture Roadmap (Single Source of Truth):**

- **`docs/latest_plan_path/datasources_architecture.md`**: **CANONICAL** - Complete platform architecture, Dictionary phases 1-7, Intelligence Service Layers, agent specifications, kernel pipeline, security hardening, known gaps, and gap closure checklist. **Always consult this document for the current state of the platform.**

**Project Architecture & Planning:**

- `docs/EngineeringArchitecture.md`: Detailed architectural roadmap and phase plans
- `data_sources_plan.md`: Complete Data Sources module specification
- `docs/goal.md`: Project mission and success criteria

**AI Agents (Artana):**

- `docs/artana-kernel/docs/agent_migration.md`: Runtime architecture and migration decisions
- `docs/artana-kernel/docs/kernel_contracts.md`: Contract-first AI patterns and schemas
- `docs/artana-kernel/docs/deep_traceability.md`: Traceability, debugging, and observability workflow
- `docs/artana-kernel/docs/Chapter5.md`: Advanced runtime and orchestration patterns

**Domain & UI:**

- `docs/curator.md`: Researcher curation workflows and UI patterns
- `docs/inboxUI/README.md`: Research Inbox and runtime architecture
- `docs/infra.md`: Infrastructure and deployment details

**Known Gaps & Future Work:**

Refer to `docs/latest_plan_path/datasources_architecture.md` (Known Gaps section and Gap Closure Checklist) for the authoritative list of remaining work. Key areas include:
- Governance Layer agent (approval routing, human-in-the-loop)
- Admin CRUD routes for Dictionary entity/relation types and value sets
- Next.js UI panels for kernel graph, dictionary management, and agent results
- Production observability (structured logging, metrics, trace exports)
- E2E integration tests across the full ingestion → graph → search pipeline

**Type Management Quick Reference:**
- **Never use `Any`** - strict policy for healthcare-grade software
- **Use existing types** from `src/type_definitions/` instead of creating new ones
- **JSON types**: `JSONObject`, `JSONValue` (use `list[JSONValue]` for arrays)
- **API responses**: `APIResponse`, `PaginatedResponse` for type-safe responses
- **Update operations**: `GeneUpdate`, `VariantUpdate`, etc. for partial updates
- **Agent contracts**: Extend `BaseAgentContract` — always include `confidence_score`, `rationale`, `evidence`
- **Test fixtures**: Always use `tests/test_types/fixtures.py` and `tests/test_types/mocks.py`

## 🎯 Development Philosophy

**"Build systems that are maintainable, testable, and evolvable. Type safety is not optional—it's foundational. Clean architecture enables confident refactoring and feature development."**

### Core Principles for AI Agents
- **First Principles**: Strip problems to core truths, challenge assumptions
- **Robust Solutions**: Always implement the most robust solution possible
- **Long-term Focus**: Design for maintainability and evolution over short-term gains
- **Quality First**: Never compromise on type safety or architectural principles

### Domain-Agnostic Design Principles
- **Universal Schema Engine**: The Dictionary is domain-agnostic — it defines entity types, relation types, value sets, and variables that can represent any domain (biomedical, sports, CS, etc.)
- **Source-Type Dispatch**: Agents and pipelines are parameterised by `source_type` — adding a new domain means adding new prompts/pipelines and dispatch entries, not modifying domain contracts or application services
- **Deterministic Core + Agent Overlay**: Every agent-driven operation has a deterministic fallback path, ensuring the system works without LLM availability
- **Research-Space Scoping**: All kernel operations are scoped to a `research_space_id`, enabling multi-tenant isolation

### Healthcare Domain Considerations
- **Patient Safety**: Medical data accuracy is critical - no shortcuts on validation
- **Privacy First**: HIPAA/compliance requirements built into every feature; PHI encrypted at rest with RLS enforcement
- **Auditability**: Every data operation is traceable via comprehensive audit logging (middleware + explicit domain actions)
- **Reliability**: 99.9%+ uptime requirements for healthcare systems

### AI Agent Guidelines
- **🚨 TYPE SAFETY FIRST**: Never use `Any` - this is a strict requirement for healthcare software
- **Context Awareness**: Consider the source type and domain constraints; agents are not hardcoded to a single domain
- **Type Management**: Use existing types from `src/type_definitions/` instead of creating new ones
- **JSON Handling**: Always use `JSONObject`, `JSONValue` (use `list[JSONValue]` for arrays)
- **API Responses**: Use `APIResponse`, `PaginatedResponse` for type-safe responses
- **Update Operations**: Use `GeneUpdate`, `VariantUpdate`, etc. TypedDict classes
- **Test Fixtures**: Always use `tests/test_types/fixtures.py` and `tests/test_types/mocks.py`
- **External APIs**: Validate responses using `src/infrastructure/validation/`
- **Testing**: Healthcare software requires extensive validation with typed fixtures
- **Documentation**: Clear docs prevent medical misinterpretation
- **Security**: Healthcare data demands fortress-level security practices

### AI Agent (Artana) Development Guidelines
- **Contract-First**: Always define domain contracts extending `BaseAgentContract` before implementation
- **Evidence-Based**: All agent outputs must include `confidence_score`, `rationale`, and `evidence`
- **Clean Architecture**: Domain contracts/ports in `src/domain/agents/`, implementations in `src/infrastructure/llm/`
- **Source-Type Dispatch**: Use `_PIPELINE_FACTORIES` and `_FALLBACK_FIELDS` dicts in adapters for multi-domain support
- **Feature Flags**: Gate agent endpoints via environment variables for safe incremental rollout
- **Governance Patterns**: Use confidence-based routing and human-in-the-loop escalation
- **Lifecycle Management**: Ensure adapters close clients/stores cleanly (`aclose`/`close`) after runs
- **State Backend**: Configure PostgreSQL backend with the `artana` schema for production
- **Factory Pattern**: Use factories for consistent agent configuration and model selection
- **Documented `Any` Exception**: External runtime adapters may require narrowly-scoped `Any`; keep confined to infrastructure, never in domain

### AI Agent Reasoning Techniques
Artana supports multiple execution styles - choose based on problem complexity:

| Reasoning Type | Artana Pattern | When to Use |
|----------------|-----------------|-------------|
| **Simple** | `SingleStepModelClient.step` | Direct query generation, bounded tasks |
| **Multi-Stage** | Deterministic app pipeline + per-stage model calls | Extraction + validation + persistence flows |
| **Branching / Search** | Harness workflows (`supervisor`, `incremental`) | Complex exploration and offline evaluation |
| **Native Reasoning** | Reasoning-capable model (`gpt-5-mini`, `gpt-5`) | Deep analysis with stronger reasoning models |

**See:** `docs/artana-kernel/docs/Chapter5.md` for runtime orchestration patterns

---

**This AGENTS.md serves as your comprehensive guide to building on the Artana Resource Library. For the authoritative platform roadmap, always consult `docs/latest_plan_path/datasources_architecture.md`. Follow these patterns to create reliable, type-safe, domain-agnostic, healthcare-grade software.**
