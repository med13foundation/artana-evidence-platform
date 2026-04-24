"""Run-level transparency helpers for graph-harness runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID  # noqa: TC003

from artana.events import KernelEvent, PauseRequestedPayload
from artana_evidence_api.harness_registry import get_harness_template
from artana_evidence_api.tool_catalog import (
    GraphHarnessToolSpec,
    get_graph_harness_tool_spec,
    visible_tool_names_for_harness,
)
from artana_evidence_api.types.common import JSONObject, json_value

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )

_RUN_CAPABILITIES_KEY = "run_capabilities"
_POLICY_DECISIONS_KEY = "policy_decisions"
_POLICY_PROFILE_NAME = "KernelPolicy.enforced_v2()"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _isoformat_now() -> str:
    return _utcnow().isoformat()


def _tool_descriptor(
    *,
    spec: GraphHarnessToolSpec,
    decision: str,
    reason: str,
) -> JSONObject:
    schema = spec.input_model.model_json_schema()
    required_fields = schema.get("required")
    return {
        "tool_name": spec.name,
        "display_name": spec.display_name,
        "description": spec.description,
        "tool_groups": list(spec.tool_groups),
        "required_capability": spec.required_capability,
        "risk_level": spec.risk_level,
        "side_effect": spec.side_effect,
        "approval_mode": spec.approval_mode,
        "idempotency_policy": spec.idempotency_policy,
        "output_summary": spec.output_summary,
        "input_schema": schema,
        "required_fields": (
            list(required_fields) if isinstance(required_fields, list) else []
        ),
        "decision": decision,
        "reason": reason,
    }


def build_run_capabilities_snapshot(
    *,
    run: HarnessRunRecord,
    runtime: GraphHarnessKernelRuntime,
) -> JSONObject:
    """Build the immutable capability snapshot for one run."""
    visible_tool_names = visible_tool_names_for_harness(run.harness_id)
    explain = runtime.explain_tool_allowlist(
        tenant_id=run.space_id,
        run_id=run.id,
        visible_tool_names=visible_tool_names,
    )
    template = get_harness_template(run.harness_id)
    decisions_raw = explain.get("decisions")
    decisions = decisions_raw if isinstance(decisions_raw, list) else []
    descriptors: list[JSONObject] = []
    for raw_decision in decisions:
        if not isinstance(raw_decision, dict):
            continue
        tool_name = raw_decision.get("tool_name")
        if not isinstance(tool_name, str):
            continue
        spec = get_graph_harness_tool_spec(tool_name)
        if spec is None:
            continue
        decision_value = raw_decision.get("decision")
        reason_value = raw_decision.get("reason")
        descriptors.append(
            _tool_descriptor(
                spec=spec,
                decision=decision_value if isinstance(decision_value, str) else "filtered",
                reason=reason_value if isinstance(reason_value, str) else "filtered_unknown",
            ),
        )
    visible_tools = [entry for entry in descriptors if entry["decision"] == "allowed"]
    filtered_tools = [entry for entry in descriptors if entry["decision"] != "allowed"]
    return {
        "run_id": run.id,
        "space_id": run.space_id,
        "harness_id": run.harness_id,
        "tool_groups": list(template.tool_groups) if template is not None else [],
        "preloaded_skill_names": (
            list(template.preloaded_skill_names) if template is not None else []
        ),
        "allowed_skill_names": (
            list(template.allowed_skill_names) if template is not None else []
        ),
        "policy_profile": {
            "kernel_policy": _POLICY_PROFILE_NAME,
            "model": json_value(explain.get("model")),
            "tenant_capabilities": json_value(explain.get("tenant_capabilities", [])),
            "visible_tool_names_applied": json_value(explain.get(
                "visible_tool_names_applied",
                False,
            )),
            "final_allowed_tools": json_value(explain.get("final_allowed_tools", [])),
        },
        "visible_tools": visible_tools,
        "filtered_tools": filtered_tools,
        "artifact_key": _RUN_CAPABILITIES_KEY,
        "created_at": _isoformat_now(),
        "updated_at": _isoformat_now(),
    }


def _declared_policy_from_capabilities(capabilities: JSONObject) -> list[JSONObject]:
    declared: list[JSONObject] = []
    for group_name in ("visible_tools", "filtered_tools"):
        group = capabilities.get(group_name)
        if not isinstance(group, list):
            continue
        for entry in group:
            if not isinstance(entry, dict):
                continue
            declared.append(
                {
                    "tool_name": entry.get("tool_name"),
                    "display_name": entry.get("display_name"),
                    "required_capability": entry.get("required_capability"),
                    "decision": entry.get("decision"),
                    "reason": entry.get("reason"),
                    "approval_mode": entry.get("approval_mode"),
                    "risk_level": entry.get("risk_level"),
                    "side_effect": entry.get("side_effect"),
                },
            )
    return declared


def ensure_run_transparency_seed(
    *,
    run: HarnessRunRecord,
    artifact_store: HarnessArtifactStore,
    runtime: GraphHarnessKernelRuntime,
) -> None:
    """Seed immutable capability and mutable policy-decision artifacts for one run."""
    capabilities_artifact = artifact_store.get_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key=_RUN_CAPABILITIES_KEY,
    )
    if capabilities_artifact is None:
        capabilities_payload = build_run_capabilities_snapshot(run=run, runtime=runtime)
        artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key=_RUN_CAPABILITIES_KEY,
            media_type="application/json",
            content=capabilities_payload,
        )
    else:
        capabilities_payload = capabilities_artifact.content

    if (
        artifact_store.get_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key=_POLICY_DECISIONS_KEY,
        )
        is None
    ):
        artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key=_POLICY_DECISIONS_KEY,
            media_type="application/json",
            content={
                "run_id": run.id,
                "space_id": run.space_id,
                "harness_id": run.harness_id,
                "artifact_key": _POLICY_DECISIONS_KEY,
                "declared_policy": _declared_policy_from_capabilities(
                    capabilities_payload,
                ),
                "records": [],
                "summary": {
                    "total_records": 0,
                    "tool_record_count": 0,
                    "manual_review_count": 0,
                    "skill_record_count": 0,
                    "paused_approval_count": 0,
                    "status_counts": {},
                },
                "created_at": _isoformat_now(),
                "updated_at": _isoformat_now(),
            },
        )
    artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={
            "run_capabilities_key": _RUN_CAPABILITIES_KEY,
            "policy_decisions_key": _POLICY_DECISIONS_KEY,
        },
    )


def _parse_pause_context(event: KernelEvent) -> tuple[str | None, str | None]:
    payload = event.payload
    if not isinstance(payload, PauseRequestedPayload) or payload.context_json is None:
        return None, None
    try:
        context: object = json.loads(payload.context_json)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(context, dict):
        return None, None
    approval_key = context.get("approval_key")
    tool_name = context.get("tool_name")
    return (
        approval_key if isinstance(approval_key, str) else None,
        tool_name if isinstance(tool_name, str) else None,
    )


def _event_payload(event: KernelEvent) -> JSONObject:
    payload = event.payload.model_dump(mode="json")
    return payload if isinstance(payload, dict) else {}


def _tool_records_from_events(  # noqa: C901, PLR0912, PLR0915
    *,
    events: tuple[KernelEvent, ...],
) -> list[JSONObject]:
    records: list[JSONObject] = []
    pending_by_key: dict[str, int] = {}
    pending_by_tool: dict[str, int] = {}

    for event in events:
        payload = _event_payload(event)
        event_type = event.event_type.value
        if event_type == "tool_requested":
            tool_name = payload.get("tool_name")
            idempotency_key = payload.get("idempotency_key")
            if not isinstance(tool_name, str):
                continue
            request_key = (
                idempotency_key
                if isinstance(idempotency_key, str) and idempotency_key != ""
                else event.event_id
            )
            record: JSONObject = {
                "record_id": f"tool:{request_key}",
                "decision_source": "tool",
                "tool_name": tool_name,
                "decision": "requested",
                "reason": "tool_requested",
                "status": "pending",
                "event_id": event.event_id,
                "approval_id": None,
                "artifact_key": None,
                "started_at": event.timestamp.isoformat(),
                "completed_at": None,
            }
            records.append(record)
            record_index = len(records) - 1
            pending_by_key[request_key] = record_index
            pending_by_tool[tool_name] = record_index
            continue

        if event_type == "pause_requested":
            approval_id, tool_name = _parse_pause_context(event)
            if tool_name is None:
                continue
            if tool_name not in pending_by_tool:
                continue
            record_index = pending_by_tool[tool_name]
            record = records[record_index]
            record["decision"] = "approval_required"
            record["reason"] = "approval_required"
            record["status"] = "paused"
            record["approval_id"] = approval_id
            continue

        if event_type != "tool_completed":
            continue

        tool_name = payload.get("tool_name")
        received_key = payload.get("received_idempotency_key")
        if not isinstance(tool_name, str):
            continue
        completed_record_index: int | None = None
        if (
            isinstance(received_key, str)
            and received_key != ""
            and received_key in pending_by_key
        ):
            completed_record_index = pending_by_key[received_key]
        elif tool_name in pending_by_tool:
            completed_record_index = pending_by_tool[tool_name]
        else:
            records.append(
                {
                    "record_id": f"tool:{event.event_id}",
                    "decision_source": "tool",
                    "tool_name": tool_name,
                    "decision": "executed",
                    "reason": (
                        payload.get("outcome")
                        if isinstance(payload.get("outcome"), str)
                        else "unknown_outcome"
                    ),
                    "status": (
                        "success" if payload.get("outcome") == "success" else "failed"
                    ),
                    "event_id": event.event_id,
                    "approval_id": None,
                    "artifact_key": None,
                    "started_at": event.timestamp.isoformat(),
                    "completed_at": event.timestamp.isoformat(),
                },
            )
            continue
        record = records[completed_record_index]
        record["decision"] = "executed"
        record["reason"] = (
            payload.get("outcome")
            if isinstance(payload.get("outcome"), str)
            else "unknown_outcome"
        )
        record["status"] = (
            "success" if payload.get("outcome") == "success" else "failed"
        )
        record["completed_at"] = event.timestamp.isoformat()
        record["event_id"] = event.event_id
        if isinstance(received_key, str) and received_key in pending_by_key:
            del pending_by_key[received_key]
        if pending_by_tool.get(tool_name) == record_index:
            del pending_by_tool[tool_name]
    return records


def _decision_records(
    policy_content: JSONObject,
    *,
    decision_source: str,
) -> list[JSONObject]:
    records = policy_content.get("records")
    if not isinstance(records, list):
        return []
    matching_records: list[JSONObject] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("decision_source") != decision_source:
            continue
        matching_records.append(cast("JSONObject", record))
    return matching_records


def _manual_review_records(policy_content: JSONObject) -> list[JSONObject]:
    return _decision_records(policy_content, decision_source="manual_review")


def _skill_records(policy_content: JSONObject) -> list[JSONObject]:
    return _decision_records(policy_content, decision_source="skill")


def _sort_records(records: list[JSONObject]) -> list[JSONObject]:
    def _sort_key(record: JSONObject) -> tuple[str, str]:
        started_at = record.get("started_at")
        completed_at = record.get("completed_at")
        primary = started_at if isinstance(started_at, str) else ""
        secondary = completed_at if isinstance(completed_at, str) else ""
        return primary, secondary

    return sorted(records, key=_sort_key)


def _summary_for_records(records: list[JSONObject]) -> JSONObject:
    status_counts: dict[str, int] = {}
    tool_record_count = 0
    manual_review_count = 0
    skill_record_count = 0
    paused_approval_count = 0
    for record in records:
        status = record.get("status")
        if isinstance(status, str):
            status_counts[status] = status_counts.get(status, 0) + 1
        source = record.get("decision_source")
        if source == "tool":
            tool_record_count += 1
        elif source == "manual_review":
            manual_review_count += 1
        elif source == "skill":
            skill_record_count += 1
        if isinstance(record.get("approval_id"), str):
            paused_approval_count += 1
    return {
        "total_records": len(records),
        "tool_record_count": tool_record_count,
        "manual_review_count": manual_review_count,
        "skill_record_count": skill_record_count,
        "paused_approval_count": paused_approval_count,
        "status_counts": status_counts,
    }


def sync_policy_decisions_artifact(
    *,
    space_id: UUID | str,
    run_id: UUID | str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    runtime: GraphHarnessKernelRuntime,
) -> JSONObject | None:
    """Sync the mutable policy-decision artifact from Artana events and manual records."""
    run = run_registry.get_run(space_id=space_id, run_id=run_id)
    if run is None:
        return None
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=runtime,
    )
    capabilities_artifact = artifact_store.get_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key=_RUN_CAPABILITIES_KEY,
    )
    if capabilities_artifact is None:
        return None
    policy_artifact = artifact_store.get_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key=_POLICY_DECISIONS_KEY,
    )
    existing_policy = policy_artifact.content if policy_artifact is not None else {}
    tool_records = _tool_records_from_events(
        events=runtime.get_events(run_id=run.id, tenant_id=run.space_id),
    )
    manual_records = _manual_review_records(existing_policy)
    skill_records = _skill_records(existing_policy)
    records = _sort_records([*tool_records, *manual_records, *skill_records])
    summary = _summary_for_records(records)
    content = {
        "run_id": run.id,
        "space_id": run.space_id,
        "harness_id": run.harness_id,
        "artifact_key": _POLICY_DECISIONS_KEY,
        "declared_policy": _declared_policy_from_capabilities(
            capabilities_artifact.content,
        ),
        "records": records,
        "summary": summary,
        "created_at": (
            existing_policy.get("created_at")
            if isinstance(existing_policy.get("created_at"), str)
            else _isoformat_now()
        ),
        "updated_at": _isoformat_now(),
    }
    artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key=_POLICY_DECISIONS_KEY,
        media_type="application/json",
        content=content,
    )
    artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={
            "policy_decisions_key": _POLICY_DECISIONS_KEY,
            "policy_decision_count": summary["total_records"],
            "policy_manual_review_count": summary["manual_review_count"],
            "policy_skill_count": summary["skill_record_count"],
        },
    )
    return content


def append_manual_review_decision(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    tool_name: str,
    decision: str,
    reason: str | None,
    artifact_key: str | None,
    metadata: JSONObject,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    runtime: GraphHarnessKernelRuntime,
) -> None:
    """Append one manual-review record to the policy decision artifact for a source run."""
    current = sync_policy_decisions_artifact(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=runtime,
    )
    if current is None:
        return
    records = current.get("records")
    normalized_records = list(records) if isinstance(records, list) else []
    now = _isoformat_now()
    normalized_records.append(
        {
            "record_id": (
                f"manual_review:{tool_name}:{decision}:{metadata.get('proposal_id', run_id)}:{now}"
            ),
            "decision_source": "manual_review",
            "tool_name": tool_name,
            "decision": decision,
            "reason": reason or "manual_review",
            "status": "completed",
            "event_id": None,
            "approval_id": None,
            "artifact_key": artifact_key,
            "started_at": now,
            "completed_at": now,
            "metadata": metadata,
        },
    )
    updated_records = _sort_records(
        [
            cast("JSONObject", record)
            for record in normalized_records
            if isinstance(record, dict)
        ],
    )
    updated_summary = _summary_for_records(updated_records)
    updated_content = {
        **current,
        "records": updated_records,
        "summary": updated_summary,
        "updated_at": now,
    }
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_POLICY_DECISIONS_KEY,
        media_type="application/json",
        content=updated_content,
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "policy_decisions_key": _POLICY_DECISIONS_KEY,
            "policy_decision_count": updated_summary["total_records"],
            "policy_manual_review_count": updated_summary["manual_review_count"],
            "policy_skill_count": updated_summary["skill_record_count"],
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run_id,
        event_type="run.manual_review_decision",
        message=f"Manual review recorded for '{tool_name}' with decision '{decision}'.",
        payload={
            "decision_source": "manual_review",
            "tool_name": tool_name,
            "decision": decision,
            "artifact_key": artifact_key,
            "metadata": metadata,
        },
    )


def append_skill_activity(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    skill_names: tuple[str, ...],
    source_run_id: str | None,
    source_kind: str,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    runtime: GraphHarnessKernelRuntime,
) -> None:
    """Append skill activation records to the parent run transparency artifact."""
    if not skill_names:
        return
    current = sync_policy_decisions_artifact(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=runtime,
    )
    if current is None:
        return
    existing_records = current.get("records")
    normalized_records = (
        list(existing_records) if isinstance(existing_records, list) else []
    )
    existing_keys = {
        (
            record.get("tool_name"),
            (
                record.get("metadata", {}).get("source_run_id")
                if isinstance(record.get("metadata"), dict)
                else None
            ),
        )
        for record in normalized_records
        if isinstance(record, dict) and record.get("decision_source") == "skill"
    }
    now = _isoformat_now()
    for skill_name in skill_names:
        record_key = (skill_name, source_run_id)
        if record_key in existing_keys:
            continue
        normalized_records.append(
            {
                "record_id": f"skill:{skill_name}:{source_run_id or run_id}:{now}",
                "decision_source": "skill",
                "tool_name": skill_name,
                "decision": "activated",
                "reason": "active_runtime_skill",
                "status": "completed",
                "event_id": None,
                "approval_id": None,
                "artifact_key": None,
                "started_at": now,
                "completed_at": now,
                "metadata": {
                    "source_run_id": source_run_id,
                    "source_kind": source_kind,
                    "skill_name": skill_name,
                },
            },
        )
    updated_records = _sort_records(
        [
            cast("JSONObject", record)
            for record in normalized_records
            if isinstance(record, dict)
        ],
    )
    updated_summary = _summary_for_records(updated_records)
    updated_content = {
        **current,
        "records": updated_records,
        "summary": updated_summary,
        "updated_at": now,
    }
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_POLICY_DECISIONS_KEY,
        media_type="application/json",
        content=updated_content,
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "policy_decisions_key": _POLICY_DECISIONS_KEY,
            "policy_decision_count": updated_summary["total_records"],
            "policy_manual_review_count": updated_summary["manual_review_count"],
            "policy_skill_count": updated_summary["skill_record_count"],
        },
    )


def active_skill_names_from_policy_content(policy_content: JSONObject) -> list[str]:
    """Derive active skill names from a synced policy-decision artifact."""
    active_skill_names: list[str] = []
    seen_names: set[str] = set()
    for record in _skill_records(policy_content):
        skill_name = record.get("tool_name")
        if not isinstance(skill_name, str):
            continue
        normalized_name = skill_name.strip()
        if normalized_name == "" or normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        active_skill_names.append(normalized_name)
    return active_skill_names


__all__ = [
    "append_manual_review_decision",
    "append_skill_activity",
    "active_skill_names_from_policy_content",
    "build_run_capabilities_snapshot",
    "ensure_run_transparency_seed",
    "sync_policy_decisions_artifact",
]
