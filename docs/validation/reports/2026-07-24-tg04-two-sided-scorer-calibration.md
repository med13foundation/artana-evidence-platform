# TG-04 Two-Sided Scorer Calibration

**Date:** 2026-07-24
**Fixture:** `scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json`
**Provider calls:** none
**Standing tests:** `tests/unit/test_gold_as_predictions_calibration.py`

Delivers **V1** from the direction adjustment ("gold-as-predictions calibration"), plus its inverse. Two
runs against the same scorer separate three failure modes that were previously tangled: a broken scorer, a
miscut fixture, and a miscut gate.

---

## Result

| Run | Predictions fed in | Whole-event precision | Whole-event recall | Gate |
|---|---|---:|---:|---|
| **A** — gold-as-predictions | the 53 gold events | 1.0000 (53/53) | 1.0000 (53/53) | **PASS** |
| **B** — corpus-faithful | gold + the 223 corpus events the importer dropped | 0.1920 (53/276) | 1.0000 (53/53) | **FAIL** |

Run A passes **only after a one-line repair** (below). Before it, every whole-event metric was pinned at
zero.

---

## Run A found a real defect: V1 could not have passed

Feeding the gold records back as predictions originally produced:

```
whole_event_precision  0.0000  (0/53)
whole_event_recall     0.0000  (0/53)
trigger_precision      1.0000  (53/53)     <- triggers matched perfectly
trigger_recall         1.0000  (53/53)
```

Triggers matched; **no whole event did.** The cause is a field-name asymmetry in the two key builders:

| Side | Function | Reads | Gets |
|---|---|---|---|
| gold | `_gold_argument_key` | `argument.role` | `"GENE_OR_PROTEIN"` |
| prediction | `_argument_key` | `argument.get("role")` | `None` → `""` |

The gold **object** exposes a convenience `.role` alias, but the gold **JSON** serializes
`participant_role` (`bionlp_import.py:480`). So every argument key differed in its first slot and no
whole-event key could ever match.

**Fix** (`scoring.py`, `_argument_key`):

```python
_string(argument.get("role") or argument.get("participant_role")) or "",
```

With it, Run A goes to 1.0 on all four gated metrics.

### Scope of this defect — important

**Live TG-04 scoring was not broken by this.** The inventory schema the model fills emits `role`
(`ClaimInventoryArgument.model_json_schema()` → `['role', 'event_role', 'exact_span', ...]`), matching
what the scorer reads. The defect is confined to payloads using the fixture's own serialization:

- the V1 calibration itself — i.e. the Gate 1 check the direction adjustment mandates
- `finite_source_unit/representation_service.py:212`, which emits `participant_role`

Two prediction producers disagree with each other today: `service.py:429` and
`controlled_event_trial/runner.py:341` emit `role`; `representation_service.py:212` emits
`participant_role`. The fix makes the scorer tolerant of both, but the underlying schema inconsistency is
worth resolving deliberately.

**What this does establish:** V1 has almost certainly never been run. Anyone who ran it would have hit
`0/53` immediately.

---

## Run B confirms the precision gate is miscut

A simulated extractor that returns the gold events **plus** the corpus events the importer dropped from the
same documents:

```
whole_event_recall     1.0000  (53/53)     <- found every gold event
whole_event_precision  0.1920  (53/276)    <- gate requires >= 0.90
GATE PASSES: False
```

**An extractor with perfect recall is rejected**, purely for also reporting real corpus annotations that
the importer filtered out. `whole_event_precision` divides by every prediction
(`scoring.py:382`), unrestricted to gold-covered spans, against a 0.90 gate (`evaluation.py:215`).

The extra predictions are placeholders: only their **count** affects precision, since the denominator
counts predictions regardless of their relationship to the corpus. That is itself the finding.

This is a property of the panel, not of any model. It cannot be fixed by prompting.

---

## What the two runs together establish

1. **The scorer is sound.** Given gold, it returns a perfect score. The matching machinery works.
2. **The calibration path was broken** by a field-name asymmetry, and is now fixed and pinned by a test.
3. **The panel is miscut independently of the scorer.** Recall is measurable; precision is not, because a
   corpus-faithful extractor is scored as ~81% false positives.

Read with the [exclusion ledger](2026-07-24-tg04-gold-importer-exclusion-ledger.md), the picture is that
the TG-04 stall was never primarily a model-quality problem.

---

## Recommended next decisions

1. **Repair the precision denominator** — restrict it to gold-covered spans, or score only events the
   importer would have retained. Until then, no precision threshold on this fixture is meaningful.
2. **Resolve the `role` / `participant_role` schema inconsistency** at the source rather than relying on
   the scorer's tolerance.
3. **Keep V1 as a standing gate.** It is now a unit test with no provider dependency; it should run in CI
   on every change to the scoring lane.
4. **Then decide whether TG-04 is the right target at all.** It is a nine-type event benchmark; the Phase 2
   pilot scope is binary gene relations. Repairing it fully may be substantial work on a target that does
   not match the pilot.
