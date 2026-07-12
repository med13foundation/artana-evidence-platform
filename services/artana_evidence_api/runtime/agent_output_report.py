"""Deterministic reporting for registered agent-output governance."""

from __future__ import annotations

from artana_evidence_api.runtime.agent_output_debt import (
    validate_agent_output_debt_coverage,
)
from artana_evidence_api.runtime.agent_output_manifest import (
    AGENT_OUTPUT_SCHEMA_REGISTRY,
)

_REPORT_SCHEMA_VERSION = "agent_output_registry_report.v1"


def build_agent_output_registry_report() -> dict[str, object]:
    """Return a stable machine-readable schema, origin, and debt inventory."""

    debt_manifest = validate_agent_output_debt_coverage()
    registered_schemas: list[dict[str, object]] = []
    numeric_field_count = 0
    origin_governed_numeric_field_count = 0
    debt_numeric_field_count = 0
    category_field_count = 0
    for policy in AGENT_OUTPUT_SCHEMA_REGISTRY.policies():
        numeric_fields = [
            {
                "path": field.path,
                "origin": field.origin.value if field.origin is not None else None,
                "debt_id": field.debt_id,
            }
            for field in policy.numeric_fields
        ]
        categorical_fields = [
            {
                "path": field.path,
                "values": [value.value for value in field.values],
                "allow_schema_subset": field.allow_schema_subset,
                "debt_id": field.debt_id,
            }
            for field in policy.categorical_fields
        ]
        numeric_field_count += len(numeric_fields)
        origin_governed_numeric_field_count += sum(
            field.origin is not None for field in policy.numeric_fields
        )
        debt_numeric_field_count += sum(
            field.debt_id is not None for field in policy.numeric_fields
        )
        category_field_count += len(categorical_fields)
        registered_schemas.append(
            {
                "schema_id": policy.schema_id,
                "schema_names": list(policy.schema_names),
                "shape_hash": policy.shape_hash,
                "numeric_fields": numeric_fields,
                "categorical_fields": categorical_fields,
            },
        )

    unquarantined_ids = sorted(
        item.debt_id for item in debt_manifest if not item.quarantined
    )
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "registered_schema_count": len(registered_schemas),
        "registered_numeric_field_count": numeric_field_count,
        "origin_governed_numeric_field_count": origin_governed_numeric_field_count,
        "debt_numeric_field_count": debt_numeric_field_count,
        "registered_category_field_count": category_field_count,
        "active_debt_count": len(debt_manifest),
        "unquarantined_debt_count": len(unquarantined_ids),
        "unquarantined_debt_ids": unquarantined_ids,
        "registered_schemas": registered_schemas,
        "debt_manifest": [item.model_dump(mode="json") for item in debt_manifest],
    }


__all__ = ["build_agent_output_registry_report"]
