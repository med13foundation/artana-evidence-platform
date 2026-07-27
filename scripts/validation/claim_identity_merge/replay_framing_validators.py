"""Replay recorded claim-framing model outputs through today's validators, at $0.

``harvest_real_labels.py`` recovers what the model *authored*. This script
answers the next question: what survives. Every framing call persists both its
prompt (``model_requested``) and its output (``model_terminal``) to
``artana.kernel_events``, and the prompt carries the ``BOUND INVENTORY ITEM``
JSON and the ``CLAIM-LOCAL FROZEN SOURCE REGION`` verbatim. That is the entire
input to the framing validator chain, so it can be re-executed against current
code without a new provider call:

    ClaimInventoryItem -> bind_claim_inventory -> derive_claim_local_source_region
    -> _require_inventory_consistency -> llm_relation_to_candidate
    -> normalize_claim_frame

Two details decide whether the replay matches production rather than flattering
it, and both are reproduced here:

* **One answer per inventory claim.** The stage runs one first attempt and, if
  that attempt is rejected, exactly one schema retry whose value it returns.
  Both calls are persisted. Counting them both would double-count the same
  claim, so the retry supersedes its first attempt.
* **A call is all-or-nothing.** ``_validate`` raises out of the whole call on
  the first bad relation, so a call keeps its frames only if *every* relation
  in it passes. Scoring relations independently would overstate the yield.

Only labels, counts and fingerprints are written; ``_reject_spans`` refuses to
write at all if any label exceeds the extraction prompt's own 50-character cap
or carries a sentence boundary, on the same reasoning as the harvest script.

Usage: python3 -m scripts.validation.claim_identity_merge.replay_framing_validators
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "services"))
sys.path.insert(0, str(REPO_ROOT))

from artana_evidence_api.claim_fingerprint import (  # noqa: E402
    compute_claim_fingerprint,
)
from artana_evidence_api.document_extraction_prompting import (  # noqa: E402
    build_single_claim_framing_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (  # noqa: E402
    ClaimArgument,
    ClaimInventoryItem,
    bind_claim_inventory,
    derive_claim_local_source_region,
    normalize_claim_frame,
)
from artana_evidence_api.document_extraction_support.llm_extraction import (  # noqa: E402
    claim_framing,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (  # noqa: E402
    llm_relation_to_candidate,
)

from scripts.validation.claim_identity_merge.harvest_real_labels import (  # noqa: E402
    _SENTENCE_BOUNDARY,
    DEFAULT_CONTAINER,
    DEFAULT_DATABASE,
    DEFAULT_DATABASE_USER,
    PROMPT_LABEL_MAX_CHARS,
    SpanLeakError,
)

FINGERPRINT_PREVIEW_CHARS = 12
DROP_LOGGER = (
    "artana_evidence_api.document_extraction_support.llm_fulltext_extraction"
)

# Several validator messages quote the offending span back at you -- "framed
# relation dropped OUTCOME argument '<source phrase>'". That phrase is corpus
# text, and these reasons are aggregated into a committed results file, so the
# quoted segment is redacted before it is ever counted or written. The stable
# prefix is what carries the diagnosis; the span only says which sentence.
_QUOTED_SPAN = re.compile(r"'[^']*'")

ITEM_MARK = "---\nBOUND INVENTORY ITEM\n---\n"
REGION_MARK = "---\nCLAIM-LOCAL FROZEN SOURCE REGION\n---\n"
RETRY_MARK = "SCHEMA AND SOURCE-BINDING RETRY"

QUERY = """
select json_build_object(
  'step_key', r.payload_json::jsonb->>'step_key',
  'prompt', r.payload_json::jsonb->>'prompt',
  'output_json', t.payload_json::jsonb->>'output_json'
)::text
from artana.kernel_events r
left join artana.kernel_events t
  on t.event_type='model_terminal'
 and t.payload_json::jsonb->>'source_model_requested_event_id' = r.event_id::text
