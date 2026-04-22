# Artana Resource Library: Phase 0 – Developer Guide

## Overview

This document describes **Phase 0** of the MED13 Knowledge Base project. Phase 0 is a curated resource library that collects, cleans, and organizes all publicly available MED13-related data. The goal is **not** to build a final reasoning graph but to prepare high-quality, FAIR-compliant packages for Phase 1. These packages will feed into the TypeDB-based Knowledge Graph in later phases.

## Objectives

- **Aggregate validated information** about MED13 variants, phenotypes, and supporting evidence into a single, well-documented resource library
- **Normalize and clean data** from multiple sources, assign stable identifiers, and track provenance
- **Package data** following the FAIR principles (Findable, Accessible, Interoperable, Reusable) using the RO-Crate standard
- **Provide a simple internal curation interface** for subject-matter experts (SMEs) to review, annotate, and approve entries
- **Publish regular snapshots** (with DOIs) so researchers and clinicians can download and reuse the data
- **Acknowledge that Phase 0 is preparatory**; the relational store will be discarded or migrated in Phase 1 when the knowledge graph is built

## Data Sources

We compile data from trusted biomedical resources:

### ✅ Fully Obtainable (Open & Structured)
- **ClinVar / ClinGen**: variant interpretations and curation status
- **Human Phenotype Ontology (HPO)**: standard phenotype terms and hierarchies
- **PubMed / LitVar**: literature metadata linking MED13 variants to phenotypes
- **Orphanet**: gene-disease associations for rare disorders

### 🔄 Partially Obtainable (APIs)
- **UniProt, Gene Ontology, and GTEx**: gene function annotations, protein interactions, and tissue expression patterns
- **Crossref / Crossmark**: article metadata and retraction status
- **Other ontologies (GO, GG, DOID)**: additional biomedical context

### 🚧 Phase 1 Only (Requires Collaboration)
- **Functional studies, treatment outcomes, and natural history data**: extracted from case reports and clinical registries; placeholders exist but automated ingestion is deferred to Phase 1

*Each source is ingested via official APIs or bulk files to ensure reproducibility. Licensing metadata is recorded for every source to respect redistribution rights.*

## Additional Fields and Placeholders

To prepare for future expansions and Phase 1, the data model includes optional fields for scientific context and placeholders for clinical data.

### Gene Enhancements
Optional fields for:
- **Protein domains** and subcellular localization
- **Tissue expression patterns** (e.g., from GTEx)
- **Gene Ontology terms** and interacting proteins

*These enrich the genes table without impacting Phase 0 performance.*

### Evidence Placeholders
Optional fields such as `treatment_response`, `functional_studies`, and `patient_cohorts` in the evidence table serve as placeholders for Phase 1 data (treatment outcomes, experimental evidence, and cohort information) and remain empty in Phase 0.

## Technology Stack

| Layer | Tool | Rationale |
|-------|------|-----------|
| **ETL & Validation** | Python 3.12+, Pydantic v2 models, comprehensive quality assurance | Strong typing, strict validation, and automated testing with MyPy, Black, Ruff, Bandit |
| **Metadata Store** | SQLite (all environments) with SQLAlchemy 2.0 | Zero-configuration file-based database, ACID-compliant, perfect for MED13 data volumes, travels with Cloud Run deployment |
| **Packaging & Publishing** | RO-Crate (JSON-LD), Zenodo DOIs (future) | Ensures FAIR compliance and persistent identifiers |
| **API Layer** | FastAPI with OpenAPI docs, CORS enabled | REST API with automatic documentation, type-safe endpoints, deployed on Google Cloud Run |
| **Internal Curation UI** | Plotly Dash with Bootstrap components (Python) | Interactive dashboards for SME curation, integrated with the same codebase for simplicity |
| **Public Portal** | FastAPI-generated OpenAPI docs + custom frontend (future) | Current: Auto-generated docs; Future: Next.js/React for polished UX |
| **Quality Assurance** | MyPy, Black, Ruff, Flake8, Bandit, Pytest, Coverage, Pre-commit | Enterprise-grade code quality with automated linting, type checking, security scanning, and testing |



## Deployment Model – Single Service Architecture

Phase 0 uses a simplified, single-service architecture optimized for rapid development and cost efficiency:

### FastAPI Backend Service
Implements ETL jobs, validation, packaging, and provides REST endpoints. Deployed on Google Cloud Run with SQLite database included in the deployment. All authentication and RBAC live here.

