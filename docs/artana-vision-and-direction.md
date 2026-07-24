# Artana: Vision and Direction

**Building the infrastructure for governed scientific knowledge**

**Version:** 2.0
**Date:** July 24, 2026
**Status:** Authoritative framing. Supersedes the framing of the v1.0 Direction Adjustment; preserves and references its technical detail.
**Audience:** Everyone building Artana — engineering, curation, evaluation, product.

---

## Read this first

Version 1.0 of this document was a repair plan. It was technically correct and it is still the reference for *what* to change. But it described a system by its defects, and people do not build well from a defect list.

This version puts the defects where they belong — in a time-boxed recovery track — and spends its length on the thing that actually needs to be shared: **what Artana becomes, and why each change is a step toward it.**

---

## 1. What we are building

> **Artana is infrastructure that turns machine reading into governed scientific knowledge — where every claim is traceable to an exact source, preserved with the context that makes it meaningful, aggregated only under explicit and versioned rules, and accountable to named human judgment.**

Most "AI for science" systems are extraction pipelines with a database attached. They turn papers into triples and their ceiling is extraction accuracy. When they are wrong, you cannot tell why. When they disagree with themselves, they silently pick a winner. When the model improves, the old conclusions quietly become incomparable.

We are building the other thing: the layer that makes a fast, broad, fallible reader **useful and accountable at scale**.

### The central conviction

**LLMs propose. The system governs.**

The language model is the *reading* layer — fast, broad, tireless, and wrong often enough that its output can never be authoritative on its own. The system around it is the *knowing* layer — slower, narrower, and accountable.

Conflating those two is the defining failure mode of this product category. Artana's bet is that the durable value is not a better extractor. It is the governance substrate that makes an imperfect reader trustworthy: exact custody of sources, preserved context, explicit merge rules, server-owned verification, and human judgment recorded as a first-class asset.

A better extractor makes that substrate more productive. It cannot substitute for it.

### What changes for a scientist

Today, the state of the art is a better search result:

> *Here are 40 papers matching "SLC12A3 hypertension."*

You then read them, hold the contradictions in your head, and lose that work when you close the tab.

What Artana is for:

> *Here is what is claimed about SLC12A3 and blood pressure regulation: 12 assertions drawn from 9 distinct documents. Three disagree about direction of effect. Two are limited to mouse models. One rests on a paper that was later retracted. Here is the exact sentence behind each one. Here is who reviewed which, and when. Nothing here was merged by wording similarity.*

The difference is not summarization quality. It is that the second answer is **auditable, contextual, and cumulative** — and that a reviewer's judgment on it persists and compounds.

---

## 2. The three layers, and why they exist

The v1.0 document specifies three persisted layers. They can read as data-modeling pedantry. They are not — each one buys a specific capability we cannot get any other way.

### SourceOccurrence — *makes every claim permanently auditable*

The exact, immutable place a source said something: snapshot, locator, offsets, quote, anchors.

**Why it exists:** a conclusion you cannot trace back to a specific sentence is a conclusion you cannot defend, correct, or retract. Occurrence-level custody is what lets Artana answer "why do you believe that?" in one hop, years later, after the model, the prompt, and the schema have all changed.

### EvidenceAssertion — *preserves the context that makes a finding true*

What a source claims at that occurrence: participants, roles, polarity, uncertainty, population, comparator, setting, timeframe.

**Why it exists:** "X activates Y" is not a scientific fact. "X activates Y in mouse hippocampal neurons, in the presence of Z, per a 2019 in-vitro study" is. Systems that flatten the first into the second are not simplifying — they are **manufacturing false claims**. Every knowledge base that has become untrustworthy got there by discarding qualifiers. The assertion layer is where we refuse to.

### CanonicalProposition — *the surface you reason over, derived and never authoritative*

The normalized proposition many assertions may support, refine, limit, or contradict.

**Why it exists:** you need something to aggregate, count, and reason over. But it is a *projection*. Because it is derived from versioned keys rather than being the source of truth, we can re-derive it under a better policy tomorrow without losing a single underlying observation.

### The property that makes this infrastructure rather than a schema

**Versioned identity lets us change our mind without losing history.**

Merge rules, assertion keys, and proposition keys all carry versions. When we learn that a merge policy was too aggressive, we write a new version and re-derive — we do not migrate away our past, and we do not silently reinterpret records that were created under different rules. That single property is the difference between a database that ages badly and infrastructure that compounds.

---

## 3. Where extraction quality fits

Extraction quality matters. It is also **a floor, not a ceiling**, and treating it as the headline metric has been costing us.

- A *perfect* extractor with no governance produces an ungovernable pile: unattributable, uncontextualized, unmergeable, and impossible to correct.
- A *mediocre* extractor with strong governance produces a useful system that improves monotonically — because every error is traceable, attributable, and fixable in place.

The asymmetry is decisive. Governance capability is the multiplier on extraction quality, not the other way around.

This is why we are stopping the sequential prompt-repair series (V6→V18) — **not** because extraction quality is unimportant, but because:

