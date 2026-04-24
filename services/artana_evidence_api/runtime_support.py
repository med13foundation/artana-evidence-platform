"""Service-local runtime support for graph-harness LLM orchestration."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
import tomllib
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

_ARTANA_IMPORT_ERROR: Exception | None = None
_ARTANA_MODEL_IMPORT_ERROR: Exception | None = None

try:
    from artana.store import PostgresStore
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_IMPORT_ERROR = exc

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_MODEL_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent / "artana.toml"
_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_ENV_RUNTIME_ROLE = "ARTANA_RUNTIME_ROLE"
_ENV_ARTANA_POOL_MIN_SIZE = "ARTANA_POOL_MIN_SIZE"
_ENV_ARTANA_POOL_MAX_SIZE = "ARTANA_POOL_MAX_SIZE"
_ENV_ARTANA_COMMAND_TIMEOUT_SECONDS = "ARTANA_COMMAND_TIMEOUT_SECONDS"
_MODEL_HEALTH_CACHE_TTL_SECONDS = 60.0
_MODEL_HEALTH_PROBE_TIMEOUT_SECONDS = 10.0
_MODEL_HEALTH_PROBE_MAX_RETRIES = 0
_DEFAULT_API_POOL_MIN_SIZE = 1
_DEFAULT_API_POOL_MAX_SIZE = 1
_DEFAULT_SCHEDULER_POOL_MIN_SIZE = 1
_DEFAULT_SCHEDULER_POOL_MAX_SIZE = 2
_DEFAULT_COMBINED_POOL_MIN_SIZE = 1
_DEFAULT_COMBINED_POOL_MAX_SIZE = 2
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 30.0
_DEFAULT_POSTGRES_HOST = os.getenv("ARTANA_POSTGRES_HOST", "localhost")
_DEFAULT_POSTGRES_PORT = os.getenv("ARTANA_POSTGRES_PORT", "5432")
_DEFAULT_POSTGRES_DB = os.getenv("ARTANA_POSTGRES_DB", "artana_dev")
_DEFAULT_POSTGRES_USER = os.getenv("ARTANA_POSTGRES_USER", "artana_dev")
_DEFAULT_POSTGRES_PASSWORD = os.getenv(
    "ARTANA_POSTGRES_PASSWORD",
    "artana_dev_password",
)
_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://"
    f"{_DEFAULT_POSTGRES_USER}:{_DEFAULT_POSTGRES_PASSWORD}"
    f"@{_DEFAULT_POSTGRES_HOST}:{_DEFAULT_POSTGRES_PORT}/{_DEFAULT_POSTGRES_DB}"
)
_SHARED_STORE_LOCK = Lock()
_MODEL_HEALTH_LOCK = Lock()


def configure_litellm_runtime_logging() -> None:
    """Quiet LiteLLM's default stderr noise unless the caller opted in."""
    try:
        litellm = importlib.import_module("litellm")
        litellm_logging = importlib.import_module("litellm._logging")
    except ImportError:
        return

    with suppress(AttributeError):
        vars(litellm)["suppress_debug_info"] = True

    if os.getenv("LITELLM_LOG") is not None:
        return

    if hasattr(litellm_logging, "verbose_logger"):
        verbose_logger = litellm_logging.verbose_logger
        verbose_logger.setLevel(logging.CRITICAL)
        handlers = (
            verbose_logger.handlers if hasattr(verbose_logger, "handlers") else ()
        )
        for current_handler in handlers:
            current_handler.setLevel(logging.CRITICAL)

    if hasattr(litellm_logging, "handler"):
        current_handler = litellm_logging.handler
        current_handler.setLevel(logging.CRITICAL)


configure_litellm_runtime_logging()


class ModelCapability(str, Enum):
    """Capabilities used by graph-harness runtime model selection."""

    QUERY_GENERATION = "query_generation"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    CURATION = "curation"
    JUDGE = "judge"


