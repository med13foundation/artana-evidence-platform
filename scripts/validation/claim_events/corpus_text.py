"""Fetch-on-demand rehydration of licence-restricted BioNLP-ST GE corpus text.

The BioNLP-ST 2011 GE licence (clause 6) requires organiser permission before a
commercial or non-academic organisation may make the corpus public.  This
repository is public, so no corpus text is committed: the TG-04 fixtures ship
the parts that are ours -- offsets, event and role mappings, adjudications, the
exclusion ledger -- and carry only opaque digests of the text those offsets
address.  See `scripts/validation/RESTRICTED_CORPORA.md`.

The two halves are separated by `redact_fixture_payload` and rejoined by
`rehydrate_fixture_payload`, which is exact in both directions: rehydrating a
redacted fixture reproduces the original text-bearing bytes, so the digest a
gate pinned before the redaction still pins the same panel afterwards.

Nothing here writes inside the repository.  The corpus is fetched to a cache
that `.gitignore` excludes, or to wherever `ARTANA_BIONLP_GE_CORPUS` points.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Final, cast

#: Points at an already-extracted corpus, for offline or shared-cache runs.
RESTRICTED_CORPUS_ENV_VAR: Final = "ARTANA_BIONLP_GE_CORPUS"
#: Default fetch destination, matching `scripts/fetch_bionlp_ge_corpus.py`.
DEFAULT_CORPUS_CACHE: Final = Path(".corpus-cache/bionlp-ge-2011-devel")
_CORPUS_DIRECTORY_GLOB: Final = "BioNLP-ST_2011_genia_devel*"
_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_FETCH_COMMAND: Final = "python3 scripts/fetch_bionlp_ge_corpus.py"

#: Marks a fixture whose corpus text was removed before it was committed.
RESTRICTED_TEXT_KEY: Final = "restricted_text"
_RESTRICTED_TEXT_POLICY: Final = (
    "fetch-on-demand; see scripts/validation/RESTRICTED_CORPORA.md"
)


#: One reason string for every check that cannot run without restricted text.
#: It names why the text is absent and exactly what re-enables the check, so a
#: skipped run reports a missing corpus rather than looking like lost coverage.
RESTRICTED_CORPUS_SKIP_REASON: Final = (
    "Needs the BioNLP-ST 2011 GE corpus, which this public repository does not "
    "commit: GE licence clause 6 requires organiser permission before a "
    "commercial or non-academic organisation may make it public. "
    f"Re-enable with `{_FETCH_COMMAND}`, or by pointing "
    f"{RESTRICTED_CORPUS_ENV_VAR} at an extracted copy. "
    "See scripts/validation/RESTRICTED_CORPORA.md."
)


class RestrictedCorpusUnavailableError(RuntimeError):
    """The restricted corpus is needed but is not present on this machine."""


def _unavailable(detail: str) -> RestrictedCorpusUnavailableError:
    return RestrictedCorpusUnavailableError(
        f"{detail}\n"
        f"\n"
        f"This fixture stores no corpus text, because the BioNLP-ST 2011 GE\n"
        f"licence restricts public redistribution and this repository is\n"
        f"public.  The text is fetched on demand instead.\n"
        f"\n"
        f"    {_FETCH_COMMAND}\n"
        f"\n"
        f"or set {RESTRICTED_CORPUS_ENV_VAR} to an already-extracted copy.\n"
        f"See scripts/validation/RESTRICTED_CORPORA.md.",
    )


def corpus_root() -> Path:
    """Locate the extracted corpus, or explain exactly how to obtain it."""

    override = os.environ.get(RESTRICTED_CORPUS_ENV_VAR)
    if override:
        resolved = _data_directory(Path(override))
        if resolved is None:
            raise _unavailable(
                f"{RESTRICTED_CORPUS_ENV_VAR} is set to {override!r}, but no "
                f"BioNLP-ST GE documents were found there.",
            )
        return resolved
    resolved = _data_directory(_REPO_ROOT / DEFAULT_CORPUS_CACHE)
    if resolved is None:
        raise _unavailable("The BioNLP-ST 2011 GE corpus is not available locally.")
    return resolved


def corpus_is_available() -> bool:
    """Report whether restricted text can be rehydrated, without raising."""

    try:
        corpus_root()
    except RestrictedCorpusUnavailableError:
        return False
    return True


def _data_directory(candidate: Path) -> Path | None:
    """Accept the data directory itself, a cache root, or an extract root."""

    if not candidate.exists():
        return None
    if any(candidate.glob("*.txt")):
        return candidate
    for parent in (candidate, candidate / "extracted"):
        roots = sorted(parent.glob(_CORPUS_DIRECTORY_GLOB))
        for root in roots:
            if any(root.glob("*.txt")):
                return root
    return None


def normalized_characters(source_text: str) -> list[tuple[str, int]]:
    """Normalize newlines and trailing whitespace, keeping raw offsets."""

    newline_normalized: list[tuple[str, int]] = []
    raw_index = 0
    while raw_index < len(source_text):
        if source_text.startswith("\r\n", raw_index):
            newline_normalized.append(("\n", raw_index + 1))
            raw_index += 2
            continue
        newline_normalized.append((source_text[raw_index], raw_index))
        raw_index += 1

    lines: list[list[tuple[str, int]]] = [[]]
    newline_indices: list[int] = []
    for character in newline_normalized:
        if character[0] == "\n":
            newline_indices.append(character[1])
            lines.append([])
        else:
            lines[-1].append(character)

    normalized: list[tuple[str, int]] = []
    for line_index, line in enumerate(lines):
        while line and line[-1][0].isspace():
            line.pop()
        normalized.extend(line)
        if line_index < len(newline_indices):
            normalized.append(("\n", newline_indices[line_index]))
    while normalized and normalized[0][0].isspace():
        normalized.pop(0)
    while normalized and normalized[-1][0].isspace():
        normalized.pop()
    return normalized


def normalized_document_text(raw_source_text: str) -> str:
    """Return the normalized document text the fixture offsets address."""

    return "".join(character for character, _ in normalized_characters(raw_source_text))


def document_text(root: Path, document_id: str) -> str:
    """Read and normalize one corpus document."""

    path = root / f"{document_id}.txt"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise _unavailable(
            f"Corpus document {document_id!r} is missing from {root}.",
        ) from error
    return normalized_document_text(raw)


def text_digest(text: str) -> str:
    """Digest document text so the fixture can pin it without carrying it."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_fixture_bytes(payload: dict[str, object]) -> bytes:
    """Serialize a fixture exactly as `import_bionlp_claim_event_fixture` does."""

    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _locator(start: int, end: int) -> str:
    return f"char:{start}-{end}"


