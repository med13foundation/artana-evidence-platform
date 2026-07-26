"""The committed fixtures must carry no restricted corpus text, and must still
rehydrate to the exact panel their digests pin.

The BioNLP-ST 2011 GE licence (clause 6) bars a non-academic organisation from
making the corpus public without organiser permission, and this repository is
public.  So the fixtures ship offsets and our own labels, and the text is
fetched on demand.

These checks run without the corpus.  The round-trip is proved against a
synthetic corpus built in `tmp_path`, so the guarantee is tested everywhere, not
only on machines that happen to have fetched the real archive.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_ENV_VAR,
    RestrictedCorpusUnavailableError,
    canonical_fixture_bytes,
    corpus_root,
    is_redacted,
    redact_fixture_payload,
    rehydrate_fixture_payload,
    text_digest,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    DEVELOPMENT_FIXTURE_V2_PATH,
    REDACTED_DEVELOPMENT_FIXTURE_SHA256,
    REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256,
)

#: Every key that ever held verbatim corpus prose.
_TEXT_KEYS = frozenset({"source_text", "source_span", "trigger_span", "exact_span"})
_COMMITTED = (
    (DEFAULT_DEVELOPMENT_FIXTURE_PATH, REDACTED_DEVELOPMENT_FIXTURE_SHA256),
    (DEVELOPMENT_FIXTURE_V2_PATH, REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256),
)
_DOCUMENT = "SYNTHETIC-0001"
_SOURCE_TEXT = "Synthetic title.\n\nAlpha protein binds beta protein in vitro."


def _text_bearing_keys(node: object) -> set[str]:
    """Every key anywhere in the payload that would carry corpus prose."""

    if isinstance(node, dict):
        found = {key for key in node if key in _TEXT_KEYS}
        for value in node.values():
            found |= _text_bearing_keys(value)
        return found
    if isinstance(node, list):
        found: set[str] = set()
        for item in node:
            found |= _text_bearing_keys(item)
        return found
    return set()


def _synthetic_payload() -> dict[str, Any]:
    span_start = _SOURCE_TEXT.index("Alpha protein binds beta protein")
    span_end = span_start + len("Alpha protein binds beta protein")
    return {
        "schema_version": "tg04_nary_claim_benchmark.v1",
        "metadata": {"purpose": "synthetic"},
        "cases": [
            {
                "case_id": f"synthetic:{_DOCUMENT}",
                "title": _DOCUMENT,
                "control_status": "EVENT_GOLD",
                "source": {
                    "archive_sha256": "0" * 64,
                    "corpus": "SYNTHETIC",
                    "document_id": _DOCUMENT,
                    "mapping_version": "synthetic.v1",
                    "source_url": "https://example.invalid/synthetic.tar.gz",
                },
                "source_text": _SOURCE_TEXT,
                "events": [
                    {
                        "event_id": f"{_DOCUMENT}:E1",
                        "event_type": "BINDING",
                        "source_locator": f"char:{span_start}-{span_end}",
                        "source_span": _SOURCE_TEXT[span_start:span_end],
                        "trigger_span": "binds",
                        "trigger_source_start": _SOURCE_TEXT.index("binds"),
                        "arguments": [
                            {
                                "argument_id": "T1",
                                "event_role": "THEME",
                                "participant_role": "GENE_OR_PROTEIN",
                                "exact_span": "Alpha protein",
                                "source_start": _SOURCE_TEXT.index("Alpha protein"),
                            },
                        ],
                    },
                ],
            },
        ],
    }


@pytest.mark.parametrize(("path", "expected"), _COMMITTED)
def test_committed_fixture_carries_no_corpus_text(path: Path, expected: str) -> None:
    """The exposure this redaction exists to close, asserted on the bytes."""

    raw = path.read_bytes()
    payload: dict[str, Any] = json.loads(raw)

    assert is_redacted(payload), f"{path} must declare its restricted-text policy"
    assert _text_bearing_keys(payload) == set(), (
        f"{path} still carries verbatim corpus text"
    )
    assert hashlib.sha256(raw).hexdigest() == expected, (
        "the committed fixture moved; update the pin deliberately, never to "
        "make a gate pass"
    )


@pytest.mark.parametrize(("path", "expected"), _COMMITTED)
def test_committed_fixture_still_pins_the_text_it_no_longer_carries(
    path: Path,
    expected: str,
) -> None:
    """Removing the text must not weaken the panel's identity.

    Each case pins the digest and length of the document its offsets address,
    so a corpus at a different revision is rejected rather than silently
    rescoring the benchmark against different sentences.
    """

    payload: dict[str, Any] = json.loads(path.read_bytes())

    for case in payload["cases"]:
        assert len(case["source_sha256"]) == 64
        assert case["source_length"] > 0
    declaration = payload["restricted_text"]
    assert len(declaration["rehydrated_sha256"]) == 64
    assert declaration["corpus"] == "BioNLP-ST-2011-GE"


def test_redaction_round_trips_exactly(tmp_path: Path) -> None:
    """Rehydration must reproduce the original bytes, or the pins are lies.

    This is what lets `FROZEN_DEVELOPMENT_FIXTURE_SHA256` keep its pre-redaction
    value, and what keeps the frozen preregistration that cites it honest.
    """

    original = _synthetic_payload()
    (tmp_path / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")

    redacted = redact_fixture_payload(original)
    rehydrated = rehydrate_fixture_payload(redacted, root=tmp_path)

    assert _text_bearing_keys(redacted) == set()
    assert canonical_fixture_bytes(rehydrated) == canonical_fixture_bytes(original)


def test_rehydration_rejects_a_corpus_that_is_not_the_pinned_revision(
    tmp_path: Path,
) -> None:
    """A different corpus revision must fail loudly, not rescore quietly."""

    redacted = redact_fixture_payload(_synthetic_payload())
    (tmp_path / f"{_DOCUMENT}.txt").write_text(
        _SOURCE_TEXT.replace("Alpha", "Gamma"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the digest"):
        rehydrate_fixture_payload(redacted, root=tmp_path)


def test_rehydration_rejects_offsets_that_disagree_with_the_text(
    tmp_path: Path,
) -> None:
    """Tampered offsets must not survive: the panel digest is checked last."""

    redacted = redact_fixture_payload(_synthetic_payload())
    tampered = copy.deepcopy(redacted)
    tampered["cases"][0]["events"][0]["trigger_locator"] = "char:0-5"
    (tmp_path / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")

    with pytest.raises(ValueError, match="rehydrated fixture hashes to"):
        rehydrate_fixture_payload(tampered, root=tmp_path)


def test_redaction_refuses_offsets_that_do_not_bind_their_span() -> None:
    """Redaction is destructive, so it must verify before it discards."""

    payload = _synthetic_payload()
    payload["cases"][0]["events"][0]["source_locator"] = "char:0-4"

    with pytest.raises(ValueError, match="refusing to redact"):
        redact_fixture_payload(payload)


def test_digest_is_over_the_normalized_text() -> None:
    assert text_digest("abc") == hashlib.sha256(b"abc").hexdigest()


def test_missing_corpus_names_the_licence_and_the_remedy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing corpus must read as a missing corpus, not as a crash."""

    monkeypatch.setenv(RESTRICTED_CORPUS_ENV_VAR, str(tmp_path / "absent"))

    with pytest.raises(RestrictedCorpusUnavailableError) as error:
        corpus_root()

    message = str(error.value)
    assert "scripts/fetch_bionlp_ge_corpus.py" in message
    assert RESTRICTED_CORPUS_ENV_VAR in message
    assert "scripts/validation/RESTRICTED_CORPORA.md" in message


def test_corpus_root_accepts_a_directory_of_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")
    monkeypatch.setenv(RESTRICTED_CORPUS_ENV_VAR, str(tmp_path))

    assert corpus_root() == tmp_path


def test_corpus_root_accepts_a_fetched_cache_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The layout `scripts/fetch_bionlp_ge_corpus.py` actually produces."""

    data = tmp_path / "extracted" / "BioNLP-ST_2011_genia_devel_data_rev1"
    data.mkdir(parents=True)
    (data / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")
    monkeypatch.setenv(RESTRICTED_CORPUS_ENV_VAR, str(tmp_path))

    assert corpus_root() == data


def test_redacting_twice_is_refused() -> None:
    redacted = redact_fixture_payload(_synthetic_payload())

    with pytest.raises(ValueError, match="already redacted"):
        redact_fixture_payload(redacted)


def test_rehydrating_a_text_bearing_payload_is_refused() -> None:
    with pytest.raises(ValueError, match="no restricted-text declaration"):
        rehydrate_fixture_payload(_synthetic_payload())
