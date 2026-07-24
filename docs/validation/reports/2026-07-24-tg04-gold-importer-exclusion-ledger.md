# TG-04 Gold Importer Exclusion Ledger

**Date:** 2026-07-24
**Fixture:** `scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json`
**Importer:** `scripts/validation/claim_events/bionlp_import.py`
**Purpose:** Publish what the importer drops when building the frozen TG-04 development panel, so past and
future scores computed on it can be read honestly.

Required by the direction adjustment (V2 gold round-trip): *"published counts for events removed by the
importer, including nested-event exclusions."* Every number below was recomputed directly from the fixture
and independently re-verified.

---

## 1. Headline

The panel holds **53 of 472** expert-annotated events across the 40 selected documents — **11.2%**.

That single figure is the most alarming of three defensible denominators. All three should be quoted
together:

| Denominator | Retention | What it answers |
|---|---:|---|
| 53 / 472 — all events, all 40 documents | **11.2%** | How much of the annotated corpus survives import |
| 53 / 298 — nested events treated as out of scope | **17.8%** | Retention once a real schema limit is granted |
| 53 / 276 — within the 17 documents actually scored | **19.2%** | **The number that governs historical scores** |

The third is the operative one: predictions on the 18 representability-stress documents are discarded
before scoring (`scoring.py:217`), so only the 17 `EVENT_GOLD` documents contribute.

**Scope caveat.** 472 is the gold-event count across the 40 hash-selected documents
(`selection_method = lowest_sha256_document_ids_before_content_review`), **not** the BioNLP-GE 2011
development set as a whole. It is internally exhaustive and non-overlapping — the 53 retained and 419
excluded keys are unique with an empty intersection — but it is **not verified against the source archive**:
no `.a1`/`.a2` files are vendored, only `source_url` and `archive_sha256` are recorded. Verifying 472
against the archive is exactly the V2 round-trip work, and it remains undone.

---

## 2. Exclusions by reason, with separate verdicts

These are not one phenomenon. They deserve different judgments.

| Reason | Count | Verdict |
|---|---:|---|
| `insufficient_direct_arguments` | 237 | **Undocumented policy constant**, not a schema limit |
| `nested_event_argument` | 174 | **Genuine schema limit**, defensible |
| `repeated_argument_mention` | 6 | Correct engineering — span-uniqueness guard |
| `repeated_trigger_mention` | 2 | Correct engineering — span-uniqueness guard |
| **Total** | **419** | |

Two further drop mechanisms exist in the importer and fire **zero** times on this fixture:
`indistinct_argument_mentions` (`bionlp_import.py:365`) and `duplicate_production_identity`
(`bionlp_import.py:421`). The four above are the complete set of drops that *fired*, not the complete set
the importer can apply.

### 2.1 `nested_event_argument` (174) — defensible

```python
if any(argument.reference_id in events_by_id for argument in event.arguments):   # :339
```

An event taking another event as an argument has no slot in the Artana record. This is a real
representational limit, honestly applied.

### 2.2 `insufficient_direct_arguments` (237) — the one that needs a decision

```python
_MIN_EVENT_ARGUMENTS: Final = 2                                                   # :29
representable_arguments = tuple(
    argument for argument in event.arguments
    if argument.reference_id in document.text_bounds
)
if len(representable_arguments) < _MIN_EVENT_ARGUMENTS:                           # :349
```

This is a **policy constant, not a schema limit** — the record format would hold these events unchanged.
All 237 have exactly one text-bound argument and zero event-typed arguments.

It removes the normal unary shape of a large part of the GE ontology:

- **all 132** `Gene_expression`
- **all 22** `Transcription`
- **all 5** `Protein_catabolism`

**The rule is not a binary-relation model, and should not be described as one.** It counts arguments of
*any* role. Retained argument roles are `THEME` 62, `SITE` 27, `CAUSE` 22, `TOLOC` 3, `CSITE` 1 — and
**22 of the 53 retained events have only one core `THEME`/`CAUSE` argument**, surviving purely because a
secondary `SITE`, `CSITE`, or `TOLOC` annotation happened to exist. Retention therefore tracks *annotation
density*, not event structure.

Relaxing this constant alone would raise retention to roughly **61%** (≤290/472). Supporting
event-as-argument alone would give ≤29% (137/472).

---

## 3. Per-type retention and the crosswalk

The importer **renames** types; it does not merely recase them. Use this crosswalk
(`bionlp_import.py:13-23`) — a case-folding rule is wrong and will silently produce bad numbers if the
fixture is ever regenerated:

| BioNLP type | Artana type | Retained | Total | Retention |
|---|---|---:|---:|---:|
| `Positive_regulation` | `POSITIVE_REGULATION` | 23 | 166 | 13.9% |
| `Gene_expression` | **`EXPRESSION`** | 0 | 132 | **0.0%** |
| `Negative_regulation` | `NEGATIVE_REGULATION` | 6 | 54 | 11.1% |
| `Regulation` | `REGULATION` | 9 | 52 | 17.3% |
| `Binding` | `BINDING` | 11 | 23 | 47.8% |
| `Transcription` | `TRANSCRIPTION` | 0 | 22 | **0.0%** |
| `Localization` | `LOCALIZATION` | 3 | 13 | 23.1% |
| `Phosphorylation` | `PHOSPHORYLATION` | 1 | 5 | 20.0% |
| `Protein_catabolism` | **`DEGRADATION`** | 0 | 5 | **0.0%** |

