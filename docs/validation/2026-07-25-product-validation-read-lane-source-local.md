> **Superseded as the primary plan. Retained for its READ-lane design.**
>
> This document was written when "validate the backend" was read as *can the
> model extract claims from one paper*. The product owner subsequently defined
> it as *read many papers, create evidence, and connect it* — three capabilities,
> of which this measures only the first.
>
> **Read [2026-07-25-product-validation-read-ground-connect.md](2026-07-25-product-validation-read-ground-connect.md) first.**
> That document is the current plan. It keeps this one's READ-lane design, its
> four verified blockers, and its gold-as-predictions discipline, and re-aims the
> headline at cross-document assembly. The corpus chosen here (BioNLP-ST GENIA)
> is retained for READ and is disqualified for CONNECT: it carries zero
> entity-normalization records, so it never states what anything *is*.

# Product Validation Experiment Plan — TG-04

## Measuring whether the Artana extraction backend is actually right

**Status:** proposal. Nothing here has been executed against a model. No provider money was spent producing it.
**Date:** 2026-07-25
**Authority:** this document proposes. The preregistration it specifies (§6.6) is the thing that binds.

---

## 0. The honest answer, first

**We cannot currently state how accurate this system is.** There is no published, defensible accuracy number for any part of the extraction backend. `docs/validation/results/` contains exactly one file, and it measures run-to-run instability on a different task — not accuracy.

What we do have is unusual and worth something: **a calibrated ruler that has never been used to take a measurement.** This plan is how we take the measurement.

It is a plan to measure **one lane** of the backend — source-local claim-event extraction — against **one** expert-annotated corpus, with **one** model. It will not validate "the backend." §11 states, in detail, everything the resulting number will not be allowed to say.

---

## 1. Where we stand

### 1.1 What exists and works

- **An expert-annotated gold corpus from real published biomedical papers.** BioNLP-ST 2011 GENIA development split: 259 documents, 3,101 expert-annotated molecular-biology events (verified count, §Appendix A). Fetched and digest-verified by `scripts/fetch_bionlp_ge_corpus.py` against pinned SHA-256 `f70e5f6d…a890f`. I ran it; it verifies clean.
- **A scorer proven against a known answer.** On 2026-07-24 the gold standard was fed back as if it were the system's own predictions — an input that must score 1.0 by construction. It scored `whole_event` precision 0.0000 and recall 0.0000 while matching 53/53 triggers. The scorer was broken. It was fixed. `docs/validation/reports/2026-07-24-tg04-two-sided-scorer-calibration.md`. **This technique is the single most valuable asset in this program and it is reused as a gate throughout this plan.**
- **A repaired gold panel.** 7 of 53 records asserted a polarity their own source denies; each was read against its source sentence and corrected under a written adjudication record (`scripts/validation/claim_events/bionlp_import.py`, `POLARITY_ADJUDICATIONS`).
- **A preregistered protocol.** `docs/validation/preregistrations/2026-07-25-tg04-evaluation-protocol-v1.json`, bound to code by `tests/unit/test_evaluation_protocol_preregistration.py`.
- **A measured noise floor.** `docs/validation/reports/2026-07-25-staged-generalization-v17-noise-floor.md`: 20 replicates × 3 cases, 60 provider calls, $0.9948, prompt verified byte-identical against the sealed `provider_input_sha256`. Per-case reproducibility 0.95 / 0.85 / 0.53 (the third is 10/19 after one errored call). One case has a 95% CI spanning 0.5 — a coin flip.

### 1.2 The standing rule that governs everything below

> **A single run is a record of what happened. It is never evidence about a configuration.**

Any design that reports a point estimate from one run is wrong on arrival. This plan's primary endpoint is therefore a **rate with a confidence interval, averaged over many documents**, and the design publishes the quantity that says how much a re-run would move it.

### 1.3 A second rule: the headline is not a PASS/FAIL verdict

The current operational gate (`scripts/validation/claim_events/evaluation.py:212-247`) is a conjunction of ten pooled metric floors, **plus** per-category precision/recall floors for every event type with ≥5 gold events, **plus** three hard-zero conditions (`negative_null_leakage`, `epistemic_escalation`, `empty_control_false_positive`). Twenty-odd simultaneous conditions.

Whether that conjunction passes is not a measurement of accuracy. It is a threshold decision, and a threshold decision reports one bit while discarding the magnitude and the uncertainty — the two things a reader needs. It also makes the reported quantity discontinuous in the underlying performance, so small real changes produce large reported changes and vice versa. **The gate stays, as an operational artifact for release decisions. It is never the headline, and no PASS/FAIL is quoted as a validation result.**

### 1.4 What this experiment will settle

A number of this shape, with an interval, on documents never used during development:

> *On N held-out expert-annotated biomedical documents, selected by a content-blind order fixed before the corpus was read, Artana's production extraction path recovered R% of expert-annotated multi-argument events (95% CI [a, b], cluster-robust over documents), at a review burden of K predictions per document, under a matcher and metric set fixed in writing before the first model call.*

### 1.5 What it will not settle — on page one, not in a footnote

The corpus annotates **two** text-bound entity types (`Protein`, 4,526 annotations; `Entity`, 179 — verified) and contains **zero entity-normalization records**: I grepped every `.a1` and `.a2` file in the archive and there are no `N` lines at all.

Therefore this experiment measures the **source-local claim-event extraction lane only**. It says nothing about CURIE resolution or entity linking across our 13 namespaces, nothing about the 38-value production relation taxonomy, nothing about cross-document claim merge or deduplication, nothing about trust scoring or promotion, and nothing about what a reviewer eventually sees in the proposal queue.

**If the claim we need to defend publicly is about the governed knowledge graph, this is the wrong ruler and §3.3 applies. That question (open decision 1, §10) is free to answer and can invalidate the rest of this plan. Answer it first.**

---

## 2. Blockers — verified, at the lines cited

Every item below was checked in the repository. Four of them are **hard stops**: the first executable step of this experiment fails today.

### 2.1 Hard stops (nothing runs until these close)

| # | Blocker | Evidence | Consequence |
|---|---|---|---|
| **H1** | **The held-out fixture builder crashes.** `_parse_modifiers` raises `ValueError: event has multiple modifiers` (`bionlp_import.py:652-653`) on any event carrying both `Negation` and `Speculation`. Three held-out documents trigger it (`E62`, `E9`, `E10` in their respective files). `build_bionlp_fixture` has no per-document error handling (`:287-289`), so it raises on the first. | Reproduced by running the real importer over corpus ranks 41–259. None of the 40 development documents carries a doubly-modified event, which is why this was never hit. | The held-out panel cannot be built at all. |
| **H2** | **The live runner is pinned to the superseded v1 fixture and rejects v2.** `require_frozen_development_fixture` (`fixture.py:99-109`) compares against `DEFAULT_DEVELOPMENT_FIXTURE_PATH` = `…_v1.json` (`fixture.py:42-44`) and its frozen SHA. `runner.py:81` re-pins even when `--fixture` is passed. | Executed: `require_frozen_development_fixture(load_fixture(v2))` → `ValueError: TG-04 development gates require the frozen fixture path`. | The panel the preregistration governs cannot be run live. |
| **H3** | **The V1 calibration gate does not check what the plan and the preregistration say it checks.** `tests/unit/test_gold_as_predictions_calibration.py:29-37` runs on **v1**, not the preregistered v2, and asserts 1.0 on **4** metrics: `whole_event_precision/recall`, `trigger_precision/recall`. `_run_passes` gates on **10**. `event_type_fidelity`, `argument_precision`, `argument_recall`, `argument_set_fidelity`, `polarity_fidelity`, `epistemic_fidelity` are asserted at 1.0 by no test anywhere. | Read directly. The preregistration's `"observed": "PASS on v2 under this matcher"` has no executable check behind it. | The stop condition this whole plan rests on is not runnable. |
| **H4** | **The runner aborts the entire arm on the first transport error and writes nothing.** `_execute_case` catches only `ValidationError \| StructuredModelValidationError` (`runner.py:257-258`). Any litellm timeout, rate-limit or connection error propagates out of the serial `for case in fixture.cases` loop (`runner.py:115-143`). The report is assembled only *after* the loop (`runner.py:150-206`); `predictions` lives in memory; there is no checkpoint. `runner.py:150-152` then re-collects repository evidence and raises `RuntimeError` if any tracked file changed — **after** the spend, before scoring, before anything is written. | Read directly. The noise floor observed 1 error in 60 calls. At that rate the probability a ~2,400-call arm completes without an uncaught transport error is `0.983^2400 ≈ 10⁻¹⁸`. | The most likely outcome of a full run today is **no data, hours in, money spent**. |

### 2.2 Measurement-correctness blockers (a run would produce a plausible-looking wrong number)