where r.event_type='model_requested'
  and r.payload_json like '%claim_framing%';
"""


class _DropReasonCapture(logging.Handler):
    """Collect the drop reasons the candidate builder only logs."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@dataclasses.dataclass(slots=True)
class _Tally:
    """The three counters that always travel together through the replay."""

    capture: _DropReasonCapture
    stages: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter,
    )
    reasons: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter,
    )

    def record(self, stage: str, reason: str | None = None) -> None:
        """Count a stage outcome and, when given, its redacted reason."""
        self.stages[stage] += 1
        if reason is not None:
            self.reasons[_redact(reason)] += 1


def _redact(reason: str) -> str:
    """Return a validator message with any quoted source span removed."""
    return _QUOTED_SPAN.sub("'<span redacted>'", reason)


def _reject_spans(report: dict) -> None:
    """Refuse to write document prose, whatever field it arrived in."""
    for survivor in report["surviving_frames"]:
        for label in (survivor["subject"], survivor["object"]):
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


def read_framing_pairs(container: str, database: str, user: str) -> list[dict]:
    """Pull every persisted framing prompt alongside the output it produced."""
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
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def parse_document_sha(prompt: str) -> str:
    """Return the document hash the framing prompt froze into its contract."""
    for line in prompt.splitlines():
        if line.startswith("- document_sha256:"):
            return line.split(":", 1)[1].strip()
    message = "document_sha256 missing from recorded framing prompt"
    raise ValueError(message)


def parse_prompt(prompt: str) -> tuple[dict, str]:
    """Recover the bound inventory item and frozen source region from a prompt."""
    item_start = prompt.index(ITEM_MARK) + len(ITEM_MARK)
    item_end = prompt.index(REGION_MARK)
    region = prompt[item_end + len(REGION_MARK) :].rsplit("---\n", 1)[0]
    return json.loads(prompt[item_start:item_end].strip()), region.rstrip("\n")


def final_attempt_per_claim(pairs: list[dict]) -> list[dict]:
    """Keep the answer production would have returned for each inventory claim."""
    final: dict[str, dict] = {}
    for pair in pairs:
        if not pair.get("output_json"):
            continue
        item_json, _region = parse_prompt(pair["prompt"])
        key = json.dumps(item_json, sort_keys=True)
        if key not in final or RETRY_MARK in pair["prompt"]:
            final[key] = pair
    return list(final.values())


def _replay_relation(
    *,
    relation: object,
    bound: object,
    region: object,
    source_sha: str,
    tally: _Tally,
) -> dict | None:
    """Run one recorded relation through the validators; None means rejected."""
    try:
        claim_framing._require_inventory_consistency(  # noqa: SLF001
            relation=relation,
            inventory_claim=bound,
            source_region=region,
        )
    except ValueError as exc:
        tally.record("inventory_consistency", f"inventory_consistency: {exc}")
        return None
    try:
        candidate, _unknown = llm_relation_to_candidate(
            relation,
            source_text=region.text,
            source_hash=source_sha,
        )
    except ValueError as exc:
        tally.record("relation_to_candidate_raised", f"relation_to_candidate: {exc}")
        return None
    if candidate is None or candidate.claim_frame is None:
        last_message = tally.capture.messages[-1] if tally.capture.messages else None
        tally.record(
            "frame_dropped_in_candidate_build",
            None if last_message is None else f"candidate_build: {last_message}",
        )
        return None
    frame = candidate.claim_frame.model_copy(
        update={
            "assertion_arguments": tuple(
                argument.argument for argument in bound.bound_arguments
            ),
        },
    )
    try:
        frame = normalize_claim_frame(
            frame,
            region.text,
            expected_source_hash=source_sha,
        )
    except ValueError as exc:
        tally.record("normalize_claim_frame", f"normalize_claim_frame: {exc}")
        return None
    tally.record("survived")
    return {
        "subject": frame.subject,
        "predicate": frame.predicate,
        "object": frame.object,
        "dedupe_identity": frame.dedupe_identity,
        "triple_fingerprint": compute_claim_fingerprint(
            frame.subject,
            frame.predicate,
            frame.object,
        ),
        "document_sha256": source_sha,
    }


