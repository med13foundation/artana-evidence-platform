"""Issue #217 -- measure cross-document merge behaviour of candidate claim identities.

READ THE REPORT BEFORE QUOTING ANY NUMBER THIS EMITS:
``docs/validation/reports/2026-07-26-claim-identity-merge-measurement.md``.
The ``mesh_id`` arms are a tautology -- their identity is computed from the
same gold MeSH pair that defines "same fact", so recall is 1.0 by construction
and measures nothing. They are kept because the *contrast* with the
``mention_text`` arms is the finding; the 1.0 is not a result.

READ-ONLY with respect to the repository: imports production identity code
(``ClaimFrame``, ``compute_claim_fingerprint``) but changes nothing and
persists nothing. No provider calls. No corpus text is written to any output.

Corpus: BC5CDR (NCBI, public domain -- see ``corpus.py``).
Ground truth for "same fact": equality of the gold CID pair
(chemical MeSH id, disease MeSH id).

Preregistered choices (fixed BEFORE looking at any result):
  * relation label for every constructed frame: "CAUSES" (directional).
  * evidence-span heuristic: split title+abstract on sentence boundaries;
    take the FIRST sentence containing a surface mention of both the chemical
    and the disease; else the first sentence containing the disease mention;
    else the title. Locator = "PMID:<pmid>#s<index>".
  * document-level label for a MeSH id = that document's most frequent surface
    mention for the id (ties broken by lexicographic order, deterministic).
  * bootstrap: 2000 resamples of DOCUMENTS with replacement, seed 20260726.

Usage:  python3 -m scripts.validation.claim_identity_merge.measure [--out DIR]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import math
import random
import re
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "services"))
sys.path.insert(0, str(REPO_ROOT))

from artana_evidence_api.claim_fingerprint import (  # noqa: E402
    compute_claim_fingerprint,
)
from artana_evidence_api.document_extraction_support.claim_frames.arguments import (  # noqa: E402
    ClaimArgument,
    ClaimArgumentRole,
)
from artana_evidence_api.document_extraction_support.claim_frames.contracts import (  # noqa: E402
    _QUALIFIER_FIELDS,
    ClaimFrame,
    ClaimQualifier,
    EpistemicStatus,
    Polarity,
    SourceEvidenceSpan,
)
from artana_evidence_api.document_extraction_support.claim_frames.event_types import (  # noqa: E402
    ClaimEventRole,
)

from scripts.validation.claim_identity_merge import corpus as bc5cdr  # noqa: E402

RELATION = "CAUSES"
SEED = 20260726
MAX_SPAN_CHARS = 12000
WILSON_Z = 1.96
EXAMPLES_PER_VARIANT = 12
IDENTITY_PREVIEW_CHARS = 16
# A fact is only informative about merging once two documents assert it.
MIN_DOCUMENTS_FOR_A_PAIR = 2

AGENT_ROLE = list(ClaimEventRole)[0]
THEME_ROLE = list(ClaimEventRole)[1]

_SENT = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    return [s for s in _SENT.split(text) if s.strip()]


def evidence_span(
    document: bc5cdr.Document,
    chem_text: str,
    dis_text: str,
) -> tuple[str, int]:
    """Preregistered co-occurrence heuristic. Returns (sentence, index)."""
    sents = sentences(document.text)
    lowered = [s.lower() for s in sents]
    chemical, disease = chem_text.lower(), dis_text.lower()
    for index, sentence in enumerate(lowered):
        if chemical in sentence and disease in sentence:
            return sents[index], index
    for index, sentence in enumerate(lowered):
        if disease in sentence:
            return sents[index], index
    return (sents[0] if sents else document.title or "n/a"), 0


# --------------------------------------------------------------------------
# frame construction
# --------------------------------------------------------------------------
def build_frame(  # noqa: PLR0913 -- every field is a distinct frame slot
    *,
    subject: str,
    object_: str,
    span: str,
    locator: str,
    chem_text: str,
    dis_text: str,
    content: str,
) -> ClaimFrame:
    """Build a real ClaimFrame.

    content='min'  -- maximally merge-friendly: no arguments, no qualifier
                      content, no measurements. Upper bound for any variant
                      that hashes frame body text.
    content='doc'  -- arguments and one qualifier populated from THIS
                      document's own surface strings, which is what an
                      extractor that copies source text actually emits.
                      No invented jitter: every string is corpus-derived.
    """
    qualifiers = {field: ClaimQualifier.not_applicable() for field in _QUALIFIER_FIELDS}
    arguments: tuple[ClaimArgument, ...] = ()

    if content == "doc":
        qualifiers["condition"] = ClaimQualifier.present(
            value=dis_text,
            exact_span=dis_text,
        )
        if chem_text != dis_text:
            arguments = (
                ClaimArgument(
                    role=ClaimArgumentRole.CHEMICAL_OR_DRUG,
                    event_role=AGENT_ROLE,
                    exact_span=chem_text,
                    role_rationale=f"chemical mention '{chem_text}' in source sentence",
                ),
                ClaimArgument(
                    role=ClaimArgumentRole.CONDITION,
                    event_role=THEME_ROLE,
                    exact_span=dis_text,
                    role_rationale=f"disease mention '{dis_text}' in source sentence",
                ),
            )

    return ClaimFrame(
        subject=subject,
        predicate=RELATION,
        object=object_,
        source_evidence=SourceEvidenceSpan(
            exact_span=span[:MAX_SPAN_CHARS],
            locator=locator,
        ),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        assertion_arguments=arguments,
        source_measurements=(),
        extraction_rationale="constructed from BC5CDR gold CID annotation",
        **qualifiers,
    )


# --------------------------------------------------------------------------
# identity variants (production code untouched; these are candidate rules)
# --------------------------------------------------------------------------
def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def var_a(frame: ClaimFrame) -> str:
    """Today's identity, unchanged."""
    return frame.dedupe_identity


