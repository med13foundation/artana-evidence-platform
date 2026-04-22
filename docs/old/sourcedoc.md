ResoGraph: A Mechanism-Centered AI-Assisted Knowledge Graph for Diagnosing Unsolved Rare Diseases
Project Title: ResoGraph: A Hybrid AI & Knowledge Graph Platform for Resolving Unsolved Rare Genetic and Non-Genetic Diseases
Acronym: ResoGraph
Duration: 36 Months
Call Topic: JTC 2026 – Resolving Unsolved Cases in Rare Genetic and Non-Genetic Diseases

1. Executive Summary
The Challenge
Despite the widespread availability of whole-exome and whole-genome sequencing, more than 50% of rare disease patients across Europe remain undiagnosed. The primary bottleneck is no longer data acquisition, but the fragmentation of mechanistic knowledge across publications, databases, and clinical silos. Clinicians are routinely faced with Variants of Uncertain Significance (VUS) or complex non-genetic phenotypes without a reliable, systematic way to connect isolated observations to underlying biological mechanisms.
The Solution
We propose ResoGraph, a mechanism-centered, human-validated knowledge graph designed to support diagnosis in unsolved rare genetic and non-genetic diseases. ResoGraph unifies genetic, molecular, and phenotypic evidence into a single, structured reasoning framework. Unlike static databases or black-box AI systems, ResoGraph employs AI agents exclusively as hypothesis generators, traversing explicit mechanistic relationships to propose biologically grounded explanations (e.g., “Variant X likely disrupts Mechanism Y”). All hypotheses are subject to mandatory human expert review prior to any clinical or experimental interpretation.
Validation and Evaluation
ResoGraph will be evaluated on more than 1,000 unsolved cases contributed by a transnational consortium, spanning both:
Genetic disorders (e.g., neurodevelopmental disorders, ciliopathies)
Non-genetic conditions (e.g., immune-mediated diseases)
Primary Objective
To achieve a 15–25% relative increase in diagnostic yield, compared to baseline resolution rates in participating cohorts, by providing a human-in-the-loop decision-support system that enables systematic VUS reclassification and mechanistically grounded hypothesis generation.
Scope and Generalizability
Although ResoGraph is developed and evaluated strictly within the context of rare disease diagnosis, it is intentionally designed around domain-agnostic mechanistic abstractions. Rare diseases provide a stringent, high-value testbed for validating this approach. No functionality beyond rare disease diagnosis is developed or evaluated within the scope of this project; however, architectural decisions ensure that future reuse requires new data rather than redesign of the system.

2. Alignment with ERDERA JTC 2026
JTC 2026 Focus Area
ResoGraph Alignment
Genetic & Non-Genetic Diseases
Integrated cohorts include both genetic and immune-mediated non-genetic diseases, demonstrating mechanism-agnostic reasoning.
Resolving Unsolved Cases
Core focus on VUS reclassification and mechanistic explanation of orphan phenotypes.
Knowledge Graphs
Explicit modeling of causal biological mechanisms, not just gene–phenotype associations.
Advanced AI Tools
AI agents used under strict human governance for hypothesis generation only.


3. Scientific Excellence: The Hybrid Intelligence Model
General Mechanistic Reasoning Abstraction (Architecture-Level)
Input → Structural / Functional Context → Biological Mechanism → Clinical Phenotype
This abstraction defines how heterogeneous biomedical inputs—genetic, molecular, or biochemical—are translated into clinically interpretable hypotheses through explicit mechanistic reasoning. It is independent of disease area or data modality and serves as the core architectural principle of ResoGraph.
Concrete Instantiation in This Project
Within the scope of this proposal, the general abstraction is instantiated in a genomics-first configuration:
Genetic Variant → Protein Domain → Molecular Mechanism → Phenotype (HPO)
This instantiation provides a clinically rigorous and technically demanding test case for validating the broader architecture in unsolved rare diseases.

