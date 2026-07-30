"""Recover REAL model-authored claim labels from the kernel audit trail, at $0.

The extractor aborts on real BC5CDR abstracts inside the claim-framing
validators, so no ``ClaimFrame`` survives to the return value. But every framing
call is persisted to ``artana.kernel_events`` BEFORE validation, so the model's
own subject/object labels are recoverable without a new provider call.

These are PRE-VALIDATION model outputs. They are evidence about what labels the
model authors -- which is what a frame-body identity would hash -- and they are
NOT evidence about what the production write path would persist or merge. Ten
of the eleven documents never reached persistence at all.

Each frame is correlated back to its BC5CDR document by locating the frame's own
``sentence`` inside the corpus. The sentence is used and discarded: only labels,
MeSH ids and counts are written, and ``_reject_spans`` refuses to write at all
if a label ever exceeds the extraction prompt's own 50-character cap or carries
a sentence boundary. That cap is why the labels are worth reading -- see
``docs/validation/reports/2026-07-26-claim-identity-merge-measurement.md``.

Usage: python3 -m scripts.validation.claim_identity_merge.harvest_real_labels
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "services"))
sys.path.insert(0, str(REPO_ROOT))

from artana_evidence_api.claim_fingerprint import (  # noqa: E402
    _normalize_label,
    compute_claim_fingerprint,
)

from scripts.validation.claim_identity_merge import corpus as bc5cdr  # noqa: E402

DEFAULT_CONTAINER = "artana-evidence-platform-postgres-1"
DEFAULT_DATABASE = "artana_dev"
DEFAULT_DATABASE_USER = "artana_dev"
FINGERPRINT_PREVIEW_CHARS = 12

# The extraction prompt caps subject and object at 50 characters
# (``document_extraction_prompting.py``). Anything longer is not a label the
# model could have authored, so it would be corpus prose that leaked in.
PROMPT_LABEL_MAX_CHARS = 50
_SENTENCE_BOUNDARY = re.compile(r"[.!?]\s")

QUERY = (
    "select payload_json from artana.kernel_events "
    "where event_type='model_terminal' "
    "and payload_json::text like '%claim_framing%';"
)


class SpanLeakError(RuntimeError):
    """Raised when an output string is document prose rather than an entity label."""


def _reject_spans(report: dict) -> None:
    """Refuse to write document prose, whatever field it arrived in."""
    for subject, _relation, object_ in report["labels"]:
        for label in (subject, object_):
            if label is None:
                continue
            if len(label) > PROMPT_LABEL_MAX_CHARS:
                message = (
                    f"label of {len(label)} characters exceeds the extraction "
                    f"prompt's {PROMPT_LABEL_MAX_CHARS}-character cap; this is "
                    "document prose, not a model-authored label"
                )
                raise SpanLeakError(message)
            if _SENTENCE_BOUNDARY.search(label):
                message = "label carries a sentence boundary; refusing to write prose"
                raise SpanLeakError(message)


def read_framing_events(container: str, database: str, user: str) -> list[dict]:
    """Pull every persisted claim-framing model terminal from the audit trail."""
    command = [  # noqa: S607 -- fixed argv; docker is resolved from PATH by design
        "docker", "exec", container, "psql",
        "-U", user, "-d", database, "-t", "-A", "-c", QUERY,
    ]
    raw = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    frames: list[dict] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        body = payload.get("output_json")
        if not body:
            continue
        try:
            decoded = json.loads(body) if isinstance(body, str) else body
        except json.JSONDecodeError:
            continue
        for relation in decoded.get("relations") or []:
            frames.append(
                {
                    "subject": relation.get("subject"),
                    "relation_type": relation.get("relation_type"),
                    "object": relation.get("object"),
                    "sentence": relation.get("sentence") or "",
                    "polarity": relation.get("polarity"),
                    "epistemic_status": relation.get("epistemic_status"),
                    "cost_usd": payload.get("cost_usd"),
                },
            )
    return frames


def locate(frames: list[dict], corpus: bc5cdr.Corpus) -> None:
    """Attach the PMID, gold facts and triple fingerprint to each frame in place."""
    facts_of_document: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for fact, pmids in corpus.cid_facts.items():
        for pmid in pmids:
            facts_of_document[pmid].append(fact)

    texts = {pmid: document.text for pmid, document in corpus.documents.items()}
    for frame in frames:
        sentence = frame["sentence"].strip()
        matches = [pmid for pmid, text in texts.items() if sentence and sentence in text]
        frame["pmid"] = matches[0] if len(matches) == 1 else None
        frame["gold_facts_in_document"] = (
            sorted("|".join(fact) for fact in facts_of_document.get(frame["pmid"], []))
            if frame["pmid"]
            else []
        )
        complete = frame["subject"] and frame["object"] and frame["relation_type"]
        frame["triple_fingerprint"] = (
            compute_claim_fingerprint(
                frame["subject"],
                frame["relation_type"],
                frame["object"],
            )
            if complete
            else None
        )
        frame["normalised_subject"] = (
            _normalize_label(frame["subject"]) if frame["subject"] else None
        )
        frame["normalised_object"] = (
            _normalize_label(frame["object"]) if frame["object"] else None
        )


def build_report(frames: list[dict]) -> dict:
    located = [frame for frame in frames if frame["pmid"]]
    by_fingerprint = collections.Counter(
        frame["triple_fingerprint"] for frame in located if frame["triple_fingerprint"]
    )

    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for frame in located:
        groups[frame["triple_fingerprint"]].append(frame)
    cross_document = [
        {
            "fingerprint": fingerprint[:FINGERPRINT_PREVIEW_CHARS],
            "documents": sorted({member["pmid"] for member in members}),
            "labels": sorted({(m["subject"], m["object"]) for m in members}),
        }
        for fingerprint, members in groups.items()
        if len({member["pmid"] for member in members}) > 1
    ]

    return {
        "provenance": "pre-validation model output recovered from "
        "artana.kernel_events; no new provider calls",
        "framing_calls_with_a_frame_body": len(
            {frame["sentence"] for frame in frames if frame["sentence"]},
        ),
        "frames_recovered": len(frames),
        "frames_located_in_bc5cdr": len(located),
        "distinct_documents_covered": len({frame["pmid"] for frame in located}),
        "distinct_triple_fingerprints": len(by_fingerprint),
        "fingerprints_shared_by_more_than_one_frame": sum(
            1 for count in by_fingerprint.values() if count > 1
        ),
        "cross_document_fingerprint_agreements": cross_document,
        "labels": sorted(
            {
                (frame["subject"], frame["relation_type"], frame["object"])
                for frame in located
            },
        ),
        "documents_and_their_gold_facts": {
            frame["pmid"]: frame["gold_facts_in_document"] for frame in located
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=None, help="BC5CDR directory")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--user", default=DEFAULT_DATABASE_USER)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "validation" / "results"),
    )
    args = parser.parse_args()

    frames = read_framing_events(args.container, args.database, args.user)
    corpus = bc5cdr.load(args.corpus)
    locate(frames, corpus)
    report = build_report(frames)
    _reject_spans(report)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "2026-07-26-claim-identity-merge-model-labels.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"frames recovered            : {report['frames_recovered']}")
    print(f"located in BC5CDR           : {report['frames_located_in_bc5cdr']}")
    print(f"distinct documents covered  : {report['distinct_documents_covered']}")
    print(
        f"cross-document fingerprint agreements: "
        f"{len(report['cross_document_fingerprint_agreements'])}",
    )
    print("\nmodel-authored labels (subject | relation | object):")
    for subject, relation, object_ in report["labels"]:
        print(f"   {subject!r} | {relation} | {object_!r}")
    print("\ndocument -> gold CID facts it actually asserts:")
    for pmid, facts in report["documents_and_their_gold_facts"].items():
        print(f"   {pmid}: {facts}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