| # | Blocker | Evidence | Consequence |
|---|---|---|---|
| **M1** | **Every event from an incomplete document is discarded before scoring.** `runner.py:286-288`: `events = framed_events if executable else []`. When a document terminates `SEMANTICALLY_INCOMPLETE`, `executable` is False and the prediction becomes an **empty list** — that document scores recall 0.0, not partial recall. The 2026-07-17 bounded-convergence pilot records `SEMANTICALLY_INCOMPLETE` as the extractor's *normal* terminal state on this task. | Read directly. | The headline recall would be a measurement of the convergence loop's termination behaviour, not of extraction — and it would look exactly like a real recall number. |
| **M2** | **The preregistered precision metric is wired into nothing.** `scope_aware_precision` (`corpus_attestation.py:161-175`) is implemented and unit-tested; the only repo-wide importer is its own test; it is not even in `corpus_attestation.__all__` (`:189-196`). `scoring.py:379-381` still divides by all predictions and `evaluation.py:213` gates on that. | `grep -rn scope_aware_precision scripts tests services docs`. | The 2026-07-24 calibration proved the current denominator **cannot distinguish a corpus-faithful extractor from a pure hallucinator** — both scored 0.1920. A precision figure reported under it is noise wearing a decimal point. |
| **M3** | **`scope_aware_precision` is blind to every label error.** The attestation digest (`corpus_attestation.py:32-47`) is `document_id + trigger_span + trigger_source_start + sorted(argument_spans)`. No event type, no polarity, no epistemic status, no argument role. A prediction with the right trigger and right argument spans but a **flipped polarity** or **wrong event type** is neither a gold match nor an unattested prediction — it is silently removed from the denominator. | Read directly. Corroborating: the committed index carries `corpus_event_count = 472` against `digest_count = 432`, so 40 corpus events are structurally indistinguishable from another corpus event even inside the corpus. | The report would show precision ≈ 1.0 while the system emits wrong-polarity claims at scale. Polarity is exactly the axis M4 says is fraught. |
| **M4** | **The gold panel is unreachable on polarity by construction.** 8 of 53 v2 gold events carry `polarity: UNCERTAIN`; the production schema `InventoryPolarity` (`services/artana_evidence_api/document_extraction_support/claim_frames/semantics.py:27-32`) admits only `SUPPORT / REFUTE / NULL_RESULT`. `polarity_fidelity = polarity_matches / expected_events` (`scoring.py:414`) against a 0.95 floor. Origin: one importer line, `bionlp_import.py:533-534`, mapping `Speculation → ("UNCERTAIN","UNCERTAIN")`. | Measured fixture v2 polarity counts: `{SUPPORT: 33, REFUTE: 12, UNCERTAIN: 8}`. | Polarity fidelity is capped at 45/53 = **0.8491**. The gate is unpassable no matter how good the model is. |
| **M5** | **The operational gate fails the whole run closed on any incomplete qualification document.** `operational.py:85-93` requires `qualification_incomplete == 0`. | Read directly. | Combined with M1, a full run very likely produces **no score at all**, for the second time. |
| **M6** | **Length-correlated missingness.** `runner.py:419` builds `LiteLLMAdapter(timeout_seconds=60.0)` while the model registry allows 900 s for the same reasoning model (`services/artana_evidence_api/artana.toml:123`). The held-out set contains documents up to **20,199 characters** against a development maximum of 2,357. | Read directly; lengths measured. | Timeouts bite hardest on the longest prompts. Excluding failed documents is then MNAR and removes exactly the hardest cases, biasing recall **upward**. The same length asymmetry hits the binder's exactly-once `exact_span` rule. |

### 2.3 Growth and hygiene blockers

| # | Blocker | Evidence | Consequence |
|---|---|---|---|
| **G1** | **Licence exposure.** `tg04_bionlp_ge_development_v1.json` and `…_v2.json` are git-tracked in a public repo, 278 KB each, and embed verbatim corpus `source_text` for all 40 documents (**54,834 characters** measured) plus trigger spans, argument spans, offsets and original `E`/`T`/`M` annotation ids. `scripts/fetch_bionlp_ge_corpus.py:3-11` states the corpus is "deliberately NOT vendored." Corpus licence clause 6 requires organiser permission for public use by commercial/non-academic organisations. | Measured. | Growing the panel ~5× multiplies the exposure ~5×. **Blocking on growth.** |
| **G2** | **The attestation index cannot be regenerated or audited.** `scripts/build_corpus_attestation_index.py` is referenced by `fetch_bionlp_ge_corpus.py:11` and **does not exist anywhere in the tree**. The committed 432-digest index has no builder. | `find`/`grep` across the tree. | M2's fix makes the gate's denominator depend on this artifact. An unauditable denominator is not defensible. |
| **G3** | **The calibration tests run in no automated path.** `test_evaluation_protocol_preregistration.py`, `test_gold_as_predictions_calibration.py`, `test_corpus_attestation.py` and `test_gold_polarity_adjudication.py` appear in neither `ARTANA_EVIDENCE_API_TEST_PATHS` (`Makefile:105-121`) nor any workflow in `.github/workflows/`. | `grep -rn … Makefile .github/workflows/` → no hits. | The scorer can silently regress to the 0/53 state we already discovered once. |
| **G4** | **Concurrency does not exist.** `runner.py:115-143` is a strictly serial `for` loop with `await` inside, one kernel, one store. | Read directly. | Wall-clock estimates must be the serial ones. See §8. |
| **G5** | **The noise-floor harness exists only in an archive tag.** `scripts/run_v17_noise_floor.py` is tracked on HEAD but fails with `ModuleNotFoundError: No module named 'scripts.validation.public_gold'`. The V6→V18 machinery lives at `refs/tags/archive/alvaro/tg04-source-general-claim-verification-v17` (commit `db96b23d`), which also contains `biored_adapter.py`, `bionlp_cg_adapter.py`, `source_selection.py`, `representability.py`. | Executed the import; confirmed the tag. | The only reproducible replicate harness we have is one `git gc` away from being unrecoverable. Recover it in Phase 0. |

---

## 3. Ground truth: the choice, the justification, the fallback

### 3.1 Primary: BioNLP-ST 2011 GENIA, scaled onto its own untouched remainder

**Decision: the BioNLP-GE 2011 devel split, held-out documents at hash ranks 71–259.**

**Reason 1 — the crosswalk exists and is already proven.** Mapping a gold corpus's vocabulary onto ours is the expensive, dangerous part of any validation. For BioNLP-GE it is a **9-entry event-type dictionary** plus a 2-entry role dictionary (`bionlp_import.py:13-27`) that has passed a gold-as-predictions calibration at exactly 1.0 on four metrics (and must be extended to all ten — H3). Every alternative corpus requires building a crosswalk from scratch **and then proving it**. We have exactly one data point about what happens when we trust an unproven scorer: it returned 0.0000/0.0000 while matching 53/53 triggers.

**Reason 2 — a real held-out set already exists, at zero annotation cost.** `select_document_ids` (`bionlp_import.py:108-124`) orders documents by `sha256(document_id)` and takes the first 40. That order was fixed a priori, in code, before anything was read. Ranks 41–259 have never been scored.

**Reason 3 — structural fit.** BioNLP-GE annotates a **trigger span with character offsets**, typed arguments, and Negation/Speculation modifiers. Our `ClaimEvent` contract is trigger span + `ClaimEventType` (15 values) + `ClaimEventRole` (12 values) + polarity + epistemic status + `exact_span` + `source_start`. **No other candidate corpus annotates a trigger span at all.**

**Reason 4 — the alternative costs ~100× for the same interval.** A bespoke expert-labelled set of comparable size: 2 annotators × 80 abstracts × 0.75 h × $75/h = $9,000, plus adjudication 80 × 0.25 h × $75 = $1,500 → **~$10,500 and 4–8 weeks**, yielding on the order of 300 events. The held-out remainder yields more, for $0 of annotation cost. Bespoke annotation buys domain fit, not statistical power.

### 3.2 Corpora considered and rejected

| Candidate | Verdict | Reason |
|---|---|---|
| **SemMedDB** | Rejected | Machine-generated by SemRep. Scoring against it measures agreement with another NLP system's error profile, not correctness. |
| **CTD / curated relation databases** | Rejected as a scorer | Assert relations at database level with no per-sentence label → uncontrolled recall denominator. A paper-level assertion absent from an extraction is not necessarily a miss. Useful for plausibility triage only. |
| **ChemProt / DrugProt** | Rejected | These tasks supply gold entity offsets **as input**. They measure relation classification given perfect entities — not end-to-end extraction, which is what we ship. |
| **INDRA** | Not ground truth | A comparable *system*. Its curation sets are judgments on outputs INDRA itself produced. The defensible use is a blind head-to-head on shared documents with human adjudication — a worthwhile follow-up, not a first move. |
| **PubTator** | Not ground truth | Normalized candidates are a useful tool for an agent, not independent proof that a claim is correct. |

### 3.3 Fallback: BioRED — and its exact trigger conditions

**Fallback = BioRED** (document-level biomedical relations, normalized entity identifiers, multiple entity and relation types). A `biored_adapter.py` already exists in the archive tag named in G5, so the fallback is genuinely available rather than hypothetical.

Switch if **any one** of these fires:

