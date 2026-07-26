"""Two supplementary measurements the main sweep cannot express.

(1) SURFACE-FORM AMBIGUITY CENSUS -- corpus-wide, over every annotated mention,
    not only the ones participating in a CID fact. This is the mechanism that
    produces every false merge observed in the main sweep, measured with far
    more power than the 325 multi-document facts provide.

(2) INTRA-DOCUMENT COLLISIONS -- how many documents would emit two drafts with
    the same fingerprint inside a single ``create_proposals()`` call. Per the
    blast-radius trace, one such collision parks that document's ENTIRE
    extraction output as ``identity_pending``
    (``sqlalchemy_stores.py`` ``_retain_conflicting_proposals``).

Unlike the main sweep, (2) is not circular: it takes the mention-label rule the
persistence path actually uses and asks whether two DIFFERENT gold facts inside
one document collide under it. The mesh-label row is there as a contrast, and
its zero is a tautology in the same way the main sweep's is -- distinct facts
have distinct MeSH pairs by definition.

No provider calls. Read-only. Emits MeSH ids and entity labels only, never a
span of document prose.

Usage: python3 -m scripts.validation.claim_identity_merge.supplementary
"""

from __future__ import annotations

import argparse
import collections
import json
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

RELATION = "CAUSES"
UNLINKED_CONCEPT_IDS = frozenset({"-1", "-"})
WORST_FORMS_REPORTED = 15
COLLISION_EXAMPLES_REPORTED = 10
MANY_FORMS_THRESHOLD = 5


def surface_form_census(corpus: bc5cdr.Corpus) -> tuple[dict, dict]:
    """How many surface forms denote more than one concept, and vice versa."""
    form_to_mesh: dict[str, set[str]] = collections.defaultdict(set)
    mesh_to_forms: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter,
    )
    mention_instances = 0
    for document in corpus.documents.values():
        for mesh, counter in document.mentions.items():
            if mesh in UNLINKED_CONCEPT_IDS:
                continue
            for text, count in counter.items():
                form = _normalize_label(text)
                form_to_mesh[form].add(mesh)
                mesh_to_forms[mesh][form] += count
                mention_instances += count

    ambiguous = {form: mesh for form, mesh in form_to_mesh.items() if len(mesh) > 1}
    ambiguous_instances = sum(
        count
        for forms in mesh_to_forms.values()
        for form, count in forms.items()
        if form in ambiguous
    )
    ambiguity = {
        "distinct_normalised_forms": len(form_to_mesh),
        "forms_denoting_more_than_one_mesh_concept": len(ambiguous),
        "share_of_forms_ambiguous": len(ambiguous) / len(form_to_mesh),
        "mention_instances": mention_instances,
        "mention_instances_carrying_an_ambiguous_form": ambiguous_instances,
        "share_of_mention_instances_ambiguous": ambiguous_instances / mention_instances,
        "worst_forms": [
            {"form": form, "mesh_concepts": sorted(mesh), "n_concepts": len(mesh)}
            for form, mesh in sorted(ambiguous.items(), key=lambda kv: -len(kv[1]))[
                :WORST_FORMS_REPORTED
            ]
        ],
    }

    forms_per_mesh = [len(forms) for forms in mesh_to_forms.values()]
    variety = {
        "distinct_mesh_concepts": len(mesh_to_forms),
        "mean_normalised_forms_per_concept": sum(forms_per_mesh) / len(forms_per_mesh),
        "concepts_with_one_form_only": sum(1 for n in forms_per_mesh if n == 1),
        "concepts_with_5_or_more_forms": sum(
            1 for n in forms_per_mesh if n >= MANY_FORMS_THRESHOLD
        ),
    }
    return ambiguity, variety


