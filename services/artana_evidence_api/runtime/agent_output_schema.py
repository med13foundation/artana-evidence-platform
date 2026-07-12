"""Fail-closed contracts for registered agent output schemas."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field


class AgentOutputSchemaRegistrationError(ValueError):
    """Raised when an agent output schema violates its registered contract."""


class NumericOrigin(str, Enum):
    """Allowed deterministic or observed origins for numeric output fields."""

    SOURCE_MEASUREMENT = "source_measurement"
    RETRIEVAL_ALGORITHM = "retrieval_algorithm"
    DETERMINISTIC_POLICY = "deterministic_policy"
    CALIBRATION_MODEL = "calibration_model"
    COMPUTED_METRIC = "computed_metric"
    RUNTIME_OBSERVATION = "runtime_observation"


class SourceMeasurementNumber(BaseModel):
    """A number copied from a source with complete extraction provenance."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "source_measurement"},
    )

    origin: Literal["source_measurement"] = "source_measurement"
    value: float
    source_locator: str = Field(..., min_length=1)
    literal_span: str = Field(..., min_length=1)
    field_name: str = Field(..., min_length=1)
    unit: str = Field(..., min_length=1)
    extraction_method: str = Field(..., min_length=1)
    source_hash: str = Field(..., min_length=1)


class RetrievalAlgorithmNumber(BaseModel):
    """A retrieval score with the exact algorithm and acquisition context."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "retrieval_algorithm"},
    )

    origin: Literal["retrieval_algorithm"] = "retrieval_algorithm"
    value: float
    provider_algorithm_id: str = Field(..., min_length=1)
    algorithm_version: str = Field(..., min_length=1)
    query_input_hash: str = Field(..., min_length=1)
    affected_candidate_acquisition: bool


class DeterministicPolicyNumber(BaseModel):
    """A deterministic mapping from complete categorical policy inputs."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "deterministic_policy"},
    )

    origin: Literal["deterministic_policy"] = "deterministic_policy"
    value: float
    categorical_inputs: dict[str, str]
    policy_id: str = Field(..., min_length=1)
    policy_version: str = Field(..., min_length=1)
    mapping_version: str = Field(..., min_length=1)
    caps: list[str]
    vetoes: list[str]
    blocking_categories: list[str]


class CalibrationModelNumber(BaseModel):
    """A calibrated value tied to one fitted policy and held-out protocol."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "calibration_model"},
    )

    origin: Literal["calibration_model"] = "calibration_model"
    value: float
    input_policy_id: str = Field(..., min_length=1)
    input_policy_version: str = Field(..., min_length=1)
    calibration_algorithm: str = Field(..., min_length=1)
    calibration_version: str = Field(..., min_length=1)
    training_set_hash: str = Field(..., min_length=1)
    held_out_protocol: str = Field(..., min_length=1)
    calibration_status: Literal["unavailable", "diagnostic", "validated"]


class ComputedMetricNumber(BaseModel):
    """A reproducible metric over immutable input artifacts."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "computed_metric"},
    )

    origin: Literal["computed_metric"] = "computed_metric"
    value: float
    metric_specification: str = Field(..., min_length=1)
    metric_version: str = Field(..., min_length=1)
    input_artifact_hashes: list[str] = Field(..., min_length=1)
    denominator: int = Field(..., ge=0)
    aggregation_scope: str = Field(..., min_length=1)