1. **Scope trigger.** The claim we must defend is about the *graph* layer — normalized entities, the 38-value taxonomy, cross-document merge. BioNLP-GE is structurally incapable of speaking to this (zero normalization records). *Evaluate this before any money is spent.*
2. **Calibration trigger.** After the crosswalk changes in §4, gold-as-predictions fails to return **exactly 1.0** on every gated metric on two consecutive attempts. Do not debug your way to a passing scorer under time pressure; switch rulers.
3. **Licence trigger.** The remediation in X4 is rejected or cannot be completed, so the panel cannot grow without growing the exposure.

BioRED's costs, stated honestly and **not verified in this session**: roughly 8 document-level relation types must map onto our 38-value taxonomy, and BioRED carries **no evidence span** — so scoring it means discarding the span anchor that is our core product guarantee. Its licence terms and relation inventory must be verified by fetch before commitment.

---

## 4. The crosswalk: the experiment's principal scientific artifact

If the crosswalk is wrong, every number downstream is wrong in a way that looks entirely plausible.

### 4.1 What it maps

**Event types** (`bionlp_import.py:13-23`) — 9 entries. These are renames, not case-folding, which is why they must be explicit and reviewed. Held-out counts are in Appendix A.

`Binding→BINDING`, `Positive_regulation→POSITIVE_REGULATION`, `Negative_regulation→NEGATIVE_REGULATION`, `Regulation→REGULATION`, `Localization→LOCALIZATION`, `Phosphorylation→PHOSPHORYLATION`, `Gene_expression→EXPRESSION`, `Transcription→TRANSCRIPTION`, `Protein_catabolism→DEGRADATION`.

**Participant roles** (`:24-27`): `Protein→GENE_OR_PROTEIN`, `Entity→OTHER_ENTITY`. Numeric role suffixes (`Theme2`) are stripped to `event_role`.

**Modality.** Two defects, one fix.

- `Negation → polarity = REFUTE, epistemic = ASSERTED`. Sound; this is what the 2026-07-25 polarity repair enforced.
- `Speculation → ("UNCERTAIN", "UNCERTAIN")` is **wrong** (M4). `Speculation` is an *epistemic modality*, not a truth value. The production schema already models this correctly: `epistemic_status = UNCERTAIN` with a truth-valued `polarity`.
- An event carrying **both** modifiers currently raises (H1).

**One adjudication fixes both.** `Negation` and `Speculation` are orthogonal in the production schema and must compose:

| corpus modifiers | polarity | epistemic_status |
|---|---|---|
| none | `SUPPORT` | `ASSERTED` |
| `Negation` | `REFUTE` | `ASSERTED` |
| `Speculation` | `SUPPORT` | `UNCERTAIN` |
| `Negation` + `Speculation` | `REFUTE` | `UNCERTAIN` |

> **Explicit warning against the tempting wrong fix.** Do **not** widen `InventoryPolarity` to admit `UNCERTAIN`. That changes the production extraction schema, and therefore the `output_schema_sha256` that provider receipts bind to, purely to make a benchmark pass. Fix `bionlp_import.py:533-534` and `_parse_modifiers`, and regenerate the fixture.

This adjudication must be **written down and reviewed before the fixture is sealed**. It is a semantic decision, not a bug fix.

**The polarity adjudication table does not scale, and this is undisclosed work.** `POLARITY_ADJUDICATIONS` is hand-curated by `(document_id, event_id)` — 7 entries for 53 development events (13%), each read individually against its source sentence. The code comment says so explicitly: *"This is deliberately a table and not a rule."* Scaling to ~1,600 held-out events at the same rate implies **on the order of 200 hand adjudications**.

The only version that scales: **derive the negation-inheritance rule from the 7 adjudicated cases, verify it reproduces all 7 exactly, apply it mechanically, and publish it as part of the crosswalk.** All 7 are events whose dropped nested parent carried the negation, so a rule is plausible — but deriving it changes the crosswalk and therefore requires re-running V1–V6. If no rule reproduces all 7, budget the manual work honestly or reduce the panel. **X5 is sized for the rule-derivation path.**

**Retention policy.**
- Nested events (arguments referencing other events) are excluded: a genuine schema limit.
- `_MIN_EVENT_ARGUMENTS` (`:29`) is a **policy constant, not a schema limit** — see §4.2.
- Mention uniqueness: the production binder requires an `exact_span` to occur exactly once in the source chunk. This dropped 8 development events and is the root cause of the 2026-07-16 controlled stop.

**The retention denominator ships with the result.** Three defensible denominators exist and the operative one must be named in the headline sentence. On the development panel: 53/472 = 11.2% of all events in the selected documents; 53/298 = 17.8% granting the nested-event schema limit; 53/276 = 19.2% within the documents actually scored.

### 4.2 `_MIN_EVENT_ARGUMENTS`: decided on a stated scientific criterion, before any run

This is not a cosmetic knob. Measured with the real importer over held-out ranks 41–259 (216 parseable documents):

| | `_MIN_EVENT_ARGUMENTS = 2` | `= 1` |
|---|---|---|
| Retained events | 296 | 1,632 |
| Documents carrying gold (`EVENT_GOLD`) | **85** | **187** |
| `REPRESENTABILITY_STRESS` documents (predictions **discarded** by `scoring.py:214-217`) | **102** | **0** |
| `TRUE_NO_EVENT_CONTROL` documents | 29 | 29 |
| Artana event types with zero coverage | **3 of 9** | 0 of 9 |

At min = 2, **102 of 216 documents are paid for and produce nothing scoreable**, and three event types (`EXPRESSION`, `TRANSCRIPTION`, `DEGRADATION`) have zero gold. At min = 1 the representability-stress class disappears entirely and every document either carries gold or is a genuine control.

**Decision: `_MIN_EVENT_ARGUMENTS = 1`, with mandatory stratification.**

The score-blind rule "regenerate at min=1, run gold-as-predictions, accept if 1.0" cannot discriminate — gold-as-predictions is a self-consistency check of the scorer against its own fixture and returns 1.0 for essentially any arity policy. It is a necessary sanity check, not a decision procedure. The decision is made on the criterion above: **panel efficiency and event-type coverage**, both computable without a score.

**But single-argument events are a different task.** A one-argument `Gene_expression` is closer to typed-mention detection than to n-ary event extraction, and is almost certainly much easier. Pooling ~1,177 of them with 264 multi-argument events into one number is exactly the mechanism that produces a flattering, meaningless figure.

**Therefore the panel is built at min = 1 and reported in two strata that are never pooled:**

- **Stratum A — multi-argument events (≥ 2 direct arguments).** This is the n-ary extraction task the `ClaimEvent` contract is about. **Primary endpoint.**
- **Stratum B — single-argument events.** Reported always, alongside, with its own CI. **Never merged into a headline number.**

No pooled recall figure is published, in any venue.

### 4.3 How the crosswalk is validated — six free checks

**All six must pass, at the exact commit SHA that will execute the run, immediately before the run.** All are free. All go into CI (X10).

| Check | Method | Pass condition |
|---|---|---|
| **V1 — Gold-as-predictions** | Feed the gold panel back as the system's own predictions. | **Exactly 1.0** on **all ten** gated metrics, on the fixture that will actually be run. This is the check that caught a scorer returning 0.0000 while matching 53/53 triggers. Today it asserts 4 metrics on the wrong fixture (H3). |
| **V2 — Two-sided calibration** | Run A: a pure hallucinator (plausible events not in the corpus). Run B: a corpus-faithful extractor emitting every corpus event including those the importer excluded. | Run A precision ≈ 0. Run B recall = 1.0 **and** `scope_aware_precision` = 1.0. Under the current denominator both score 0.1920 — that is M2, and V2 is the test that proves it fixed. |
| **V3 — Bounded-tolerance negatives** | Perturb gold predictions in ways that must fail: shifted offsets, wrong event type, flipped polarity, dropped argument. | Each perturbation must reduce the score. The one accepted tolerance — a prediction whose trigger span *contains* the gold trigger at the exact gold start offset — must be documented, tested, and justified by measurement (widening every trigger by 12 characters goes 1.0 → 0.0 under equality and 53/53 under containment). |
| **V4 — Archive round-trip** | Parse `.a1`/`.a2` directly from the digest-verified archive and reconcile the crosswalk's own counts against the source. | **Done for the development panel during this planning.** The real importer over ranks 1–40 returns `corpus_events = 472`, `retained = 53`, exclusions `{insufficient_direct_arguments: 237, nested_event_argument: 174, repeated_argument_mention: 6, repeated_trigger_mention: 2}` = 419, and 53 + 419 = 472 exactly. Must be repeated for the held-out fixture. |
| **V5 — Coverage ledger** | Publish, per Artana event type, how many gold events exist and how many were retained, **per stratum**. | Zero-coverage and underpowered types are named in the report, not discovered by a reader. |
| **V6 — Label-sensitivity of the precision metric** *(new; closes M3)* | Take the gold panel, flip every polarity; separately, corrupt every event type. Rescore. | `scope_aware_precision` **must fall** in both cases. If it does not, the metric is not shippable. |

