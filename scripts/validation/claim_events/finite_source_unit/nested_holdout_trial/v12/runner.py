"""Execute the create-once V12 schema-bound scientific diagnostic."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.corpus import (
    verified_corpus_root,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.custody import (
    require_v12_prompt_preregistration,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.journal import (
    V12ExecutionJournal,
    v12_journal_identity,
    v12_journal_path,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.prompts import (
    V12_EXTRACTION_PROMPT_POLICY,
    V12_NORMALIZATION_PROMPT_VERSION,
    V12_NORMALIZED_REVIEW_PROMPT_VERSION,
    v12_normalization_prompt,
    v12_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.report import (
    build_v12_report,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.selection import (
    select_twelfth_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    execute_three_source_unit_agents,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
    as_model_client,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_events.runner import build_tg04_runtime
from scripts.validation.claim_frames.evidence import collect_repository_evidence

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
        NestedHoldoutSelection,
    )

_REPO_ROOT: Final = Path(__file__).resolve().parents[6]
_MODEL_ID: Final = "openai:gpt-5.6-luna"


class RepeatAuthorization(Protocol):
    """Execution-facing subset of the sealed V12 reservation."""

    @property
    def run_id(self) -> str: ...

    @property
    def repeat_index(self) -> int: ...

    @property
    def token(self) -> str: ...

    @property
    def output(self) -> Path: ...

    @property
    def reservation_path(self) -> Path: ...

    @property
    def repository_evidence(self) -> dict[str, object]: ...

    def require_active(self) -> None: ...

    def provider_evidence_unit_id(self) -> str: ...

    def claimed_provider_evidence_unit_id(self) -> str: ...


class AsyncClosable(Protocol):
    """Runtime resource closed after the provider sequence."""

    async def close(self) -> None: ...


def run_twelfth_nested_event_holdout_trial(
    *,
    archive: Path,
    run_id: str,
    repeat_index: int,
    authorization: RepeatAuthorization,
) -> dict[str, object]:
    """Run the V12 schema-bound, source-complete diagnostic once."""

    if authorization.run_id != run_id or authorization.repeat_index != repeat_index:
        raise RuntimeError("twelfth holdout authorization does not match the request")
    authorization.require_active()
    with verified_corpus_root(archive) as corpus_root:
        selection = select_twelfth_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("twelfth holdout trial requires a clean tracked worktree")
    if repository_evidence != authorization.repository_evidence:
        raise RuntimeError("repository differs from sealed twelfth reservation")
    raw_client, tenant, execution_model_id, kernel, store = build_tg04_runtime(
        _MODEL_ID
    )
    try:
        client = as_model_client(raw_client)
        prepared_extraction_prompt = _prepare_v12_extraction_prompt(selection)
        audit_evidence_unit_id = authorization.provider_evidence_unit_id()
        journal = V12ExecutionJournal.create(
            path=v12_journal_path(authorization.reservation_path),
            identity=v12_journal_identity(
                authorization=authorization,
                audit_evidence_unit_id=audit_evidence_unit_id,
                unit_id=selection.unit.unit_id,
            ),
        )
    except Exception:
        asyncio.run(_close_runtime(kernel, store))
        raise
    try:
        report = asyncio.run(
            _run_twelfth_trial(
                selection=selection,
                run_id=run_id,
                repeat_index=repeat_index,
                repository_evidence=repository_evidence,
                audit_evidence_unit_id=audit_evidence_unit_id,
                prepared_extraction_prompt=prepared_extraction_prompt,
                client=client,
                tenant=tenant,
                execution_model_id=execution_model_id,
                evidence_observer=journal,
                kernel=kernel,
                store=store,
            )
        )
    except Exception:
        asyncio.run(_close_runtime(kernel, store))
        raise
    return _bind_repeat_authorization(report, authorization=authorization)


def recover_twelfth_nested_event_holdout_trial(
    *,
    archive: Path,
    run_id: str,
    repeat_index: int,
    authorization: RepeatAuthorization,
) -> dict[str, object]:
    """Rebuild a terminal report from durable evidence without a provider call."""

    if authorization.run_id != run_id or authorization.repeat_index != repeat_index:
        raise RuntimeError("twelfth holdout recovery authorization does not match")
    authorization.require_active()
    with verified_corpus_root(archive) as corpus_root:
        selection = select_twelfth_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence != authorization.repository_evidence:
        raise RuntimeError("repository differs from sealed twelfth reservation")
    audit_evidence_unit_id = authorization.claimed_provider_evidence_unit_id()
    identity = v12_journal_identity(
        authorization=authorization,
        audit_evidence_unit_id=audit_evidence_unit_id,
        unit_id=selection.unit.unit_id,
    )
    journal = V12ExecutionJournal.open_existing(
        path=v12_journal_path(authorization.reservation_path),
        identity=identity,
    )
    agent_run = journal.latest_evidence(unit=selection.unit)
    report = build_v12_report(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
        configured_model_id=_MODEL_ID,
        execution_model_id=_MODEL_ID.replace(":", "/", 1),
        repository_evidence=repository_evidence,
        agent_run=agent_run,
    )
    return _bind_repeat_authorization(report, authorization=authorization)


def preflight_twelfth_nested_event_holdout_trial(*, archive: Path) -> None:
    """Verify the sealed archive and V12 source before reservation."""

    with verified_corpus_root(archive) as corpus_root:
        select_twelfth_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )


async def _run_twelfth_trial(  # noqa: PLR0913
    *,
    selection: NestedHoldoutSelection,
    run_id: str,
    repeat_index: int,
    repository_evidence: dict[str, object],
    audit_evidence_unit_id: str,
    prepared_extraction_prompt: str,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    execution_model_id: str,
    evidence_observer: V12ExecutionJournal,
    kernel: AsyncClosable,
    store: AsyncClosable,
) -> dict[str, object]:
    try:
        agent_run = await execute_three_source_unit_agents(
            client=client,
            tenant=tenant,
            model_id=execution_model_id,
            execution_namespace=hashlib.sha256(
                audit_evidence_unit_id.encode("utf-8")
            ).hexdigest(),
            unit=selection.unit,
            extraction_prompt_policy=V12_EXTRACTION_PROMPT_POLICY,
            prepared_extraction_prompt=prepared_extraction_prompt,
            normalization_prompt_builder=v12_normalization_prompt,
            normalization_prompt_version=V12_NORMALIZATION_PROMPT_VERSION,
            normalization_output_schema=SourceUnitNormalizationOutputV12,
            review_prompt_builder=v12_normalized_review_prompt,
            review_prompt_version=V12_NORMALIZED_REVIEW_PROMPT_VERSION,
            audit_evidence_unit_id=audit_evidence_unit_id,
            evidence_observer=evidence_observer,
            attempt_observer=evidence_observer.observe_attempt,
        )
    finally:
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()
    if collect_repository_evidence(_REPO_ROOT) != repository_evidence:
        raise RuntimeError("repository changed during twelfth holdout trial")
    return build_v12_report(
        selection=selection,
        run_id=run_id,
        repeat_index=repeat_index,
        configured_model_id=_MODEL_ID,
        execution_model_id=execution_model_id,
        repository_evidence=repository_evidence,
        agent_run=agent_run,
    )


async def _close_runtime(kernel: AsyncClosable, store: AsyncClosable) -> None:
    """Close a prepared runtime when execution cannot start or complete."""

    with suppress(Exception):
        await kernel.close()
    with suppress(Exception):
        await store.close()


def _prepare_v12_extraction_prompt(selection: NestedHoldoutSelection) -> str:
    """Build and verify the first V12 prompt before claiming the one-shot."""

    prompt = V12_EXTRACTION_PROMPT_POLICY.extraction_prompt(selection.unit)
    require_v12_prompt_preregistration(prompt)
    return prompt


def _bind_repeat_authorization(
    report: dict[str, object],
    *,
    authorization: RepeatAuthorization,
) -> dict[str, object]:
    authorization.require_active()
    report.pop("report_sha256", None)
    report["repeat_authorization"] = {
        "run_id": authorization.run_id,
        "repeat_index": authorization.repeat_index,
        "token_sha256": hashlib.sha256(authorization.token.encode()).hexdigest(),
    }
    report["report_sha256"] = sha256_json(report)
    return report


__all__ = [
    "preflight_twelfth_nested_event_holdout_trial",
    "recover_twelfth_nested_event_holdout_trial",
    "run_twelfth_nested_event_holdout_trial",
]