def endpoint_cap_contradiction(attempts: list[dict]) -> dict:
    """Measure the caps that make some claims unframeable however the model answers.

    ``_require_inventory_consistency`` demands that a framed endpoint be exactly
    equal to one of the inventory's typed argument spans. Those spans are
    allowed up to ``ClaimArgument.exact_span``'s 1000 characters, but the
    framing output schema caps ``subject`` and ``object`` at 50. When the claim's
    endpoint argument is longer than the endpoint cap, no schema-valid answer
    can satisfy the consistency check: the model must truncate to fit the
    schema, and the truncated string is then not the argument span. The schema
    retry re-runs the identical impossible task.

    The signature of this happening is a rejected endpoint whose length sits
    exactly at the cap, so both halves are reported.
    """
    endpoint_cap = _endpoint_cap()
    argument_cap = _argument_span_cap()
    span_lengths: list[int] = []
    claims_with_an_over_cap_argument = 0
    rejected_lengths: list[int] = []

    for pair in attempts:
        item_payload, _region = parse_prompt(pair["prompt"])
        spans = [
            argument["exact_span"] for argument in item_payload.get("arguments", [])
        ]
        span_lengths.extend(len(span) for span in spans)
        if any(len(span) > endpoint_cap for span in spans):
            claims_with_an_over_cap_argument += 1
        span_set = set(spans)
        for relation in json.loads(pair["output_json"]).get("relations") or []:
            for role in ("subject", "object"):
                value = relation.get(role)
                if value is not None and value not in span_set:
                    rejected_lengths.append(len(value))

    return {
        "framing_endpoint_cap_chars": endpoint_cap,
        "inventory_argument_span_cap_chars": argument_cap,
        "inventory_argument_spans": len(span_lengths),
        "argument_spans_longer_than_the_endpoint_cap": sum(
            1 for length in span_lengths if length > endpoint_cap
        ),
        "claims_with_at_least_one_over_cap_argument": claims_with_an_over_cap_argument,
        "claims_examined": len(attempts),
        "rejected_endpoints": len(rejected_lengths),
        "rejected_endpoints_pinned_at_the_cap": sum(
            1 for length in rejected_lengths if length >= endpoint_cap - 2
        ),
    }


def _endpoint_cap() -> int:
    """Read the framing schema's own subject/object length cap."""
    schema = build_single_claim_framing_output_schema()
    relation_model = schema.model_fields["relations"].annotation.__args__[0]
    for meta in relation_model.model_fields["subject"].metadata:
        if hasattr(meta, "max_length"):
            return int(meta.max_length)
    message = "framing endpoint cap not declared on the output schema"
    raise ValueError(message)


def _argument_span_cap() -> int:
    """Read the inventory argument's own exact_span length cap."""
    for meta in ClaimArgument.model_fields["exact_span"].metadata:
        if hasattr(meta, "max_length"):
            return int(meta.max_length)
    message = "inventory argument span cap not declared on ClaimArgument"
    raise ValueError(message)