**M3's fix is not "extend the digest with labels."** That would reintroduce the filtered-out-event penalty the attestation index exists to remove: a correctly-extracted event that the importer excluded would count against precision. The fix is a **fourth reported bucket**:

```
matches                             — attested and gold-matched
structurally_attested_mislabelled   — attested identity, wrong type/polarity/role/epistemic
attested_out_of_scope               — attested identity, importer-excluded event
unattested                          — not in the corpus at all
```

`scope_aware_precision = matches / (matches + unattested)` stays as preregistered. `structurally_attested_mislabelled` is counted and published per document, and it is **counted in review burden** (§6.5), because a reviewer must read and reject it.

---

## 5. What must be built

Sizes are estimates in engineer-days, not measurements.

| ID | Item | Why | Size |
|---|---|---|---|
| **X0** | **Modifier composition adjudication + implementation.** Write the §4.1 table as a reviewed adjudication record; implement in `_parse_modifiers` and `_epistemic_categories`; per-document error handling in `build_bionlp_fixture` so a parse failure quarantines one document instead of killing the build. | Closes **H1** and **M4** with one decision. Nothing else can start. | 1 d |
| **X11** | **Extend V1 to all ten gated metrics, on the fixture that will be run.** Repoint `_GATED_METRICS` and `_FIXTURE`; add the same assertion for the held-out fixture. | Closes **H3**. Converts the plan's central promise from an assertion into a test. **Do this second.** | 0.5 d |
| **X1** | Move the live-gate fixture pin off the hard-coded v1 path; generalize `require_frozen_development_fixture` into a **registry of frozen fixtures keyed by (path, sha, purpose)**. | Closes **H2**. Without it no held-out fixture can be run at all. | 1 d |
| **X7** | **Runner hardening: error containment + checkpointing + resume + latency + replicates.** Per-document `try/except` producing a typed `ERROR` outcome; append-only JSONL persistence of each prediction as it completes; resume-from-partial; per-document worktree check that aborts *early* rather than after the spend; per-call latency recorded alongside the cost the harness already records; adapter timeout raised from 60 s to the registry's 900 s; a **replicate dimension** threaded through the fixture contract, the runner, `score_fixture` and `operational.py` (`fixture.py:87-88` raises on duplicate case ids and `scoring.py:167-171` raises on unknown prediction case ids, so replicates cannot be expressed today). | Closes **H4** and **M6**. Without it, a 20–40 hour serial run is destroyed by any single timeout. | 5 d |
| **X6** | **Separate measurement from the operational gate.** Score `framed_events` regardless of `executable` (`runner.py:286`); carry `execution_outcome` as a per-document covariate; relax `operational.py:85-93` so only *provider/transport* failures are operational aborts and incompleteness is recorded as measured recall loss. | Closes **M1** and **M5**. Without the `runner.py:286` change, the headline measures the convergence loop, not extraction. | 1.5 d |
| **X2** | Wire `scope_aware_precision` and the four-bucket accounting into `score_fixture` and the gate; add it to `__all__`; amend the preregistration to a new version, because the denominator change re-baselines what "0.90" means. | Closes **M2** and **M3**. | 3 d |
| **X3** | **Build `scripts/build_corpus_attestation_index.py`** (missing), recover the regeneration rule that produced 432 digests from 472 corpus events, and build the held-out index (~2,600 events over ~219 documents — a new artifact, not a rebuild). | Closes **G2**. X2 makes the gate's denominator depend on this. | 2 d |
| **X5** | Held-out fixture builder producing a frozen, sealed panel over ranks 71–259 under the corrected modifier composition, the derived negation-inheritance rule (§4.1), and `_MIN_EVENT_ARGUMENTS = 1`; includes V4 archive round-trip and the V5 coverage ledger. | The preregistration asserts a held-out set "remains untouched"; **no such artifact exists.** | 3 d |
| **X4** | **Licence remediation, decoupled.** Apply a digest-only design (offsets + digests tracked; `source_text` and annotation content hydrated at runtime from `.corpus-cache` with digest verification) **to the new held-out fixture only**. Add a test that fails if any *new* tracked fixture field contains corpus text. The correct pattern already exists in `corpus_attestation.py`. | Closes **G1** where it matters: growth. Retrofitting v1/v2 would change `fixture.sha256`, which is asserted in `test_evaluation_protocol_preregistration.py:54-56` and pinned in the preregistration, forcing a new protocol version and reopening a sealed artifact — a 5-day job for no reduction in the risk that is actually growing. | 1 d (decoupled) / 5 d (full migration, deferred) |
| **X9** | Reporting: document-level rates, **cluster bootstrap over documents**, per-stratum and per-event-type breakdown, length-stratified breakdown, split-half difference, `SE_reproduce` and `SE_generalize`. Fix `evaluation.py:35-41`, which computes `underpowered_categories` from `scores[0]` only — a per-category power judgment made from one run. | Naive event-level intervals are 2–4× too narrow at ICC 0.2 (§6.2). | 2 d |
| **X8** | Aggregator accepting N reports. `scripts/evaluate_nary_claim_event_matrix.py:30` hard-codes `nargs=6`, which is `_MODELS` (2) × `_RUNS_PER_MODEL = 3` (`evaluation.py:38,43`), and `_RUN_ID_RE = ^tg04-(luna\|sol)-nary-(01\|02\|03)$` (`:48`) hard-codes the run-id grammar. The aggregator is entangled with a 2×3 model-comparison design this experiment abandons. | A replicate study of any other shape has no aggregator. | 1.5 d |
| **X10** | Add V1–V6 to `ARTANA_EVIDENCE_API_TEST_PATHS` and both CI workflows; add a `make tg04-*` target (none exists). | Closes **G3**. | 0.5 d |
| **X12** | *(Diagnostic, optional)* Adapter from the product proposal surface to scoreable events. Feasible: feeding all 53 gold events through the production `bind_claim_inventory_items` bound 44 and reproduced gold trigger and argument offsets exactly on all 44; the 9 failures were 8 polarity-enum rejections (M4) and 1 mention-uniqueness rejection. Target shape already written once at `runner.py:459-521`. | Checks the extraction number survives the framing/binding layer. Does **not** validate entity linking or the graph. | 1 d |

**Total: ~22 engineer-days ≈ 4.5 engineer-weeks** (21 d without X12; +4 d if the full licence migration is taken). X0, X11, X1, X7, X6, X2, X3, X5 are the critical path. X4, X8, X9, X10, X12 can land in parallel.

**Engineering cost dominates provider cost by roughly two orders of magnitude (§8). That is the real budget line.**

---

## 6. Statistics

### 6.1 Three units, three roles

- **Sampling / independence unit = the DOCUMENT.** `DEFAULT_RELATION_EXTRACTION_CHUNK_CHARS = 4000` (`services/artana_evidence_api/document_extraction_support/full_text_chunking.py:9`). All 40 development documents are single-chunk (max 2,357 chars). **7 of the 216 parseable held-out documents exceed the chunk limit (max 20,199 chars)**, giving **229 chunk-runs for 216 documents**. Cost is counted in chunk-runs; independence is at the document.
- **Scoring unit = the EVENT**, within stratum. It is what a reviewer adjudicates and what the gold defines.
- **Argument = diagnostic only.** Reportable, never gating.

### 6.2 Clustering is not optional

Gold events cluster hard inside documents. Measured over the confirmatory set (ranks 71–259):

| Stratum | Events | Documents | Kish mean cluster size | Max in one document |
|---|---|---|---|---|
| A — multi-argument | 264 | 71 | **7.19** | 19 |
| B — single-argument | 1,177 | 159 | **17.49** | 65 |

Design effect `DEFF = 1 + (Kish − 1)·ICC`. At ICC 0.2, DEFF is 2.24 for Stratum A and 4.30 for Stratum B — meaning a naive event-level interval is **1.5×** and **2.1×** too narrow respectively.

Every headline reads **`x / y events across d documents`**, with a document-level cluster bootstrap CI. Treating events as independent trials is the same class of error as counting rows where documents were meant.

### 6.3 Replicates: R = 1 on the main arm, and this is derivable

Two-level model: document *i* has latent per-run success probability `pᵢ`; the estimand is `θ = E[pᵢ]`; `σ²_b = Var(pᵢ)`; the within-document Bernoulli component is `E[pᵢ(1−pᵢ)] = θ(1−θ) − σ²_b`.

```
Var(θ̂) = [ σ²_b + E[p(1−p)]/R ] / N
        = [ σ²_b·(1 − 1/R) + θ(1−θ)/R ] / N        (identical; θ(1−θ) is the MARGINAL variance)
```

Fix the budget in document-runs `B = N·R` and substitute `N = B/R`:

```
Var(θ̂) = [ σ²_b·(R − 1) + θ(1−θ) ] / B            ← strictly increasing in R for all σ²_b ≥ 0
```

**R = 1 is optimal for the corpus mean, at every budget, for every σ²_b.** The intuition: a new document gives a fresh draw of **both** noise sources; a repeat of an old document re-draws only one.