def var_b(frame: ClaimFrame) -> str:
    """Drop source_evidence; keep the existing qualifier exact_span strip."""
    payload = frame.model_dump(mode="json")
    payload.pop("extraction_rationale")
    payload.pop("source_evidence")
    for qualifier in _QUALIFIER_FIELDS:
        payload[qualifier].pop("exact_span", None)
    return _hash(payload)


def _reduced_arguments(payload: dict) -> list[dict]:
    return sorted(
        [
            {"role": argument["role"], "event_role": argument["event_role"]}
            for argument in payload["assertion_arguments"]
        ],
        key=lambda argument: (argument["role"], argument["event_role"]),
    )


def var_c(frame: ClaimFrame) -> str:
    """(b) plus stripping every remaining per-document text carrier."""
    payload = frame.model_dump(mode="json")
    payload.pop("extraction_rationale")
    payload.pop("source_evidence")
    for qualifier in _QUALIFIER_FIELDS:
        payload[qualifier] = {
            "state": payload[qualifier]["state"],
            "value": payload[qualifier]["value"],
        }
    payload["assertion_arguments"] = _reduced_arguments(payload)
    payload["source_measurements"] = sorted(
        [
            {
                "field_name": measurement["field_name"],
                "value": measurement["value"],
                "unit": measurement["unit"],
            }
            for measurement in payload["source_measurements"]
        ],
        key=lambda m: (m["field_name"], str(m["value"]), str(m["unit"])),
    )
    return _hash(payload)


def var_c2(frame: ClaimFrame) -> str:
    """(c) plus reducing qualifiers to state and dropping measurements."""
    payload = frame.model_dump(mode="json")
    payload.pop("extraction_rationale")
    payload.pop("source_evidence")
    for qualifier in _QUALIFIER_FIELDS:
        payload[qualifier] = {"state": payload[qualifier]["state"]}
    payload["assertion_arguments"] = _reduced_arguments(payload)
    payload["source_measurements"] = []
    return _hash(payload)


def var_e(frame: ClaimFrame) -> str:
    """Normalised triple + polarity + epistemic_status."""
    return _hash(
        {
            "triple": compute_claim_fingerprint(
                frame.subject,
                frame.predicate,
                frame.object,
            ),
            "polarity": frame.polarity.value,
            "epistemic_status": frame.epistemic_status.value,
        },
    )


def var_d(frame: ClaimFrame) -> str:
    """Triple-only -- exactly what the span-free fallback branch already emits."""
    return compute_claim_fingerprint(frame.subject, frame.predicate, frame.object)