Layer 1: Mechanism-Centered Knowledge Graph (The “Map”)
ResoGraph’s foundation is a structured, FAIR-compliant knowledge graph that explicitly represents mechanistic causality, rather than statistical association. The graph encodes relationships between:
Variants and Protein Domains (structural and functional context)
Protein Domains and Biological Mechanisms (e.g., Mediator complex disruption, ciliary transport failure)
Biological Mechanisms and Clinical Phenotypes (Human Phenotype Ontology)
Novelty:
Unlike existing gene–phenotype association resources, ResoGraph treats biological mechanisms as first-class entities, enabling explicit reasoning over causal pathways rather than post-hoc correlation.

Layer 2: AI Agents as Hypothesis Generators (The “Scouts”)
AI agents are used solely to explore and synthesize mechanistic paths already encoded in the graph. Their functions are strictly limited to:
Traversal: Identifying plausible mechanistic paths linking inputs to phenotypes
Proposal: Generating candidate mechanistic hypotheses grounded in existing evidence
Explanation: Producing structured, human-readable reports citing all supporting graph nodes
Agents operate over typed mechanistic relationships, not disease-specific heuristics.
Hard Safety Constraint:
AI agents cannot create, modify, or approve graph knowledge and are incapable of making diagnostic decisions.

Layer 3: Human-in-the-Loop Validation (The “Judges”)
All hypotheses undergo mandatory review by multidisciplinary clinical and scientific experts within the consortium.
Clinical Curation: Assessment of biological plausibility and clinical relevance
Consensus Validation: Only human-approved hypotheses are incorporated into the persistent graph
Functional Validation: A subset of high-confidence hypotheses undergo wet-lab validation (e.g., transcriptomics, functional assays)
This ensures ResoGraph functions strictly as a decision-support system, not an autonomous diagnostic tool.

4. Implementation Strategy
Phase 1: Gold-Standard Calibration (MED13 Pilot)
MED13 is selected as a calibration system due to:
Well-characterized molecular biology
Broad and heterogeneous phenotypic spectrum
Activities:
Manual curation of a validated MED13 mechanistic subgraph
Agent evaluation against ground-truth mechanistic reasoning
Phase 2: Transnational Cohort Expansion
Disease Area
Type
Purpose
Neurodevelopmental Disorders
Genetic
High VUS burden; mechanistic convergence
Ciliopathies / Mitochondrial Disorders
Genetic
Strong structural biology signal
Immune-Mediated Diseases
Non-Genetic
Explicit ERDERA requirement; non-genomic inputs (e.g., cytokine dysregulation → pathway disruption → phenotype)


5. Diagnostic Workflow
Input: Unsolved patient data (HPO + VUS or biochemical/immune profiles)
Agent Traversal: Bottom-up and top-down mechanistic exploration
Hypothesis Generation: Candidate mechanisms proposed with transparent confidence scoring criteria
Human Review: Multidisciplinary expert evaluation
Outcome: Diagnostic confirmation or referral for functional validation
Iteration: Validated outcomes incorporated into the knowledge graph

6. Impact and Outcomes
Clinical Impact
15–25% relative increase in diagnostic yield, compared to baseline cohort resolution
Reclassification of 100–200 VUSs using mechanistic evidence
Demonstrated applicability to non-genetic rare diseases
Scientific Outputs
Open, agent-assisted mechanistic graph platform for the rare disease community
A validated blueprint for safe, auditable AI in clinical genomics

7. Budget and Resources
Total Budget: ~€1.8M (Consortium total)
Allocation:
35% Computational (graph engineering, agents, scoring)
30% Clinical (phenotyping, expert review)
25% Functional validation
10% Management and ELSI compliance
Planned Collaborators:
Wilhelm Foundation
CombinedBrain
Undiagnosed Diseases Network (UDN)

Conclusion
ResoGraph introduces a novel diagnostic paradigm based on explicit mechanistic reasoning, hybrid intelligence, and strict human governance. By modeling biological mechanisms as first-class entities and constraining AI to a supportive, auditable role, ResoGraph delivers a scalable, ethically robust solution to one of the most persistent challenges in rare disease diagnosis—while remaining fully aligned with ERDERA’s scientific and clinical priorities.