Illustrative, at B = 600 document-runs, θ = 0.80, σ²_b = 0.03 (**placeholder — see below**):

| R | half-width |
|---|---|
| 1 | ±0.032 |
| 3 | ±0.037 |
| 10 | ±0.053 |
| 20 | ±0.068 (2.1× worse for the same money) |

> **σ²_b is unknown to within an order of magnitude, and this plan does not pretend otherwise.** The only variance components we have come from **three** cases on a **different** task (reproducibility of a sealed PASS/FAIL panel verdict on the staged-generalization prompt: 19/20, 17/20, 10/19). A variance estimated from n = 3 has a χ²(2) sampling distribution — a 95% interval spanning roughly [0.27×, 39×] the estimate. Elsewhere this plan argues that n = 10 gives [0.69×, 1.83×] and is too loose to size anything; n = 3 is far worse. The naive estimate is also inflated by within-item sampling noise and must have `E[p(1−p)]/R` subtracted before use. **The R = 1 conclusion does not depend on σ²_b at all — it drops out at R = 1 — so it stands. Every σ²_b-dependent number in this plan is a placeholder until the pilot's stability arm measures it.**

**Per-item pass rate must never be an endpoint.** Pinning one coin-flip document to ±0.10 costs 93 replicates. Replicates exist here only to estimate a variance component and to detect mid-run drift.

### 6.4 Sample size and intervals — the real numbers

The confirmatory set is **ranks 71–259**: 189 documents, of which **3 currently fail to parse** (H1) and are quarantined, leaving **186**. All counts below exclude the 3 and **must be re-derived after X0 lands**.

Composition at `_MIN_EVENT_ARGUMENTS = 1`: **162 `EVENT_GOLD`** documents, **0 `REPRESENTABILITY_STRESS`**, **24 `TRUE_NO_EVENT_CONTROL`**. **199 chunk-runs.**

| | Stratum A (multi-arg) | Stratum B (single-arg) |
|---|---|---|
| Events | 264 | 1,177 |
| Event-bearing documents | 71 | 159 |
| Kish | 7.19 | 17.49 |
| **Document-level** half-width, θ=0.80 | **±0.093** | ±0.062 |
| Document-level, worst case (θ=0.50) | ±0.116 | ±0.078 |
| **Event-level** half-width at θ=0.80, ICC 0.1 / 0.2 / 0.3 | ±0.061 / **±0.072** / ±0.082 | ±0.037 / **±0.047** / ±0.056 |

**Say the uncomfortable thing plainly: the primary endpoint lands at roughly ±0.07 event-level and ±0.09 document-level.** That is a usable interval and a large one. It is honest, and it is what 189 held-out documents buy. For comparison, the status quo — the 53-event development panel — gives ±0.131 at p = 0.85 once clustered at its measured Kish of 5.26 (the commonly-quoted ±0.096 is the unclustered figure and is not defensible).

**The only free route to a tighter interval is more gold documents.** The GE 2011 **train** split (~908 documents) would, at the measured retention rate, yield roughly 4× the events and take Stratum A to about ±0.036 at ICC 0.2. `fetch_bionlp_ge_corpus.py` hardcodes the devel archive only. **Establishing whether the train split is fetchable and licence-compatible is a Phase-0 task (open decision 8), and the preregistration must commit to the resulting N before the run — not after seeing the devel result.**

**Safety endpoint power is weak and must be labelled as such.** 24 zero-gold control documents. Even a flawless result (zero invented events) bounds the invented-event rate only at `3/24 = 0.125` events per document by the rule of three. If the product needs a tighter safety bound, more zero-gold documents must be bought; there is no analytical shortcut.

**Both standard errors get published**, because this is the direct answer to "a single run is never evidence":

- `SE_reproduce = √( E[p(1−p)] / (N·R) )` — how much the headline moves on a re-run of the same documents.
- `SE_generalize = √( σ²_b/N + E[p(1−p)]/(N·R) )` — how much it moves on new documents from the same population.

Note that `SE_reproduce` is bounded above by `√(0.25/N)` regardless of the data, so **a hypothesis stated on `SE_reproduce` at these sample sizes is true by arithmetic and tests nothing.** The stability hypothesis (H3, §6.6) is stated on `SE_generalize`, which contains `σ²_b/N` and can actually fail.

### 6.5 Endpoints

**PRIMARY (one):** *Stratum A (multi-argument) event recall of the held-out gold panel, aggregated at the document level, with a cluster-robust 95% CI, reported subject to a preregistered review-burden cap.*

Recall is primary because the costs are asymmetric and the product makes them so: **a false positive costs a reviewer minutes; a false negative costs the claim entirely, invisibly, with no governance step able to recover it.** A claim never proposed can never be reviewed.

**CO-REPORTED, always, never pooled:** Stratum B (single-argument) event recall, with its own CI.

**Recall is reported three ways, all preregistered** (this is the M1 fix, and it must be committed to in advance so the choice cannot be made after seeing the numbers):
1. over **all** documents, with `SEMANTICALLY_INCOMPLETE` documents contributing whatever they extracted;
2. over `BOUND_OUTPUT` documents only;
3. the **incompleteness rate itself**, as a first-class published number.

**CONSTRAINT, co-reported, not co-primary — review burden.** Defined as **everything a reviewer would have to look at, per document**:

```
burden = matches + structurally_attested_mislabelled + attested_out_of_scope
       + unattested + review_only_events
```

Attestation is the right correction for *precision* (which is about credit) and the wrong correction for *burden* (which is about volume): a mislabelled-but-structurally-real prediction still costs a human the same minute. Reference point: the corpus-faithful extractor in the 2026-07-24 calibration emitted 276 predictions across 17 scored documents = **16.2 predictions/document**. The cap `B_max` **must be declared before the run**. I am not inventing a number: **no reviewer-minutes-per-claim measurement exists anywhere in this repository.** This is a product decision (§10, item 2).

**SAFETY endpoint, separate, one-sided:** invented-event rate on the 24 zero-gold documents, with the power caveat in §6.4.

**Rejected as primary, with reasons.** F1 — averages two quantities with different costs and hides which moved; reportable, never primary. Precision — on this panel it is largely a property of the importer's filter (retention is 11.2–19.2%), and a *perfect-recall* extractor scored 0.1920 under the unfixed denominator. Any PASS/FAIL gate — §1.3. Any pooled A+B recall — §4.2.

*(Correction to the current preregistration, for the amendment: it states only the 17 `EVENT_GOLD` documents are scored, but `scoring.py:214-217` zeroes predictions only for `REPRESENTABILITY_STRESS`, so **22** development documents contribute to the precision denominator. At `_MIN_EVENT_ARGUMENTS = 1` the representability-stress class is empty and the distinction disappears.)*

### 6.6 Preregistration

**Split.** Selection order fixed a priori in code by `sha256(document_id)`. Development = ranks 1–40. **Pilot = ranks 41–70. Confirmatory = ranks 71–259.** The pilot is excluded from the confirmatory denominator so that documents whose outcomes were observed during parameter measurement never enter the confirmatory headline. Record the split digest in the protocol.

**A precise statement of blindness, because the loose one is false.** *The selection order was fixed before any inspection. Aggregate annotation structure of the held-out documents — event counts, type distribution, cluster sizes, document lengths, control counts — was computed and published (Appendix A) before the run, in order to size the experiment. No held-out document text was read, no model was run, and no score was computed on any held-out document.* That is what is true, and it is what the report will say.

**Hypotheses — each stated on a CI *bound*, never a point estimate.**

- **H1 (value).** Lower bound of the 95% cluster-robust CI on **Stratum A** event recall ≥ 0.60, at burden ≤ `B_max`. *(At ±0.072 this requires a point estimate ≥ 0.672. Stated in advance so nobody discovers it afterwards.)*
- **H2 (safety).** Upper bound of the 95% CI on invented events per zero-gold document ≤ `B_safety`. *(With 24 controls, `B_safety` cannot be set below 0.125. If the product needs tighter, buy more controls.)*
- **H3 (stability).** `SE_generalize` of the Stratum A headline ≤ 0.05.

**Stopping rule.** Fixed N. **No interim analysis, no extension, no early stop on the score.** One operational abort: if the provider **error** rate exceeds 5% of calls, stop, publish the error rate, publish nothing else. Errored calls are retried at most twice on byte-identical input; a document still failing is recorded `ERROR`, excluded from the primary denominator with its count published, **and additionally reported as a sensitivity analysis with errored documents counted as failures** — because exclusion is MNAR when the failures correlate with document length (M6).

**Typed transport errors must be separated from scientific failures,** or they get silently scored as failures. This is the discipline that produced an honest `10/19` rather than `10/20` in the noise floor.

**Length stratification is preregistered**, not optional: recall is reported separately for documents ≤ 4,000 chars and > 4,000 chars, so length effects are visible rather than absorbed.

