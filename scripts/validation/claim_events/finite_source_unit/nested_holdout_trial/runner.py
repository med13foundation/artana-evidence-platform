"""Execute one pre-registered hidden nested-event holdout repeat."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.corpus import (
    verified_corpus_root,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.eighth_selection import (
    select_eighth_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.fourth_selection import (
    select_fourth_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.report import (
    build_nested_holdout_report,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.second_selection import (
    select_second_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    NestedHoldoutSelection,
    select_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.third_selection import (
    select_third_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.service import as_model_client
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    execute_source_unit_agents,
    sha256_json,
)
from scripts.validation.claim_events.runner import build_tg04_runtime
from scripts.validation.claim_frames.evidence import collect_repository_evidence

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.eighth_sequence import (
        EighthRepeatAuthorization,
    )

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_MODEL_ID: Final = "openai:gpt-5.6-luna"
_BINDING_REPAIR_MIN_TRIAL_GENERATION: Final = 3


def run_nested_event_holdout_trial(
    *,
    archive: Path,
    run_id: str,
    repeat_index: int,
) -> dict[str, object]:
    """Run extractor and blinded verifier once on the sealed source-only unit."""

    with verified_corpus_root(archive) as corpus_root:
        selection = select_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )
    return _run_selected_trial(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
    )


def run_second_nested_event_holdout_trial(
    *,
    archive: Path,
    run_id: str,
    repeat_index: int,
) -> dict[str, object]:
    """Run the sealed post-remediation holdout without exposing its expert graph."""

    with verified_corpus_root(archive) as corpus_root:
        selection = select_second_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )
    return _run_selected_trial(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
    )


def run_third_nested_event_holdout_trial(
    *,
    archive: Path,
    run_id: str,
    repeat_index: int,
) -> dict[str, object]:
    """Run the sealed projection-aware v3 holdout without exposing its gold set."""

    with verified_corpus_root(archive) as corpus_root:
        selection = select_third_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )
    return _run_selected_trial(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
    )


def run_fourth_nested_event_holdout_trial(
    *,
    archive: Path,
    run_id: str,
    repeat_index: int,
) -> dict[str, object]:
    """Run the sealed v4 holdout without exposing its projection set."""

    with verified_corpus_root(archive) as corpus_root:
        selection = select_fourth_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )
    return _run_selected_trial(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
    )


def run_eighth_nested_event_holdout_trial(
    *,
    archive: Path,
    run_id: str,
    repeat_index: int,
    authorization: EighthRepeatAuthorization,
) -> dict[str, object]:
    """Run the source-derived, agent-expert-adjudicated v8 holdout."""

    if authorization.run_id != run_id or authorization.repeat_index != repeat_index:
        raise RuntimeError("eighth holdout authorization does not match the request")
    authorization.require_active()
    with verified_corpus_root(archive) as corpus_root:
        selection = select_eighth_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )
    report = _run_selected_trial(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
        authorization=authorization,
    )
    authorization.require_active()
    report.pop("report_sha256", None)
    report["repeat_authorization"] = {
        "run_id": authorization.run_id,
        "repeat_index": authorization.repeat_index,
        "token_sha256": hashlib.sha256(authorization.token.encode()).hexdigest(),
    }
    report["report_sha256"] = sha256_json(report)
    return report


def _run_selected_trial(
    *,
    selection: NestedHoldoutSelection,
    run_id: str,
    repeat_index: int,
    authorization: EighthRepeatAuthorization | None = None,
) -> dict[str, object]:
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("nested holdout trial requires a clean tracked worktree")
    if (
        authorization is not None
        and repository_evidence != authorization.repository_evidence
    ):
        raise RuntimeError("repository differs from eighth holdout reservation")
    return asyncio.run(
        _run_trial(
            selection=selection,
            run_id=run_id,
            repeat_index=repeat_index,
            repository_evidence=repository_evidence,
            audit_evidence_unit_id=(
                None
                if authorization is None
                else authorization.provider_evidence_unit_id()
            ),
        ),
    )


async def _run_trial(
    *,
    selection: NestedHoldoutSelection,
    run_id: str,
    repeat_index: int,
    repository_evidence: dict[str, object],
    audit_evidence_unit_id: str | None = None,
) -> dict[str, object]:
    client, tenant, execution_model_id, kernel, store = build_tg04_runtime(_MODEL_ID)
    try:
        agent_run = await execute_source_unit_agents(
            client=as_model_client(client),
            tenant=tenant,
            model_id=execution_model_id,
            execution_namespace=(
                f"{run_id}:{repeat_index}:{selection.unit.unit_id}:{uuid4().hex}"
            ),
            unit=selection.unit,
            allow_binding_repair=(
                selection.trial_generation >= _BINDING_REPAIR_MIN_TRIAL_GENERATION
            ),
            audit_evidence_unit_id=audit_evidence_unit_id,
        )
    finally:
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()
    if collect_repository_evidence(_REPO_ROOT) != repository_evidence:
        raise RuntimeError("repository changed during nested holdout trial")
    return build_nested_holdout_report(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
        configured_model_id=_MODEL_ID,
        execution_model_id=execution_model_id,
        repository_evidence=repository_evidence,
        agent_run=agent_run,
    )


__all__ = [
    "run_eighth_nested_event_holdout_trial",
    "run_fourth_nested_event_holdout_trial",
    "run_nested_event_holdout_trial",
    "run_second_nested_event_holdout_trial",
    "run_third_nested_event_holdout_trial",
]