def _parse_locator(raw: object, label: str) -> tuple[int, int]:
    if not isinstance(raw, str) or not raw.startswith("char:"):
        raise ValueError(f"{label} must use char:<start>-<end>")
    start_text, _, end_text = raw.removeprefix("char:").partition("-")
    if not start_text.isdigit() or not end_text.isdigit():
        raise ValueError(f"{label} must use char:<start>-<end>")
    return int(start_text), int(end_text)


def _cases(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", payload["cases"])


def _events(case: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", case["events"])


def _arguments(event: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", event["arguments"])


def is_redacted(payload: dict[str, object]) -> bool:
    """Report whether a fixture payload had its corpus text removed."""

    return RESTRICTED_TEXT_KEY in payload


def redact_fixture_payload(payload: dict[str, object]) -> dict[str, object]:
    """Strip every verbatim corpus string, keeping offsets and our own labels.

    Each removed span becomes a locator, so `rehydrate_fixture_payload` can
    recover it exactly from the fetched document.  The redacted payload records
    the digest of the text-bearing fixture it came from, so the panel a gate
    pinned before redaction stays pinned to the same bytes afterwards.
    """

    redacted = copy.deepcopy(payload)
    if is_redacted(redacted):
        raise ValueError("fixture payload is already redacted")
    archive_digests: set[str] = set()
    corpora: set[str] = set()
    for case in _cases(redacted):
        source_text = case.pop("source_text")
        if not isinstance(source_text, str):
            raise TypeError("case source_text must be a string")
        case["source_sha256"] = text_digest(source_text)
        case["source_length"] = len(source_text)
        source = cast("dict[str, object]", case["source"])
        archive_digests.add(cast("str", source["archive_sha256"]))
        corpora.add(cast("str", source["corpus"]))
        for event in _events(case):
            _redact_event(event, source_text)
    redacted[RESTRICTED_TEXT_KEY] = {
        "archive_sha256": sorted(archive_digests)[0] if archive_digests else "",
        "corpus": sorted(corpora)[0] if corpora else "",
        "policy": _RESTRICTED_TEXT_POLICY,
        "rehydrated_sha256": hashlib.sha256(
            canonical_fixture_bytes(payload),
        ).hexdigest(),
    }
    return redacted


def _redact_event(event: dict[str, object], source_text: str) -> None:
    source_span = event.pop("source_span")
    trigger_span = event.pop("trigger_span")
    trigger_start = event.pop("trigger_source_start")
    if not isinstance(trigger_span, str) or not isinstance(trigger_start, int):
        raise TypeError("event trigger fields are malformed")
    start, end = _parse_locator(event["source_locator"], "source_locator")
    if source_text[start:end] != source_span:
        raise ValueError("source_locator does not bind its span; refusing to redact")
    trigger_end = trigger_start + len(trigger_span)
    if source_text[trigger_start:trigger_end] != trigger_span:
        raise ValueError("trigger offset does not bind its span; refusing to redact")
    event["trigger_locator"] = _locator(trigger_start, trigger_end)
    for argument in _arguments(event):
        exact_span = argument.pop("exact_span")
        argument_start = argument.pop("source_start")
        if not isinstance(exact_span, str) or not isinstance(argument_start, int):
            raise TypeError("argument span fields are malformed")
        argument_end = argument_start + len(exact_span)
        if source_text[argument_start:argument_end] != exact_span:
            raise ValueError(
                "argument offset does not bind its span; refusing to redact",
            )
        argument["source_locator"] = _locator(argument_start, argument_end)


def rehydrate_fixture_payload(
    payload: dict[str, object],
    *,
    root: Path | None = None,
) -> dict[str, object]:
    """Restore corpus text into a redacted fixture, verifying every document.

    The result is byte-identical to the fixture that was redacted, so callers
    may hash it against a digest pinned before the corpus text was removed.
    """

    if not is_redacted(payload):
        raise ValueError("fixture payload carries no restricted-text declaration")
    resolved = corpus_root() if root is None else root
    rehydrated = copy.deepcopy(payload)
    declaration = cast(
        "dict[str, object]",
        rehydrated.pop(RESTRICTED_TEXT_KEY),
    )
    for case in _cases(rehydrated):
        source = cast("dict[str, object]", case["source"])
        document_id = cast("str", source["document_id"])
        source_text = document_text(resolved, document_id)
        _require_declared_text(case, document_id, source_text)
        case["source_text"] = source_text
        for event in _events(case):
            _rehydrate_event(event, source_text)
    _require_declared_digest(rehydrated, declaration)
    return rehydrated


def _require_declared_text(
    case: dict[str, object],
    document_id: str,
    source_text: str,
) -> None:
    expected_digest = case.pop("source_sha256")
    expected_length = case.pop("source_length")
    if len(source_text) != expected_length:
        raise ValueError(
            f"corpus document {document_id} is {len(source_text)} characters, "
            f"but the fixture pins {expected_length}",
        )
    if text_digest(source_text) != expected_digest:
        raise ValueError(
            f"corpus document {document_id} does not match the digest the "
            f"fixture pins; the local corpus is not the frozen revision",
        )


def _rehydrate_event(event: dict[str, object], source_text: str) -> None:
    start, end = _parse_locator(event["source_locator"], "source_locator")
    event["source_span"] = source_text[start:end]
    trigger_start, trigger_end = _parse_locator(
        event.pop("trigger_locator"),
        "trigger_locator",
    )
    event["trigger_source_start"] = trigger_start
    event["trigger_span"] = source_text[trigger_start:trigger_end]
    for argument in _arguments(event):
        argument_start, argument_end = _parse_locator(
            argument.pop("source_locator"),
            "argument source_locator",
        )
        argument["source_start"] = argument_start
        argument["exact_span"] = source_text[argument_start:argument_end]


def _require_declared_digest(
    rehydrated: dict[str, object],
    declaration: dict[str, object],
) -> None:
    expected = declaration.get("rehydrated_sha256")
    observed = hashlib.sha256(canonical_fixture_bytes(rehydrated)).hexdigest()
    if observed != expected:
        raise ValueError(
            f"rehydrated fixture hashes to {observed}, but the committed "
            f"fixture pins {expected}; offsets and corpus text disagree",
        )


__all__ = [
    "DEFAULT_CORPUS_CACHE",
    "RESTRICTED_CORPUS_ENV_VAR",
    "RESTRICTED_CORPUS_SKIP_REASON",
    "RESTRICTED_TEXT_KEY",
    "RestrictedCorpusUnavailableError",
    "canonical_fixture_bytes",
    "corpus_is_available",
    "corpus_root",
    "document_text",
    "is_redacted",
    "normalized_characters",
    "normalized_document_text",
    "redact_fixture_payload",
    "rehydrate_fixture_payload",
    "text_digest",
]
