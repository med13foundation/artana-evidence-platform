"""
Test configuration and shared fixtures for Artana Resource Library tests.

Provides pytest fixtures, test database setup, and common test utilities
across unit, integration, and end-to-end tests.
"""

import os
from collections.abc import Generator
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_bootstrap_database_url = os.environ.get("DATABASE_URL", "")
if not _bootstrap_database_url.startswith("postgresql"):
    os.environ.setdefault("GRAPH_DB_SCHEMA", "public")
    os.environ.setdefault("ARTANA_EVIDENCE_API_DB_SCHEMA", "public")

_SRC_AVAILABLE = False
AuditLog = object
UserModel = object


def to_async_database_url(sync_url: str) -> str:
    replacements = (
        ("postgresql+psycopg2://", "postgresql+asyncpg://"),
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
    )
    for prefix, replacement in replacements:
        if sync_url.startswith(prefix):
            return sync_url.replace(prefix, replacement, 1)
    return sync_url


def resolve_async_database_url() -> str:
    async_override = os.getenv("ASYNC_DATABASE_URL")
    if async_override:
        return async_override
    return to_async_database_url(os.getenv("DATABASE_URL", TEST_DATABASE_URL))


def graph_schema_name(raw_value: str | None = None) -> str | None:
    schema = (
        raw_value if raw_value is not None else os.getenv("GRAPH_DB_SCHEMA", "graph_runtime")
    ).strip() or "graph_runtime"
    if schema == "public":
        return None
    return schema


def graph_postgres_search_path(raw_value: str | None = None) -> str:
    schema = graph_schema_name(raw_value)
    if schema is None:
        return "public"
    return f'"{schema}", public'


try:
    import artana_evidence_db.claim_relation_persistence_model  # noqa: F401

    # Load service-local mappings so the shared test engine can create graph
    # tables in the standalone graph-service test image.
    import artana_evidence_db.entity_embedding_model  # noqa: F401
    import artana_evidence_db.entity_lookup_models  # noqa: F401
    import artana_evidence_db.kernel_claim_models  # noqa: F401
    import artana_evidence_db.kernel_concept_models  # noqa: F401
    import artana_evidence_db.kernel_dictionary_models  # noqa: F401
    import artana_evidence_db.kernel_entity_models  # noqa: F401
    import artana_evidence_db.kernel_relation_models  # noqa: F401
    import artana_evidence_db.observation_persistence_model  # noqa: F401
    import artana_evidence_db.operation_run_models  # noqa: F401
    import artana_evidence_db.pack_seed_models  # noqa: F401
    import artana_evidence_db.provenance_model  # noqa: F401
    import artana_evidence_db.read_models  # noqa: F401
    import artana_evidence_db.reasoning_path_persistence_models  # noqa: F401
    import artana_evidence_db.relation_projection_source_model  # noqa: F401
    import artana_evidence_db.source_document_model  # noqa: F401
    import artana_evidence_db.space_models  # noqa: F401
    from artana_evidence_db.orm_base import Base
except ModuleNotFoundError:
    import artana_evidence_api.models.harness  # noqa: F401
    from artana_evidence_api.models.base import Base

# Test database configuration (absolute path to avoid divergent relative paths)
# Support pytest-xdist by using unique database files per worker

worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
process_id = os.getpid()
db_suffix_parts = [part for part in (worker_id, str(process_id)) if part]
db_filename = f"test_med13_{'_'.join(db_suffix_parts)}.db"
TEST_DB_PATH = Path.cwd() / db_filename
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"
TEST_ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

# Set core env vars early so imports (e.g., SessionLocal) bind to the test DB.
_existing_database_url = os.environ.get("DATABASE_URL", "")
if _existing_database_url.startswith("postgresql"):
    os.environ.setdefault("GRAPH_DATABASE_URL", _existing_database_url)
    os.environ.setdefault("GRAPH_DB_SCHEMA", "graph_runtime")
    os.environ.setdefault("ARTANA_EVIDENCE_API_DB_SCHEMA", "artana_evidence_api")
