"""Execute one pre-registered hidden nested-event holdout repeat."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import Final
from uuid import uuid4

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.corpus import (
    verified_corpus_root,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.report import (
    build_nested_holdout_report,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    NestedHoldoutSelection,
    select_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.service import as_model_client
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    execute_source_unit_agents,
)
from scripts.validation.claim_events.runner import build_tg04_runtime
from scripts.validation.claim_frames.evidence import collect_repository_evidence

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_MODEL_ID: Final = "openai:gpt-5.6-luna"


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
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("nested holdout trial requires a clean tracked worktree")
    return asyncio.run(
        _run_trial(
            selection=selection,
            run_id=run_id,
            repeat_index=repeat_index,
            repository_evidence=repository_evidence,
        ),
    )


async def _run_trial(
    *,
    selection: NestedHoldoutSelection,
    run_id: str,
    repeat_index: int,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
    client, tenant, execution_model_id, kernel, store = build_tg04_runtime(_MODEL_ID)
    if execution_model_id != _MODEL_ID:
        raise RuntimeError("nested holdout runtime model identity changed")
    try:
        agent_run = await execute_source_unit_agents(
            client=as_model_client(client),
            tenant=tenant,
            model_id=execution_model_id,
            execution_namespace=(
                f"{run_id}:{repeat_index}:{selection.unit.unit_id}:{uuid4().hex}"
            ),
            unit=selection.unit,
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
        execution_model_id=execution_model_id,
        repository_evidence=repository_evidence,
        agent_run=agent_run,
    )


__all__ = ["run_nested_event_holdout_trial"]
