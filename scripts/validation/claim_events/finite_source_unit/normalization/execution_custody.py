"""Immutable issued-contract custody for source-unit agent execution."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType, ModuleType
from typing import TYPE_CHECKING, Protocol, cast

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitExtractionResult,
    SourceUnitPromptPolicy,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
        SourceUnitNormalizationOutput,
        SourceUnitNormalizedReviewOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.review import (
        NormalizedReviewBinder,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        ExtractionPromptBuilder,
        VerificationPromptBuilder,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


class IssuedExecutionContractBoundaryError(RuntimeError):
    """An issued contract crossed a caller-composed execution boundary."""


class NormalizationPromptBuilder(Protocol):
    """Build normalization input only after extraction is frozen."""

    def __call__(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
    ) -> str: ...


class NormalizedReviewPromptBuilder(Protocol):
    """Build review input only after both preceding stages are frozen."""

    def __call__(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
        normalized: SourceUnitNormalizationResult,
    ) -> str: ...


class IssuedExecutionPolicy(Protocol):
    """Provider-visible components of one issued execution policy."""

    @property
    def contract_version(self) -> str: ...

    @property
    def extraction_prompt_policy(self) -> SourceUnitPromptPolicy: ...

    @property
    def normalization_prompt_builder(self) -> NormalizationPromptBuilder: ...

    @property
    def normalization_prompt_version(self) -> str: ...

    @property
    def normalization_output_schema(self) -> type[SourceUnitNormalizationOutput]: ...

    @property
    def review_prompt_builder(self) -> NormalizedReviewPromptBuilder: ...

    @property
    def review_prompt_version(self) -> str: ...

    @property
    def review_output_schema(self) -> type[SourceUnitNormalizedReviewOutput]: ...

    @property
    def review_binder(self) -> NormalizedReviewBinder: ...


@dataclass(frozen=True, slots=True)
class IssuedExecutionSnapshot:
    """Private immutable execution components captured during registration."""

    extraction_prompt_policy: SourceUnitPromptPolicy
    normalization_prompt_builder: NormalizationPromptBuilder
    normalization_prompt_version: str
    normalization_output_schema: type[SourceUnitNormalizationOutput]
    review_prompt_builder: NormalizedReviewPromptBuilder
    review_prompt_version: str
    review_output_schema: type[SourceUnitNormalizedReviewOutput]
    review_binder: NormalizedReviewBinder
    contract_version: str
    manifest_sha256: str
    authority: object


def issued_execution_policy_manifest_sha256(policy: IssuedExecutionPolicy) -> str:
    """Fingerprint every provider-visible component and immutable capture."""

    extraction_policy = policy.extraction_prompt_policy
    return canonical_json_sha256(
        {
            "contract_version": policy.contract_version,
            "extraction_prompt_version": extraction_policy.extraction_version,
            "extraction_prompt": _callable_source_fingerprint(
                extraction_policy.extraction_prompt
            ),
            "verification_prompt_version": extraction_policy.verification_version,
            "verification_prompt": _callable_source_fingerprint(
                extraction_policy.verification_prompt
            ),
            "normalization_prompt_version": policy.normalization_prompt_version,
            "normalization_prompt": _callable_source_fingerprint(
                policy.normalization_prompt_builder
            ),
            "normalization_output_schema_sha256": output_schema_json_sha256(
                policy.normalization_output_schema
            ),
            "review_prompt_version": policy.review_prompt_version,
            "review_prompt": _callable_source_fingerprint(policy.review_prompt_builder),
            "review_output_schema_sha256": output_schema_json_sha256(
                policy.review_output_schema
            ),
            "review_binder": _callable_source_fingerprint(policy.review_binder),
        }
    )


def execution_components_manifest_sha256(  # noqa: PLR0913
    *,
    extraction_prompt_policy: SourceUnitPromptPolicy,
    normalization_prompt_builder: NormalizationPromptBuilder,
    normalization_prompt_version: str,
    normalization_output_schema: type[SourceUnitNormalizationOutput],
    review_prompt_builder: NormalizedReviewPromptBuilder,
    review_prompt_version: str,
    review_output_schema: type[SourceUnitNormalizedReviewOutput],
    review_binder: NormalizedReviewBinder,
) -> str:
    """Fingerprint an execution tuple independently from its caller label."""

    return canonical_json_sha256(
        {
            "extraction_prompt_version": extraction_prompt_policy.extraction_version,
            "extraction_prompt": _callable_source_fingerprint(
                extraction_prompt_policy.extraction_prompt
            ),
            "verification_prompt_version": (
                extraction_prompt_policy.verification_version
            ),
            "verification_prompt": _callable_source_fingerprint(
                extraction_prompt_policy.verification_prompt
            ),
            "normalization_prompt_version": normalization_prompt_version,
            "normalization_prompt": _callable_source_fingerprint(
                normalization_prompt_builder
            ),
            "normalization_output_schema_sha256": output_schema_json_sha256(
                normalization_output_schema
            ),
            "review_prompt_version": review_prompt_version,
            "review_prompt": _callable_source_fingerprint(review_prompt_builder),
            "review_output_schema_sha256": output_schema_json_sha256(
                review_output_schema
            ),
            "review_binder": _callable_source_fingerprint(review_binder),
        }
    )


_ISSUED_V13_POLICY_MANIFESTS = {
    "tg04.finite_source_unit.v13_execution.v2": (
        "a099669b6ebf9bddb6257f8d69ef17e880a85aa60f72768bf6426267517c1a64"
    ),
    "tg04.finite_source_unit.v13_execution.v3": (
        "7ed3f92006de99ba269f64d9468c470dbca24088232eb8b0ef85cc48bb38b563"
    ),
}
_ISSUED_V13_COMPONENT_MANIFESTS = frozenset(
    {
        "3bcdcd622f3d712ddcaa9573c6caacf530bf2cbd560401294e4d5e8e28a4d554",
        "922b324128f094aceab674dea5e074e07014fba6b018d3a84784e1225c22d29f",
    }
)


def expected_issued_manifest(contract_version: str) -> str | None:
    return _ISSUED_V13_POLICY_MANIFESTS.get(contract_version)


def is_issued_component_manifest(manifest_sha256: str) -> bool:
    return manifest_sha256 in _ISSUED_V13_COMPONENT_MANIFESTS


def _make_issued_execution_authority() -> tuple[
    Callable[[IssuedExecutionPolicy], tuple[object, str]],
    Callable[..., bool],
]:
    expected_manifests = dict(_ISSUED_V13_POLICY_MANIFESTS)
    authorities: dict[tuple[str, str], object] = {}

    def register(policy: IssuedExecutionPolicy) -> tuple[object, str]:
        manifest_sha256 = issued_execution_policy_manifest_sha256(policy)
        expected = expected_manifests.get(policy.contract_version)
        if expected is None or manifest_sha256 != expected:
            raise IssuedExecutionContractBoundaryError(
                "issued V13 policy does not match its frozen component manifest"
            )
        key = (policy.contract_version, manifest_sha256)
        authority = authorities.setdefault(key, object())
        return authority, manifest_sha256

    def require(
        *,
        contract_version: str,
        manifest_sha256: str | None,
        authority: object | None,
    ) -> bool:
        if manifest_sha256 is None:
            return False
        return authorities.get((contract_version, manifest_sha256)) is authority

    return register, require


_register_policy, _require_authority = _make_issued_execution_authority()


def register_issued_execution_policy(
    policy: IssuedExecutionPolicy,
) -> IssuedExecutionSnapshot:
    """Validate and privately capture all fields of an issued policy."""

    authority, manifest_sha256 = _register_policy(policy)
    extraction_prompt_policy = SourceUnitPromptPolicy(
        extraction_version=policy.extraction_prompt_policy.extraction_version,
        verification_version=policy.extraction_prompt_policy.verification_version,
        extraction_prompt=cast(
            "ExtractionPromptBuilder",
            _freeze_issued_function(policy.extraction_prompt_policy.extraction_prompt),
        ),
        verification_prompt=cast(
            "VerificationPromptBuilder",
            _freeze_issued_function(
                policy.extraction_prompt_policy.verification_prompt
            ),
        ),
    )
    return IssuedExecutionSnapshot(
        extraction_prompt_policy=extraction_prompt_policy,
        normalization_prompt_builder=cast(
            "NormalizationPromptBuilder",
            _freeze_issued_function(policy.normalization_prompt_builder),
        ),
        normalization_prompt_version=policy.normalization_prompt_version,
        normalization_output_schema=policy.normalization_output_schema,
        review_prompt_builder=cast(
            "NormalizedReviewPromptBuilder",
            _freeze_issued_function(policy.review_prompt_builder),
        ),
        review_prompt_version=policy.review_prompt_version,
        review_output_schema=policy.review_output_schema,
        review_binder=cast(
            "NormalizedReviewBinder",
            _freeze_issued_function(policy.review_binder),
        ),
        contract_version=policy.contract_version,
        manifest_sha256=manifest_sha256,
        authority=authority,
    )


def require_issued_execution_authority(
    *,
    contract_version: str,
    manifest_sha256: str | None,
    authority: object | None,
) -> bool:
    return _require_authority(
        contract_version=contract_version,
        manifest_sha256=manifest_sha256,
        authority=authority,
    )


def _callable_source_fingerprint(
    value: Callable[..., object],
) -> dict[str, object]:
    defaults = getattr(value, "__defaults__", None)
    keyword_defaults = getattr(value, "__kwdefaults__", None)
    return {
        "module": getattr(value, "__module__", ""),
        "qualname": getattr(value, "__qualname__", ""),
        "source_sha256": canonical_json_sha256(inspect.getsource(value)),
        "captured_values_sha256": canonical_json_sha256(
            {
                "defaults": _captured_callable_value(defaults),
                "keyword_defaults": _captured_callable_value(keyword_defaults),
            }
        ),
    }


def callable_source_fingerprint(
    value: Callable[..., object],
) -> dict[str, object]:
    """Return the stable implementation identity of an experiment callable."""

    return _callable_source_fingerprint(value)


def module_runtime_fingerprints(module: ModuleType) -> dict[str, object]:
    """Fingerprint every function and class currently owned by one module."""

    owned_callables = {
        name: value
        for name, value in vars(module).items()
        if callable(value)
        and getattr(value, "__module__", None) == module.__name__
        and (inspect.isfunction(value) or inspect.isclass(value))
    }
    return {
        name: _callable_source_fingerprint(value)
        for name, value in sorted(owned_callables.items())
    }


def _captured_callable_value(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, tuple):
        return [_captured_callable_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _captured_callable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if callable(value):
        return _callable_source_fingerprint(value)
    raise TypeError(
        "issued execution callable captures must be immutable canonical values"
    )


def _freeze_issued_function(
    value: Callable[..., object],
    *,
    memo: dict[int, Callable[..., object]] | None = None,
) -> Callable[..., object]:
    if not isinstance(value, FunctionType):
        raise IssuedExecutionContractBoundaryError(
            "issued execution callables must be plain functions"
        )
    if value.__closure__:
        raise IssuedExecutionContractBoundaryError(
            "issued execution functions cannot depend on mutable closures"
        )
    frozen_by_id = {} if memo is None else memo
    existing = frozen_by_id.get(id(value))
    if existing is not None:
        return existing
    frozen_by_id[id(value)] = value
    frozen_globals = dict(value.__globals__)
    for name in value.__code__.co_names:
        dependency = frozen_globals.get(name)
        if isinstance(dependency, FunctionType) and dependency is not value:
            frozen_globals[name] = _freeze_issued_function(
                dependency,
                memo=frozen_by_id,
            )
    defaults = tuple(
        _freeze_issued_capture(item, memo=frozen_by_id)
        for item in (value.__defaults__ or ())
    )
    frozen = FunctionType(
        value.__code__,
        frozen_globals,
        value.__name__,
        defaults or None,
        None,
    )
    frozen.__kwdefaults__ = {
        name: _freeze_issued_capture(item, memo=frozen_by_id)
        for name, item in (value.__kwdefaults__ or {}).items()
    }
    frozen.__qualname__ = value.__qualname__
    frozen_by_id[id(value)] = frozen
    return frozen


def _freeze_issued_capture(
    value: object,
    *,
    memo: dict[int, Callable[..., object]],
) -> object:
    if isinstance(value, FunctionType):
        return _freeze_issued_function(value, memo=memo)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, tuple):
        return tuple(_freeze_issued_capture(item, memo=memo) for item in value)
    raise IssuedExecutionContractBoundaryError(
        "issued execution defaults must be immutable canonical values"
    )


__all__ = [
    "IssuedExecutionContractBoundaryError",
    "IssuedExecutionPolicy",
    "IssuedExecutionSnapshot",
    "NormalizationPromptBuilder",
    "NormalizedReviewPromptBuilder",
    "callable_source_fingerprint",
    "execution_components_manifest_sha256",
    "expected_issued_manifest",
    "is_issued_component_manifest",
    "module_runtime_fingerprints",
    "issued_execution_policy_manifest_sha256",
    "register_issued_execution_policy",
    "require_issued_execution_authority",
]
