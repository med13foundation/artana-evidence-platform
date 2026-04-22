Status: Future/Optional

This document describes a potential TypeDB migration path. The current execution path uses **Postgres-backed graph storage with NetworkX traversal** (see `docs/plan.md`). Use this document as a future reference, not the active roadmap.

Below is a **full, production-ready roadmap** for your MED13 World Model development.
It includes:

* **Phase 1 (Foundational World Model)**
* **Phase 2 (Enterprise Temporal + Agentic World Model)**
* Clear milestones, deliverables, metrics, and risk controls.
* Designed to align with a future TypeDB migration, plus pgvector/Postgres (current system of record), GPT-5 deep research, your Meta-Agent framework, and biomedical research workflows.

This is the kind of plan you can present to:
Stanford collaborators, CZI reviewers, PIs, or funding bodies.

---

# 🚀 **MED13 WORLD MODEL — DEVELOPMENT ROADMAP (v1.0 → v2.0)**

*A hybrid neuro-symbolic world model for rare-disease research.*

---

# 🌱 **PHASE 1 — FOUNDATIONAL CAUSAL WORLD MODEL (6–10 weeks)**

**Goal:**
Build a clean, causal, explainable, research-focused MED13 world model using **TypeDB + GPT-5 deep research**, with minimal complexity.

**Guiding principles:**

* Keep it simple
* Focus on biological reasoning
* Build only the core schema
* Enable GPT-5 agents to fill in missing knowledge
* No outbox, no temporal system yet
* No vector DB needed (optional pgvector only)
* Fast iteration, minimal overhead

---

## **PHASE 1 — Workstreams and Milestones**

### ✅ **Milestone 1.1 — Minimal TypeDB Schema Implemented**

Deliverables:

* Core entities: gene, protein, variant, phenotype, pathway, evidence
* Core relations: occurs-in-gene, has-consequence, causes-phenotype, participates-in, supported-by
* Simple attributes: uuid, symbol, description

Success criteria:

* Schema loads without errors
* Sample queries return paths
* MED13 seeded with basic knowledge

---

### ✅ **Milestone 1.2 — Knowledge Seeding (MED13 v0)**

Deliverables:

* Insert MED13 gene entity
* Insert known variants (from ClinVar + OMIM)
* Insert MED13 phenotypes (HPO terms)
* Insert mediator complex pathway nodes
* Insert links: variant → phenotype, protein → pathway

Success criteria:

* Causal paths exist
* TypeDB returns:
  *“Why does variant X cause phenotype Y?”*

---

### 🧠 **Milestone 1.3 — GPT-5 Deep Research Integration**

Deliverables:

* Retrieval agent reads MED13 papers
* Automated extraction of structured facts:

  * variant effects
  * phenotype associations
  * mechanism descriptions
* Tool to auto-generate TypeDB inserts

Success criteria:

* GPT-5 generates 50+ new evidence items
* At least 10 novel mechanistic insights extracted
* Insert tool validated against schema

---

### 📚 **Milestone 1.4 — Query API + Research Interface**

Deliverables:

* FastAPI or Flask interface
* Queries like:

  * `/gene/MED13/phenotypes`
  * `/variant/{v}/explain`
  * `/pathway/{p}/mechanisms`

Success criteria:

* Researchers can query with natural language (“explain variant X”)
* Responses use TypeDB + GPT-5 fusion

---

### 📊 **Milestone 1.5 — Validation with Researchers**

Deliverables:

* Internal demo to clinicians or rare-disease group
* Evaluate correctness, usefulness, missing links

Success criteria:

* 75%+ of causal explanations accepted by domain experts
* Identify 20+ high-priority schema extensions

---

### 🎉 **PHASE 1 Completion Goal**

A **functional biomedical world model** for MED13 with:

* causal graph
* evidence paths
* phenotype mapping
* GPT-5 semantic integration
* research query API

This is enough to publish a **Phase 1 poster** or preprint.

---

# 🌳 **PHASE 2 — FULL TEMPORAL + AGENTIC WORLD MODEL (3–6 months)**

