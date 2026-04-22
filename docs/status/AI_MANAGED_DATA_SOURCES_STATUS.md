# Status: Implementation of AI-Managed Data Sources (Artana Integration)

**Date:** January 10, 2026
**Status:** Implementation Complete (Phase 1: PubMed)
**Architecture:** Clean Architecture, Type-Safe AI Orchestration
**Framework:** Artana (Type-Safe AI Workflows)

---

## 📋 Executive Summary & Project Context

### The Big Picture: Evolving into a Translational AI Platform
The **Artana Resource Library** is a curated biomedical data platform specializing in genetic variants, phenotypes, and evidence related to the MED13 syndrome. Our core mission is to provide researchers with a reliable, type-safe environment for managing and discovering scientific data.

As outlined in our `@docs/plan.md`, the project is currently evolving from a "Variant Registry" into a **Translational AI Platform**. This evolution involves moving beyond flat data records toward a **System Biology Model** powered by a Knowledge Graph. Our goal is to enable mechanistic reasoning (`Variant -> ProteinDomain -> Mechanism -> Phenotype`) and automated hypothesis generation.

### The Role of AI-Managed Data Sources
The integration of the **Artana** framework is a critical step in this roadmap. It transforms our ingestion infrastructure from a passive "downloader" into an active **"Research Scout."**

By enabling **AI-Managed Data Sources**, we allow the system to:
1.  **Understand Context**: Use high-level research space descriptions to steer discovery.
2.  **Generate Intelligent Queries**: Dynamically adapt search strategies across multiple data sources (PubMed, ClinVar, ClinicalTrials.gov, etc.) to find the most relevant and novel information.
3.  **Ensure Provenance**: Maintain a strict, auditable trail of how AI steered the discovery process, ensuring clinical and scientific credibility.

This implementation establishes the **Source-Agnostic Agent Pattern**. While PubMed is the first active source, the architecture is designed to scale horizontally across any biomedical database by simply registering new specialized agents.

---

## 🏗️ Architectural Implementation

Following our **Clean Architecture** principles, the implementation is distributed across the following layers:

### 1. Domain Layer (`/domain/entities`)
We extended the data source configuration to include AI steering parameters without introducing infrastructure dependencies.
- **`AiAgentConfig`**: New value object in `data_source_configs/pubmed.py`.
    - `is_ai_managed`: Boolean toggle for automation.
    - `agent_prompt`: Natural language instructions to steer agent behavior.
    - `use_research_space_context`: Toggle to feed the Space Description into the LLM.

### 2. Application Layer (`/application/services`)
Orchestration logic was added to handle the "AI-to-Search" flow.
- **`AiAgentPort`**: An abstract interface (Port) defined in `ports/ai_agent_port.py` to decouple business logic from the specific LLM provider or framework.
- **`PubMedIngestionService`**: Updated to intercept ingestion calls. If AI-managed, it resolves the intelligent query via the port before proceeding with the standard fetching/transformation pipeline.

### 3. Infrastructure Layer (`/infrastructure/llm`)
The heavy lifting of AI orchestration lives here, powered by **Artana**.
- **`ArtanaAgentAdapter`**: Our implementation of `AiAgentPort`.
    - **Scalable Registry**: Uses a registry pattern to map `source_type` to specialized Artana agents. This allows us to add ClinVar, UniProt, or custom scrapers without modifying the core adapter logic.
    - **Source-Specific Optimization**: Each agent (e.g., PubMed agent) is tuned with specific system prompts for that database's query syntax.
    - **Structured Output**: Uses Pydantic models to ensure the AI always returns a valid, parsable query object.
- **`artana.toml`**: Provides a SQLite fallback; production uses `ARTANA_STATE_URI` pointing to the Postgres `artana` schema for durable audit trails.

### 4. Presentation Layer (Next.js Admin UI)
Updated the frontend to provide curators with control over the new AI capabilities.
- **AI Management Section**: Added to `CreateDataSourceDialog.tsx` with toggles and a dedicated steering prompt textarea.
- **Visual Feedback**: Added an **"AI Managed"** badge to data source cards in `DataSourcesList.tsx` for immediate identification of automated pipelines.

---

## 🤖 Why Artana?

We chose **Artana** for this integration for several strategic reasons:
1.  **Type Safety**: Artana enforces Pydantic-based inputs and outputs, aligning with our "Never Any" project policy.
2.  **Durable Execution**: Every AI query generation is recorded in a cryptographic audit trail, essential for scientific provenance.
3.  **Human-in-the-Loop (HITL)**: Future phases can leverage Artana's native HITL features to pause for researcher approval before ingesting large batches of data.
4.  **Resilience**: Built-in retries and state persistence ensure that transient LLM failures don't break our background cron jobs.

---

## 🔄 Workflow Lifecycle

1.  **Configuration**: A curator enables AI management for a PubMed source and provides a prompt (e.g., *"Focus on MED13L missense variants in the IDR region"*).
2.  **Trigger**: The source is triggered manually or by its configured **Cron Schedule**.
3.  **Context Assembly**: The system retrieves the research space description.
4.  **AI Generation**: The Artana agent combines the prompt and context into a high-fidelity Boolean query.
5.  **Execution**: The standard PubMed gateway uses the AI query to fetch the latest literature.
6.  **Persistence**: The AI-generated query is snapshotted in the `IngestionJob` record for full auditability.

---

## 🚀 Roadmap: Scaling the Research Scout

This integration is the foundation for the **Sprint 2 (Atlas Ingestion)** goals in our implementation plan. We are moving toward an autonomous "Atlas" that not only finds data but understands it.

### Phase 2: Knowledge Extraction Agents
Use Artana to not just *find* papers, but to *extract* high-fidelity facts directly from PDFs:
- **HGVS Variant Extraction**: Identify specific genetic variants mentioned in text.
- **Phenotype Mapping**: Automatically map symptoms to HPO (Human Phenotype Ontology) terms.
- **Evidence Linking**: Associate mechanistic claims with specific sentences in the paper.

### Phase 3: Multi-Source AI Enrichment
Extend the `AiAgentPort` to orchestrate discovery across a wider ecosystem:
- **ClinVar & UniProt**: Cross-reference literature with structural biology and clinical classifications.
- **ClinicalTrials.gov**: Identify relevant trials based on space descriptions.

### Phase 4: The Inference Feedback Loop
As part of our **Phase 4 (AI Engine)** goals, we will allow the Knowledge Graph to steer the agents:
- **Gap Discovery**: The AI identifies "holes" in our current knowledge graph and generates queries specifically to fill them.
- **Human-in-the-Loop Learning**: Agents learn from curator approvals/rejections to refine their precision.

---

## 💬 Team Feedback Request

We are looking for feedback on:
1.  **Agent Steering**: Are the current steering parameters (`agent_prompt`, `use_research_space_context`) sufficient for your research needs?
2.  **Auditability**: Is the snapshot of the generated query in the ingestion logs enough, or should we expose the full Artana trace in the UI?
3.  **Scheduling**: Should AI-managed sources have different default frequencies compared to standard sources?

---
*Created by Cursor Agent (MED13 Foundation)*
