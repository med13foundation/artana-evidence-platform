# Claim identity and cross-document merge: what was measured, and what may be quoted

**Date:** 2026-07-26
**Issue:** #217 — "does removing the source span from claim identity let two papers be recognised as asserting the same fact?"
**Corpus:** BC5CDR (NCBI, public domain), 1500 documents, 2434 distinct gold CID facts, 325 of them asserted by two or more documents
**Provider calls:** none — the model outputs used here were already paid for and persisted to `artana.kernel_events`
**Scripts:** `scripts/validation/claim_identity_merge/` (see `MANIFEST.txt`)
**Results:** `docs/validation/results/2026-07-26-claim-identity-merge-{measurement,supplementary,model-labels}.json`

This document exists mainly to stop three of its own numbers being reused. The
sweep is committed because its *contrasts* are informative and its scripts are
worth re-running. Several of its headline figures are not evidence of anything,
and one is a tautology. Read this section before the results.

---

## Do not quote these numbers

### 1. "100% recall with perfect entity resolution" is circular

`measurement.json` reports recall `1.0` for every span-free variant in the
`mesh_id/min` and `mesh_id/doc` arms. It is not a result. It is the definition
restated.

In those arms `measure.py` sets the frame's `subject` and `object` to the gold
chemical and disease MeSH ids. The preregistered ground truth for "these two
documents assert the same fact" is *equality of that same gold MeSH pair*
(`preregistered.same_fact_ground_truth`). So the identity is computed from the
answer key. Any identity rule that stops hashing per-document text must then
score 1.0, and the Wilson and bootstrap intervals around it — `[0.998, 1.0]`,
`[1.0, 1.0]` — are intervals around an identity, not around an estimate.

The arms are kept because the *ordering within* the `mesh_id/doc` arm is the
real finding (below), and because deleting the circular arm would leave the
contrast unreadable. `measurement.json` now carries a `circularity_warning`
on both `mesh_id` arms so the file cannot be read without it.

**What it would take to get a real number here:** an entity resolver whose
output is not the label set that defines the ground truth. There isn't one in
this measurement, and there isn't one wired into the pipeline.

### 2. "36.4% recall" is an artifact of an arbitrary label rule

`mention_text/*` variant `d_triple_only` reports 36.4%. The rule that produced
it — "a document's label for a MeSH id is its most frequent surface mention,
ties broken lexicographically" — was preregistered, which makes it honest, not
robust. Within this one file the same identity variant moves between **31.7%
and 47.2%** purely by changing which frame fields are stripped, with entity
labels held perfect. An independent review of the original measurement put the
range across plausible label rules at **35.7–50.6%**; that range is *not*
re-derived here and should be cited to that review, not to this artifact.

Quote 36.4% as "roughly a third, under one arbitrary label rule, and the rule
moves it by fifteen points". Do not quote it as a recall figure.

### 3. The false-merge counts understate the operational risk

`measurement.json` reports 3 to 5 false-merge *pairs* per arm, and merge
precision above 0.993. Those are pair counts over the 325 multi-document facts,
which is a small denominator and the wrong unit. The independent review found
false merges understated by roughly **13x** once counted properly, and put the
operationally meaningful figure at **1.8–4.1% of auto-promotable nodes
contaminated**. Those numbers are also not re-derived here.

`supplementary.json` measures the mechanism with far more power and is the
figure to use instead: **246 of 4929 normalised surface forms (4.99%) denote
more than one MeSH concept**, covering **1435 of 28849 mention instances
(4.97%)**. That is the ceiling on how often a label-based identity can fuse two
different facts, and it is measured over every annotated mention in the corpus
rather than over 325 facts.

### 4. End-to-end recall is currently unmeasurable, not low

No number in these files is a measurement of the production path. `measure.py`
constructs `ClaimFrame` objects directly from gold annotations; it never runs
the extractor. The one attempt to run the extractor over real BC5CDR abstracts
aborted inside the claim-framing validators on 10 of 11 documents, which is why
`harvest_real_labels.py` exists at all — it recovers the model's output from the
audit trail *before* validation. `model-labels.json` says so in its
`provenance` field, and it is the only honest thing to say about it.

---

## What the measurement does establish

### A. Removing the source span, by itself, does not do the job

This is the ordering inside the `mesh_id/doc` arm. Entity labels are held
perfect and identical across documents, so anything short of 100% is the frame
body's remaining per-document text and nothing else:

