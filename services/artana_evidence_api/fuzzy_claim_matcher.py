"""Fuzzy near-duplicate detection for claim triples.

Uses ``difflib.SequenceMatcher`` to find claims that are *similar* but not
*identical* to a proposed claim.  These surface as non-blocking warnings
during curation — the user decides whether to proceed.

Only claims with an **exact relation-type match** and **both** subject and
object label similarity above the threshold are reported.  Exact matches
(ratio == 1.0 on both labels) are excluded — those are caught by the
fingerprint-based exact dedup.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


def _normalize(label: str) -> str:
    """NFKC casefold + collapse whitespace — same as fingerprint normalisation."""
    s = unicodedata.normalize("NFKC", label).casefold().strip()
    return re.sub(r"\s+", " ", s)


@dataclass(frozen=True, slots=True)
class FuzzyMatch:
    """One near-duplicate match found by the fuzzy matcher."""

    claim_id: str
    claim_status: str
    source_label: str | None
    target_label: str | None
    relation_type: str
    subject_similarity: float
    object_similarity: float
    claim_text: str | None


def find_near_duplicates(
    *,
    proposal_subject: str,
    proposal_relation: str,
    proposal_object: str,
    existing_claims: list[dict[str, object]],
    threshold: float = 0.85,
) -> list[FuzzyMatch]:
    """Find claims whose labels are similar but not identical to the proposal.

    Parameters
    ----------
    proposal_subject:
        Display label of the proposed subject entity.
    proposal_relation:
        Relation type of the proposed claim (e.g. ``ASSOCIATED_WITH``).
    proposal_object:
        Display label of the proposed object entity.
    existing_claims:
        List of claim dicts with at least ``id``, ``claim_status``,
        ``source_label``, ``target_label``, ``relation_type``, ``claim_text``.
    threshold:
        Minimum similarity ratio (0–1) for *both* labels. Default 0.85.

    Returns
    -------
    list[FuzzyMatch]
        Near-duplicates sorted by combined similarity (descending).
        Exact matches (both ratios == 1.0) are excluded.
    """
    ns = _normalize(proposal_subject)
    no = _normalize(proposal_object)
    nr = _normalize(proposal_relation)

    matches: list[FuzzyMatch] = []

    for claim in existing_claims:
        cr = _normalize(str(claim.get("relation_type", "")))
        if cr != nr:
            continue

        cs = _normalize(str(claim.get("source_label", "") or ""))
        ct = _normalize(str(claim.get("target_label", "") or ""))

        if not cs or not ct:
            continue

        # Try both orientations (proposal subject↔source, proposal subject↔target)
        sim_ss = SequenceMatcher(None, ns, cs).ratio()
        sim_oo = SequenceMatcher(None, no, ct).ratio()
        forward = min(sim_ss, sim_oo)

        sim_so = SequenceMatcher(None, ns, ct).ratio()
        sim_os = SequenceMatcher(None, no, cs).ratio()
        reverse = min(sim_so, sim_os)

        if forward >= reverse:
            sub_sim, obj_sim = sim_ss, sim_oo
        else:
            sub_sim, obj_sim = sim_so, sim_os

        # Skip if below threshold
        if sub_sim < threshold or obj_sim < threshold:
            continue

        # Skip exact matches — those are caught by fingerprint dedup
        if sub_sim == 1.0 and obj_sim == 1.0:
            continue

        matches.append(
            FuzzyMatch(
                claim_id=str(claim.get("id", "")),
                claim_status=str(claim.get("claim_status", "")),
                source_label=str(claim.get("source_label", "")) or None,
                target_label=str(claim.get("target_label", "")) or None,
                relation_type=str(claim.get("relation_type", "")),
                subject_similarity=round(sub_sim, 3),
                object_similarity=round(obj_sim, 3),
                claim_text=str(claim.get("claim_text", "")) or None,
            ),
        )

    # Sort by combined similarity descending
    matches.sort(key=lambda m: -(m.subject_similarity + m.object_similarity))
    return matches