- each version is a single sample per case (n=1), on a model already measured as run-to-run unstable in this repo (the one replicate study we ran returned `repeatability proof: FAIL`, 7 unstable records);
- the panel it optimizes against sits outside the pilot scope, so even a clean sweep would unblock nothing;
- and it consumes the attention that the substrate work needs.

Extraction improves continuously, in the background, measured against a ruler we trust. It does not get to be the roadmap.

**Corollary for how we talk about progress:** we do not report extraction scores as product progress. We report traceability, context preservation, review throughput, and disagreement surfaced. Those are the things the vision is made of.

---

## 4. Three parallel tracks

The work runs as three tracks that move together. Each has a different question it is answering, and no track's success substitutes for another's.

| Track | The question it answers | Failure if run alone |
|---|---|---|
| **Architecture** | Can the system *represent* governed knowledge? | A beautiful model nobody uses and nothing validates |
| **Validation** | Can we *believe* what it tells us? | A trustworthy ruler measuring a system nobody wants |
| **Product** | Is any of this *usable for real work*? | Shipping usable software over an untrustworthy substrate |

### Track A — Architecture: build the substrate

Persist the three layers. Make identifiers the join key. Make support verification server-owned. Keep human decisions attributed and immutable. Detail in v1.0 §4, §5, Phase 0 and Phase 2.

### Track B — Validation: prove the ruler before trusting the numbers

Calibrate the scorer, publish what the importer excludes, preregister thresholds, measure run-to-run noise. Detail in v1.0 Phase 1 and Phase 4.

### Track C — Product: keep real workflows in view *(new)*

Deliberately lightweight. Its job is not to ship polish — it is to prevent the other two tracks from drifting away from anything a person would actually use.

**The rule:** *at every phase, one real workflow must be usable end-to-end by a real person.* If no one can use it, we have built a specification, not a product.

- **PT-1 (weeks 1–4) — The reviewer surface.** The review queue is our first product, and reviewers are our first users. Minimal but genuinely usable: show the exact occurrence, the structured assertion, the verification result, and the proposed proposition together, and record a real decision with a real identity. No redesign — one honest screen.
- **PT-2 (weeks 4–8) — "What do we know about X."** A read path over the pilot slice that answers a real question with traceable evidence. This is the first time the vision is visible to someone who is not building it.
- **PT-3 (weeks 8–12) — The disagreement view.** Surface contradictions rather than resolving them. This is the capability no competing system has, and it falls out of the assertion layer almost for free.
- **Cadence — weekly dogfood.** One real scientific question, asked against the real system, by someone who wants the answer. Log every place it fails. That log prioritizes the following week across all three tracks.

**Explicitly not now:** broad reviewer UI redesign, general read/assembler layers, public-facing surfaces. Those wait until the data contract settles (v1.0 §14).

---

## 5. Short-term recovery (the next two weeks)

This is the part that *is* about fixing today's system. It is time-boxed, it is nearly all wiring rather than building, and every item below states the long-term capability it unlocks — because that is the only reason any of it is worth doing.

### We are further along than the audit implies

The most useful finding from verification: **the substrate is largely built. It is not connected.**

| Capability we need | Already exists | Status |
|---|---|---|
| Replicate runs + instability gate | PR6 repeatability harness | Unwired from the extraction lane |
| Assert returned model == requested | `provider_receipt_boundary/identity.py` | Unwired from production |
| Deterministic request key | `llm_fulltext_extraction.py:135-161` | Dead code, zero callers |
| Identifier-first entity resolution | `entity_repository.py:661-677` | Not reached by extraction |
| Repeated-mention binder + anchors | Landed in #162 | **Done and working** |

That reframes the next two weeks: mostly connecting proven parts, not inventing new ones.

### Week 1 — no provider calls, no API key required

| Work | Unlocks |
|---|---|
| Derive `invocation_id` instead of minting a UUID into the prompt (`structured_step.py:71`) | **Reproducibility.** Today the persisted prompt hash differs on every run of identical input — we cannot prove two runs sent the same request. One line stabilizes the prompt hash, stabilizes `run_id`, and makes the kernel's existing replay actually hit. Three tickets, one change. |
| Publish the importer exclusion ledger | **Honest measurement.** The gold fixture retains 53 of 472 events (11.2%), excluding all nested and multi-argument events. Every score to date is over an easy subset. The counts already exist; publishing them costs nothing and changes how we read every historical number. |
| Add `claim_events/` + `public_gold/` to CI triggers; wire staged tests into coverage | **Governance that holds.** A PR lowering a qualification floor currently plans no CI jobs and passes. Versioned thresholds mean nothing if they are unenforced. |
| Build V1 gold-as-predictions | **A ruler we trust.** Feed gold back as predictions; if any gated metric ≠ 1.0, the scorer is miscut and no score is interpretable. Zero provider calls. |

### Weeks 1–2, parallel — information integrity

Ordered by consequence, per verification (this revises v1.0 §13):