**Goal:**
Upgrade the foundational model into a **versioned, auditable, multi-agent, temporal world model** with:

* Immutable world-events
* Evidence lifecycle
* Agent-based updates
* Transactional outbox
* Multi-database synchronization
* Full provenance
* Hypothesis tracking
* Reproducible state changes

---

# 🔥 **PHASE 2 — Workstreams and Milestones**

### 🕒 **Milestone 2.1 — Temporal Evidence Layer**

Implement temporal elements:

* `world-event`
* `world-state-change`
* event-type (“NEW_FINDING”, “HYPOTHESIS”, “UPDATE”, “RETRACTION”)
* agent attribution
* justification text
* confidence score

Success criteria:

* Every fact in TypeDB has a timestamped event
* You can ask:
  *“What did we believe about MED13 in June 2025?”*

This is huge for world modeling.

---

### 🔁 **Milestone 2.2 — Event-Sourced Knowledge Ingestion**

Deliverables:

* Every update done through “world-event”
* Immutable knowledge history
* “Correction” events supported
* Evidence provenance chain
* GPT-5 agent generates justification text

Success criteria:

* Full state reconstruction possible
* No knowledge overwritten — only superseded

---

### 📤 **Milestone 2.3 — Transactional Outbox Implementation**

Purpose:

* Guarantee sync across TypeDB ←→ pgvector/Postgres
* Kafka-like reliability without running Kafka
* Required for agentic updates at scale

Deliverables:

* `outbox-event` entity
* Worker process to publish updates
* Retry and dead-letter queues

Success criteria:

* Zero lost updates
* Vector DB always consistent with TypeDB

---

### 🤖 **Milestone 2.4 — Multi-Agent System Integration**

Agents added:

* **IR Agent:** retrieves TypeDB data + GPT-5 deep research
* **EVL Agent:** validates and scores evidence
* **SIM Agent:** runs mechanistic simulations
* **GEN Agent:** generates new hypotheses
* **ORC Agent:** orchestrates all tasks
* **UPDATE Agent:** commits world-events

Success criteria:

* Agents perform full research cycles
* Hypotheses are inserted as world-events
* Productive cross-agent workflows

---

### 🧪 **Milestone 2.5 — Evaluation Framework**

Deliverables:

* Precision/recall measurement on known MED13 knowledge
* Hallucination tests
* Consistency rules
* Causal path validation
* Mechanism plausibility scoring

Success criteria:

* LLM-generated findings achieve 90%+ correctness post-validation
* Zero-inconsistent causal links

---

### 🌐 **Milestone 2.6 — Multi-Syndrome Support**

Extend schema to support:

* MED13L
* TBCK
* CHD gene families
* RASopathies

Success criteria:

* New diseases added with <10 hours manual curation
* Schema remains stable & general

---

### 🏁 **PHASE 2 Completion Goal**

A **full enterprise neuro-symbolic world model**, with:

* type-safe schema
* temporal versioning
* immutable knowledge events
* causal reasoning
* GPT-5 semantic research
* multi-agent system
* provenance tracking
* cross-database synchronization

This is publishable as a **Nature Methods**, **Bioinformatics**, or **AMIA** paper.

---

# 🪜 **Growth Path: Phase 1 → Phase 2**

### 🟩 Phase 1 = build the “world”

* Entities
* Mechanisms
* Variants
* Phenotypes
* Causal graph
* Simple evidence

### 🟧 Phase 2 = build the “history, governance, and intelligence”

* Temporal reality
* Agent-driven discovery
* Version control
* Auditable lineage
* Sync patterns
* Hypothesis lifecycle
* Research automation

Phase 1 is a **knowledge graph**.
Phase 2 is a **true world model**.

---

 ==========

 # DATA FOR PHASE 1

 Great — here is exactly **what data you should store in Phase 1**, **where to get it**, and **how to load it into TypeDB** to start building your MED13 World Model immediately.

I’ll keep it extremely actionable.

---

# 🌱 **PHASE 1 — DATA YOU SHOULD STORE IN THE WORLD MODEL**