def replay(pairs: list[dict]) -> dict:
    """Replay every recorded framing answer and report where each one stopped."""
    capture = _DropReasonCapture()
    drop_logger = logging.getLogger(DROP_LOGGER)
    drop_logger.setLevel(logging.DEBUG)
    drop_logger.addHandler(capture)

    schema = build_single_claim_framing_output_schema()
    tally = _Tally(capture=capture)
    stages = tally.stages
    reasons = tally.reasons
    survivors: list[dict] = []
    documents: set[str] = set()
    relations_seen = 0

    attempts = final_attempt_per_claim(pairs)
    for pair in attempts:
        item_payload, region_text = parse_prompt(pair["prompt"])
        source_sha = parse_document_sha(pair["prompt"])
        documents.add(source_sha)
        try:
            item = ClaimInventoryItem.model_validate(item_payload)
            bound = bind_claim_inventory(
                (item,),
                source_text=region_text,
                source_sha256=source_sha,
                chunk_index=0,
            )[0]
            region = derive_claim_local_source_region(bound)
        except ValueError as exc:
            tally.record("inventory_binding", f"inventory_binding: {exc}")
            continue
        try:
            parsed = schema.model_validate(json.loads(pair["output_json"]))
        except ValueError as exc:
            tally.record("output_schema", f"output_schema: {type(exc).__name__}")
            continue

        call_survivors: list[dict] = []
        call_aborted = False
        for relation in parsed.relations:
            relations_seen += 1
            survivor = _replay_relation(
                relation=relation,
                bound=bound,
                region=region,
                source_sha=source_sha,
                tally=tally,
            )
            if survivor is None:
                call_aborted = True
            else:
                call_survivors.append(survivor)
        if call_aborted:
            stages["frames_lost_to_a_sibling_relation"] += len(call_survivors)
        else:
            survivors.extend(call_survivors)

    triples = collections.Counter(
        survivor["triple_fingerprint"] for survivor in survivors
    )
    identities = collections.Counter(
        survivor["dedupe_identity"] for survivor in survivors
    )
    cross_document = [
        fingerprint
        for fingerprint, count in triples.items()
        if count > 1
        and len(
            {
                survivor["document_sha256"]
                for survivor in survivors
                if survivor["triple_fingerprint"] == fingerprint
            },
        )
        > 1
    ]
    return {
        "provenance": "recorded framing prompts and outputs replayed from "
        "artana.kernel_events against current code; no new provider calls",
        "inventory_claims_replayed": len(attempts),
        "relations_in_those_answers": relations_seen,
        "documents_that_reached_framing": len(documents),
        "documents_with_at_least_one_surviving_frame": len(
            {survivor["document_sha256"] for survivor in survivors},
        ),
        "frames_reaching_the_write_path": len(survivors),
        "distinct_frame_dedupe_identities": len(identities),
        "distinct_triple_fingerprints": len(triples),
        "cross_document_triple_agreements": len(cross_document),
        "first_rejecting_stage": dict(stages.most_common()),
        "rejection_reasons": dict(reasons.most_common()),
        "surviving_frames": survivors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--user", default=DEFAULT_DATABASE_USER)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "validation" / "results"),
    )
    args = parser.parse_args()

    pairs = read_framing_pairs(args.container, args.database, args.user)
    report = replay(pairs)
    _reject_spans(report)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "2026-07-26-claim-framing-validator-replay.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"inventory claims replayed        : {report['inventory_claims_replayed']}")
    print(f"relations in those answers       : {report['relations_in_those_answers']}")
    print(
        f"documents that reached framing   : "
        f"{report['documents_that_reached_framing']}",
    )
    print(
        f"documents yielding >=1 frame     : "
        f"{report['documents_with_at_least_one_surviving_frame']}",
    )
    print(
        f"frames reaching the write path   : "
        f"{report['frames_reaching_the_write_path']}",
    )
    print(
        f"cross-document triple agreements : "
        f"{report['cross_document_triple_agreements']}",
    )
    print("\nfirst rejecting stage:")
    for stage, count in report["first_rejecting_stage"].items():
        print(f"   {stage:36s} {count}")
    print("\nrejection reasons:")
    for reason, count in report["rejection_reasons"].items():
        print(f"   [{count}] {reason}")
    print("\nframes that survive (subject | predicate | object):")
    for survivor in report["surviving_frames"]:
        preview = survivor["dedupe_identity"][:FINGERPRINT_PREVIEW_CHARS]
        print(
            f"   {survivor['subject']!r} | {survivor['predicate']} | "
            f"{survivor['object']!r} -> {preview}",
        )
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