else:
    os.environ.setdefault("GRAPH_DATABASE_URL", TEST_DATABASE_URL)
    os.environ["GRAPH_DB_SCHEMA"] = "public"
    os.environ["ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
    os.environ["ARTANA_EVIDENCE_API_DATABASE_URL"] = TEST_DATABASE_URL

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("ASYNC_DATABASE_URL", TEST_ASYNC_DATABASE_URL)
os.environ.setdefault("TESTING", "true")
os.environ.setdefault(
    "AUTH_JWT_SECRET",
    "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
)
os.environ.setdefault(
    "GRAPH_JWT_SECRET",
    "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
)
os.environ.setdefault("GRAPH_SERVICE_RELOAD", "0")
os.environ.setdefault("ARTANA_ENABLE_DICTIONARY_SEARCH_HARNESS", "0")


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


# Configure pytest-asyncio to use auto mode
# With asyncio_mode = auto in pytest.ini, pytest-asyncio automatically
# manages event loops, so we don't need an explicit event_loop fixture


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine."""
    active_database_url = os.environ.get("DATABASE_URL", TEST_DATABASE_URL)
    engine_kwargs: dict[str, object]
    if active_database_url.startswith("postgresql"):
        engine_kwargs = {"future": True, "pool_pre_ping": True}
    else:
        engine_kwargs = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }

    test_engine = create_engine(active_database_url, **engine_kwargs)
    if active_database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=test_engine)
    elif active_database_url.startswith("postgresql"):
        graph_schema = graph_schema_name()
        if graph_schema is not None:

            @event.listens_for(test_engine, "connect")
            def _set_test_graph_search_path(
                dbapi_connection: object,
                _connection_record: object,
            ) -> None:
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(
                        f"SET search_path TO {graph_postgres_search_path(graph_schema)}",
                    )
                finally:
                    cursor.close()

        _prepare_postgres_graph_schema(test_engine)
        Base.metadata.create_all(bind=test_engine)
    yield test_engine
    if active_database_url.startswith("sqlite"):
        Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session]:
    """Provide a database session for tests."""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _apply_test_environment(existing_db_url: str) -> None:
    use_postgres = existing_db_url.startswith("postgresql")
    if not use_postgres:
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL
        os.environ["ASYNC_DATABASE_URL"] = TEST_ASYNC_DATABASE_URL
        os.environ["GRAPH_DATABASE_URL"] = TEST_DATABASE_URL
        os.environ["ARTANA_EVIDENCE_API_DATABASE_URL"] = TEST_DATABASE_URL
        os.environ["GRAPH_DB_SCHEMA"] = "public"
        os.environ["ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
    elif not os.environ.get("ASYNC_DATABASE_URL"):
        os.environ["ASYNC_DATABASE_URL"] = to_async_database_url(existing_db_url)
    if use_postgres:
        os.environ["GRAPH_DATABASE_URL"] = existing_db_url
        os.environ.setdefault("GRAPH_DB_SCHEMA", "graph_runtime")
        os.environ.setdefault("ARTANA_EVIDENCE_API_DB_SCHEMA", "artana_evidence_api")

    os.environ["TESTING"] = "true"
    os.environ["AUTH_JWT_SECRET"] = (
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    )
    os.environ["GRAPH_JWT_SECRET"] = (
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    )
    os.environ["GRAPH_SERVICE_RELOAD"] = "0"


def _prepare_postgres_graph_schema(engine) -> None:
    graph_schema = graph_schema_name()
    with engine.begin() as connection:
        if graph_schema is not None:
            connection.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{graph_schema}"'),
            )
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


def _wire_container_dependencies() -> None:
    return None


def _propagate_session_local(session_module: ModuleType) -> None:
    import sys

    for module_name in ("tests.e2e.test_curation_detail_endpoint",):
        if module_name not in sys.modules:
            try:
                __import__(module_name)
            except ImportError:
                continue
        module = sys.modules.get(module_name)
        if module:
            module.SessionLocal = session_module.SessionLocal
            module.engine = session_module.engine


def _wire_sync_session() -> None:
    return None


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    original_env = os.environ.copy()

    existing_db_url = os.environ.get("DATABASE_URL", "")
    _apply_test_environment(existing_db_url)
    _wire_container_dependencies()
    _wire_sync_session()

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(scope="session")
def postgres_required():
    """Skip test if PostgreSQL is not available."""
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL required")


@pytest.fixture
def sample_gene_data():
    """Provide sample gene data for testing."""
    return {
        "gene_id": "MED13_TEST",
        "symbol": "MED13",
        "name": "Mediator complex subunit 13",
        "description": "Test gene for MED13",
        "gene_type": "protein_coding",
        "chromosome": "17",
        "start_position": 60000000,
        "end_position": 60010000,
        "ensembl_id": "ENSG00000108510",
        "ncbi_gene_id": 9968,
        "uniprot_id": "Q9UHV7",
    }


@pytest.fixture
def sample_variant_data():
    """Provide sample variant data for testing."""
    return {
        "variant_id": "VCV000000001",
        "clinvar_id": "RCV000000001",
        "variation_name": "c.123A>G",
        "gene_references": ["MED13"],
        "clinical_significance": "Pathogenic",
        "chromosome": "17",
        "start_position": 60001234,
        "hgvs_notations": {"c": "c.123A>G", "p": "p.Arg41Gly"},
    }


@pytest.fixture
def sample_phenotype_data():
    """Provide sample phenotype data for testing."""
    return {
        "hpo_id": "HP:0001249",
        "hpo_term": "Intellectual disability",
        "definition": "Subnormal intellectual functioning",
        "category": "Clinical",
        "gene_references": ["MED13"],
    }


@pytest.fixture
def sample_provenance():
    """Provide sample provenance data for testing."""
    pytest.skip(
        "Monolith provenance model is unavailable in service-only test images",
    )


@pytest.fixture
def mock_api_response():
    """Provide a mock API response fixture."""

    class MockResponse:
        def __init__(self, status_code=200, json_data=None, text=""):
            self.status_code = status_code
            self.json_data = json_data or {}
            self.text = text

        def json(self):
            return self.json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    return MockResponse


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")
    config.addinivalue_line(
        "markers",
        "graph: marks tests as graph and claim-ledger invariant coverage",
    )


# Test data fixtures
@pytest.fixture
def test_data_factory():
    """Factory for creating test data of various types."""

    def create_data(data_type: str, **kwargs):
        factories = {
            "gene": lambda: {
                "gene_id": kwargs.get("gene_id", "TEST001"),
                "symbol": kwargs.get("symbol", "TEST"),
                "name": kwargs.get("name", "Test Gene"),
                "gene_type": kwargs.get("gene_type", "protein_coding"),
                **kwargs,
            },
            "variant": lambda: {
                "variant_id": kwargs.get("variant_id", "VCV000TEST"),
                "clinvar_id": kwargs.get("clinvar_id", "RCV000TEST"),
                "variation_name": kwargs.get("variation_name", "c.123A>G"),
                "gene_references": kwargs.get("gene_references", ["TEST"]),
                **kwargs,
            },
            "phenotype": lambda: {
                "hpo_id": kwargs.get("hpo_id", "HP:000TEST"),
                "hpo_term": kwargs.get("hpo_term", "Test phenotype"),
                "gene_references": kwargs.get("gene_references", ["TEST"]),
                **kwargs,
            },
        }

        factory = factories.get(data_type)
        if not factory:
            raise ValueError(f"Unknown data type: {data_type}")

        return factory()

    return create_data


# Database cleanup utilities
@pytest.fixture(autouse=True)
def clean_database(db_session):
    """Automatically clean database between tests."""
    # This runs before each test
    yield
    # This runs after each test
    db_session.rollback()


# Custom test markers
@pytest.fixture
def skip_if_no_database():
    """Skip test if database is not available."""
    pytest.skip(
        "Monolith database session is unavailable in service-only test images",
    )


@pytest.fixture
def skip_if_no_external_api():
    """Skip test if external APIs are not available."""
    if os.getenv("SKIP_EXTERNAL_TESTS"):
        pytest.skip("External API tests disabled")