| Identity variant | What it strips | Recall |
|---|---|---:|
| `a_today` | nothing (today's `dedupe_identity`) | 0.0% |
| `b_drop_source_evidence` | `source_evidence` | 31.7% |
| `c_b_plus_strip_perdoc_text` | + argument `exact_span`, argument `role_rationale`, measurement fields | 47.2% |
| `c2_c_plus_states_only` | + qualifier `value` | 100% (circular — see above) |

Today's `dedupe_identity` already drops `extraction_rationale` and qualifier
`exact_span`. Beyond `source_evidence` there remain **four** per-document text
carriers in the hash: qualifier `value`, argument `exact_span`, argument
`role_rationale`, and the measurement fields.

The step that matters is `b` → `c`: **31.7% to 47.2%, with entity labels held
perfect and identical**. Those 15.5 points are attributable to remaining
frame-body text and to nothing else, and they are not circular — the circularity
only bites at the last row, where the qualifier `value` is the last thing
standing between the identity and the answer key. So dropping the span alone
leaves *at least* a further 15.5 points of collapse unrealised even under
perfect entity resolution. How much more, this measurement cannot say.

The `min` arms confirm the mechanism by removing it: with no arguments and no
qualifier content there is nothing left to strip, and `b`, `c` and `c2` are
identical (31.7% for `mention_text`, 100% for `mesh_id`).

**So the issue's framing — "strip the span and papers will merge" — is wrong on
its own terms, before any question about entity resolution arises.**

### B. The real fork is resolved-vs-raw entity labels, and it is in one expression

`document_extraction_drafts.py` chooses the fingerprint like this:

```python
claim_fingerprint = (
    candidate.claim_frame.dedupe_identity
    if candidate.claim_frame is not None
    else compute_claim_fingerprint(
        resolved_subject_label,
        candidate.relation_type,
        resolved_object_label,
    )
)
```

The two branches do not differ only in *how much* they hash. They differ in
*what they hash*:

- the **fallback** branch fingerprints `resolved_subject_label` /
  `resolved_object_label` — the output of entity resolution;
- the **frame** branch hashes the frame's own `subject` / `object`, which come
  straight from the model.

And the model's labels are, by instruction, not canonical.
`document_extraction_prompting.py` caps `subject` and `object` at **50
characters** and describes them as a "concise source-native entity span copied
exactly from the evidence clause; do not paraphrase, canonicalize, or reorder
its words."

`model-labels.json` is what that produces in practice. 33 real frames, 9
documents, recovered from the audit trail:

- **Zero cross-document fingerprint agreements.** All 7 fingerprints shared by
  more than one frame are shared *within* a single document. Nine documents,
  and the raw labels never once agreed across two of them — even though five of
  the nine assert gold fact `D006220|D002375` and four assert `D007980|D004409`.
- Labels that are not entity names at all: `'its'`, `'7e'`, `'was not'`,
  `'optimization steps'`.
- Labels that are clauses, truncated by the 50-character cap mid-word — the
  same document produced two different truncation points on two different
  framing calls.
- One label reads `'stereotaxic surgery using a microelectrode teknik?'`. The
  string `teknik` **does not occur anywhere in BC5CDR**. A second framing call
  over the same document, for the same relation, emitted the same phrase
  truncated at `techniq`. So the raw label is not even a faithful copy of the
  source, let alone a stable key: one document, one assertion, two strings.

That is the fork. Hashing resolved labels inherits whatever entity resolution
achieves. Hashing raw labels inherits a 50-character truncation of
non-canonicalised model prose, which the audit trail shows is unstable across
two calls over one document. Choosing between them is a bigger decision than
choosing which frame fields to strip, and #217 does not currently name it.

### C. Surface-form ambiguity bounds any label-based identity, in both directions

From `supplementary.json`, over every annotated mention in the corpus:

| | |
|---|---:|
| distinct normalised surface forms | 4929 |
| forms denoting more than one MeSH concept | 246 (4.99%) |
| mention instances carrying such a form | 1435 / 28849 (4.97%) |
| distinct MeSH concepts | 2350 |
| mean normalised forms per concept | 2.21 |
| concepts with one surface form only | 1244 |
| concepts with five or more surface forms | 198 |

Roughly 5% of mentions wear a form that another concept also wears — that is
the false-merge side. And the average concept is split across 2.21 forms, with
198 concepts split across five or more — that is the missed-merge side. Neither
number is circular: both are properties of the corpus, measured independently
of any identity rule.

---

## The three blockers this ran into, in order

The question in #217 turns out to be third in a queue. Each of these was
verified in code, not inferred.

**B1 — frame-backed proposals cannot be persisted at all.**
`harness_proposals.claim_fingerprint` is `String(32)` (`models/harness.py:264`),
and the live column is `character varying(32)`. `ClaimFrame.dedupe_identity`
returns a full `hashlib.sha256(...).hexdigest()` — 64 characters. The fallback
`compute_claim_fingerprint` returns `hexdigest()[:32]` and fits. So the frame
branch of the expression in §B writes 64 characters into a 32-character column.
This also explains the fail-closed promotion error
`qualified_claim_persistence_not_ready`.

**B2 — `identity_pending` is terminal.** A fingerprint collision parks the
second proposal there. There is no adjudication endpoint, no unpark path, it is
invisible in the default review queue, and `available_actions` is `[]`. Every
merge this measurement could recover would be an observation moved somewhere
nobody can see or action.

**B3 — one collision parks the whole batch.** The pre-check in
`sqlalchemy_stores.py` queries *already-persisted* rows, so two drafts that
collide *within one batch* both get `pending_review`, the flush violates the
partial unique index, and the `IntegrityError` handler calls
`_retain_conflicting_proposals(..., proposals=proposals)` with the entire batch.
Measured on BC5CDR: **66 of 1500 documents (4.4%)** would trip this, parking
**241 drafts** out of 3116 — see
`supplementary.json::intra_document_collisions_mention_labels`. (An earlier
pass also reported that 2.2% of drafts already lose identity to a same-document
sibling under current code. That figure is not re-derived here.)

None of these is about identity design. All three sit in front of it.

---

## Redaction: what was stripped before committing

BC5CDR is NCBI-authored and carries a PUBLIC DOMAIN NOTICE — "the NLM and the
U.S. Government have not placed any restriction on its use or reproduction" —
so it is not a restricted corpus in the sense of
`scripts/validation/RESTRICTED_CORPORA.md`, and no licence forbids
redistributing it. The name-versus-span rule in that document was applied
anyway, because it is the house rule for what a derived artifact carries and it
should not depend on which corpus happens to be underneath.

**Stripped: `framing_events.jsonl`** (172 kB, 25 raw `model_terminal` payloads,
sha256 `dcb19d98d1b25563c8a0440144279f120c740f65c32afa57b0d17e0168ff735f`). Each
row carries a verbatim BC5CDR sentence in its `sentence` field and quotes the
source again in `decision_rationale`. That is prose reproduced as prose. It was
also an intermediate: `harvest_real_labels.py` reads the same rows straight from
`artana.kernel_events`, so nothing committed depends on it.

**Kept: entity labels.** `model-labels.json`, `measurement.json` and
`supplementary.json` carry the strings the model or the corpus annotators used
to name an entity — `'buspirone'`, `'hemorrhagic cystitis'`, `'its'`,
`'teknik?'`. Those are names, and they are the analytical content of §B and §C:
a report that said "the subject label was a digest" would be unreadable.
`harvest_real_labels.py::_reject_spans` enforces the boundary mechanically — it
refuses to write if any emitted label exceeds the extraction prompt's own
50-character cap or carries a sentence boundary — so a future run cannot let
prose through under the label field.

No corpus sentence, span, offset-addressed excerpt or document text is present
in any committed file here. `make restricted-corpus-digest-check` passes.

---

## Reproduction

The corpus is fetched on demand, not committed. Digests are in
`scripts/validation/claim_identity_merge/MANIFEST.txt`.

```sh
export ARTANA_BC5CDR_CORPUS=/path/to/bc5cdr
PYTHONPATH=. python3 -m scripts.validation.claim_identity_merge.measure
PYTHONPATH=. python3 -m scripts.validation.claim_identity_merge.supplementary
```

Both rewrite the committed results in place, so `git diff` after a re-run *is*
the reproduction check. Both were verified byte-identical under two values of
`PYTHONHASHSEED`.

One defect was fixed in landing. The original `supplementary.py` iterated a
`set` of PMIDs, so its `examples` list was ordered by string hash and
reshuffled between runs while every count stayed fixed — an artifact a later
reader would have taken for a change in the finding. Both loops are sorted now.
The counts in this report are the counts the original run produced; the
`examples` slice is a different, and now stable, ten.

`harvest_real_labels.py` reads `artana.kernel_events` from the local Postgres
container and reproduces only against that database. It makes no provider call.

---

## What changed about the recommendation

Before: "remove the source span from claim identity so two papers can be
recognised as asserting the same fact."

After: the span is one of five per-document text carriers in the hash, removing
it alone leaves at least 15.5 points of collapse unrealised under perfect entity
labels, and the collapse cannot be persisted, adjudicated or reviewed today
regardless of any of this. The identity question is
real but it is not first, and when it is reached, the decision that matters is
whether identity is keyed on resolved entities or on raw model labels — not
which frame fields to drop.

Order of work: **B1** (widen the column, or make the frame branch emit a
32-character fingerprint — a deliberate choice, not a cast), then **B3** (park
the colliding proposal, not its batch), then **B2** (an adjudication path out of
`identity_pending`), then the identity model itself, resolved-vs-raw named
explicitly.