Three Artana types — `EXPRESSION`, `TRANSCRIPTION`, `DEGRADATION` — have **zero** representation,
covering 159 of 472 events (33.7%). The panel is silent on the corpus's three most frequent simple event
types.

---

## 4. The retained panel is not "easy"

An earlier draft of this analysis called the survivors an "easy subset." That is **backwards** and is
corrected here:

- **38 of 53 (71.7%)** are regulation-family events — generally the harder class, not the easier one.
- **13 of 53** carry non-default polarity or epistemic status (`SUPPORT` 40 / `UNCERTAIN` 8 / `REFUTE` 5;
  `ASSERTED` 45 / `UNCERTAIN` 8).

The accurate characterization is **structurally simplified and unrepresentative**, not easy.

**Do not cite `control_status` as evidence of design intent.** Those labels are assigned *post hoc* from
the importer's own output (`bionlp_import.py:264-276`) after content-blind hash selection.
`REPRESENTABILITY_STRESS` means exactly "the filter dropped 100% of this document's gold events" — citing
it to justify the drops is circular. Only the 5 `TRUE_NO_EVENT_CONTROL` documents genuinely contain no
source events. The 18 stress documents hold **196 real gold events**, 42% of the excluded mass.

---

## 5. Two defects found while compiling this ledger

### 5.1 The precision gate penalizes correct extraction — **severity: high**

```python
whole_event_precision=CountRate.of(counts.whole_matches, counts.predicted_events)   # scoring.py:382
(metrics.whole_event_precision, 0.90),                                              # evaluation.py:215
```

The precision denominator is **every prediction the model makes**, with no restriction to gold-covered
spans. In the 17 scored documents the corpus annotates **276** events while gold holds **53**.

An extractor that reads the papers faithfully and returns all 276 corpus events therefore caps at
**53/276 = 19.2% precision against a 90% gate** — it cannot pass, no matter how correct it is. Every
correctly extracted event that the importer filtered out is scored as a false positive.

**The panel does not merely fail to measure recall on the excluded events; it actively punishes producing
them.** It rewards reproducing the importer's filter rather than reading the source. This is the most
likely explanation for the historical TG-04 stall, and it should be resolved before any threshold on this
fixture is treated as meaningful.

### 5.2 Polarity-inverted gold records — **severity: high, data defect**

20 of the 53 retained events are children of a dropped nested parent; 7 of those parents are
`Negative_regulation`. Polarity is derived only from a `Negation` modifier attached to the event *itself*,
so a surviving child keeps `SUPPORT` / `ASSERTED` even when the corpus asserts the opposite.

Three verified examples — the gold label contradicts the source text:

| Record | Source text | Gold label |
|---|---|---|
| `PMID-9164948:E2` | "…**the failure of** p65 translocation to the nucleus…" | `SUPPORT` / `ASSERTED` |
| `PMID-10402173:E9` | "…but **did suppress** their nuclear localization" | `SUPPORT` / `ASSERTED` |
| `PMID-10402173:E10` | "…but **did suppress** their nuclear localization" | `SUPPORT` / `ASSERTED` |

These are wrong, not ambiguous. They should be re-polarized or excluded before the fixture is used again.
A model that reads these sentences correctly is currently marked wrong.

---

## 6. Repo statements this ledger supersedes

| Location | Problem |
|---|---|
| `docs/artana-vision-and-direction.md` §5 | Says "excluding all nested and **multi-argument** events" — inverted; it excludes **single**-argument events. Also calls the remainder "an easy subset" — see §4. Corrected in this change. |
| `docs/validation/tg04-nary-model-ablation-protocol.md:102-106` | Exclusion list omits the 237 arity drops and describes the exclusions as cases "Artana's categorical inventory schema cannot express" — untrue of the arity rule, which is a policy constant over an expressible shape. |

---

## 7. Recommended follow-ups

1. **Fix or waive the precision denominator** (§5.1) before treating any threshold on this fixture as
   meaningful. Options: restrict the denominator to gold-covered spans, or score only events the importer
   would have retained.
2. **Re-polarize or drop the 7 nested-parent children** (§5.2).
3. **Decide on `_MIN_EVENT_ARGUMENTS`** (§2.2) — document it as intentional scope, or relax it to 1 and
   regenerate. It is currently an undocumented constant carrying a third of the exclusion mass.
4. **Complete the V2 round-trip** — 472 is unverified against the source archive.
5. **Regenerate this ledger** whenever the fixture or importer changes; it is a derived artifact.

---

## Appendix — reproducing these numbers

```python
import json, collections
d = json.load(open("scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"))
ex = d["metadata"]["event_exclusions"]
kept = [(c, e) for c in d["cases"] for e in c["events"]]

len(kept), len(ex)                                        # 53, 419
collections.Counter(x["reason"] for x in ex)              # the four reasons
gold = {c["title"] for c in d["cases"] if c.get("control_status") == "EVENT_GOLD"}
len(kept) + sum(1 for e in ex if e["document_id"] in gold)   # 276 -> the scored denominator
```
