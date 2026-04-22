# **MED13 Curation Dashboard – User Experience Design Overview**

> **Legacy Notice**: The Dash-based curator experience described below has been retired in favor of the unified Next.js admin interface. This document is retained for historical reference.

## **1. Purpose & Vision**

The MED13 Curation Dashboard is designed as a **clinical reasoning workspace**, not a data-management tool. Its goal is to make variant and phenotype curation intuitive, visually clear, and scientifically rigorous. The interface turns evidence evaluation into an engaging, traceable process that reflects MED13 Foundation’s guiding UX principle:

> **“Scientific clarity with human warmth.”**

This means every interaction should balance precision, provenance, and empathy — supporting expert clinicians, curators, and data scientists alike.

---

## **2. Core UX Objectives**

### **Clarity and Focus**

* Prioritize context-rich information instead of raw IDs and codes.
* Use visual hierarchy (cards, tabs, badges) to guide expert attention.

### **Efficiency and Flow**

* Reduce cognitive load by using **progressive disclosure** — users see summaries first, then expand details as needed.
* Minimize clicks with clear default views and pre-filtered queues.

### **Transparency and Trust**

* Embed **provenance trails** and confidence indicators at every level.
* All decisions are auditable, logged, and reversible.

### **Empathy and Accessibility**

* Inclusive color palette (MED13 reds, teals, neutrals) and language that’s collaborative, not punitive (“Send for review” instead of “Reject”).
* WCAG AA compliant visuals and bilingual readiness (English/Spanish).

---

## **3. Core Interface Components**

### **A. Variant Review Cards (Queue View)**

Replaces static tables with **clinical review cards** displaying essential information:

* Variant ID, gene, and confidence score at a glance.
* Phenotype badges (HPO terms) and evidence pills summarizing source counts.
* Quick actions: *Approve*, *Send for Review*, *Flag for Discussion*.

Hovering expands each card to show an evidence preview without navigating away. This allows curators to triage rapidly.

### **B. Multi-Panel Clinical Viewer**

When a variant is selected, users enter a **tabbed evidence viewer**:

* **Summary Tab** – overview of significance, confidence, and source counts.
* **Evidence Analysis** – side-by-side matrix comparing ClinVar, Orphanet, and internal curation.
* **Phenotype Associations** – frequency and co-occurrence heatmaps.
* **Literature** – linked PubMed abstracts with highlight excerpts.
* **Conflict Resolution** – timeline of conflicting interpretations with decision tools.

Each tab is self-contained and lazy-loaded to improve performance.

### **C. Conflict Resolution Panel**

A dedicated panel highlights discrepancies:

* Color-coded conflict badges (red, yellow, orange) indicate disagreement level.
* Each conflict includes source details and evidence summary.
* Users can choose resolution paths: *Accept*, *Override*, or *Flag for Expert Review*.
* A **Conflict Timeline** shows when discrepancies arose and were resolved.

### **D. Expert Annotation & Audit Drawer**

A right-hand drawer tracks expert commentary and logs every action:

* Annotation form for rationale, supporting references, and confidence override.
* Each note becomes a permanent part of the variant’s audit trail.
* Activity timeline shows who made which decision and when.

### **E. Smart Queue Filters**

A collapsible filter accordion enables precise triage:

* Filter by significance (pathogenic, uncertain, benign).
* Set thresholds for confidence and evidence level.
* Filter by phenotype or conflict status.
* A “My Queue” view shows cases assigned to the current curator.

### **F. Analytics & Progress Dashboard**

A top-level dashboard provides feedback loops:

* Progress gauge (variants reviewed vs. pending).
* Conflict resolution rate and curator workload metrics.
* Recent activities and pending high-priority items.

---

## **4. Visual System**

### **Color & Typography**

| Element                   | Color                                   | Purpose                |
| :------------------------ | :-------------------------------------- | :--------------------- |
| Pathogenic                | #C0392B                                 | Red – high severity    |
| Likely Benign             | #1ABC9C                                 | Teal – safe zone       |
| Uncertain                 | #F1C40F                                 | Gold – requires review |
| Confidence (High/Med/Low) | Green/Yellow/Red                        | Gauge clarity          |
| Typography                | Inter (sans-serif), Lora (serif titles) | Readability + trust    |

### **Layout Principles**

* **Grid-based structure** with high whitespace ratio for focus.
* **Cards over tables** – visual summaries instead of dense data grids.
* **Responsive design** – optimized for 13” laptops and tablets.

---

## **5. UX Advantages Over Traditional Dashboards**

| Category              | Old Model                  | MED13 Curation UX                                                          |
| :-------------------- | :------------------------- | :------------------------------------------------------------------------- |
| **Information Load**  | Dense tables, unstructured | Hierarchical cards and panels with summary-first approach                  |
| **Decision Context**  | Data detached from meaning | Context-rich cards show gene, phenotype, and evidence strength immediately |
| **Workflow Guidance** | Manual tracking            | Built-in audit drawer, progress gauges, and smart queue filters            |
| **Conflict Handling** | Static alerts              | Visual conflict timeline and resolution tools                              |
| **User Psychology**   | Bureaucratic task          | Empowering clinical reasoning interface                                    |