def intra_document_collisions(corpus: bc5cdr.Corpus) -> dict[str, dict]:
    """Documents whose own drafts collide, and the whole batch they would park."""
    # Sorted, not set-iteration order: the counts below are stable either way,
    # but the `examples` slice is not, and an example list that reshuffles under
    # PYTHONHASHSEED is an artifact a later reader would take for a change.
    per_document: dict[str, list[dict]] = collections.defaultdict(list)
    for (chem, dis), pmids in sorted(corpus.cid_facts.items()):
        for pmid in sorted(pmids):
            document = corpus.documents.get(pmid)
            if not document:
                continue
            chem_text = document.label_for(chem)
            dis_text = document.label_for(dis)
            if chem_text is None or dis_text is None:
                continue
            per_document[pmid].append(
                {
                    "fact": (chem, dis),
                    "mention": compute_claim_fingerprint(chem_text, RELATION, dis_text),
                    "mesh": compute_claim_fingerprint(chem, RELATION, dis),
                    "labels": (chem_text, dis_text),
                },
            )

    blocks: dict[str, dict] = {}
    for mode in ("mention", "mesh"):
        colliding: list[dict] = []
        for pmid, rows in sorted(per_document.items()):
            groups: dict[str, list[dict]] = collections.defaultdict(list)
            for row in rows:
                groups[row[mode]].append(row)
            for members in groups.values():
                if len({member["fact"] for member in members}) > 1:
                    colliding.append(
                        {
                            "pmid": pmid,
                            "drafts_in_batch": len(rows),
                            "gold_facts_fused": sorted(
                                {"|".join(member["fact"]) for member in members},
                            ),
                            "labels": sorted({m["labels"] for m in members}),
                        },
                    )
        blocks[f"intra_document_collisions_{mode}_labels"] = {
            "documents_emitting_at_least_one_cid_draft": len(per_document),
            "documents_with_an_intra_batch_collision": len(colliding),
            "share_of_documents": len(colliding) / len(per_document),
            "drafts_that_would_be_parked_whole_batch": sum(
                row["drafts_in_batch"] for row in colliding
            ),
            "total_cid_drafts": sum(len(rows) for rows in per_document.values()),
            "examples": colliding[:COLLISION_EXAMPLES_REPORTED],
        }
    return blocks


def _print_summary(report: dict) -> None:
    ambiguity = report["surface_form_ambiguity"]
    print("SURFACE-FORM AMBIGUITY (drives every false merge observed)")
    print(
        f"  distinct normalised surface forms      : "
        f"{ambiguity['distinct_normalised_forms']}",
    )
    print(
        f"  forms denoting >1 MeSH concept         : "
        f"{ambiguity['forms_denoting_more_than_one_mesh_concept']} "
        f"({ambiguity['share_of_forms_ambiguous']:.2%})",
    )
    print(
        f"  mention instances wearing such a form  : "
        f"{ambiguity['mention_instances_carrying_an_ambiguous_form']} / "
        f"{ambiguity['mention_instances']} "
        f"({ambiguity['share_of_mention_instances_ambiguous']:.2%})",
    )
    variety = report["surface_form_variety"]
    print("\nSURFACE-FORM VARIETY (caps recall for label-based identity)")
    print(f"  distinct MeSH concepts                 : {variety['distinct_mesh_concepts']}")
    print(
        f"  mean normalised forms per concept      : "
        f"{variety['mean_normalised_forms_per_concept']:.2f}",
    )
    print(
        f"  concepts with >=5 distinct forms       : "
        f"{variety['concepts_with_5_or_more_forms']}",
    )
    for mode in ("mention", "mesh"):
        block = report[f"intra_document_collisions_{mode}_labels"]
        print(f"\nINTRA-DOCUMENT COLLISIONS ({mode} labels)")
        print(
            f"  documents with an intra-batch collision: "
            f"{block['documents_with_an_intra_batch_collision']} / "
            f"{block['documents_emitting_at_least_one_cid_draft']} "
            f"({block['share_of_documents']:.2%})",
        )
        print(
            f"  drafts parked as a consequence         : "
            f"{block['drafts_that_would_be_parked_whole_batch']} / "
            f"{block['total_cid_drafts']}",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=None, help="BC5CDR directory")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "validation" / "results"),
    )
    args = parser.parse_args()

    corpus = bc5cdr.load(args.corpus)
    ambiguity, variety = surface_form_census(corpus)
    report: dict = {
        "corpus_digests": corpus.digests,
        "surface_form_ambiguity": ambiguity,
        "surface_form_variety": variety,
    }
    report.update(intra_document_collisions(corpus))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "2026-07-26-claim-identity-merge-supplementary.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    _print_summary(report)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