class ModelSpec(BaseModel):
    """Minimal model registry entry required by graph-harness runtimes."""

    model_id: str
    capabilities: frozenset[ModelCapability] = Field(default_factory=frozenset)
    timeout_seconds: float = Field(default=30.0, gt=0)
    is_enabled: bool = True

    model_config = {"frozen": True}

    def supports_capability(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities


class ArtanaModelRegistry:
    """Service-local registry loader for graph-harness runtime models."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path) if config_path else _CONFIG_PATH
        self._models: dict[str, ModelSpec] = {}
        self._defaults: dict[ModelCapability, str] = {}
        self._allow_runtime_model_overrides = False
        self._load_configuration()

    def _load_configuration(self) -> None:
        config = _read_artana_toml(str(self._config_path))
        models_section = config.get("models", {})
        if not isinstance(models_section, dict):
            return
        self._models = self._parse_models(models_section)
        self._defaults = self._parse_defaults(models_section)
        raw_allow_overrides = models_section.get("allow_runtime_model_overrides")
        self._allow_runtime_model_overrides = (
            raw_allow_overrides if isinstance(raw_allow_overrides, bool) else False
        )

    def _parse_models(self, models_section: dict[str, object]) -> dict[str, ModelSpec]:
        models: dict[str, ModelSpec] = {}
        registry = models_section.get("registry", {})
        if not isinstance(registry, dict):
            return models
        for model_id, raw_spec in registry.items():
            if not isinstance(raw_spec, dict):
                continue
            raw_capabilities = raw_spec.get("capabilities", [])
            capabilities = frozenset(
                ModelCapability(value)
                for value in raw_capabilities
                if isinstance(value, str)
                and value in ModelCapability._value2member_map_
            )
            models[model_id] = ModelSpec(
                model_id=model_id,
                capabilities=capabilities,
                timeout_seconds=float(raw_spec.get("timeout_seconds", 30.0)),
                is_enabled=bool(raw_spec.get("is_enabled", True)),
            )
        return models

    def _parse_defaults(
        self,
        models_section: dict[str, object],
    ) -> dict[ModelCapability, str]:
        defaults: dict[ModelCapability, str] = {}
        capability_map = {
            "default_query_generation": ModelCapability.QUERY_GENERATION,
            "default_evidence_extraction": ModelCapability.EVIDENCE_EXTRACTION,
            "default_curation": ModelCapability.CURATION,
            "default_judge": ModelCapability.JUDGE,
        }
        for config_key, capability in capability_map.items():
            value = models_section.get(config_key)
            if isinstance(value, str):
                defaults[capability] = value
        return defaults

    def get_model(self, model_id: str) -> ModelSpec:
        if model_id not in self._models:
            available = list(self._models.keys())
            message = f"Model '{model_id}' not found. Available: {available}"
            raise KeyError(message)
        return self._models[model_id]

    def get_default_model(self, capability: ModelCapability) -> ModelSpec:
        env_key = f"ARTANA_AI_{capability.value.upper()}_MODEL"
        env_model = os.getenv(env_key)
        if isinstance(env_model, str) and env_model in self._models:
            model = self._models[env_model]
            if model.is_enabled and model.supports_capability(capability):
                return model

        default_id = self._defaults.get(capability)
        if isinstance(default_id, str) and default_id in self._models:
            model = self._models[default_id]
            if model.is_enabled and model.supports_capability(capability):
                return model

        for model in self._models.values():
            if model.is_enabled and model.supports_capability(capability):
                return model

        message = f"No model available for capability: {capability.value}"
        raise ValueError(message)

    def validate_model_for_capability(
        self,
        model_id: str,
        capability: ModelCapability,
    ) -> bool:
        if model_id not in self._models:
            return False
        model = self._models[model_id]
        return model.is_enabled and model.supports_capability(capability)

    def allow_runtime_model_overrides(self) -> bool:
        raw_env = os.getenv("ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES")
        if isinstance(raw_env, str):
            normalized = raw_env.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return self._allow_runtime_model_overrides


@dataclass(frozen=True)
class UsageLimits:
    """Usage limits for graph-harness runtime operations."""

    total_cost_usd: float | None = None
    max_turns: int | None = None
    max_tokens: int | None = None

    @classmethod
    def from_environment(cls) -> UsageLimits:
        cost_raw = os.getenv("ARTANA_USAGE_COST_LIMIT")
        turns_raw = os.getenv("ARTANA_USAGE_MAX_TURNS")
        tokens_raw = os.getenv("ARTANA_USAGE_MAX_TOKENS")
        return cls(
            total_cost_usd=float(cost_raw) if cost_raw else 1.0,
            max_turns=int(turns_raw) if turns_raw else 10,
            max_tokens=int(tokens_raw) if tokens_raw else 8192,
        )


@dataclass(frozen=True)
class GovernanceConfig:
    """Minimal governance settings used by graph-harness runtimes."""

    usage_limits: UsageLimits = field(default_factory=UsageLimits.from_environment)

    @classmethod
    def from_environment(cls) -> GovernanceConfig:
        return cls(usage_limits=UsageLimits.from_environment())


ReplayPolicy = Literal["strict", "allow_prompt_drift", "fork_on_drift"]
_DEFAULT_REPLAY_POLICY: ReplayPolicy = "fork_on_drift"


@dataclass(frozen=True)
class ArtanaRuntimePolicy:
    """Global runtime settings that must remain deterministic across runs."""

    replay_policy: ReplayPolicy = _DEFAULT_REPLAY_POLICY
    extraction_config_version: str = "v1"
    context_system_prompt_hash: str | None = None
    context_builder_version: str | None = None
    context_compaction_version: str | None = None


class ModelHealthProbeResult(BaseModel):
    """Health result for the configured artana-kernel model probe."""

    model_config = ConfigDict(strict=True, frozen=True)

    status: Literal["healthy", "degraded", "unknown"]
    model_id: str | None = None
    capability: str
    timeout_seconds: float | None = None
    latency_seconds: float | None = None
    checked_at: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ArtanaPostgresStoreConfig:
    """Resolved process-local Artana Postgres store configuration."""

    dsn: str
    min_pool_size: int
    max_pool_size: int
    command_timeout_seconds: float


@dataclass
class _SharedStoreState:
    store: PostgresStore | None = None
    config: ArtanaPostgresStoreConfig | None = None


_SHARED_STORE_STATE = _SharedStoreState()


@dataclass
class _ModelHealthState:
    result: ModelHealthProbeResult | None = None
    refreshed_at: float = 0.0


_MODEL_HEALTH_STATE = _ModelHealthState()


def _read_artana_toml(config_path: str | None = None) -> dict[str, object]:
    path = Path(config_path) if config_path else _CONFIG_PATH
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    return loaded if isinstance(loaded, dict) else {}


@lru_cache(maxsize=1)
def get_model_registry() -> ArtanaModelRegistry:
    return ArtanaModelRegistry()


@lru_cache(maxsize=1)
def load_runtime_policy(config_path: str | None = None) -> ArtanaRuntimePolicy:
    config = _read_artana_toml(config_path)
    runtime_section = config.get("runtime", {})
    if not isinstance(runtime_section, dict):
        runtime_section = {}
    replay_policy = _resolve_replay_policy(
        os.getenv("ARTANA_REPLAY_POLICY"),
        runtime_section.get("replay_policy"),
    )
    return ArtanaRuntimePolicy(
        replay_policy=replay_policy,
        extraction_config_version=_resolve_string(
            os.getenv("ARTANA_EXTRACTION_CONFIG_VERSION"),
            runtime_section.get("extraction_config_version"),
            default="v1",
        ),
        context_system_prompt_hash=_resolve_optional_string(
            os.getenv("ARTANA_CONTEXT_SYSTEM_PROMPT_HASH"),
            runtime_section.get("context_system_prompt_hash"),
        ),
        context_builder_version=_resolve_optional_string(
            os.getenv("ARTANA_CONTEXT_BUILDER_VERSION"),
            runtime_section.get("context_builder_version"),
        ),
        context_compaction_version=_resolve_optional_string(
            os.getenv("ARTANA_CONTEXT_COMPACTION_VERSION"),
            runtime_section.get("context_compaction_version"),
        ),
    )


def _resolve_replay_policy(
    env_value: str | None,
    config_value: object,
) -> ReplayPolicy:
    for raw_value in (env_value, config_value):
        normalized = _normalize_replay_policy(raw_value)
        if normalized is not None:
            return normalized
    return _DEFAULT_REPLAY_POLICY


def _normalize_replay_policy(raw_value: object) -> ReplayPolicy | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip().lower()
    if normalized == "strict":
        return "strict"
    if normalized == "allow_prompt_drift":
        return "allow_prompt_drift"
    if normalized == "fork_on_drift":
        return "fork_on_drift"
    return None


def _resolve_string(
    env_value: str | None,
    config_value: object,
    *,
    default: str,
) -> str:
    for raw_value in (env_value, config_value):
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                return normalized
    return default


def _resolve_optional_string(env_value: str | None, config_value: object) -> str | None:
    for raw_value in (env_value, config_value):
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                return normalized
    return None


def resolve_configured_openai_api_key() -> str | None:
    raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized or normalized.lower() in _INVALID_OPENAI_KEYS:
        return None
    return normalized


def has_configured_openai_api_key() -> bool:
    return resolve_configured_openai_api_key() is not None


def stable_sha256_digest(payload: str, *, length: int = 24) -> str:
    import hashlib

    normalized_length = max(length, 1)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:normalized_length]


def normalize_litellm_model_id(model_id: str) -> str:
    """Convert registry provider:model ids into LiteLLM execution ids."""
    normalized = model_id.strip()
    if ":" not in normalized:
        return normalized
    provider, model_name = normalized.split(":", 1)
    if provider.strip() == "" or model_name.strip() == "":
        return normalized
    return f"{provider.strip()}/{model_name.strip()}"


def _resolve_default_pool_bounds() -> tuple[int, int]:
    runtime_role = os.getenv(_ENV_RUNTIME_ROLE, "all").strip().lower()
    if runtime_role == "api":
        return _DEFAULT_API_POOL_MIN_SIZE, _DEFAULT_API_POOL_MAX_SIZE
    if runtime_role == "scheduler":
        return _DEFAULT_SCHEDULER_POOL_MIN_SIZE, _DEFAULT_SCHEDULER_POOL_MAX_SIZE
    return _DEFAULT_COMBINED_POOL_MIN_SIZE, _DEFAULT_COMBINED_POOL_MAX_SIZE


def _read_positive_int_env(env_name: str, *, default_value: int) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return default_value
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        logger.warning(
            "Invalid Artana pool override %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive Artana pool override %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def _read_positive_float_env(env_name: str, *, default_value: float) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return default_value
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        logger.warning(
            "Invalid Artana timeout override %s=%r; using default %.1f",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive Artana timeout override %s=%r; using default %.1f",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def _resolve_database_url() -> str:
    return os.getenv(
        "ARTANA_EVIDENCE_API_DATABASE_URL",
        os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL),
    )


def resolve_artana_state_uri() -> str:
    explicit_uri = os.getenv("ARTANA_STATE_URI")
    if explicit_uri:
        return explicit_uri
    return _add_artana_schema(_normalize_postgres_dsn(_resolve_database_url()))


def _normalize_postgres_dsn(database_url: str) -> str:
    replacements = (
        ("postgresql+psycopg2://", "postgresql://"),
        ("postgresql+psycopg://", "postgresql://"),
        ("postgresql+asyncpg://", "postgresql://"),
    )
    for prefix, replacement in replacements:
        if database_url.startswith(prefix):
            return database_url.replace(prefix, replacement, 1)
    return database_url


def _add_artana_schema(postgres_url: str) -> str:
    split = urlsplit(postgres_url)
    query_items = parse_qsl(split.query, keep_blank_values=True)

    existing_options = [value for key, value in query_items if key == "options"]
    if existing_options:
        new_options = f"{existing_options[0]} -c search_path=artana,public"
        query_items = [(key, value) for key, value in query_items if key != "options"]
        query_items.append(("options", new_options))
    else:
        query_items.append(("options", "-c search_path=artana,public"))

    rebuilt_query = urlencode(query_items, doseq=True)
    return urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            rebuilt_query,
            split.fragment,
        ),
    )


def resolve_artana_postgres_store_config() -> ArtanaPostgresStoreConfig:
    default_min_pool_size, default_max_pool_size = _resolve_default_pool_bounds()
    min_pool_size = _read_positive_int_env(
        _ENV_ARTANA_POOL_MIN_SIZE,
        default_value=default_min_pool_size,
    )
    max_pool_size = _read_positive_int_env(
        _ENV_ARTANA_POOL_MAX_SIZE,
        default_value=default_max_pool_size,
    )
    if max_pool_size < min_pool_size:
        logger.warning(
            "Artana pool max (%d) is below min (%d); clamping max to min",
            max_pool_size,
            min_pool_size,
        )
        max_pool_size = min_pool_size
    return ArtanaPostgresStoreConfig(
        dsn=resolve_artana_state_uri(),
        min_pool_size=min_pool_size,
        max_pool_size=max_pool_size,
        command_timeout_seconds=_read_positive_float_env(
            _ENV_ARTANA_COMMAND_TIMEOUT_SECONDS,
            default_value=_DEFAULT_COMMAND_TIMEOUT_SECONDS,
        ),
    )


def create_artana_postgres_store() -> PostgresStore:
    """Create one request-local Artana PostgresStore."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        message = (
            "artana-kernel is required for Artana state storage. Install "
            "dependency 'artana-kernel @ git+https://github.com/"
            "aandresalvarez/artana-kernel.git@"
            "5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(message) from _ARTANA_IMPORT_ERROR

    resolved_config = resolve_artana_postgres_store_config()
    return PostgresStore(
        resolved_config.dsn,
        min_pool_size=resolved_config.min_pool_size,
        max_pool_size=resolved_config.max_pool_size,
        command_timeout_seconds=resolved_config.command_timeout_seconds,
    )


def get_shared_artana_postgres_store() -> PostgresStore:
    """Return the process-local Artana store singleton.

    The Artana PostgresStore is event-loop affine, so sharing it across loops in
    the same process is unsafe. The API no longer executes harness logic on the
    request loop; queue-first routes hand work to the worker, and the worker
    owns the stable loop that uses this singleton.
    """
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        message = (
            "artana-kernel is required for shared Artana state storage. Install "
            "dependency 'artana-kernel @ git+https://github.com/"
            "aandresalvarez/artana-kernel.git@"
            "5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(message) from _ARTANA_IMPORT_ERROR

    resolved_config = resolve_artana_postgres_store_config()
    with _SHARED_STORE_LOCK:
        if _SHARED_STORE_STATE.store is not None:
            if resolved_config == _SHARED_STORE_STATE.config:
                return _SHARED_STORE_STATE.store
            logger.warning(
                "Shared Artana PostgresStore already initialized with %s; "
                "ignoring later config change to %s for this process",
                _SHARED_STORE_STATE.config,
                resolved_config,
            )
            return _SHARED_STORE_STATE.store
        _SHARED_STORE_STATE.store = PostgresStore(
            resolved_config.dsn,
            min_pool_size=resolved_config.min_pool_size,
            max_pool_size=resolved_config.max_pool_size,
            command_timeout_seconds=resolved_config.command_timeout_seconds,
        )
        _SHARED_STORE_STATE.config = resolved_config
        return _SHARED_STORE_STATE.store


async def close_shared_artana_postgres_store() -> None:
    with _SHARED_STORE_LOCK:
        store = _SHARED_STORE_STATE.store
        _SHARED_STORE_STATE.store = None
        _SHARED_STORE_STATE.config = None
    if store is None:
        return
    try:
        await store.close()
    except Exception:  # noqa: BLE001
        logger.warning("Shared Artana PostgresStore close failed", exc_info=True)


def close_shared_artana_postgres_store_sync() -> None:
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(close_shared_artana_postgres_store())
        return
    running_loop.create_task(close_shared_artana_postgres_store())


def _resolve_model_health_timeout(model_timeout_seconds: float | None) -> float:
    if model_timeout_seconds is None:
        return _MODEL_HEALTH_PROBE_TIMEOUT_SECONDS
    return min(max(model_timeout_seconds, 1.0), _MODEL_HEALTH_PROBE_TIMEOUT_SECONDS)


def _build_model_probe_pending_result() -> ModelHealthProbeResult:
    model_id: str | None = None
    timeout_seconds: float | None = None
    detail = "Model probe has not completed in this process yet."
    try:
        registry = get_model_registry()
        model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
        model_id = normalize_litellm_model_id(model_spec.model_id)
        timeout_seconds = _resolve_model_health_timeout(model_spec.timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        detail = f"{detail} {exc}"
    return ModelHealthProbeResult(
        status="unknown",
        model_id=model_id,
        capability=ModelCapability.EVIDENCE_EXTRACTION.value,
        timeout_seconds=timeout_seconds,
        checked_at=datetime.now(tz=UTC).isoformat(),
        detail=detail,
    )


def build_model_health_probe_output_schema() -> type[BaseModel]:
    """Build the structured output schema for the health probe."""

    class _ProbeOutput(BaseModel):
        model_config = ConfigDict(strict=True)

        status: Literal["ok"] = Field(default="ok")

    return _ProbeOutput


async def _run_model_health_probe(
    *,
    model_id: str,
    timeout_seconds: float,
) -> ModelHealthProbeResult:
    from uuid import uuid4

    output_schema = build_model_health_probe_output_schema()

    # The probe runs under its own short-lived event loop via asyncio.run().
    # Using the process-shared store here can bind the store on one loop and
    # then close it from another, which trips Artana's loop-affinity guard.
    kernel = ArtanaKernel(
        store=create_artana_postgres_store(),
        model_port=LiteLLMAdapter(
            timeout_seconds=timeout_seconds,
            max_retries=_MODEL_HEALTH_PROBE_MAX_RETRIES,
        ),
    )
    client = SingleStepModelClient(kernel=kernel)
    started_at = time.perf_counter()
    try:
        await client.step(
            run_id=f"model-health:{uuid4()}",
            tenant=TenantContext(
                tenant_id="model-health",
                capabilities=frozenset(),
                budget_usd_limit=0.1,
            ),
            model=model_id,
            prompt=(
                "Return JSON with the exact field `status` set to `ok` and nothing else."
            ),
            output_schema=output_schema,
            step_key="model_health.probe.v1",
            replay_policy="fork_on_drift",
        )
    finally:
        await kernel.close()

    return ModelHealthProbeResult(
        status="healthy",
        model_id=model_id,
        capability=ModelCapability.EVIDENCE_EXTRACTION.value,
        timeout_seconds=timeout_seconds,
        latency_seconds=time.perf_counter() - started_at,
        checked_at=datetime.now(tz=UTC).isoformat(),
        detail="Model probe completed successfully.",
    )


def get_artana_model_health(*, refresh: bool = False) -> ModelHealthProbeResult:
    """Return the cached or freshly probed model health for the service."""
    with _MODEL_HEALTH_LOCK:
        cached = _MODEL_HEALTH_STATE.result
        cached_age = time.monotonic() - _MODEL_HEALTH_STATE.refreshed_at
        if (
            not refresh
            and cached is not None
            and cached_age < _MODEL_HEALTH_CACHE_TTL_SECONDS
        ):
            return cached
        if not refresh and cached is None:
            result = _build_model_probe_pending_result()
            _MODEL_HEALTH_STATE.result = result
            _MODEL_HEALTH_STATE.refreshed_at = time.monotonic()
            return result

    if _ARTANA_IMPORT_ERROR is not None or _ARTANA_MODEL_IMPORT_ERROR is not None:
        result = ModelHealthProbeResult(
            status="unknown",
            capability=ModelCapability.EVIDENCE_EXTRACTION.value,
            detail="artana-kernel is unavailable in this environment.",
        )
    elif not has_configured_openai_api_key():
        registry = get_model_registry()
        try:
            model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
            default_model_id = normalize_litellm_model_id(model_spec.model_id)
            default_timeout_seconds = _resolve_model_health_timeout(
                model_spec.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            result = ModelHealthProbeResult(
                status="unknown",
                capability=ModelCapability.EVIDENCE_EXTRACTION.value,
                detail=str(exc),
            )
        else:
            result = ModelHealthProbeResult(
                status="degraded",
                model_id=default_model_id,
                capability=ModelCapability.EVIDENCE_EXTRACTION.value,
                timeout_seconds=default_timeout_seconds,
                detail="OPENAI_API_KEY is not configured.",
            )
    else:
        model_id: str | None = None
        timeout_seconds: float | None = None
        try:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
            model_id = normalize_litellm_model_id(model_spec.model_id)
            timeout_seconds = _resolve_model_health_timeout(model_spec.timeout_seconds)
            result = asyncio.run(
                _run_model_health_probe(
                    model_id=model_id,
                    timeout_seconds=timeout_seconds,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Artana model health probe failed",
                extra={
                    "model_id": model_id,
                    "timeout_seconds": timeout_seconds,
                    "exception_type": type(exc).__name__,
                },
            )
            result = ModelHealthProbeResult(
                status="degraded",
                model_id=model_id,
                capability=ModelCapability.EVIDENCE_EXTRACTION.value,
                timeout_seconds=timeout_seconds,
                checked_at=datetime.now(tz=UTC).isoformat(),
                detail=str(exc),
            )

    with _MODEL_HEALTH_LOCK:
        _MODEL_HEALTH_STATE.result = result
        _MODEL_HEALTH_STATE.refreshed_at = time.monotonic()
    return result


__all__ = [
    "ArtanaModelRegistry",
    "ArtanaPostgresStoreConfig",
    "ArtanaRuntimePolicy",
    "GovernanceConfig",
    "ModelCapability",
    "ModelSpec",
    "ReplayPolicy",
    "UsageLimits",
    "ModelHealthProbeResult",
    "build_model_health_probe_output_schema",
    "close_shared_artana_postgres_store",
    "close_shared_artana_postgres_store_sync",
    "create_artana_postgres_store",
    "get_artana_model_health",
    "get_model_registry",
    "get_shared_artana_postgres_store",
    "has_configured_openai_api_key",
    "load_runtime_policy",
    "normalize_litellm_model_id",
    "resolve_artana_postgres_store_config",
    "resolve_artana_state_uri",
    "resolve_configured_openai_api_key",
    "stable_sha256_digest",
]