## **5.5 Technical Feasibility Assessment**

### **High Feasibility Components** ✅
- **Framework Alignment:** Plotly Dash + Bootstrap Components matches existing tech stack
- **Data Availability:** Domain entities contain rich clinical data (evidence levels, confidence scores, phenotypes)
- **API Integration:** FastAPI backend can extend current endpoints
- **Security:** OAuth2/JWT authentication aligns with current implementation

### **Implementation Challenges** ⚠️
- **Data Richness:** Current transformed data is minimal; requires richer clinical datasets
- **Conflict Algorithms:** New logic needed for evidence comparison and discrepancy detection
- **Performance:** Lazy-loading required for large datasets with multi-panel views
- **Audit Storage:** Current review system lacks detailed annotation persistence

---

## **6. Implementation Priority Roadmap**

### **Phase 1: Core Clinical Context (Weeks 1-3)**
1. **Variant Review Cards** - Replace table with clinical cards showing gene, significance, confidence
2. **Basic Clinical Viewer** - Summary tab with essential clinical information
3. **Smart Filters** - Clinical significance, confidence thresholds, phenotype filters

### **Phase 2: Evidence Analysis (Weeks 4-6)**
4. **Evidence Comparison Panel** - Side-by-side source comparison
5. **Conflict Detection** - Basic conflict identification and badges
6. **Annotation System** - Expert commentary and rationale capture

### **Phase 3: Advanced Features (Weeks 7-8)**
7. **Conflict Resolution Tools** - Interactive resolution workflows
8. **Audit Timeline** - Complete decision history visualization
9. **Progress Analytics** - Curation metrics and workload tracking

---

## **6.5 Operational Workflow (Back-End + UI Contract)**

To deliver the enhanced experience, the curation dashboard will consume a single **Curated Record Detail** payload produced by new back-end services and rendered through the Dash component stack.

### **System Flow**
1. **Queue Selection**
   Reviewer selects a card in the review queue. Dash emits a detail request to FastAPI.
2. **Detail Aggregation**
   FastAPI resolves the `CurationDetailService`, which:
   * Pulls primary entities (variant, linked phenotypes, evidence) through existing application services.
   * Invokes the new `ConflictDetector` to generate structured conflict summaries and severity levels.
   * Packages provenance, audit state, and recommended actions into a typed DTO.
3. **Payload Serialization**
   Route serializer converts the DTO into JSON shaped for the front end:
   ```json
   {
     "variant": {...},
     "phenotypes": [...],
     "evidence": [...],
     "conflicts": [...],
     "provenance": {...},
     "audit": {...}
   }
   ```
4. **Dash Rendering**
   The payload is cached in a `dcc.Store` and handed to:
   * `clinical_viewer` – summary + provenance display.
   * `evidence_comparison` – source-by-source comparison matrix.
   * `conflict_panel` – badges, severity, and available resolution actions.
5. **Reviewer Action**
   Resolution actions (approve, override, requeue) POST back to `/curation/.../decisions`, which records outcomes through the existing `ReviewService`, emits domain events, and updates audit history.

### **Key New Modules**
```python
src/application/curation/
├── conflict_detector.py        # Evidence & significance reconciliation
├── services/
│   └── detail_service.py       # Aggregates curated record payloads
└── dto.py                      # Typed response objects for curation detail

src/routes/
└── curation.py                 # Adds GET /curation/{entity_type}/{entity_id}

src/presentation/dash/components/curation/
├── clinical_viewer.py
├── evidence_comparison.py
└── conflict_panel.py
```

### **Data Contract Highlights**
* **ConflictSummary** – `{ "kind": "clinical_significance", "severity": "high", "evidence_ids": [...], "message": "Pathogenic vs benign interpretations" }`
* **EvidenceSnapshot** – normalized representation combining level, source, assertions, confidence score, and supporting references.
* **AuditInfo** – reviewer assignments, last decision, outstanding tasks, and link to annotation history.

This workflow enforces separation of concerns: heavy analysis lives in the application layer, the API exposes a consistent contract, and Dash focuses solely on rendering and user interaction.

### **Local Demo Seed**

Run `make db-seed` to populate a demo MED13 variant with linked phenotypes, evidence, review metadata, and an audit comment. The script (`scripts/seed_database.py`) is idempotent and ensures the curation dashboard always has illustrative data when developing locally.

---

## **7. Enhanced Visual System & Components**

### **Expanded Color & Typography**