VARIANTS: tuple[tuple[str, Callable[[ClaimFrame], str]], ...] = (
    ("a_today", var_a),
    ("b_drop_source_evidence", var_b),
    ("c_b_plus_strip_perdoc_text", var_c),
    ("c2_c_plus_states_only", var_c2),
    ("e_triple_polarity_status", var_e),
    ("d_triple_only", var_d),
)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def wilson(successes: int, total: int, z: float = WILSON_Z) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total),
        )
        / denominator
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


def score(records: list[dict], identity_key: str) -> dict:
    """records: {'pmid','fact','identity'} -- one per (document, gold fact)."""
    by_fact: dict[tuple, list[dict]] = collections.defaultdict(list)
    by_identity: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        by_fact[record["fact"]].append(record)
        by_identity[record[identity_key]].append(record)

    true_pairs = merged_true = 0
    for rows in by_fact.values():
        for left, right in itertools.combinations(rows, 2):
            if left["pmid"] == right["pmid"]:
                continue
            true_pairs += 1
            if left[identity_key] == right[identity_key]:
                merged_true += 1

    false_pairs = 0
    fused_groups = []
    for identity, rows in by_identity.items():
        facts = {row["fact"] for row in rows}
        if len(facts) < MIN_DOCUMENTS_FOR_A_PAIR:
            continue
        local_false = sum(
            1
            for left, right in itertools.combinations(rows, 2)
            if left["fact"] != right["fact"] and left["pmid"] != right["pmid"]
        )
        if local_false:
            fused_groups.append(
                {
                    "identity": identity[:IDENTITY_PREVIEW_CHARS],
                    "gold_facts": sorted(facts),
                    "documents": sorted({row["pmid"] for row in rows}),
                    "labels": sorted({(r["subject"], r["object"]) for r in rows}),
                    "false_pairs": local_false,
                },
            )
        false_pairs += local_false

    facts_fully_collapsed = 0
    multi_facts = 0
    for rows in by_fact.values():
        if len({row["pmid"] for row in rows}) < MIN_DOCUMENTS_FOR_A_PAIR:
            continue
        multi_facts += 1
        if len({row[identity_key] for row in rows}) == 1:
            facts_fully_collapsed += 1

    merges_total = merged_true + false_pairs
    return {
        "true_pairs": true_pairs,
        "merged_true_pairs": merged_true,
        "recall": merged_true / true_pairs if true_pairs else 0.0,
        "recall_wilson": wilson(merged_true, true_pairs),
        "false_merge_pairs": false_pairs,
        "fused_identity_groups": len(fused_groups),
        "merge_precision": merged_true / merges_total if merges_total else None,
        "merge_precision_wilson": (
            wilson(merged_true, merges_total) if merges_total else None
        ),
        "multi_document_facts": multi_facts,
        "facts_fully_collapsed": facts_fully_collapsed,
        "distinct_identities": len(by_identity),
        "examples": sorted(fused_groups, key=lambda g: -g["false_pairs"])[
            :EXAMPLES_PER_VARIANT
        ],
    }


def bootstrap(records: list[dict], identity_key: str, resamples: int) -> dict:
    """Cluster bootstrap over DOCUMENTS -- pairs are not independent."""
    rng = random.Random(SEED)  # noqa: S311 -- resampling, not cryptography
    by_pmid: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        by_pmid[record["pmid"]].append(record)
    pmids = sorted(by_pmid)

    recalls: list[float] = []
    falses: list[int] = []
    precisions: list[float] = []
    for _ in range(resamples):
        # Draw documents with replacement. A redrawn document keeps its ORIGINAL
        # pmid, so pairs between its clones are excluded by the same-document
        # guard in score(); only the weighting of each document changes. This
        # avoids the trivial "a document always merges with itself" inflation
        # that renaming clones would introduce.
        sample: list[dict] = []
        for pmid in rng.choices(pmids, k=len(pmids)):
            sample.extend(by_pmid[pmid])
        result = score(sample, identity_key)
        if result["true_pairs"]:
            recalls.append(result["recall"])
        falses.append(result["false_merge_pairs"])
        if result["merge_precision"] is not None:
            precisions.append(result["merge_precision"])

    return {
        "recall_ci": _interval(recalls),
        "false_merge_pairs_ci": _interval(falses),
        "merge_precision_ci": _interval(precisions),
        "resamples": resamples,
        "seed": SEED,
    }


def _interval(values: list[float]) -> tuple[float, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return (
        ordered[int(0.025 * len(ordered))],
        ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))],
    )