Phase 1 should contain **5 minimal data categories**:

1. **Gene-level data (MED13 + related genes)**
2. **Variant data (MED13 variants + clinically reported cases)**
3. **Phenotype data (HPO terms)**
4. **Mechanistic/pathway data (Mediator complex + Reactome)**
5. **Evidence data (links to publications)**

This is the minimum required to get **causal paths** and **explanation queries** working.

You **do not** need drugs, trials, temporal events, or complicated entities yet.

---

# 🧬 **1. GENE-LEVEL DATA**

### What to store:

* Gene symbol (MED13)
* Ensembl ID
* Gene description
* Associated transcripts
* Associated protein (MED13 protein)
* Mediator complex membership
* Interactions with other Mediator subunits

### Where to get it:

| Source        | URL                                                            | What to extract                 |
| ------------- | -------------------------------------------------------------- | ------------------------------- |
| **Ensembl**   | [https://www.ensembl.org](https://www.ensembl.org)             | Gene metadata, IDs, transcripts |
| **UniProt**   | [https://www.uniprot.org](https://www.uniprot.org)             | Protein metadata, domains       |
| **NCBI Gene** | [https://ncbi.nlm.nih.gov/gene](https://ncbi.nlm.nih.gov/gene) | Gene summary, aliases           |
| **Reactome**  | [https://reactome.org](https://reactome.org)                   | Pathways involving MED13        |
| **GeneCards** | [https://genecards.org](https://genecards.org)                 | Summaries, interactions         |

**Recommended starting file:**
Download the **UniProt JSON** for MED13.

---

# 🧬 **2. VARIANT DATA (MED13 MUTATIONS)**

### What to store:

* HGVS notation
* Variant type (missense, nonsense, frameshift)
* Genomic coordinates
* ClinVar IDs
* Variant consequence (LOF, missense impact)
* Associated phenotypes (if reported)

### Where to get it:

| Source       | URL                                                                          | What to extract      |
| ------------ | ---------------------------------------------------------------------------- | -------------------- |
| **ClinVar**  | [https://www.ncbi.nlm.nih.gov/clinvar](https://www.ncbi.nlm.nih.gov/clinvar) | All MED13 variants   |
| **dbSNP**    | [https://www.ncbi.nlm.nih.gov/snp](https://www.ncbi.nlm.nih.gov/snp)         | Genomic positions    |
| **gnomAD**   | [https://gnomad.broadinstitute.org](https://gnomad.broadinstitute.org)       | Population frequency |
| **Decipher** | [https://www.deciphergenomics.org](https://www.deciphergenomics.org)         | Case reports         |

**Recommended starting action:**
Search ClinVar:
“MED13 [gene]” → Download VCF.

---

# 🧬 **3. PHENOTYPE DATA (HPO TERMS)**

### What to store:

* HPO ID
* Phenotype name
* Phenotype category
* Severity (mild / moderate / severe)
* Onset (congenital, childhood)
* Links to MED13 cases

### Where to get it:

| Source                             | URL                                        | What to extract             |
| ---------------------------------- | ------------------------------------------ | --------------------------- |
| **HPO (Human Phenotype Ontology)** | [https://hpo.jax.org](https://hpo.jax.org) | All phenotype definitions   |
| **OMIM**                           | [https://omim.org](https://omim.org)       | MED13 clinical descriptions |
| **Case studies**                   | PubMed                                     | Case-reported phenotypes    |

**Recommended starting point:**
Download the **HPO annotation file (`phenotype.hpoa`)**, filter for “MED13”.

---

# 🧬 **4. PATHWAY & MECHANISTIC DATA**

### What to store:

* Mediator complex membership
* Subunits interacting with MED13
* Pathway names
* Biological processes affected
* Known mechanisms (e.g., transcriptional regulation)

### Where to get it:

| Source       | URL                                                      | What to extract                      |
| ------------ | -------------------------------------------------------- | ------------------------------------ |
| **Reactome** | [https://reactome.org](https://reactome.org)             | MED13’s role in the Mediator complex |
| **KEGG**     | [https://www.genome.jp/kegg](https://www.genome.jp/kegg) | Transcription pathways               |
| **UniProt**  | Protein interaction details                              |                                      |
| **BioGRID**  | [https://thebiogrid.org](https://thebiogrid.org)         | Interaction networks                 |

**Recommended:**
Reactome’s pathway: **"Transcriptional regulation by Mediator complex"**

---

# 📚 **5. EVIDENCE DATA (PUBLICATIONS)**

This is your foundation for explainable causal paths.

### What to store:

* PubMed ID
* Title
* Abstract
* Sections relevant to MED13
* Links between variant ↔ phenotype ↔ mechanism
* Case descriptions

### Where to get it:

| Source             | URL                                                                | What to extract                  |
| ------------------ | ------------------------------------------------------------------ | -------------------------------- |
| **PubMed**         | [https://pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov) | Case reports, mechanistic papers |
| **Google Scholar** | [https://scholar.google.com](https://scholar.google.com)           | Additional literature            |

**Recommended:**
PubMed search:

```
MED13 AND neurodevelopment
MED13 AND variant
MED13 syndrome
MED13 AND transcription
```

---

# 📦 **Phase 1 Checklist — What to Insert into TypeDB Immediately**

### Insert Phase 1:

#### Gene

* MED13
* MED13L (optional, but recommended)

#### Variants

* All known ClinVar MED13 variants
* Pathogenic and VUS

#### Phenotypes

* HPO terms linked to MED13
* Severity + onset

#### Pathways

* Mediator complex
* Transcriptional regulation pathways

#### Evidence

* 20–50 PubMed publications as evidence objects
* Link them to variants and phenotypes

---

# 🛠 **Phase 1 Data Acquisition: Step-by-Step Plan (very practical)**

### **1. MED13 gene + protein**

* Visit UniProt
* Search for “MED13”
* Download JSON

### **2. MED13 variants**

* Go to ClinVar
* Filter by Gene = MED13
* Export TSV or XML

### **3. Phenotypes**

* Download HPO `phenotype.hpoa`
* Filter for “MED13”

### **4. Pathways**

* Download Reactome “Mediator complex” pathway JSON

### **5. Evidence**

* Use PubMed API:

```
/entrez/eutils/esearch.fcgi?term=MED13
```

---

# 📥 **How to Insert Into TypeDB (example)**

### Example: MED13 gene

```typeql
insert
$g isa gene,
  has name "MED13",
  has symbol "MED13",
  has external-id "ENSG00000100888",
  has description "Mediator complex subunit 13";
```

### Example: Variant

```typeql
insert
$v isa variant,
  has hgvs "NM_005121.4:c.1234G>A",
  has genomic-location "chr17:12345678",
  has consequence "missense",
  has external-id "SCV0000001";
```

### Example: Phenotype

```typeql
insert
$p isa phenotype,
  has hpo-id "HP:0000717",
  has name "Intellectual disability";
```

### Example: Link variant → phenotype

```typeql
insert
(relates variant $v, relates phenotype $p) isa causes-phenotype;
```

### Example: Evidence

```typeql
insert
$e isa evidence,
  has pubmed-id "34567890",
  has description "Case report describing MED13 missense variant causing speech delay";
```

---

# 🧭 **Summary — Phase 1 Data to Start Storing**

| Category       | Specific Data to Start With      | Source            |
| -------------- | -------------------------------- | ----------------- |
| **Genes**      | MED13, MED13L                    | Ensembl, UniProt  |
| **Variants**   | All MED13 ClinVar variants       | ClinVar           |
| **Phenotypes** | HPO-set linked to MED13          | HPO, PubMed       |
| **Pathways**   | Mediator complex                 | Reactome          |
| **Evidence**   | 20–50 PubMed papers              | PubMed            |
| **Mechanisms** | Transcriptional regulation roles | UniProt, Reactome |

This is enough to power:

* causal reasoning
* mechanistic paths
* phenotype clustering
* GPT-5 research agent integration

This is exactly what Phase 1 needs.
