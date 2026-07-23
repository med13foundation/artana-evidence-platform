"""Deterministically extend the frozen reserve for one eligible replacement."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.bionlp_cg_adapter import (
    load_development_directory,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    DEFAULT_PATHS as V1_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.selection import (
    _is_frozen_token_span,
    _select_document,
    _verify_exact_span,
    load_frozen_selection,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (
    CONSUMED_CASE_ID,
    REPLACEMENT_DOCUMENT_ID,
    RESERVATION_BASE_COMMIT,
    RESERVATION_SALT,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.contracts import (
    FreshCGSelectionV2,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        FreshCGCase,
    )

_PMID = re.compile(r"PMID-[0-9]+")
_RETAINED_CASE_COUNT = 7


def _git_executable() -> str:
    value = shutil.which("git")
    if value is None:  # pragma: no cover - repository execution requires Git.
        raise RuntimeError("git executable was not found")
    return value


_GIT = _git_executable()


def build_selection(development_path: Path) -> FreshCGSelectionV2:
    """Preserve seven untouched cases and add the first eligible extended case."""

    original = load_frozen_selection(V1_PATHS.selection)
    retained = tuple(
        case for case in original.cases if case.case_id != CONSUMED_CASE_ID
    )
    if len(retained) != _RETAINED_CASE_COUNT:
        raise ValueError("sealed V1 consumed-case accounting changed")
    ordered = _reservation_order(development_path)
    if tuple(ordered[:12]) != original.reserve_order:
        raise ValueError("recomputed reservation does not preserve the original twelve")
    replacement, replacement_position = _first_extended_eligible(
        development_path,
        ordered,
    )
    if replacement.document_id != REPLACEMENT_DOCUMENT_ID:
        raise ValueError("configured replacement differs from deterministic selection")
    cases = tuple(
        case.model_copy(update={"case_order": order})
        for order, case in enumerate((*retained, replacement), start=1)
    )
    selected_ids = tuple(case.document_id for case in cases)
    unused_original = tuple(
        item for item in original.reserve_order if item not in selected_ids
    )
    return FreshCGSelectionV2(
        reservation_extension_policy=(
            "SAME_SALTED_ORDER_FIRST_ELIGIBLE_AFTER_ORIGINAL_TWELVE"
        ),
        reservation_base_commit=RESERVATION_BASE_COMMIT,
        reservation_salt=RESERVATION_SALT,
        original_reserve_order=original.reserve_order,
        extended_reserve_order=tuple(ordered[:replacement_position]),
        selected_document_ids=selected_ids,
        unused_original_document_ids=unused_original,
        consumed_case_id=CONSUMED_CASE_ID,
        consumed_document_id=original.cases[0].document_id,
        replacement_document_id=replacement.document_id,
        replacement_reserve_position=replacement_position,
        skipped_documents=original.skipped_documents,
        cases=cases,
        provider_packet_excludes=original.provider_packet_excludes,
    )


def load_v2_selection(path: Path) -> FreshCGSelectionV2:
    selection = FreshCGSelectionV2.model_validate_json(path.read_text(encoding="utf-8"))
    for case in selection.cases:
        _verify_case(case)
    return selection


def write_selection(path: Path, development_path: Path) -> None:
    selection = build_selection(development_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(selection.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reservation_order(development_path: Path) -> tuple[str, ...]:
    tracked = subprocess.run(  # noqa: S603 - fixed local Git read.
        [
            _GIT,
            "grep",
            "-I",
            "-h",
            "-o",
            "PMID-[0-9][0-9]*",
            RESERVATION_BASE_COMMIT,
            "--",
        ],
        cwd=V1_PATHS.selection.parents[3],
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode not in {0, 1}:
        raise ValueError("cannot reconstruct pre-reservation tracked PMIDs")
    excluded = set(_PMID.findall(tracked.stdout))
    corpus = {path.stem for path in development_path.glob("PMID-*.txt")}
    return tuple(
        sorted(
            corpus - excluded,
            key=lambda item: hashlib.sha256(
                f"{RESERVATION_SALT}{item}".encode()
            ).hexdigest(),
        )
    )


def _first_extended_eligible(
    development_path: Path,
    reserve_order: tuple[str, ...],
) -> tuple[FreshCGCase, int]:
    documents = {
        document.document_id: document
        for document in load_development_directory(development_path)
    }
    for position, document_id in enumerate(reserve_order[12:], start=13):
        document = documents.get(document_id)
        if document is None:
            raise ValueError(f"extended reserve document is absent: {document_id}")
        case, _ = _select_document(development_path, document, case_order=8)
        if case is not None:
            return case, position
    raise ValueError("extended reserve contains no eligible replacement")


def _verify_case(case: FreshCGCase) -> None:
    source_bytes = base64.b64decode(case.source_bytes_base64, validate=True)
    if source_bytes.decode(case.source_encoding) != case.source_text:
        raise ValueError(f"frozen source bytes differ from text: {case.case_id}")
    if hashlib.sha256(source_bytes).hexdigest() != case.source_sha256:
        raise ValueError(f"frozen source hash mismatch: {case.case_id}")
    _verify_exact_span(case.source_text, case.permitted_context, case.case_id)
    _verify_exact_span(case.source_text, case.event.trigger, case.case_id)
    if not _is_frozen_token_span(case.source_text, case.event.trigger):
        raise ValueError(f"frozen event mention splits a token: {case.case_id}")
    for participant in case.participants:
        _verify_exact_span(case.source_text, participant.mention, case.case_id)
        if not _is_frozen_token_span(case.source_text, participant.mention):
            raise ValueError(f"participant mention splits a token: {case.case_id}")
    reference_payload = {
        "document_id": case.document_id,
        "event": case.event,
        "participants": case.participants,
    }
    if canonical_sha256(reference_payload) != case.direct_cg_reference_sha256:
        raise ValueError(f"direct CG reference hash mismatch: {case.case_id}")


__all__ = ["build_selection", "load_v2_selection", "write_selection"]
