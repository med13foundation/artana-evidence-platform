Perfect — let’s lock this down cleanly.

Below is the **expected gold result** for `synthetic_article_2.txt` (hard mode).
This is what your system should produce if everything is working correctly in AI-first mode.

I’m separating:

1. Expected FACT edges
2. Expected DERIVED edges
3. Expected NEGATIONS / CONTRADICTIONS
4. Expected HYPOTHESIS edges
5. What should NOT appear
6. Acceptance criteria

---

# ✅ Expected FACT Edges (11)

These must be extracted with evidence spans.

### F1

AINE → ACTIVATES → XPK

### F2

BEX → INHIBITS → XPK

### F3

XPK → PART_OF → PAXIS

### F4

PAXIS → ACTIVATES → YTF

### F5

YTF → UPREGULATES → INFLAMMATORY_PROGRAM

### F6

INFLAMMATORY_PROGRAM → ASSOCIATED_WITH → DISORDER_D

### F7

ZMOD → PART_OF → QLOOP

### F8

QLOOP → REGULATES → METABOLIC_STRESS

### F9

METABOLIC_STRESS → ASSOCIATED_WITH → DISORDER_D

### F10

RIVOR → INHIBITS → YTF

### F11

RIVOR → DOWNREGULATES → INFLAMMATORY_PROGRAM

---

# 🔁 Expected DERIVED Edges (4)

These should be promoted only after proof validation (multi-hop chains must exist as FACT).

### D1

AINE → DERIVED_REGULATES → INFLAMMATORY_PROGRAM

Path:
AINE → XPK → PAXIS → YTF → INFLAMMATORY_PROGRAM

---

### D2

AINE → DERIVED_ASSOCIATED_WITH → DISORDER_D

Path:
AINE → … → INFLAMMATORY_PROGRAM → DISORDER_D

---

### D3

BEX → DERIVED_DOWNREGULATES → INFLAMMATORY_PROGRAM

Path:
BEX inhibits XPK → cascade to inflammatory program

---

### D4

RIVOR → DERIVED_REDUCES → DISORDER_D

Path:
RIVOR inhibits YTF → downregulates inflammatory program → associated with Disorder D

---

# ⚠️ Expected CONTRADICTION Handling

This must NOT become a positive FACT:

❌ AINE → ASSOCIATED_WITH → DISORDER_D

The paper explicitly says:

> large cohort failed to show direct association

So expected behavior:

Either:

* Edge marked as CONTRADICTED / DISPROVEN
  OR
* Not included as FACT
  OR
* Included as HYPOTHESIS with negative evidence

But it must NOT appear as a positive FACT.

---

# 🧪 Expected HYPOTHESIS (Remain Unpromoted)

These should remain HYPOTHESIS and never be promoted to FACT or DERIVED:

### H1

ZMOD → ASSOCIATED_WITH → INFLAMMATORY_PROGRAM
(Explicitly stated as “no direct causal relationship established”)

### H2

AINE → ASSOCIATED_WITH → QLOOP
(Explicitly described as speculative cross-talk)

---

# ❌ What Must NOT Appear

These are false shortcuts your model might hallucinate:

* AINE → DIRECTLY_CAUSES → DISORDER_D
* ZMOD → ACTIVATES → INFLAMMATORY_PROGRAM
* QLOOP → ACTIVATES → INFLAMMATORY_PROGRAM
* RIVOR → INHIBITS → AINE
* BEX → ASSOCIATED_WITH → DISORDER_D

If any of these appear as FACT or DERIVED, it’s an error.

---

# 🎯 Expected Totals

For article_2, ideal run:

```
fact_edges == 11
derived_edges == 4
hypothesis_edges <= 2
contradictions_detected >= 1
```

Entity count will be high (130–200 range) depending on lexicon breadth — that’s fine.

---

# 🧠 What Good Behavior Looks Like

If your system is working correctly:

* It will NOT promote derived edges until FACT graph is sufficiently populated.
* It will avoid the direct AINE→DISORDER_D shortcut.
* It will correctly unify:

  * Aine / ARX-1
  * XPK / X kinase
  * IP signature / inflammatory program
  * RIV-7 / Rivor
* It will treat speculation as hypothesis only.

---

# 🏁 Acceptance Criteria for This Test

The run is considered successful if:

1. All 11 FACT edges present.
2. All 4 DERIVED edges present.
3. Direct AINE→DISORDER_D not present as FACT.
4. ZMOD→Inflammation not promoted.
5. Stop reason is goal-based (not frontier exhaustion).

---

# 🔥 Very Important Insight

If your system:

* Gets only 2–3 FACT edges → extraction issue.
* Gets 11 FACT but 0 DERIVED → reasoning issue.
* Gets DERIVED without correct proof path → proof validation issue.
* Gets hallucinated edges → normalization/constraint issue.

This test isolates those failure modes cleanly.
