# SPECIFIC AIMS

**Google.org Impact Challenge: AI for Science**
**MED13 Foundation | 36 Months**

## ResoGraph: An Evidence-First, Claim-Governed Knowledge Graph and AI Research Runtime for Rare Disease Discovery

Despite major advances in genomic sequencing, approximately 60% of rare
disease patients remain undiagnosed or lack a therapeutic path. The central
challenge is not simply lack of data, but lack of structured, explainable
mechanistic context. The information needed to connect genetic variants,
biological pathways, phenotypes, and therapeutic ideas exists across more than
39 million scientific publications, genomic databases, and patient
observations, but remains fragmented, difficult to synthesize, and poorly
organized for mechanistic reasoning.

Most biomedical knowledge systems capture associations such as gene-disease
links, but they rarely preserve the full scientific structure needed for
trustworthy discovery: explicit evidence, governed claims, disagreement,
provenance, and reviewable reasoning chains. This is especially limiting in
ultra-rare disease, where purely statistical approaches often fail because only
a small number of patients may exist worldwide.

ResoGraph will address this gap by building and integrating:

1. an evidence-first, claim-governed knowledge graph
2. derived mechanistic reasoning paths built from claim-backed graph structure
3. a separate AI research runtime that generates ranked, reviewable proposals
   outside the canonical graph

ResoGraph is designed around an evidence-first architecture:

```text
Evidence -> Claims -> Projections -> Canonical Graph -> Reasoning Artifacts
```

In this model:

- claims are the authoritative scientific assertion ledger
- canonical graph relations are derived projections of eligible support claims
- reasoning paths are derived, rebuildable artifacts used for mechanistic
  exploration
- hypotheses and candidate claims are first stored in a proposal layer outside
  the authoritative graph and only enter the graph through governed review

This design allows ResoGraph to preserve what most knowledge systems lose:
traceability, uncertainty, disagreement, and reviewable mechanistic reasoning.
In effect, the graph functions as a governed scientific argument structure, not
just a store of biomedical associations.

The proposed platform will integrate literature, genomic resources, and
patient phenotype observations to support evidence-traceable reasoning over
paths such as:

```text
Variant -> Candidate Molecular Mechanism -> Cellular Dysfunction -> Phenotype -> Therapeutic Hypothesis
```

These paths will not be treated as autonomous scientific truth. Instead, they
will be assembled from evidence-backed claims, graph structure, and derived
reasoning artifacts, then used by the AI runtime to generate ranked,
reviewable candidate hypotheses and graph proposals.

The AI research runtime will operate separately from the graph system of
record. It will synthesize literature, explore graph structure, analyze
reasoning paths, and propose candidate claims, mechanistic hypotheses, and
curation actions. These outputs will be stored in a proposal layer outside the
canonical graph, ensuring that uncertain or exploratory AI outputs do not
contaminate the authoritative knowledge base. The runtime will maintain
structured research state, including open questions, prior hypotheses, and
work history, and will operate under explicit ranking, budget, and review
constraints. Only after human review will approved proposals be promoted into
the governed claim pipeline.

We will calibrate and test the system on MED13 syndrome and related Mediator
disorders, beginning with a community of approximately 200 known MED13
families across 17 countries, use it to generate and prioritize mechanistic
hypotheses, and establish the architecture and workflows needed for broader
expansion across rare disease research.

## Why This Approach Matters for Rare Disease

Large biomedical datasets have grown rapidly, but ultra-rare disease discovery
remains difficult. GeneDx has generated roughly one million clinical exomes
and genomes, and large public resources such as CELLxGENE now contain tens of
millions of cellular profiles. Yet ultra-rare disease remains structurally
hard: when only a small number of patients exist worldwide, statistical power
collapses even in very large datasets. The 100,000 Genomes Project reported
226 rare diseases across 34,851 cases, with 29 diseases represented by fewer
than 5 cases. GeneDx has also reported 5,600 emerging gene-disease
relationships still awaiting a second patient for confirmation. In this
setting, the bottleneck is not only data availability, but the ability to
organize sparse evidence into mechanistically meaningful, reviewable reasoning
structures.

ResoGraph is designed for exactly this setting. Rather than depending only on
large cohort statistics, it supports evidence-traceable reasoning across
literature, pathway knowledge, and sparse patient observations. This mirrors
real scientific practice: assemble evidence, evaluate competing claims, explore
mechanistic explanations, generate hypotheses, and iteratively refine the
knowledge base. The goal is not to replace large-scale genomics resources, but
to make them more actionable for diseases that remain below conventional
statistical detection thresholds.

## Aim 1. Build

### Construct an evidence-first, claim-governed knowledge graph for MED13 and related Mediator disorders.

We will build a knowledge graph that integrates literature, genomic resources,
and patient phenotype observations using an evidence-first claim architecture.
In this system, scientific assertions are stored as governed claims linked to
evidence and provenance, while canonical graph relations are derived as
projections of eligible support claims.

Large language models will operate within a retrieval-augmented pipeline in
which every extracted claim must be traceable to a specific PubMed identifier
or structured database record before entering the governed claim pipeline.

This architecture will enable:

- explicit linkage between evidence and scientific assertions
- preservation of disagreement, uncertainty, and review state
- explainable canonical graph relations
- derived mechanistic reasoning paths that can be rebuilt as knowledge evolves

The initial graph will focus on MED13 and related Mediator disorders, capturing
variants, phenotypes, pathways, molecular functions, and literature-linked
scientific claims.