1. **ART-VAL-006** — server-owned support semantics. *(The v1.0 doc calls this endpoint "advisory." It is not: its verdict is persisted onto the claim and gates claim resolution, which triggers graph materialization. An authorization-relevant field is currently derived from unverified caller metadata.)* → **Unlocks:** trustworthy promotion, and eventually opening the quarantine for the pilot.
2. **ART-DATA-001** — preserve collisions. *(Retarget: the silent drop is in the production store `sqlalchemy_stores.py:704-717`, not the in-memory `proposal_store.py` the v1.0 doc cites. Six callers do not compensate.)* → **Unlocks:** the "no silent loss" invariant the whole model rests on.
3. **ART-GOV-002** — stop discarding `reviewed_by`. → **Unlocks:** human judgment as a durable, attributable asset.
4. **ART-DATA-003** — count distinct documents. → **Unlocks:** honest evidence strength. *(Note: auto-promotion already counts source families correctly — the promotion decision is sound; the reported counts are not.)*
5. **ART-MODEL-004** — pinned-snapshot profile. → **Unlocks:** comparable results across time. *(Note: no dated snapshot exists in the registry today, and the extraction lane runs `gpt-5.6-luna`, not the model v1.0 §D8 names. Resolve before implementing.)*

### Then — one decision, roughly one dollar

Run the sealed V17 prompt ten times on its three cases and measure the flip rate. If identical prompts produce different verdicts, the V6→V18 series measured noise and retires. If it fails identically ten times, its hypothesis is real and worth one run. Either answer is worth more than another version.

**Struck from the v1.0 backlog:** ART-EVAL-011 (binder repair) — already landed in #162 with full regressions.

---

## 6. The road after recovery

Each phase below is named for the capability it delivers, not the work it contains. Technical detail remains in v1.0 Phases 2–5.

**Phase 2 — "One thing, done completely."** A narrow vertical slice (PubMed abstracts, HGNC-grounded human genes, `ACTIVATES`/`INHIBITS`) running end to end: occurrence → assertion → receipt → human review → proposition. Narrow on purpose. The goal is not coverage; it is proving the object boundaries hold under real data. First moment the vision is demonstrable.

**Phase 3 — "It scales past the demo."** Generalize layered identity, migrate existing data additively, dual-write and shadow-compare. The unglamorous phase that decides whether this is a prototype or a platform.

**Phase 4 — "We can prove it works."** Sealed held-out evaluation, measured noise floor, replay. The point at which quality claims stop being assertions and become evidence.

**Phase 5 — "It compounds."** More entity types, more relation families, disease-level synthesis, contradiction maps. Every addition inherits the governance guarantees instead of relitigating them — which is the entire return on the preceding work.

---

## 7. How we know we are winning

Defect counters (`proposal_collision_dropped_total = 0`, `human_review_missing_actor_total = 0`) stay in v1.0 §10.7. They are floors — necessary, and not the point.

These are the measures that describe the vision:

| Measure | Why it is the right thing to watch |
|---|---|
| % of graph claims traceable to an exact occurrence | Target 100%. Below that, we cannot defend our own output. |
| % of propositions backed by >1 distinct document | Corroboration is the product. |
| Count of `DISPUTED` propositions surfaced | **Should be greater than zero.** A system that never finds disagreement is not reading carefully. |
| Reviewer decisions recorded with attribution | Human judgment accumulating as an asset. |
| Time from ingestion to reviewable item | Whether the loop is fast enough for real work. |
| Assertions per proposition | Evidence pooling actually happening, rather than fragmenting. |

Extraction scores are reported alongside these as an input — never as the headline.

---

## 8. What we will not do

Carried forward from v1.0 §14, restated as commitments rather than restrictions:

- **We will not let a machine's judgment wear a human's name.** Automated qualification and human acceptance stay separate, permanently.
- **We will not merge on wording.** Identity comes from authorities and versioned keys. An LLM may propose merge candidates; it never adjudicates them.
- **We will not treat a quote as proof.** Text custody and entailment are different claims, verified separately.
- **We will not claim quality from the development set.** Development experiments guide engineering. Only sealed held-out evaluation is evidence.
- **We will not open broad AI persistence before the gates pass.** Fail-closed stays the default outside explicitly approved pilot spaces.

---

## 9. The one-paragraph version

Artana is building the layer that makes machine reading trustworthy: exact source custody so every claim can be audited, preserved context so findings stay true, explicit and versioned merge rules so knowledge can be re-derived rather than migrated away, server-owned verification so support cannot be forged, and attributed human review so judgment compounds. LLMs read; the system governs. The next two weeks reconnect proven parts and prove our measurements. Everything after that is about making the thing that reads the literature into the thing that knows what the literature says — and can show its work.

---

## Appendix — Relationship to v1.0

v1.0 remains the technical reference for the data model (§4), identity and merge rules (§5), state semantics (§6), invariants (§7), migration method (§12), and gates (§11). This document supersedes its framing, its §13 backlog ordering, and its §2 emphasis. Verified corrections to v1.0 — the retargeted collision anchor, the already-complete binder ticket, the non-advisory validation endpoint, the dead-code step key, the absent dated snapshot, and the importer's exclusion rate — are folded into §5 above and should be applied to v1.0's ticket text before implementation begins.
