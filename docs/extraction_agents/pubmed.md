Status: Postgres-first

This extraction template supports the current Postgres-backed graph schema. References to TypeDB below are retained as a future migration guide, not the active implementation path.

Perfect — you want a **universal extraction template** that works for *any* biomedical paper, not just for MED13 and not just the example I gave.

Below I will give you the **official extraction framework** used by:

* Rare disease curation groups
* ClinGen
* DECIPHER
* OMIM
* Orphanet
* CZI Biohub
* Recursion Pharmaceuticals
* Academic KG builders

And I’ll show you how to convert this template into **graph facts** stored in Postgres today, with TypeDB conversion as a future option.

This will be your “Paper Extraction SOP” for your world model.

---

- ✅ Application services (data discovery, audit trail, evidence, publication, authorization, gene, variant) now avoid `Any` in favor of the TypedDict/Protocol patterns described in `docs/type_examples.md`, advancing the "never Any" initiative.

  3. ✅ Remaining `Any` usages in routes/tests now rely on the TypedDict/Protocol patterns outlined in `docs/type_examples.md`, preserving the “never Any” requirement.
# 📘 **UNIVERSAL BIOMEDICAL PAPER EXTRACTION TEMPLATE**

*(works for MED13, MED13L, TBCK, TBP, RASopathies, epilepsy genes, etc.)*

Every paper—case study, mechanistic paper, review—can be distilled into **7 standard categories of knowledge**.

This is exactly the structure your Postgres-backed graph schema supports.

---

# 🧩 **CATEGORY 1 — Study Metadata (Always Extract)**

These fields help you track and cite evidence.

### **Extract:**

* Title
* Authors
* Year
* Journal
* PubMed ID
* DOI
* Abstract (optional)
* Study type (case report, cohort, mechanistic, review)

### **Why:**

The graph schema needs publication nodes + evidence linking.

---

# 🧬 **CATEGORY 2 — Gene-Level Information**

### Extract:

* Gene(s) discussed
* Gene function if mentioned
* Protein complex info (e.g., Mediator complex)
* Known pathways mentioned
* Animal model findings (optional, but useful)

### **Why:**

The graph schema stores genes, proteins, pathways.

---

# 🧬 **CATEGORY 3 — Variant Extraction Template**

For *each* variant reported in the paper:

### Extract:

* HGVS notation (DNA + protein)
* Genomic coordinates
* Variant type (missense, nonsense, LOF, frameshift)
* Zygosity (heterozygous, homozygous)
* De novo or inherited
* Pathogenicity classification (if present)
* Any computational predictions mentioned

### **Why:**

Variants are nodes and attributes in your schema.

---

# 🔍 **CATEGORY 4 — Patient & Clinical Case Information**

This is one of the most important categories for rare disease work.

### Extract:

* Age / sex (if present)
* Family history
* De novo vs inherited
* Developmental milestones
* Key neurological findings
* Onset age
* Severity

### **Convert all symptoms → HPO terms.**

Your GPT-5 agent will automate most of this.

---

# 🧠 **CATEGORY 5 — Phenotype Extraction (HPO mapping)**

For *each* patient or phenotype mentioned:

### Extract:

* Symptom name (natural language)
* Map to HPO
* Severity
* Onset
* System involved (neurological, cardiac, skeletal, etc.)

### **Example mapping:**

| Text                         | HPO        |
| ---------------------------- | ---------- |
| “Speech delay”               | HP:0000750 |
| “Global developmental delay” | HP:0001263 |
| “Hypotonia”                  | HP:0001252 |

This mapping is Phase 1 critical.

---

# 🛠 **CATEGORY 6 — Mechanistic / Pathway-Level Information**

This is what makes your MED13 world model powerful.

### Extract:

* Descriptions of disrupted biological processes
* Protein–protein interactions
* Complexes involved (e.g., Mediator)
* Transcriptional dysregulation
* Pathway disruption
* Proposed mechanisms

### Examples of mechanistic sentences:

* “The variant likely disrupts Mediator complex function.”
* “This leads to reduced transcriptional activation of neural genes.”
* “Pathogenicity is mediated through LOF effects.”

### **Future: Convert to TypeDB facts**

* variant → affects → protein
* protein → participates-in → pathway
* pathway → linked-to → phenotype

Even if it’s speculative → it goes in evidence with lower confidence.

---

# 🔬 **CATEGORY 7 — Evidence Links**

For every relationship extracted from the paper:

### Extract:

* The statement supporting the relationship
* Confidence assigned by the authors
* Data type (experimental, computational, clinical)

Examples of evidence types:

* Case report → strong evidence
* Review summary → medium
* Computational prediction → low
* Animal model → contextual

### **Why:**

The graph schema uses evidence nodes to justify all causal links.