**What would falsify the approach:**
- H1 upper bound < 0.60 → the lane does not recover most expert-annotated multi-argument events; "we surface the evidence" is false as currently stated.
- H2 lower bound > `B_safety` → the system invents claims on empty documents; governed review is a cost multiplier, not a safeguard.
- Burden exceeds `B_max` at any recall → the recall number is unusable regardless of its value.
- σ²_b so large that the confirmatory N cannot bound generalization → conclude **"this configuration is not measurable at this budget."** That is itself a publishable, defensible statement, and a reason to change the **configuration** (self-consistency over k samples, lower-variance decoding), not to buy more calls.
- V1 fails at the run commit → the ruler is broken; no result may be reported.

**Forbidden after unblinding — enumerated, because a vague commitment is no commitment:**
1. Dropping, re-running, or re-scoring any document after seeing its score.
2. Changing the matcher, the precision denominator, the eligibility filter, the arity policy, or any threshold.
3. Reporting best-of-k, max-over-replicates, or any per-document selection among replicates.
4. Switching the primary endpoint, promoting a secondary to primary, or pooling Strata A and B.
5. Reinterpreting the corpus-attestation exclusion rule.
6. Rescoring any sealed historical artifact (already forbidden by the protocol's `governance` block; v1/v2 stay sealed).
7. Any subgroup analysis not named in advance. Named subgroups are labelled exploratory.

**Bound to code**, so a run cannot silently deviate: protocol version, split digest, fixture SHA, matcher name, endpoint definitions, stratum boundary, N, the arity constant, the bootstrap seed, and the split-half seed are all asserted in `tests/unit/test_evaluation_protocol_preregistration.py`.

---

## 7. Two tiers

### 7.1 Tier 1 — Pilot

**Main arm:** ranks 41–70, 30 documents, R = 1. Verified composition at `_MIN_EVENT_ARGUMENTS = 1`: all 30 parse; all 30 single-chunk (max 3,686 chars); **25 `EVENT_GOLD`**, **0 `REPRESENTABILITY_STRESS`**, **5 `TRUE_NO_EVENT_CONTROL`**; **191 retained events (32 Stratum A, 159 Stratum B)**. **30 chunk-runs.**

**Purpose is parameter measurement, not validity.** It measures: actual calls per chunk on our prompts, actual $ per call, per-call latency, provider error rate, σ²_b, `E[p(1−p)]`, observed review burden, the `SEMANTICALLY_INCOMPLETE` rate, and whether checkpoint/resume works under a real failure.

**At 25 event-bearing documents the worst-case document-level half-width is ±0.196.** Far too wide to state publicly. **The preregistration says so up front so nobody quotes it.** Stratum A at n = 32 events is not usable for anything except a smoke test; treat Stratum A pilot recall as diagnostic only.

### 7.2 Tier 2 — Confirmatory

**Main arm:** ranks 71–259, 186 parseable documents (189 after X0 fixes the three parse failures), **199 chunk-runs**, R = 1.

**Split-half, to make the run-level shock estimable.** The 186 documents are split into two disjoint halves by a preregistered seed and run **on different days**. The between-half difference is published alongside `SE_reproduce`. Cost is unchanged (the same 186 document-runs); it converts an unestimable confound into a reported number. Without it, any run-level common shock — the model alias moving mid-run, a provider config change, a throttling episode — is perfectly confounded with the run and contributes exactly zero to the reported SE.

**Stability arm:** 20 documents drawn from the **pilot** range (ranks 41–60), R = 20 = **400 chunk-runs**, **interleaved** into the confirmatory sequence. Drawing them from the pilot range is deliberate: the stability documents are then not in the confirmatory denominator at all, so there is no undeclared 20× weighting and no ambiguity about which replicate feeds the headline. (n = 20 items gives a 95% CI on the between-item SD of roughly [0.76×, 1.46×] the estimate — adequate; n = 10 gives [0.69×, 1.83×], too loose to size anything.) Interleaving is the only available defence against undetectable model-alias drift over a multi-day run.

**Total Tier 2: 599 chunk-runs. Grand total including the pilot: 629 chunk-runs.**

**Expected yield:** Stratum A 264 events over 71 documents; Stratum B 1,177 events over 159 documents; 24 zero-gold safety controls. Intervals as in §6.4.

### 7.3 Go / no-go between the tiers

**Go to Tier 2 only if all of the following hold. The pilot's recall value is explicitly NOT one of them.**

1. **V1 returns exactly 1.0 on all ten gated metrics**, on the held-out fixture, at the exact commit SHA that will execute the full run.
2. V2–V6 all pass at that same SHA.
3. Provider **error** rate < 5% of calls, and **every** error was contained per-document without losing the arm.
4. Checkpoint/resume demonstrated: kill the pilot mid-run, resume, and confirm the resumed report is byte-identical in the completed portion.
5. Measured cost per chunk-run is within **3×** the budget in §8.
6. The stability arm's σ²_b implies **`SE_generalize` ≤ 0.05** at the confirmatory N.
7. Zero unattributable `ERROR` outcomes — typed transport errors cleanly separated from scientific failures.
8. No tracked-file change between the pilot commit and the full-run commit other than parameters the preregistration explicitly permits.

> **If the pilot's recall is used to tune the endpoint, the threshold, the stratum boundary, or the decision to proceed, the full run stops being confirmatory and must be re-preregistered on a fresh split.** This sentence goes into the preregistration verbatim.

---

## 8. Cost and duration — arithmetic shown

**Per-call anchor (measured, but from a different task):** `$0.99479 / 59 costed calls = $0.016861 per call`, `gpt-5.6-luna`. Observed per-call spread in that run: `$0.007036–$0.038722` (5.5×). One of 60 calls errored and carried no cost.

**The anchor is a placeholder with a wide, unsigned error bar.** It was measured at `reasoning_effort = high` on short verification prompts. TG-04 resolves through the model registry, where luna's `default_reasoning_settings` are `effort = "medium"` (`services/artana_evidence_api/artana.toml:127-129`), and its prompts carry up to 4,000 characters of document plus a 15-type / 12-role output schema. **The direction of the error is unknown.** Call it ±5× until the pilot measures it; the pilot's first deliverable is replacing this number.

**Calls per chunk (read off the code, range 2–6, not measured):** 1 inventory call; +1 zero-retry only if the inventory binds empty; +1 completeness review; + up to `MAX_INVENTORY_RECOVERY_ROUNDS = 2` recovery rounds, each costing one recovery call plus one confirmation review (`inventory_convergence.py:33`, `llm_extraction/runner.py:490-556`).

| Stage | chunk-runs | calls/chunk | calls | @ $0.016861 | @ 2× anchor |
|---|---|---|---|---|---|
| Pilot | 30 | 2 | 60 | $1.01 | $2.02 |
| Pilot | 30 | **4** | 120 | **$2.02** | $4.05 |
| Pilot | 30 | 6 | 180 | $3.03 | **$6.07** |
| Tier 2 | 599 | 2 | 1,198 | $20.20 | $40.40 |
| Tier 2 | 599 | **4** | 2,396 | **$40.40** | $80.80 |
| Tier 2 | 599 | 6 | 3,594 | $60.60 | **$121.20** |

- **Base case (4 calls/chunk, anchor price): pilot $2.02 + Tier 2 $40.40 = $42.42.**
- **Worst case on every assumption simultaneously: $6.07 + $121.20 = $127.27.**

For comparison, the noise-floor measurement that produced our only published result cost $0.9948. **The experiment that has never been run is a rounding error. Its absence was never a budget problem — it was an engineering-readiness problem, and it still is.**

**On the tenant budget cap.** `runner.py:423-427` constructs `TenantContext(..., budget_usd_limit=20.0)`. The artana budget is enforced per `run_id` (`artana/middleware/quota.py:21-45`) and `runner.py:238` mints a fresh invocation namespace per case, so the cap is **$20 per document**, not $20 per arm — it does not bind this experiment. **Re-confirm this by code read at the run commit**, and impose an external spend cap regardless.

**Wall clock — serial only.** `runner.py:115-143` is a strictly sequential `for` loop with one kernel and one store. There is no concurrency to enable, and none is budgeted. `wall = calls × latency`. Nothing in the repository records per-call latency (the noise-floor report has no latency field at all), so this is a parameterised table, not a claim:

| | 30 s/call | 60 s/call | 120 s/call |
|---|---|---|---|
| Pilot (120 calls) | 1.0 h | 2.0 h | 4.0 h |
| Tier 2 (2,396 calls) | **20.0 h** | **39.9 h** | **79.9 h** |

**A 20–80 hour unresumable single process is not a runnable experiment.** This is why X7's checkpoint/resume is on the critical path and not an optimisation. X7 also records per-call latency, which permanently closes the gap that makes this table a guess.

---

## 9. Threats to validity

Read this section as the objections a hostile reviewer will raise.

### 9.1 Ways this experiment could produce a number that looks real but is not

1. **Scoring incomplete documents as zero recall.** `runner.py:286` discards every extracted event when a document terminates `SEMANTICALLY_INCOMPLETE` — and the 2026-07-17 pilot says that is the extractor's normal terminal state on this task. The result would be a measurement of the convergence loop wearing the label "recall." *Mitigation: X6 changes the scoring input; recall is preregistered in three forms; the incompleteness rate is published as a first-class number.*
2. **Publishing precision under the unfixed denominator.** Already demonstrated uninformative: a corpus-faithful extractor and a pure hallucinator both scored 0.1920. *Mitigation: X2 on the critical path; V2 gates it.*
3. **Publishing a label-blind precision.** The attestation digest carries no type, polarity, role or epistemic status, so a wrong-polarity prediction vanishes from the denominator and precision reads ≈ 1.0 while the system emits wrong-polarity claims at scale. *Mitigation: the four-bucket accounting, and V6 — flip every gold polarity and require the metric to fall.*
4. **A burden cap that cannot bind.** Defining burden over unattested predictions only makes it identically zero for any non-hallucinating extractor, and — combined with threat 3 — scores every mislabelled-but-structurally-real prediction as free reviewer work. *Mitigation: burden is defined over everything a reviewer sees (§6.5).*
5. **An event-level interval computed as if events were independent.** At the measured Kish values and ICC 0.2, the naive interval is 1.5× too narrow for Stratum A and 2.1× too narrow for Stratum B. *Mitigation: X9, cluster bootstrap over documents, mandatory.*
6. **Pooling the two strata.** ~1,177 largely single-argument events would swamp 264 multi-argument ones and produce a flattering figure that moves for reasons unrelated to the system improving. *Mitigation: no pooled number is published, ever.*
7. **Quoting a development-panel number as validation.** The 40 development documents were used to fix the scorer, repair 7 gold polarity records, and adjudicate the matcher. Any number computed on them is tuned-on. *Mitigation: only ranks 71–259 carry confirmatory weight, and the report states the split.*
8. **Reading recall on a heavily filtered target as recall on the corpus.** Retention at min = 1 is 1,632/2,629 = 62.1% of held-out corpus events; the rest are excluded by the nested-event schema limit and mention-uniqueness. *Mitigation: publish all three denominators and the per-type, per-stratum coverage ledger; name the operative denominator in the headline sentence.*
9. **Length-correlated missingness.** The 60 s adapter timeout against a 900 s registry allowance, on documents up to 20,199 chars. Excluding timed-out documents removes the hardest cases and biases recall upward. *Mitigation: raise the timeout to the registry value before the run; preregister length-stratified reporting; report errors-as-failures as a sensitivity analysis.*
10. **Distribution shift misread as generalization failure.** The held-out Stratum A is Binding-dominated (120 of 264 in the confirmatory set) where the development panel is Positive_regulation-dominated. Scores will move for purely distributional reasons. *Mitigation: pre-commit to per-category reporting with the `underpowered_categories` guard **before** seeing results, and fix that guard to consider all reports rather than `scores[0]`.*
11. **Undetectable model drift mid-run.** `gpt-5.6-luna` has no dated snapshot (`snapshot_pinned = false`) and the provider-returned model id is never read back (issue #206; `known_limits.returned_model_unobserved` in the preregistration). A multi-day run could straddle an alias change with no artifact showing it. *Mitigation: interleave the stability arm; record per-call `response_id` and timestamps; treat a within-run discontinuity in the stability arm as an abort condition. **This is a mitigation, not a fix** — the fix is reading back the returned model id.*
12. **A run-level shock invisible in the reported SE.** `SE_reproduce` contains only the independent per-document component; any common shock is perfectly confounded with the run. *Mitigation: the split-half design (§7.2), which costs nothing extra and turns the confound into a published number.*
13. **Silent scorer regression.** V1–V6 run in no CI or make path today. *Mitigation: X10, plus re-running V1–V6 at the exact run commit SHA.*
14. **Replicates are not exact replays.** Byte-identical replay is impossible: a fresh UUID is injected into the provider prompt per invocation, and the completeness convergence loop is path-dependent. Replicate variance therefore includes prompt nondeterminism. *Measure it as a variance component; do not assume it away.*
15. **Best-of-k across replicates.** Explicitly forbidden; with R = 1 on the main arm the temptation mostly does not arise.

### 9.2 Structural limits that no amount of care removes

- **One corpus, one domain, one language.** English molecular-biology abstracts and PMC sections. Nothing here speaks to clinical text, variant literature, or any other domain the product targets.
- **One model, on a floating alias whose returned identity we do not read back.**
- **One lane.** The offline runner exercises the inventory/completeness/recovery boundary. It does **not** exercise framing, entity linking, CURIE resolution, trust scoring, or graph promotion. X12 extends this by one layer — binding — and no further.
- **Gold standards encode their own annotation guidelines.** BioNLP-GE decides what counts as an event. Disagreement with it is not automatically an error; it can be a legitimately different representation. The 2026-07-18 representation adjudication already recorded an `ACCEPTABLE_ALTERNATE` outcome for exactly this reason.
- **The importer defines the target.** Recall is bounded above by what the crosswalk retained. A high number on a filtered target invites — and deserves — exactly that objection.
- **The safety endpoint is underpowered.** 24 zero-gold controls; a rule-of-three bound of 0.125 events/document is the best attainable result.
- **Licence.** Whether re-serialized event annotations count as annotation content under corpus clause 6 is a **licence question, not an engineering one**. It is flagged here, not resolved. X4 removes the growth exposure regardless of the answer.
- **Some redesign items from the 2026-07-16 controlled stop are not visibly closed.** The abort mechanism was fixed (categorical `BOUND_OUTPUT` / `NO_OUTPUT` / `UNBINDABLE_OUTPUT` outcomes), but mention-level anchoring and repeated-mention handling show no visible closure, and the binder's exactly-once `exact_span` rule was the original root cause. Trace it before assuming a full arm can bind — and note that the rule is mechanically harder to satisfy in a 20,000-character document than in a 2,000-character one.

---

## 10. Open decisions that must be closed before any money is spent

1. **Which layer does "validate the backend" mean?** If it means source-local claim-event extraction, BioNLP-GE is right. If it means the governed graph — normalized entities, 38 relation types, dedup, trust promotion — GE is *structurally incapable* of answering (zero normalization records) and BioRED becomes primary. **This single question can flip the whole plan. It is free to answer and it belongs to the product owner.**
2. **What is `B_max`, the acceptable review burden in predictions per document?** No reviewer-time data exists in the repository. A stopwatch study with one expert and 20 claims costs zero provider dollars and closes it.
3. **Is the modifier composition table in §4.1 accepted?** It is a semantic adjudication and must be reviewed and recorded before the fixture is sealed.
4. **Does a mechanical negation-inheritance rule reproduce all 7 hand adjudications?** If yes, the crosswalk scales and X5's estimate holds. If no, roughly 200 manual adjudications must be budgeted or the panel reduced.
5. **Is the GE 2011 train split (~908 documents) fetchable and licence-compatible?** It is the only free route from ±0.072 to ~±0.036 on the primary endpoint. Decide, and commit N in the preregistration, before the run.
6. **Was the v1 runner pin deliberate or an unfinished follow-up?** `fixture.py:57-59` says moving the gates to v2 "belongs in the evaluation preregistration"; that document now exists and pins v2. This reads as a follow-up that never landed — confirm with the author before assuming X1 is small.
7. **Is `scope_aware_precision` unwired by intent or by oversight?** The module, its tests and the attestation fixture all shipped on 2026-07-25 alongside a preregistration declaring the old definition superseded — yet nothing calls it and it is not exported.
8. **Where do experiment outputs land?** Prediction payloads contain corpus source spans. `docs/validation/results/` holds one file; the noise-floor harness deliberately wrote *outside* the repository. Answer this **before** the run, not after.
9. **Does `ClaimVerificationBudget` (`max_cost_usd = 5.0`) bind the TG-04 runner path?** No reference found under `scripts/validation/claim_events/`. Unresolved, the only real bounds are `MAX_INVENTORY_RECOVERY_ROUNDS = 2` and the per-document $20 tenant cap. Confirm, or impose an external spend cap.

---

## 11. What the result will let us claim — and what it will not

### 11.1 What we will be able to say

> *On 186 held-out BioNLP-ST 2011 GENIA development documents, never scored during development and selected by a content-blind hash order fixed in code before the corpus was read, Artana's production extraction path recovered **R%** (95% CI [a, b], cluster-robust over documents) of **264** expert-annotated **multi-argument** molecular-biology events — requiring the correct trigger span, the exact argument set with correct character offsets, the correct event type, polarity and epistemic status — at a review burden of **K** predictions per document. On the **1,177** single-argument events in the same documents it recovered **S%** (95% CI [c, d]), reported separately and never pooled with the above. On **24** documents containing no annotated events it produced **M** invented events (95% CI upper bound **u**). The matcher, the metric definitions, the endpoints, the stratum boundary and the sample size were fixed in writing on \<date\>, before any model call. Re-running the identical configuration on the same documents moves the headline by **±c** (95%); the two independently-run halves of the corpus differed by **±h**. The scorer was proven to return exactly 1.0 on its own gold standard, on all ten gated metrics, at the exact commit that executed the run.*

Every element of that sentence is a quantity this design produces, with its uncertainty attached.

### 11.2 What we will still not be able to say — and the report must say so

- **Not** "the backend is validated." One lane of it was measured against one gold standard.
- **Not** anything about **entity linking or CURIE resolution**. The corpus has two entity types and zero normalization records.
- **Not** anything about the **38-value relation taxonomy**, cross-document merge, deduplication, trust scoring, or graph promotion.
- **Not** anything about **what a reviewer sees**. The proposal surface drops event type, trigger span and per-argument offsets; scoring it requires reconstructing events from the layer *underneath* the proposal.
- **Not** a claim about **any other model**. One model, on a floating alias, whose returned identity we do not read back.
- **Not** a claim about **any other domain or language**.
- **Not** a claim that we recover *most biomedical claims in the literature*. We recover a measured fraction of a **filtered** expert annotation set, and the filter's retention rate is published alongside the number, or the number is dishonest.
- **Not** a claim of **human-level or better** performance. No human comparator was measured. Inter-annotator agreement on this corpus is a property of the corpus, not of us.
- **Not** a claim about **reviewer time saved**. No reviewer-minutes were measured anywhere in this program.
- **Not** a strong safety claim. 24 controls bound the invention rate at best to 0.125 events/document.

**The scope sentence ships attached to the number, in the same paragraph, in every venue.** Not in a footnote, not in an appendix. That constraint is what makes the number worth publishing at all.

---

## 12. Sequencing

**Phase 0 — free, no provider spend. One engineer-day of it can start immediately.**

*Day one, all read-only, all free:*
1. Recover the noise-floor harness: `git worktree add` at `refs/tags/archive/alvaro/tg04-source-general-claim-verification-v17` and land it on a branch **before the archive tags are ever pruned**.
2. Fetch and verify the corpus (works today; I ran it).
3. Answer open decision 1 (extraction lane vs. governed graph). It is free, it belongs to the product owner, and it can invalidate everything else.
4. Write the modifier composition adjudication (§4.1) — one decision that closes both H1 and M4.
5. Extend `_GATED_METRICS` to all ten and repoint at the fixture that will be run (X11) — half a day, and it converts this plan's central promise from an assertion into a test.

*Then, in order:*
6. Land X0, X1, X7, X6, X2, X3, X5, X4 (decoupled), X9, X10.
7. Regenerate every count in §6 and Appendix A from the real importer after X0, with the three currently-quarantined documents restored.
8. Build the held-out fixture over ranks 71–259 at `_MIN_EVENT_ARGUMENTS = 1`; seal its SHA.
9. Run V1–V6. **All six must pass at the run commit SHA. If V1 is not exactly 1.0 on all ten metrics, stop and spend nothing.**
10. Write and seal the preregistration (§6.6). Bind protocol version, split digest, fixture SHA, matcher name, endpoint definitions, stratum boundary, N, arity constant, bootstrap seed and split-half seed to constants in `tests/unit/test_evaluation_protocol_preregistration.py`.

**Phase 1 — pilot (§7.1). Phase gate (§7.3). Phase 2 — confirmatory run (§7.2), two half-passes on different days.**

**Phase 3 — report.** Per-stratum cluster-bootstrapped intervals; per-event-type breakdown with underpowered categories named; recall in all three preregistered forms plus the incompleteness rate; length-stratified breakdown; retention denominators; provider error rate; the errors-as-failures sensitivity analysis; the split-half difference; `SE_reproduce` and `SE_generalize`; and the scope sentence attached to every number.

---

## Appendix A — Verified facts

All computed read-only, at zero provider cost, using the **real importer** (`scripts/validation/claim_events/bionlp_import.py`) against the digest-verified corpus fetched into a scratch directory. **No file in the repository was modified.** Reproduce with:

```
cd <repository checkout>
set -a; . .env.postgres; set +a
export PYTHONPATH="$PWD/services"
venv/bin/python3 <scratch>/final_counts.py
venv/bin/python3 <scratch>/strata.py
venv/bin/python3 <scratch>/final_chunks.py
```

**Corpus.** 259 documents; archive SHA-256 `f70e5f6d…a890f` verifies clean. Text-bound annotation types across the split: `Protein` 4,526, `Entity` 179 (both mapped by the crosswalk), plus event-trigger types. **Zero `N` (normalization) lines** across all `.a1`/`.a2` files.

**Selection reproduces exactly.** `select_document_ids(root, count=259)[:40]` equals the fixture's `metadata.selected_document_ids` verbatim.

**Development panel (ranks 1–40), V4 archive round-trip — reconciles exactly.** `corpus_events = 472`, `retained = 53` at min-args = 2, exclusions `{insufficient_direct_arguments: 237, nested_event_argument: 174, repeated_argument_mention: 6, repeated_trigger_mention: 2}` = 419. 53 + 419 = 472. Case classes: 17 `EVENT_GOLD`, 18 `REPRESENTABILITY_STRESS`, 5 `TRUE_NO_EVENT_CONTROL`. Kish 5.26, max 10 events in one document. All 40 single-chunk, max 2,357 chars. At min-args = 1: 284 retained, 35 `EVENT_GOLD`, 0 stress, Kish 12.07.

**Parse failures.** Exactly **3** held-out documents raise `ValueError: event has multiple modifiers` (`E62`, `E9`, `E10` in their respective files). No development document does. All counts below exclude them.

**Held-out, ranks 41–259 (216 parseable of 219).** 2,629 corpus events. 229 chunk-runs; 7 documents exceed 4,000 chars; max 20,199 chars. 29 `TRUE_NO_EVENT_CONTROL`.

| | min-args = 2 | min-args = 1 |
|---|---|---|
| Retained events | 296 | 1,632 |
| `EVENT_GOLD` docs | 85 | 187 |
| `REPRESENTABILITY_STRESS` docs | 102 | 0 |
| Kish | 6.73 | 19.49 |
| Event types with zero coverage | 3 of 9 | 0 of 9 |

**Pilot, ranks 41–70 (30 documents, all parse, all single-chunk, max 3,686 chars).** 294 corpus events; 30 chunk-runs; 5 `TRUE_NO_EVENT_CONTROL`. At min-args = 1: 191 retained (32 Stratum A over 14 docs, Kish 2.94; 159 Stratum B over 25 docs, Kish 11.01), 25 `EVENT_GOLD`, 0 stress. At min-args = 2: 32 retained, 14 `EVENT_GOLD`, 11 stress.

**Confirmatory, ranks 71–259 (186 parseable of 189).** 199 chunk-runs; 7 documents exceed 4,000 chars. At min-args = 1: 1,441 retained events, 162 `EVENT_GOLD`, 0 stress, 24 `TRUE_NO_EVENT_CONTROL`.

| Stratum | Events | Docs | Kish | Max/doc | Type composition |
|---|---|---|---|---|---|
| A (≥2 args) | 264 | 71 | 7.19 | 19 | BINDING 120, POSITIVE_REGULATION 68, REGULATION 20, PHOSPHORYLATION 20, LOCALIZATION 19, NEGATIVE_REGULATION 17 |
| B (1 arg) | 1,177 | 159 | 17.49 | 65 | EXPRESSION 509, NEGATIVE_REGULATION 155, POSITIVE_REGULATION 150, TRANSCRIPTION 110, BINDING 106, PHOSPHORYLATION 58, REGULATION 46, LOCALIZATION 26, DEGRADATION 17 |

**Confidence half-widths** (`1.96·√(θ(1−θ)/n · [1+(Kish−1)·ICC])`), θ = 0.80 unless stated:

- Document-level: Stratum A, 71 docs → **±0.093** (worst case, θ=0.5: ±0.116). Stratum B, 159 docs → ±0.062 (worst case ±0.078). Pilot, 25 docs → ±0.157 (worst case ±0.196).
- Event-level at ICC 0.1 / 0.2 / 0.3: Stratum A (n=264, Kish 7.19) → ±0.061 / **±0.072** / ±0.082. Stratum B (n=1,177, Kish 17.49) → ±0.037 / **±0.047** / ±0.056.
- Status quo for comparison: development panel n = 53, Kish 5.26, at p = 0.85 → **±0.131** clustered at ICC 0.2 (the unclustered ±0.096 is not defensible).

**Cost arithmetic.** `$0.99479 / 59 = $0.016861` per call, spread `$0.007036–$0.038722`. Pilot 30 chunk-runs; Tier 2 599 chunk-runs (199 main + 400 stability). At 4 calls/chunk: `120 × 0.016861 = $2.02` and `2,396 × 0.016861 = $40.40`; base total **$42.42**, worst case (6 calls/chunk at 2× anchor) **$127.27**.

**Working files (none in the repository):** `<scratch>/final_counts.py`, `<scratch>/strata.py`, `<scratch>/final_chunks.py`, `<scratch>/rv_holdout.py`, and the verified corpus under `<scratch>/corpus/`, where `<scratch>` is `/private/tmp/claude-501/-Users-alvaro-Documents-Code-artana-evidence-platform--claude-worktrees-reviewer-surface-pt1-d0c60c/d52d5201-71b0-48a1-ada7-77c00bbab4af/scratchpad`.