| Element                   | Color                                   | Purpose                |
| :------------------------ | :-------------------------------------- | :--------------------- |
| Pathogenic                | #C0392B                                 | Red – high severity    |
| Likely Pathogenic         | #E74C3C                                 | Red-orange – high risk |
| Uncertain                 | #F1C40F                                 | Gold – requires review |
| Likely Benign             | #27AE60                                 | Green – moderate safe  |
| Benign                    | #1ABC9C                                 | Teal – safe zone       |
| **Evidence Levels**       |                                        |                       |
| Definitive                | #2C3E50                                 | Dark blue – strongest  |
| Strong                    | #34495E                                 | Blue – robust          |
| Supporting                | #7F8C8D                                 | Gray – moderate        |
| Limited                   | #BDC3C7                                 | Light gray – weakest   |
| **Conflict Indicators**   |                                        |                       |
| High Conflict             | #E74C3C                                 | Red – urgent attention |
| Medium Conflict           | #F39C12                                 | Orange – review needed |
| Low Conflict              | #F1C40F                                 | Yellow – monitor       |
| Typography                | Inter (sans-serif), Lora (serif titles) | Readability + trust    |

### **Component Architecture**

```python
# Proposed component structure for implementation
src/presentation/dash/components/curation/
├── clinical_card.py          # Review card component
├── evidence_matrix.py        # Comparison matrix
├── conflict_panel.py         # Resolution interface
├── annotation_drawer.py      # Expert notes
├── confidence_gauge.py       # Visual confidence meter
└── progress_analytics.py     # Dashboard metrics
```

### **Enhanced Data Visualizations**

#### **Evidence Strength Heatmap**
```python
def create_evidence_heatmap():
    """Visualize evidence strength across multiple dimensions"""
    return go.Figure(data=go.Heatmap(
        z=[[1, 0.8, 0.6], [0.9, 1, 0.4], [0.7, 0.5, 1]],
        x=['ClinVar', 'PubMed', 'Internal'],
        y=['Pathogenic', 'Uncertain', 'Benign'],
        colorscale='RdYlGn'
    ))
```

#### **Conflict Detection Specificity**
- **Inter-source conflicts** (ClinVar vs PubMed)
- **Intra-source conflicts** (multiple ClinVar submissions)
- **Temporal conflicts** (evidence evolution over time)
- **Methodological conflicts** (functional vs population studies)

### **Layout Principles**
* **Grid-based structure** with high whitespace ratio for focus.
* **Cards over tables** – visual summaries instead of dense data grids.
* **Responsive design** – optimized for 13" laptops and tablets.
* **Mobile optimization** – tablet support for field/clinic curation with touch interactions.

---

## **8. Integration with Phase 0 Architecture**

* **Framework:** Plotly Dash + Bootstrap Components matches existing tech stack.
* **Backend:** FastAPI endpoints extend current architecture for clinical data retrieval.
* **Frontend:** Embedded seamlessly under `med13foundation.org/curation` (Next.js shell).
* **Security:** OAuth2/SSO authentication with JWT-based role enforcement.
* **Logging:** Every curator interaction logged to `/api/audit/log` in real time.
* **External Integrations:** Direct links to genome browsers (UCSC, Ensembl), variant databases (gnomAD, ClinVar), and literature tools (PubMed, Google Scholar).

This integration ensures curation stays modular, secure, and maintainable while sharing a unified brand experience.

---

## **9. Accessibility & Internationalization**

* **WCAG AA** compliant color contrast and keyboard navigation.
* **Spanish localization** (`react-intl` and Dash translation hooks) for bilingual inclusivity.
* **Screen-reader-friendly labels** on all buttons and charts.
* **Tablet optimization** for field work and clinical settings with touch-based interactions.

---

## **10. Emotional Design & User Empowerment**

* **Confidence Meter:** Converts abstract statistics into emotional reassurance for curators.
* **Conflict Resolution Animation:** Glows softly when evidence conflicts are reconciled, symbolizing scientific progress.
* **Progress Bar:** Reinforces community impact ("80% of MED13 variants reviewed this quarter").
* **Tone of Voice:** Encouraging and human ("Ready for expert review") instead of judgmental ("Incomplete data").
* **Expert Validation:** Visual feedback when clinical decisions align with evidence strength.

---

## **11. Final Assessment & Recommendations**

### **Overall Rating: 9/10** ⭐⭐⭐⭐⭐⭐⭐⭐⭐

**Exceptional clinical workflow understanding with strong technical alignment.**

### **Strengths** ✅
- **Deep clinical insight** into curation challenges and expert needs
- **Progressive disclosure** reduces cognitive load effectively
- **Human-centered design** balances precision with empathy
- **Technical feasibility** within existing Plotly Dash architecture
- **Comprehensive conflict handling** addresses real evidence discrepancies

### **Key Recommendations** 🎯
1. **Immediate Priority:** Implement Phase 1 clinical cards to replace current table view
2. **Data Enhancement:** Expand transformed datasets with richer clinical information
3. **Mobile Support:** Add tablet optimization for field/clinic curation workflows
4. **External Links:** Integrate direct connections to genomic and literature resources

### **Expected Impact** 📈
This interface transforms curation from a **repetitive data review task** into an **engaging clinical reasoning experience**, significantly improving curation efficiency, decision quality, and expert satisfaction.

By combining thoughtful design, expert workflows, and emotional intelligence, the MED13 Curation Dashboard becomes a model for FAIR-compliant, clinician-empowering research interfaces.