### Key Architectural Decisions
- **SQLite Database**: File-based database travels with the Cloud Run deployment, eliminating database management overhead
- **Source Deployments**: Direct GitHub-to-Cloud Run deployment without Docker complexity
- **Quality Gates**: Comprehensive pre-commit and CI/CD quality assurance
- **Cost Optimization**: Serverless scaling with minimal infrastructure costs

### Future Frontend
Next.js/React portal will consume the API via HTTPS, providing polished UX and SEO optimization when needed.

## ETL Pipeline

The extraction-transformation-loading process comprises several stages:

### 1. 📥 Ingest
Download or query data from each source (ClinVar, HPO, PubMed, OMIM, etc.) and save raw files with timestamps.

### 2. 🔄 Transform
Normalize identifiers, parse records into Pydantic models, and map variant-phenotype-publication relations.

### 3. ✅ Validate
Run comprehensive checks:
- **Syntactic checks**: ID patterns and data formats
- **Completeness checks**: Row counts and required fields
- **Referential integrity**: Foreign key relationships
- **Transformation correctness**: Map ClinVar significance to evidence levels
- **Semantic checks**: Flag nonsensical phenotype links

### 4. 👥 Curate
Present new records in the internal dashboard for SME review; curators can approve or reject evidence and add comments.

### 5. 📦 Package
Generate RO-Crate packages that include cleaned tables, provenance metadata, licensing information, and a `licenses.yaml` manifest.

### 6. 🚀 Publish
Upload each release to Zenodo or a similar repository, mint a DOI, and update the public portal.
## Validation & Governance

### Governance Board
A small panel of clinical geneticists, bioinformaticians, and ethicists oversees curation policies and resolves disputes.

### Role-Based Access
- **Public users**: Can read data
- **Authenticated curators**: Can edit and validate records

### Audit Trail
Every curation action (approve/reject) logs the user ID, timestamp, and change in an audit table.

### Licensing Compliance
Each data source has a license entry specifying redistribution rules. Text or annotations from proprietary sources (OMIM, SNOMED) are never redistributed; only IDs and links are shared.

### Security Measures
- All services run behind HTTPS with OAuth2 authentication
- Data at rest uses encryption
- Backups and recovery procedures are documented

### User-Centered Design
Interviews with clinicians and researchers inform the dashboard workflow; usability is measured via standard surveys.

## Packaging & Attribution

### RO-Crate Metadata
The ETL pipeline creates a `ro-crate-metadata.json` file describing the dataset, authors, creation date, and context. It conforms to the RO-Crate 1.1 specification.

### Licenses File
A `licenses.yaml` file lists each source with fields: `license_name`, `license_url`, `attribution_text`, `redistribution_ok`, `commercial_ok`, `share_alike`, and `notes`. This ensures transparency and helps downstream users respect licensing.

### API Controls
The public API implements an `?include_text` flag:
- When `false` (default): Proprietary text is replaced with a notice
- When `true`: API returns full text only for sources that allow redistribution

## Phase 0 → Phase 1 Interface

Phase 0's output is **not** a direct database migration; it is a data export used as input for the Phase 1 knowledge graph.

### Export Process
- Each validated record is exported as structured JSON or CSV aligned with a draft TypeDB schema
- A `type_map.yaml` defines how Phase 0 fields map to TypeDB entities, attributes, and relations

### Phase 1 ETL
The Phase 1 ETL reads RO-Crates, applies the mapping, and loads data into TypeDB. There is no expectation of reusing Phase 0 SQL queries or repository classes.

### Benefits
This decoupling eliminates the conceptual mismatch between relational and graph models.

## Strategic Implementation

### Chosen Path
**SQLite-based resource library** with schema migration ready for Phase 1 knowledge graph.

### Rationale
SQLite provides zero-configuration deployment, ACID compliance, and perfect fit for MED13 data volumes while maintaining schema compatibility for future graph database migration. The file-based approach eliminates operational complexity and enables seamless Cloud Run deployments.

### Phase 1 Migration
RO-Crate exports will facilitate smooth transition to TypeDB or other graph databases when advanced reasoning capabilities are needed.

---

## Summary

The **Artana Resource Library (Phase 0)** consolidates high-quality information about MED13 into a FAIR-compliant package. It provides curated data to clinicians and researchers, records provenance and licensing, and prepares exports for the future graph-based discovery system. This foundation ensures that subsequent phases can focus on causal reasoning and AI-driven insights rather than basic data collection and cleaning.

---

*🏥 **MED13 Foundation** - Building the future of genetic medicine through open, collaborative data curation.*