def build_records(corpus: bc5cdr.Corpus, label_mode: str, content: str) -> tuple[list[dict], int]:
    """One record per (document, gold CID fact), carrying every candidate identity."""
    records: list[dict] = []
    skipped = 0
    for (chem, dis), pmids in sorted(corpus.cid_facts.items()):
        for pmid in sorted(pmids):
            document = corpus.documents.get(pmid)
            if document is None:
                skipped += 1
                continue
            chem_text = document.label_for(chem)
            dis_text = document.label_for(dis)
            if chem_text is None or dis_text is None:
                skipped += 1
                continue
            span, index = evidence_span(document, chem_text, dis_text)
            subject = chem if label_mode == "mesh_id" else chem_text
            object_ = dis if label_mode == "mesh_id" else dis_text
            frame = build_frame(
                subject=subject,
                object_=object_,
                span=span,
                locator=f"PMID:{pmid}#s{index}",
                chem_text=chem_text,
                dis_text=dis_text,
                content=content,
            )
            record = {
                "pmid": pmid,
                "fact": (chem, dis),
                "subject": subject,
                "object": object_,
                "chem_text": chem_text,
                "dis_text": dis_text,
            }
            for name, identity_of in VARIANTS:
                record[name] = identity_of(frame)
            records.append(record)
    return records, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--corpus", default=None, help="BC5CDR directory")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "validation" / "results"),
    )
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)

    corpus = bc5cdr.load(args.corpus)
    multi = sum(1 for pmids in corpus.cid_facts.values() if len(pmids) >= MIN_DOCUMENTS_FOR_A_PAIR)
    print(
        f"corpus: {len(corpus.documents)} documents, "
        f"{len(corpus.cid_facts)} distinct gold CID facts",
    )
    print(f"        {multi} facts in >=2 documents")

    report: dict = {
        "READ_FIRST": (
            "docs/validation/reports/"
            "2026-07-26-claim-identity-merge-measurement.md -- the mesh_id arms "
            "are a tautology (identity derived from the answer key) and the "
            "mention_text recall figures are rule-dependent. Do not quote a "
            "number from this file without reading which ones survive."
        ),
        "corpus": {
            "name": "BC5CDR (NCBI, public domain)",
            "digests": corpus.digests,
            "documents": len(corpus.documents),
            "distinct_cid_facts": len(corpus.cid_facts),
            "multi_document_cid_facts": multi,
        },
        "preregistered": {
            "relation": RELATION,
            "span_heuristic": "first sentence containing both mentions; "
            "else first containing disease; else title",
            "label_rule": "most frequent surface mention per document, "
            "lexicographic tie-break",
            "same_fact_ground_truth": "equality of gold (chemical MeSH, disease MeSH)",
            "bootstrap_seed": SEED,
        },
        "arms": {},
    }

    for label_mode in ("mention_text", "mesh_id"):
        for content in ("min", "doc"):
            arm = f"{label_mode}/{content}"
            records, skipped = build_records(corpus, label_mode, content)
            arm_report: dict = {
                "frames": len(records),
                "skipped": skipped,
                "variants": {},
            }
            if label_mode == "mesh_id":
                arm_report["circularity_warning"] = (
                    "subject/object ARE the gold MeSH ids that define the "
                    "ground truth, so any variant that drops per-document text "
                    "scores recall 1.0 by construction. Not a result."
                )
            print(f"\n=== arm {arm}: {len(records)} frames ({skipped} skipped)")
            for name, _ in VARIANTS:
                result = score(records, name)
                result["bootstrap"] = bootstrap(records, name, args.bootstrap)
                arm_report["variants"][name] = result
                low, high = result["bootstrap"]["recall_ci"] or (0, 0)
                false_low, false_high = result["bootstrap"]["false_merge_pairs_ci"] or (0, 0)
                print(
                    f"  {name:28s} recall {result['recall']:6.1%} "
                    f"[{low:.1%},{high:.1%}]  "
                    f"false-merge pairs {result['false_merge_pairs']:6d} "
                    f"[{false_low:.0f},{false_high:.0f}]  "
                    f"groups {result['fused_identity_groups']:4d}",
                )
            report["arms"][arm] = arm_report

    path = Path(args.out) / "2026-07-26-claim-identity-merge-measurement.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