---

# 🔁 **BONUS CATEGORY 8 — Cross-Paper Consistency**

If the paper contradicts previous knowledge, extract:

### Extract:

* Conflicts or disagreements
* Novel findings
* Corrections of earlier reports

### **Phase 2 only**

This becomes a `world-event` of type “CORRECTION”.

---

# 🧠 **Future: How do you turn this template into TypeDB Phase 1 facts?**

Below is the exact mapping.

---

# 🗂 **HOW TO STORE EACH CATEGORY IN TYPEDB (PHASE 1)**

## **CATEGORY 1 → publication + evidence**

```typeql
insert
$pub isa publication,
  has pubmed-id "...",
  has name "...";
```

## **CATEGORY 2 → gene, protein, pathway**

If it’s MED13, and you already have it, skip.
Just add new info to `description`.

---

## **CATEGORY 3 → variant**

```typeql
insert
$v isa variant,
  has hgvs "...",
  has consequence "missense",
  has description "de novo";
(relates variant $v, relates gene $g) isa occurs-in-gene;
```

---

## **CATEGORY 4 → patient info (optional for Phase 1)**

If you choose to include patients:

```typeql
insert
$pt isa patient,
  has patient-id "case-1";
```

---

## **CATEGORY 5 → phenotype (HPO)**

```typeql
insert
$p isa phenotype,
  has hpo-id "HP:0000750",
  has name "Speech delay";
(relates variant $v, relates phenotype $p) isa causes-phenotype;
```

---

## **CATEGORY 6 → mechanism**

You can represent mechanisms at the pathway or description level:

```typeql
insert
$e isa evidence,
  has description "Variant disrupts Mediator complex assembly";
(relates assertion $v, relates evidence $e) isa supported-by;
```

---

## **CATEGORY 7 → evidence mapping**

```typeql
(relates source $pub, relates mentioned-entity $v) isa mentioning;
```

---

# 🧪 **EXAMPLE: Let’s apply the full template to ANY paper**

Say the paper claims:

* Variant: c.3899T>C (p.Leu1300Pro)
* Phenotypes: speech delay, hypotonia
* Mechanism: affects transcription regulation
* Evidence: case report, strong confidence

### Future: TypeDB insertion

```typeql
# Publication
insert
$pub isa publication,
  has pubmed-id "12345678",
  has name "New MED13 missense variant case report",
  has description "Case report describing MED13 variant p.Leu1300Pro";

# Variant
match
$g isa gene, has symbol "MED13";
insert
$v isa variant,
  has hgvs "NM_005121.4:c.3899T>C",
  has consequence "missense",
  has description "p.Leu1300Pro, heterozygous, de novo";
(relates variant $v, relates gene $g) isa occurs-in-gene;

# Phenotype 1
insert
$p1 isa phenotype,
  has hpo-id "HP:0000750",
  has name "Speech delay";
(relates variant $v, relates phenotype $p1) isa causes-phenotype;

# Phenotype 2
insert
$p2 isa phenotype,
  has hpo-id "HP:0001252",
  has name "Hypotonia";
(relates variant $v, relates phenotype $p2) isa causes-phenotype;

# Mechanism evidence
insert
$e isa evidence,
  has description "Variant impacts Mediator complex and transcriptional regulation",
  has confidence-score 0.9;
(relates assertion $v, relates evidence $e) isa supported-by;

# Link publication
(relates source $pub, relates mentioned-entity $v) isa mentioning;
```

---

# 🔍 **HOW TO QUERY LATER:**

### **1. Show all variants with mechanistic evidence**

```typeql
match
$v isa variant;
$e isa evidence;
(relates assertion $v, relates evidence $e) isa supported-by;
get $v, $e;
```

### **2. Show all phenotypes linked to MED13**

```typeql
match
$g isa gene, has symbol "MED13";
$v isa variant;
(relates variant $v, relates gene $g) isa occurs-in-gene;
$p isa phenotype;
(relates variant $v, relates phenotype $p) isa causes-phenotype;
get $p;
```

### **3. Show all papers mentioning MED13**

```typeql
match
$pub isa publication;
$g isa gene, has symbol "MED13";
(relates source $pub, relates mentioned-entity $g) isa mentioning;
get $pub;
```

---

# 🎉 **FINAL: Your Universal “Paper Extraction SOP”**

This is the definitive list of what to extract from ANY paper:

### **Always Extract**

1. Publication metadata
2. Variants (HGVS + type)
3. Phenotypes (map to HPO)
4. Mechanistic claims / pathways
5. Evidence text supporting each relationship

### **Optional Extract (Phase 2)**

6. Patient-level details
7. Temporal information
8. Conflicts or corrections
9. Agent who extracted (LLM vs human)

---