class RuntimeObservationNumber(BaseModel):
    """A runtime measurement collected from one identified execution."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "runtime_observation"},
    )

    origin: Literal["runtime_observation"] = "runtime_observation"
    value: float
    runtime_provider_source: str = Field(..., min_length=1)
    unit: str = Field(..., min_length=1)
    collection_method: str = Field(..., min_length=1)
    execution_id: str = Field(..., min_length=1)


@dataclass(frozen=True, slots=True)
class NumericFieldPolicy:
    """Declare one numeric field as governed or tracked compatibility debt."""

    path: str
    origin: NumericOrigin | None = None
    debt_id: str | None = None

    def __post_init__(self) -> None:
        has_origin = self.origin is not None
        has_debt = self.debt_id is not None
        if has_origin == has_debt:
            msg = (
                f"Numeric field {self.path!r} must declare exactly one allowed "
                "origin or one debt ID."
            )
            raise AgentOutputSchemaRegistrationError(msg)
        if self.debt_id is not None and self.debt_id.strip() == "":
            msg = f"Numeric field {self.path!r} has an empty debt ID."
            raise AgentOutputSchemaRegistrationError(msg)


@dataclass(frozen=True, slots=True)
class CategoryValuePolicy:
    """Operational definition for one agent-authored categorical value."""

    value: str
    definition: str
    positive_example: str
    counterexample: str

    def __post_init__(self) -> None:
        required = {
            "value": self.value,
            "definition": self.definition,
            "positive_example": self.positive_example,
            "counterexample": self.counterexample,
        }
        missing = sorted(
            name for name, value in required.items() if value.strip() == ""
        )
        if missing:
            msg = f"Category value policy is missing: {', '.join(missing)}."
            raise AgentOutputSchemaRegistrationError(msg)


@dataclass(frozen=True, slots=True)
class CategoryFieldPolicy:
    """Declare the operational vocabulary for one categorical schema field."""

    path: str
    values: tuple[CategoryValuePolicy, ...]
    evidence_requirement: str
    invalid_behavior: str
    allow_schema_subset: bool = False
    debt_id: str | None = None

    def __post_init__(self) -> None:
        if self.path.strip() == "":
            raise AgentOutputSchemaRegistrationError("Category path cannot be empty.")
        if self.evidence_requirement.strip() == "":
            msg = f"Category field {self.path!r} lacks an evidence requirement."
            raise AgentOutputSchemaRegistrationError(msg)
        if self.invalid_behavior.strip() == "":
            msg = f"Category field {self.path!r} lacks invalid-output behavior."
            raise AgentOutputSchemaRegistrationError(msg)
        if self.debt_id is not None and self.debt_id.strip() == "":
            msg = f"Category field {self.path!r} has an empty debt ID."
            raise AgentOutputSchemaRegistrationError(msg)
        registered_values = [policy.value for policy in self.values]
        if not registered_values or len(set(registered_values)) != len(
            registered_values
        ):
            msg = f"Category field {self.path!r} has missing or duplicate values."
            raise AgentOutputSchemaRegistrationError(msg)


@dataclass(frozen=True, slots=True)
class AgentOutputSchemaPolicy:
    """Complete registration for one model-output schema boundary."""

    schema_id: str
    schema_names: tuple[str, ...]
    shape_hash: str
    producer_paths: tuple[str, ...]
    prompt_identifiers: tuple[str, ...]
    numeric_fields: tuple[NumericFieldPolicy, ...] = ()
    categorical_fields: tuple[CategoryFieldPolicy, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_id.strip() == "":
            raise AgentOutputSchemaRegistrationError("Schema ID cannot be empty.")
        if not self.schema_names or any(
            name.strip() == "" for name in self.schema_names
        ):
            msg = f"Schema {self.schema_id!r} must declare at least one schema name."
            raise AgentOutputSchemaRegistrationError(msg)
        if not self.producer_paths or any(
            path.strip() == "" for path in self.producer_paths
        ):
            msg = f"Schema {self.schema_id!r} must declare production callers."
            raise AgentOutputSchemaRegistrationError(msg)
        if not self.prompt_identifiers or any(
            prompt.strip() == "" for prompt in self.prompt_identifiers
        ):
            msg = f"Schema {self.schema_id!r} must declare prompt identities."
            raise AgentOutputSchemaRegistrationError(msg)
        if re.fullmatch(r"[0-9a-f]{64}", self.shape_hash) is None:
            msg = f"Schema {self.schema_id!r} must declare a SHA-256 shape hash."
            raise AgentOutputSchemaRegistrationError(msg)
        _assert_unique_paths(
            schema_id=self.schema_id,
            kind="numeric",
            paths=(field.path for field in self.numeric_fields),
        )
        _assert_unique_paths(
            schema_id=self.schema_id,
            kind="categorical",
            paths=(field.path for field in self.categorical_fields),
        )


class AgentOutputSchemaRegistry:
    """Validate schema identity and complete numeric/category field coverage."""

    def __init__(self, policies: Iterable[AgentOutputSchemaPolicy]) -> None:
        policy_map: dict[str, AgentOutputSchemaPolicy] = {}
        for policy in policies:
            if policy.schema_id in policy_map:
                msg = f"Duplicate agent output schema ID: {policy.schema_id}."
                raise AgentOutputSchemaRegistrationError(msg)
            policy_map[policy.schema_id] = policy
        self._policies = policy_map

    def validate(
        self,
        *,
        schema_id: str,
        output_schema: type[object],
    ) -> AgentOutputSchemaPolicy:
        """Reject unknown, renamed, or incompletely governed output schemas."""

        policy = self._policies.get(schema_id)
        if policy is None:
            raise AgentOutputSchemaRegistrationError(
                f"Unregistered agent output schema ID: {schema_id}.",
            )
        if not isinstance(output_schema, type) or not issubclass(
            output_schema, BaseModel
        ):
            msg = f"Schema {schema_id!r} must be a Pydantic BaseModel type."
            raise AgentOutputSchemaRegistrationError(msg)
        if output_schema.__name__ not in policy.schema_names:
            msg = (
                f"Schema {schema_id!r} expected one of {policy.schema_names!r}, "
                f"received {output_schema.__name__!r}."
            )
            raise AgentOutputSchemaRegistrationError(msg)

        schema = output_schema.model_json_schema()
        actual_shape_hash = _schema_shape_hash(schema)
        if actual_shape_hash != policy.shape_hash:
            msg = (
                f"Schema {schema_id!r} shape changed: expected {policy.shape_hash}, "
                f"found {actual_shape_hash}."
            )
            raise AgentOutputSchemaRegistrationError(msg)
        actual_numeric, actual_categories = _collect_governed_fields(schema)
        expected_numeric = {field.path for field in policy.numeric_fields}
        expected_categories = {field.path for field in policy.categorical_fields}
        _assert_complete_coverage(
            schema_id=schema_id,
            kind="numeric",
            actual=set(actual_numeric),
            expected=expected_numeric,
        )
        _assert_complete_coverage(
            schema_id=schema_id,
            kind="categorical",
            actual=set(actual_categories),
            expected=expected_categories,
        )
        category_policies = {field.path: field for field in policy.categorical_fields}
        for numeric_policy in policy.numeric_fields:
            schema_origin = actual_numeric[numeric_policy.path]
            if (
                numeric_policy.origin is not None
                and schema_origin != numeric_policy.origin
            ):
                msg = (
                    f"Schema {schema_id!r} numeric field {numeric_policy.path!r} "
                    f"declares {numeric_policy.origin.value!r} but is not wrapped in "
                    "the matching typed provenance envelope."
                )
                raise AgentOutputSchemaRegistrationError(msg)
            if numeric_policy.debt_id is not None and schema_origin is not None:
                msg = (
                    f"Schema {schema_id!r} numeric field {numeric_policy.path!r} "
                    "uses an origin envelope and cannot also be legacy debt."
                )
                raise AgentOutputSchemaRegistrationError(msg)
        for path, actual_values in actual_categories.items():
            expected_values = {value.value for value in category_policies[path].values}
            values_match = (
                actual_values <= expected_values
                if category_policies[path].allow_schema_subset
                else actual_values == expected_values
            )
            if not values_match:
                msg = (
                    f"Schema {schema_id!r} category {path!r} values changed: "
                    f"expected {sorted(expected_values)!r}, "
                    f"found {sorted(actual_values)!r}."
                )
                raise AgentOutputSchemaRegistrationError(msg)
        return policy

    def policy(self, schema_id: str) -> AgentOutputSchemaPolicy:
        """Return one policy or fail closed for an unknown ID."""

        policy = self._policies.get(schema_id)
        if policy is None:
            raise AgentOutputSchemaRegistrationError(
                f"Unregistered agent output schema ID: {schema_id}.",
            )
        return policy

    def schema_ids(self) -> tuple[str, ...]:
        """Return stable registered IDs for reports and CI comparisons."""

        return tuple(sorted(self._policies))

    def policies(self) -> tuple[AgentOutputSchemaPolicy, ...]:
        """Return policies in stable order for debt and origin reports."""

        return tuple(self._policies[schema_id] for schema_id in self.schema_ids())


def _assert_unique_paths(
    *,
    schema_id: str,
    kind: str,
    paths: Iterable[str],
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for path in paths:
        if path in seen:
            duplicates.add(path)
        seen.add(path)
    if duplicates:
        msg = (
            f"Schema {schema_id!r} has duplicate {kind} paths: {sorted(duplicates)!r}."
        )
        raise AgentOutputSchemaRegistrationError(msg)


def _assert_complete_coverage(
    *,
    schema_id: str,
    kind: str,
    actual: set[str],
    expected: set[str],
) -> None:
    missing = sorted(actual - expected)
    stale = sorted(expected - actual)
    if missing or stale:
        msg = (
            f"Schema {schema_id!r} has incomplete {kind} registry coverage; "
            f"unregistered={missing!r}, stale={stale!r}."
        )
        raise AgentOutputSchemaRegistrationError(msg)


def _collect_governed_fields(
    schema: Mapping[str, object],
) -> tuple[dict[str, NumericOrigin | None], dict[str, set[str]]]:
    numeric_paths: dict[str, NumericOrigin | None] = {}
    category_paths: dict[str, set[str]] = {}
    _walk_schema(
        node=schema,
        root=schema,
        path="$",
        resolving=frozenset(),
        numeric_paths=numeric_paths,
        category_paths=category_paths,
    )
    return numeric_paths, category_paths


_NON_SHAPE_SCHEMA_KEYS = frozenset(
    {
        "default",
        "description",
        "examples",
        "maxItems",
        "title",
    },
)


def agent_output_schema_shape_hash(output_schema: type[BaseModel]) -> str:
    """Return the canonical structural hash used by registry policies."""

    return _schema_shape_hash(output_schema.model_json_schema())


def _schema_shape_hash(schema: Mapping[str, object]) -> str:
    resolved = _resolve_schema_shape_references(
        node=schema,
        root=schema,
        resolving=frozenset(),
    )
    normalized = _normalize_schema_shape(resolved)
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolve_schema_shape_references(
    *,
    node: object,
    root: Mapping[str, object],
    resolving: frozenset[str],
) -> object:
    if isinstance(node, list):
        return [
            _resolve_schema_shape_references(
                node=item,
                root=root,
                resolving=resolving,
            )
            for item in node
        ]
    if not isinstance(node, Mapping):
        return node
    reference = node.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition_name = reference.rsplit("/", maxsplit=1)[-1]
        if definition_name in resolving:
            return {"$recursive_ref": definition_name}
        definitions = root.get("$defs")
        if isinstance(definitions, Mapping) and definition_name in definitions:
            return _resolve_schema_shape_references(
                node=definitions[definition_name],
                root=root,
                resolving=resolving | {definition_name},
            )
    return {
        key: _resolve_schema_shape_references(
            node=value,
            root=root,
            resolving=resolving,
        )
        for key, value in node.items()
        if key != "$defs"
    }


def _normalize_schema_shape(node: object) -> object:
    if isinstance(node, list):
        return [_normalize_schema_shape(item) for item in node]
    if not isinstance(node, Mapping):
        return node
    normalized: dict[str, object] = {}
    for key, value in sorted(node.items()):
        if key in _NON_SHAPE_SCHEMA_KEYS:
            continue
        if key == "enum":
            normalized[key] = "<registered-category-values>"
            continue
        if key == "const":
            normalized[key] = "<registered-category-constant>"
            continue
        normalized[key] = _normalize_schema_shape(value)
    return normalized


def _walk_schema(  # noqa: PLR0912, PLR0913 - recursive JSON Schema node variants
    *,
    node: object,
    root: Mapping[str, object],
    path: str,
    resolving: frozenset[str],
    numeric_paths: dict[str, NumericOrigin | None],
    category_paths: dict[str, set[str]],
) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_schema(
                node=item,
                root=root,
                path=path,
                resolving=resolving,
                numeric_paths=numeric_paths,
                category_paths=category_paths,
            )
        return
    if not isinstance(node, Mapping):
        return
    mapping = cast("Mapping[str, object]", node)
    reference = mapping.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition_name = reference.rsplit("/", maxsplit=1)[-1]
        if definition_name in resolving:
            return
        definitions = root.get("$defs")
        if isinstance(definitions, Mapping) and definition_name in definitions:
            _walk_schema(
                node=definitions[definition_name],
                root=root,
                path=path,
                resolving=resolving | {definition_name},
                numeric_paths=numeric_paths,
                category_paths=category_paths,
            )
        return

    raw_numeric_origin = mapping.get("x-artana-numeric-origin")
    if isinstance(raw_numeric_origin, str):
        try:
            numeric_origin = NumericOrigin(raw_numeric_origin)
        except ValueError as exc:
            msg = f"Unknown numeric-origin schema marker {raw_numeric_origin!r}."
            raise AgentOutputSchemaRegistrationError(msg) from exc
        numeric_paths[f"{path}.value"] = numeric_origin
        return

    field_type = mapping.get("type")
    if field_type in {"number", "integer"}:
        numeric_paths[path] = None
    raw_values = mapping.get("enum")
    if (
        isinstance(raw_values, list)
        and raw_values
        and all(isinstance(value, str) for value in raw_values)
    ):
        category_paths.setdefault(path, set()).update(cast("list[str]", raw_values))
    constant = mapping.get("const")
    if isinstance(constant, str):
        category_paths.setdefault(path, set()).add(constant)

    for branch_name in ("anyOf", "oneOf", "allOf"):
        branches = mapping.get(branch_name)
        if isinstance(branches, list):
            _walk_schema(
                node=branches,
                root=root,
                path=path,
                resolving=resolving,
                numeric_paths=numeric_paths,
                category_paths=category_paths,
            )
    properties = mapping.get("properties")
    if isinstance(properties, Mapping):
        for field_name, field_schema in properties.items():
            _walk_schema(
                node=field_schema,
                root=root,
                path=f"{path}.{field_name}",
                resolving=resolving,
                numeric_paths=numeric_paths,
                category_paths=category_paths,
            )
    items = mapping.get("items")
    if items is not None:
        _walk_schema(
            node=items,
            root=root,
            path=f"{path}[]",
            resolving=resolving,
            numeric_paths=numeric_paths,
            category_paths=category_paths,
        )
    additional_properties = mapping.get("additionalProperties")
    if additional_properties is True:
        numeric_paths[f"{path}.*"] = None
    if isinstance(additional_properties, Mapping):
        _walk_schema(
            node=additional_properties,
            root=root,
            path=f"{path}.*",
            resolving=resolving,
            numeric_paths=numeric_paths,
            category_paths=category_paths,
        )


__all__ = [
    "AgentOutputSchemaPolicy",
    "AgentOutputSchemaRegistrationError",
    "AgentOutputSchemaRegistry",
    "CategoryFieldPolicy",
    "CategoryValuePolicy",
    "CalibrationModelNumber",
    "ComputedMetricNumber",
    "DeterministicPolicyNumber",
    "NumericFieldPolicy",
    "NumericOrigin",
    "RetrievalAlgorithmNumber",
    "RuntimeObservationNumber",
    "SourceMeasurementNumber",
    "agent_output_schema_shape_hash",
]