**Deliverables**

- validated MED13-centered claim-governed knowledge graph
- at least 1,000 evidence-backed reasoning structures assembled and
  expert-prioritized for MED13-related mechanisms
- expansion to additional related rare disease genes

## Aim 2. Reason

### Deploy an AI research runtime that generates ranked, reviewable proposals from graph structure and scientific evidence.

We will build a separate AI research runtime that operates on top of the graph
system of record. This runtime will support literature synthesis, graph
exploration, reasoning-path analysis, and proposal generation through
structured workflows.

For example, an AI agent evaluating the MED13 Thr326Lys variant will retrieve
AlphaMissense predictions, inspect the structural location of the variant
within the MED13 phosphodegron region, evaluate potential disruption of Fbw7
binding, and assemble a mechanistic hypothesis regarding altered protein
stability.

The runtime will include workflows for:

- **Research Bootstrap** - initialize a research space from literature and
  external sources
- **Graph Chat** - answer researcher questions using graph context and evidence
- **Continuous Learning** - revisit the literature and propose updated
  candidate knowledge
- **Mechanism Discovery** - analyze converging reasoning paths across genes,
  pathways, and phenotypes
- **Claim Curation** - prepare governed claim and curation recommendations for
  review

AI workflows will not directly modify the canonical graph. Instead, they will
generate:

- candidate claims
- candidate hypotheses
- mechanistic proposals
- curation recommendations

These outputs will be stored in a proposal layer outside the graph ledger and
ranked using evidence quality, path support, contradiction signals, novelty
relative to existing graph content, and other explicit guardrails. Only
reviewed proposals will be promoted into the governed claim flow.

The goal is not to reclassify Variants of Uncertain Significance directly.
Instead, the runtime will generate and structure actionable mechanistic
evidence to accelerate expert review and clinical reclassification under
established ACMG/AMP frameworks.

**Deliverables**

- AI-assisted graph-grounded literature synthesis
- ranked, reviewable candidate claims and mechanistic hypotheses
- at least 10 experimentally testable, evidence-backed proposals prioritized
  for validation
- measurable reduction in time required to assemble evidence-backed, testable
  research proposals

## Aim 3. Validate

### Experimentally evaluate top-ranked, AI-assisted mechanistic hypotheses in preclinical systems.

To connect computational reasoning with biological investigation, we will
prioritize and experimentally evaluate top-ranked hypotheses produced through
the graph and AI runtime across three preclinical systems: patient-derived
fibroblasts, brain organoids, and mouse models.

The primary AI-experiment feedback loop will rely on faster, higher-throughput
systems including patient-derived fibroblasts and cortical organoids, which
enable rapid testing of mechanistic hypotheses. In parallel, we will initiate
development of a Med13 mouse model to support longer-term in vivo validation of
the most promising mechanisms. This design keeps the discovery loop on
experimentally tractable timelines while establishing a longer-term in vivo
validation framework.

The purpose of this aim is not to treat AI output as truth, but to test whether
evidence-backed, claim-traceable, graph-derived hypotheses can improve the
speed and quality of rare disease mechanism discovery.

Experimental findings will be captured as structured evidence with provenance
and proposed for promotion through the governed claim pipeline, allowing the
knowledge base to evolve through a reviewable loop of reasoning, validation,
and curation rather than through direct, unguided write-back into the
authoritative graph.

**Deliverables**

- experimentally evaluated top-ranked mechanistic hypotheses
- evidence captured and proposed for promotion through the governed claim
  structure
- refined mechanism models for MED13-related disease biology
- a validated cross-system evidence loop spanning fibroblasts, organoids, and
  mouse studies

## Aim 4. Operationalize

### Release an open, governed platform for evidence-first rare disease discovery.

We will release ResoGraph as open infrastructure for evidence-first rare
disease research. More than 7,000 rare diseases affect an estimated 300
million people worldwide, yet most disease communities lack the tools needed to
organize mechanistic evidence at research speed. The platform will include:

- a claim-governed evidence-first graph system of record
- derived reasoning-path infrastructure for mechanistic exploration
- a separate AI research runtime for proposal generation and continuous
  learning
- human-governed workflows for review, curation, and graph promotion

The platform will be designed so that exploratory AI reasoning remains
separated from authoritative scientific knowledge, while still enabling
continuous, durable, and scalable research workflows.

The platform will be released both as open-source software on GitHub and as a
hosted web portal for patient organizations and researchers who do not have the
capacity to deploy cloud infrastructure themselves. Patient organizations will
be able to use a hosted web interface for graph exploration and hypothesis
review, while research groups will be able to deploy the open-source
infrastructure in their own cloud environments.

**Deliverables**

- open platform release
- reusable workflows for bootstrap, chat, continuous learning, mechanism
  discovery, and governed curation
- adoption by at least 10 rare disease research groups or patient-led research
  programs

## Impact

If successful, ResoGraph will create a new kind of rare disease discovery
infrastructure: an evidence-first, claim-governed knowledge system with a
separate AI research runtime for mechanistic proposal generation. By combining
governed scientific assertions, explainable graph projections, derived
reasoning paths, and human-reviewed AI proposals, the system will enable a
continuous and reviewable cycle of rare disease discovery.

Rather than replacing scientific judgment, ResoGraph is designed to strengthen
it: organizing fragmented evidence, surfacing mechanistic possibilities, and
accelerating the generation of reviewable, testable hypotheses for rare
disease research.
