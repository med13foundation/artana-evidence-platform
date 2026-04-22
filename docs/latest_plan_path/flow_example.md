Here's a complete walkthrough using two papers that both mention the same MED13-phenotype connection, showing how evidence accumulates and the graph strengthens over time.

---

## The scenario

A researcher has a research space called **"MED13 Cardiac Study"**. Two PubMed papers come in on separate ingestion runs:

> **Paper A** (PMID 39012345) — *"Heterozygous MED13 variants cause dilated cardiomyopathy via Wnt signaling disruption"*
>
> **Paper B** (PMID 39098765) — *"Cardiac phenotyping of MED13 loss-of-function in a zebrafish model reveals cardiomyopathy and arrhythmia"*

---

## Tier 1 — Source Ingestion (Paper A)

1. Scheduler fires `PubMedIngestionService`.
2. `PubMedSourceGateway` fetches MEDLINE XML for PMID 39012345.
3. `source_record_ledger` — new PMID, passes through.
4. Raw record persisted to blob storage.
5. `source_documents` row created: `enrichment_status = PENDING`.

---

## Tier 2 — Content Enrichment (Paper A)

Content Enrichment Agent picks up the document:

> "PMC ID present (PMC10234567), in the OA subset."

1. Fetches full text from PMC OA API (~8,000 words).
2. Writes to blob: `StorageUseCase.DOCUMENT_CONTENT`.
3. Updates row: `enrichment_status = ENRICHED`, `enrichment_method = pmc_oa`.

---

## Tier 3 — Knowledge Extraction (Paper A)

### Entity Recognition Agent

> All `dictionary_search`, `create_*`, and `create_synonym` calls below are
> provided by the **Semantic Layer** (`DictionaryManagementService`).  The agent
> does not implement search or creation logic — it composes calls to the
> centralized service.

The agent reads the Results section:

> *"Patient III-2 carried a heterozygous c.1366C>T (p.Arg456Trp) variant in MED13 and presented with dilated cardiomyopathy (DCM) and an ejection fraction of 28%."*

**Phase 1 — Identify entity types needed:**

The agent searches `dictionary_search(["PATIENT", "GENE", "VARIANT", "PHENOTYPE"], dimensions=["entity_types"])`.

All four exist (seeded for genomics). No creation needed.

**Phase 2 — Identify variables needed:**

For "ejection fraction", the agent searches `dictionary_search(["ejection fraction"], dimensions=["variables"])`.

Hit: `VAR_EJECTION_FRACTION` — exact synonym match, score 1.0. Map.

For "dilated cardiomyopathy", the agent searches `dictionary_search(["dilated cardiomyopathy", "DCM", "HP:0001644"])`.

| Strategy | Result |
|---|---|
| Exact | No hit |
| Synonym | No hit |
| Fuzzy | `VAR_CARDIOMYOPATHY` — score 0.52 (partial match) |
| Vector | `VAR_CARDIOMYOPATHY` — description says *"Structural or functional abnormality of the heart muscle"* — cosine 0.81 |

The agent reads the description and reasons:

> "DCM is a specific subtype of cardiomyopathy. The existing variable is the parent category. I should create a more specific entry."

Calls `create_variable(...)`:

| Field | Value |
|---|---|
| `id` | `VAR_DILATED_CARDIOMYOPATHY` |
| `canonical_name` | `dilated_cardiomyopathy` |
| `display_name` | `Dilated Cardiomyopathy` |
| `data_type` | `CODED` |
| `domain_context` | `clinical` |
| `description` | `"Dilated cardiomyopathy (DCM) — a myocardial disorder characterised by ventricular dilation and impaired systolic function. HPO: HP:0001644."` |

Calls `create_synonym("VAR_DILATED_CARDIOMYOPATHY", "DCM", "ai_mapped")`.

Entry is **immediately active**. Logged with `created_by = "agent:agent_run_001"`.

**Phase 3 — Identify relation types needed:**

The text says MED13 variants "cause" cardiomyopathy. The agent searches `dictionary_search(["CAUSES"], dimensions=["relation_types"])`.

Hit: `CAUSES` exists (seeded). And `relation_constraints` has `VARIANT → CAUSES → PHENOTYPE` already. No creation needed.

But the text also says this happens "via Wnt signaling disruption". The agent searches `dictionary_search(["disrupts", "disruption", "DISRUPTS"], dimensions=["relation_types"])`.

No hit. The agent calls:

```
create_relation_type(
  id="DISRUPTS",
  description="A causal mechanism where one entity impairs or
               interferes with the normal function of another",
  is_directional=True,
  inverse_label="DISRUPTED_BY",
  domain_context="genomics"
)
```

Then registers the constraint:

```
create_relation_constraint(
  source_type="VARIANT",
  relation_type="DISRUPTS",
  target_type="PATHWAY",
  requires_evidence=True
)
```

Both immediately active, logged with provenance.

The agent also checks for "Wnt signaling" as an entity. Searches entity types — `PATHWAY` exists. Creates the entity if it doesn't exist in the graph yet.

---

### Extraction Agent

Using the resolved mappings, extracts:

**Observation 1:**

| Field | Value | Confidence |
|---|---|---|
| subject | PATIENT entity "III-2" | |
| variable | `VAR_DILATED_CARDIOMYOPATHY` | |
| value_coded | `"present"` | 0.95 |

**Observation 2:**

| Field | Value | Confidence |
|---|---|---|
| subject | PATIENT entity "III-2" | |
| variable | `VAR_EJECTION_FRACTION` | |
| value_numeric | `28` | 0.97 |
| unit | `%` | |

**Relation 1:**

| Source | Type | Target | Confidence |
|---|---|---|---|
| VARIANT c.1366C>T | `CAUSES` | PHENOTYPE dilated_cardiomyopathy | 0.88 |

**Relation 2:**

| Source | Type | Target | Confidence |
|---|---|---|---|
| VARIANT c.1366C>T | `DISRUPTS` | PATHWAY Wnt_signaling | 0.82 |

**Relation 3:**

| Source | Type | Target | Confidence |
|---|---|---|---|
| GENE MED13 | `ASSOCIATED_WITH` | PHENOTYPE dilated_cardiomyopathy | 0.91 |

---

### Governance Layer (`GovernanceService.evaluate()`)

All extraction outputs are routed through the centralized **Governance Layer**:

| Output | Confidence | Action |
|---|---|---|
| Obs: DCM present | 0.95 | Auto-approve |
| Obs: EF = 28% | 0.97 | Auto-approve |
| Rel: variant CAUSES DCM | 0.88 | Forward + queue for review |
| Rel: variant DISRUPTS Wnt | 0.82 | Forward + queue for review |
| Rel: MED13 ASSOCIATED_WITH DCM | 0.91 | Auto-approve |
| Dict: `VAR_DILATED_CARDIOMYOPATHY` | — | Flows through, audit log |
| Dict: `DISRUPTS` relation type | — | Flows through, audit log |

All review items enter the **centralized review queue** — the same queue that
curators use for Graph Connection Agent proposals and Dictionary audits.

---

### Kernel Pipeline (consuming Identity, Semantic, and Truth Layers)

For each approved output, the pipeline delegates to the Intelligence Layers:

- **Identity Layer** (`EntityResolutionService.resolve`) resolves entity mentions
  to kernel entities (GENE MED13, VARIANT c.1366C>T, etc.).
- **Semantic Layer** (`DictionaryManagementService.validate_observation`) validates
  observations against variable constraints.
- **Truth Layer** creates claim-backed projections through the relation
  materialization flow. Claims and claim evidence are written first; canonical
  relations are then rebuilt as projections and `relation_evidence` is refreshed
  as a derived cache from support-claim evidence:

**Relation 1** (variant CAUSES DCM):

- Create support claim + `claim_evidence` from Paper A.
- Materializer checks whether `(variant_c1366CT, CAUSES, phenotype_dcm, space_123)` already has a projected canonical relation. **No.**
- Create canonical edge plus one `relation_projection_sources` row back to the claim.
- Rebuild derived `relation_evidence` cache from the claim evidence.
- Status: `DRAFT` (only 1 supporting claim/document, not enough for auto-promotion)

**Relation 3** (MED13 ASSOCIATED_WITH DCM):

- Create support claim + `claim_evidence` from Paper A.
- Materializer creates the first canonical projected relation for `(gene_med13, ASSOCIATED_WITH, phenotype_dcm, space_123)`.
- `relation_evidence` now contains one derived cache row copied from the support claim evidence.
- Status: `DRAFT`

---

## Two weeks later — Paper B arrives

Tier 1 and Tier 2 proceed as before. Now the Knowledge Extraction Pipeline processes Paper B.

### Entity Recognition Agent

Paper B's text:

> *"MED13 loss-of-function zebrafish develop dilated cardiomyopathy and cardiac arrhythmia by 72 hours post-fertilization."*

The agent searches `dictionary_search(["dilated cardiomyopathy", "DCM"])`.

Hit: `VAR_DILATED_CARDIOMYOPATHY` — **exact synonym** match on "DCM" (registered by Paper A's agent run). Score 1.0. No creation needed.

For "cardiac arrhythmia", the agent searches. No match found. Creates `VAR_CARDIAC_ARRHYTHMIA` with description and registers "arrhythmia" as synonym.

All entity types and relation types already exist. The agent also confirms `GENE → ASSOCIATED_WITH → PHENOTYPE` constraint exists. No new types or constraints needed — Paper A's agent run already set everything up.

---

### Extraction Agent

Extracts:

**Relation 1** (from Paper B):

| Source | Type | Target | Confidence |
|---|---|---|---|
| GENE MED13 | `ASSOCIATED_WITH` | PHENOTYPE dilated_cardiomyopathy | 0.93 |

**Relation 2** (new):

| Source | Type | Target | Confidence |
|---|---|---|---|
| GENE MED13 | `ASSOCIATED_WITH` | PHENOTYPE cardiac_arrhythmia | 0.87 |

---

### Kernel Pipeline — Projection Rebuild and Derived Evidence (via Truth Layer)

The **Truth Layer** handles claim-backed projection rebuilds and derived
evidence-cache refreshes:

**Relation 1** (MED13 ASSOCIATED_WITH DCM):

- Check: does `(gene_med13, ASSOCIATED_WITH, phenotype_dcm, space_123)` exist? **Yes** (from Paper A).
- Create a second support claim + `claim_evidence` for the same triple.
- Materializer reuses the existing canonical relation via projection lineage.
- Rebuild derived `relation_evidence` cache from both support claims, producing cache row #2 from PMID 39098765.
- Recompute: `aggregate_confidence = 1 - (1-0.91)(1-0.93) = 1 - 0.0063 = 0.9937`
- Update: `source_count = 2`, `highest_evidence_tier = LITERATURE`

**Auto-promotion check** (via `EvidenceAggregationService.should_auto_promote`):
- `source_count = 2` AND `aggregate_confidence = 0.9937 >= 0.95` → **auto-promote to `APPROVED`**

The MED13 → DCM connection is now `APPROVED` — no curator intervention needed. Two independent papers confirmed it with high confidence.

**Relation 2** (MED13 ASSOCIATED_WITH arrhythmia):

- New support claim materializes a new canonical projected relation with one derived evidence row.
- Status: `DRAFT` (only 1 source)

---

## Graph Connection Agent (runs after extraction)

> Graph query tools are provided by the **Graph Query Port**, Dictionary search
> by the **Semantic Layer**, and relation upserts by the **Truth Layer**.  The
> Governance Layer routes outputs by confidence.

The agent detects new entities in the MED13 neighbourhood and analyses:

> "MED13 is ASSOCIATED_WITH dilated_cardiomyopathy (2 sources, 0.99 confidence, APPROVED).
> MED13 is ASSOCIATED_WITH cardiac_arrhythmia (1 source, 0.87 confidence, DRAFT).
> The variant c.1366C>T DISRUPTS Wnt_signaling pathway.
>
> Question: is there a connection between Wnt_signaling and dilated_cardiomyopathy?"

The agent calls `graph_query_shared_subjects(pathway_wnt, phenotype_dcm)` — finds that the same variant links both.

The agent calls `dictionary_search(["mediates", "contributes to", "pathway involvement"], dimensions=["relation_types"])` — finds no exact match but `EXPLAINS` (from `MECHANISM → EXPLAINS → PHENOTYPE` constraint) is semantically close via vector search (cosine 0.74).

The agent reasons:

> "The Wnt pathway isn't a MECHANISM entity — it's a PATHWAY. But the data shows a causal chain: variant DISRUPTS Wnt_signaling AND variant CAUSES DCM. This suggests the pathway mediates the phenotype. I should use ASSOCIATED_WITH since the evidence is indirect."

Calls `upsert_relation(pathway_wnt, ASSOCIATED_WITH, phenotype_dcm, confidence=0.72, evidence_tier=COMPUTATIONAL, ...)`.

Creates a new canonical edge via the **Truth Layer** with `source_count = 1`, `evidence_tier = COMPUTATIONAL`, `curation_status = DRAFT`. The **Governance Layer** forwards it and queues for review (0.72 is in the review band).

---

## Graph Search Agent (researcher query)

> The Graph Search Agent uses the **Interface Layer** for intent parsing, the
> **Semantic Layer** for term resolution, and the **Graph Query Port** for
> structured queries.

The researcher types in the admin UI:

> "What phenotypes are associated with MED13?"

The Graph Search Agent:

1. **Parses intent** (via Interface Layer): target = phenotypes linked to MED13 via any relation.
2. **Dictionary search** (via Semantic Layer): `dictionary_search(["MED13"])` → finds GENE entity "MED13".
3. **Graph traversal** (via Graph Query Port): `graph_query_relations(gene_med13, direction="outgoing", depth=1)`.
4. **Results**:

| Phenotype | Relation | Aggregate Confidence | Sources | Status | Evidence |
|---|---|---|---|---|---|
| Dilated Cardiomyopathy | ASSOCIATED_WITH | **0.9937** | **2** | **APPROVED** | PMID 39012345, PMID 39098765 |
| Cardiac Arrhythmia | ASSOCIATED_WITH | 0.87 | 1 | DRAFT | PMID 39098765 |

5. **Synthesised response**:

> "MED13 is associated with 2 phenotypes. **Dilated cardiomyopathy** has strong evidence (2 independent papers, 99.4% confidence, approved). **Cardiac arrhythmia** has preliminary evidence (1 paper, 87% confidence, pending review). Additionally, a computational analysis suggests Wnt signaling disruption may mediate the cardiomyopathy phenotype (72% confidence, pending curator review)."

---

## What the curator sees in the admin UI

| View | What's there |
|---|---|
| **Agent-Created Definitions** | `VAR_DILATED_CARDIOMYOPATHY`, `VAR_CARDIAC_ARRHYTHMIA` — with rationale and evidence for each |
| **Agent-Created Types** | Relation type `DISRUPTS` — with description and domain context |
| **Relations: Approved** | MED13 → ASSOCIATED_WITH → DCM (2 sources, auto-promoted) |
| **Relations: Pending Review** | MED13 → ASSOCIATED_WITH → Arrhythmia (1 source, 0.87) |
| **Relations: Pending Review** | Variant → CAUSES → DCM (1 source, 0.88) |
| **Relations: Pending Review** | Wnt → ASSOCIATED_WITH → DCM (computational, 0.72) |

The curator's highest-priority review items are the **weakest signals** — the computational connection and the single-source relations. The strong 2-source connection promoted itself automatically.

---

## The key takeaways

1. **Universal Dictionary via Semantic Layer** — the agent created a new relation type (`DISRUPTS`) and its constraint on the fly, without code changes, through the centralized `DictionaryManagementService`. The same mechanism works for `PLAYS_FOR` in a sports domain.

2. **Evidence accumulation via Truth Layer** — Paper B didn't create a duplicate edge. The `EvidenceAggregationService` strengthened the existing MED13→DCM connection from 0.91 (1 source, DRAFT) to 0.9937 (2 sources, auto-APPROVED).

3. **Graph Connection Agent** — discovered an implicit pathway→phenotype link that no single paper stated, using cross-document reasoning on the populated graph. Used the same Semantic Layer and Governance Layer as the extraction agents.

4. **Graph Search Agent** — translated a natural language question into a structured graph traversal via the Interface Layer, returning results ranked by evidence strength.

5. **Curator efficiency via Governance Layer** — the auto-promotion threshold eliminated review work for the strongest connection. The centralized review queue shows the curator the 3 weaker edges that need human judgment — regardless of which agent produced them.

---
---

# Example 2: MLB Baseball — A Completely Different Domain

This example demonstrates that the **exact same platform, pipeline, and agent
strategy** handles a sports analytics domain with zero code changes.  Only the
Dictionary content differs.

---

## The scenario

A sports analytics researcher creates a research space called **"MLB 2025
Season Analysis"**.  They configure two data sources:

- **Source A** — A CSV file upload: `mlb_2025_batting_stats.csv` containing
  season batting statistics for all MLB players.
- **Source B** — A web-scraped JSON feed: ESPN trade tracker with player
  transaction records from the 2025 season.

The Dictionary starts with **no sports-related entries** — only the genomics
and clinical seeds from the MED13 study.

---

## Tier 1 — Source Ingestion (CSV upload)

1. The researcher uploads `mlb_2025_batting_stats.csv` via the admin UI.
2. `IngestionSchedulingService` dispatches to `FileUploadIngestionService`.
3. The CSV is parsed into raw records — one per player row.
4. Each record is persisted to blob storage (`StorageUseCase.RAW_SOURCE`).
5. `source_documents` rows created: one per player record, `enrichment_status = PENDING`.

**Sample raw record:**

```json
{
  "player_name": "Mike Trout",
  "team": "Los Angeles Angels",
  "games_played": 142,
  "at_bats": 524,
  "hits": 161,
  "home_runs": 34,
  "batting_average": 0.307,
  "rbi": 89,
  "stolen_bases": 12,
  "ops": 0.941
}
```

---

## Tier 2 — Content Enrichment (CSV — pass-through)

The Content Enrichment Agent picks up the documents and reasons:

> "These are structured CSV records — all data fields are already present.
> No full-text acquisition needed."

Decision: `pass_through`. Updates `enrichment_status = ENRICHED` immediately.

For the ESPN trade tracker data, the agent applies the same logic — structured
JSON, pass-through.

---

## Tier 3 — Knowledge Extraction (first run — cold Dictionary)

This is where the universal Dictionary shines.  The agent encounters a domain
with **no existing Dictionary entries**.

### Entity Recognition Agent

> All `dictionary_search`, `create_*`, and `create_synonym` calls below are
> provided by the **Semantic Layer** (`DictionaryManagementService`).  The agent
> bootstraps an entire domain's Dictionary content through the same centralized
> service used by the MED13 genomics agents — no code changes needed.

The agent reads the first record (Mike Trout) and starts identifying what the
Dictionary needs.

**Phase 1 — Entity types:**

The agent searches `dictionary_search(["player", "team"], dimensions=["entity_types"])`.

No hits.  The Dictionary has `GENE`, `VARIANT`, `PHENOTYPE`, `PATIENT`,
`PUBLICATION`, etc. — but nothing for sports.

The agent calls `dictionary_search_by_domain("sports")` — empty.  This is a
brand new domain.

First, it creates the domain context (if not already in `dictionary_domain_contexts`):

```
create_domain_context(
  id="sports",
  display_name="Sports Analytics",
  description="Performance metrics, roster management, and competitive
               analysis for professional and amateur sports"
)
```

Then creates entity types:

```
create_entity_type(
  id="PLAYER",
  description="A professional athlete who competes in organised sports.
               Identified by league-issued player ID or name + team.",
  domain_context="sports",
  resolution_policy="LOOKUP",
  required_anchors=["player_id"]
)

create_entity_type(
  id="TEAM",
  description="A professional sports team or franchise.
               Identified by official team name or league abbreviation.",
  domain_context="sports",
  resolution_policy="LOOKUP",
  required_anchors=["team_code"]
)

create_entity_type(
  id="LEAGUE",
  description="A professional sports league governing competition
               and player transactions (e.g. MLB, NFL, NBA).",
  domain_context="sports",
  resolution_policy="STRICT_MATCH",
  required_anchors=["league_code"]
)

create_entity_type(
  id="SEASON",
  description="A specific competitive season within a league (e.g. MLB 2025).",
  domain_context="sports",
  resolution_policy="STRICT_MATCH",
  required_anchors=["league_code", "year"]
)
```

All immediately active.  Logged with `created_by = "agent:agent_run_sports_001"`.

**Phase 2 — Relation types:**

The agent identifies relationships in the data.  A player is on a team.  Teams
compete in a league.  Stats are observed during a season.

Searches `dictionary_search(["plays for", "roster membership"], dimensions=["relation_types"])`.  No hits.

Creates:

```
create_relation_type(
  id="PLAYS_FOR",
  description="A roster/employment relationship: a player is currently
               on the active roster of a team.",
  is_directional=True,
  inverse_label="HAS_PLAYER",
  domain_context="sports"
)

create_relation_type(
  id="COMPETES_IN",
  description="Membership of a team or player in a league or division.",
  is_directional=True,
  inverse_label="INCLUDES",
  domain_context="sports"
)
```

Registers constraints:

```
create_relation_constraint("PLAYER", "PLAYS_FOR", "TEAM", requires_evidence=False)
create_relation_constraint("TEAM", "COMPETES_IN", "LEAGUE", requires_evidence=False)
create_relation_constraint("PLAYER", "COMPETES_IN", "SEASON", requires_evidence=False)
```

**Phase 3 — Variable definitions:**

The agent reads the CSV columns and searches the Dictionary for each one.
Nothing matches — these are all new sports metrics.

The agent calls `dictionary_search_by_domain("sports")` to learn conventions.
Since this is the first batch, it establishes the naming conventions:

```
create_variable(
  id="VAR_BATTING_AVERAGE",
  canonical_name="batting_average",
  display_name="Batting Average",
  data_type="FLOAT",
  preferred_unit=None,
  constraints={"min": 0.0, "max": 1.0, "precision": 3},
  domain_context="sports",
  sensitivity="PUBLIC",
  description="A batter's hits divided by at-bats, expressed as a
               three-decimal ratio. The primary measure of batting
               proficiency in baseball."
)

create_variable(
  id="VAR_HOME_RUNS",
  canonical_name="home_runs",
  display_name="Home Runs",
  data_type="INTEGER",
  preferred_unit=None,
  constraints={"min": 0, "max": 80},
  domain_context="sports",
  sensitivity="PUBLIC",
  description="Total number of home runs hit by a batter in a season
               or career segment."
)

create_variable(
  id="VAR_OPS",
  canonical_name="on_base_plus_slugging",
  display_name="On-Base Plus Slugging (OPS)",
  data_type="FLOAT",
  preferred_unit=None,
  constraints={"min": 0.0, "max": 2.0, "precision": 3},
  domain_context="sports",
  sensitivity="PUBLIC",
  description="Sum of on-base percentage and slugging percentage.
               A composite offensive performance metric in baseball."
)
```

And similarly for `VAR_GAMES_PLAYED`, `VAR_AT_BATS`, `VAR_HITS`, `VAR_RBI`,
`VAR_STOLEN_BASES`.  Each with proper constraints and descriptions.

Registers synonyms:

```
create_synonym("VAR_BATTING_AVERAGE", "avg", "ai_mapped")
create_synonym("VAR_BATTING_AVERAGE", "ba", "ai_mapped")
create_synonym("VAR_HOME_RUNS", "hr", "ai_mapped")
create_synonym("VAR_ON_BASE_PLUS_SLUGGING", "ops", "ai_mapped")
create_synonym("VAR_RBI", "runs batted in", "ai_mapped")
```

**After the first record, the Dictionary now has all the scaffolding.**  The
remaining 800+ player records will hit **exact synonym matches** for every
field — no more agent reasoning needed for the same columns.

---

### Extraction Agent

For Mike Trout's record:

**Entities created/resolved:**

| Entity | Type | Resolution |
|---|---|---|
| Mike Trout | `PLAYER` | New entity (first time seen) |
| Los Angeles Angels | `TEAM` | New entity |
| MLB | `LEAGUE` | New entity |

**Relations (canonical upsert):**

| Source | Type | Target | Confidence |
|---|---|---|---|
| PLAYER Mike Trout | `PLAYS_FOR` | TEAM Los Angeles Angels | 0.99 |
| TEAM Los Angeles Angels | `COMPETES_IN` | LEAGUE MLB | 0.99 |

**Observations:**

| Subject | Variable | Value | Confidence |
|---|---|---|---|
| PLAYER Mike Trout | `VAR_BATTING_AVERAGE` | 0.307 | 1.0 |
| PLAYER Mike Trout | `VAR_HOME_RUNS` | 34 | 1.0 |
| PLAYER Mike Trout | `VAR_OPS` | 0.941 | 1.0 |
| PLAYER Mike Trout | `VAR_GAMES_PLAYED` | 142 | 1.0 |
| PLAYER Mike Trout | `VAR_AT_BATS` | 524 | 1.0 |
| PLAYER Mike Trout | `VAR_HITS` | 161 | 1.0 |
| PLAYER Mike Trout | `VAR_RBI` | 89 | 1.0 |
| PLAYER Mike Trout | `VAR_STOLEN_BASES` | 12 | 1.0 |

Confidence is 1.0 because the data is structured (CSV with explicit column
headers) — no NLP interpretation needed.

---

### Governance Layer

All outputs routed through `GovernanceService.evaluate()`:

All observations and relations: confidence >= 0.99 → **auto-approve**.
All Dictionary creations: flow through, visible in audit log.

The entire CSV batch processes without a single human intervention.

---

## Source B arrives — ESPN Trade Tracker

A week later, the ESPN trade tracker feed is ingested.  One record:

```json
{
  "transaction_type": "TRADE",
  "player": "Mike Trout",
  "from_team": "Los Angeles Angels",
  "to_team": "New York Yankees",
  "trade_date": "2025-07-31",
  "details": "Trout traded to Yankees for 3-player package.
              Angels receive two prospects and a draft pick."
}
```

### Entity Recognition Agent

The agent encounters "TRADE" as a concept.  Searches:

`dictionary_search(["trade", "player transaction"], dimensions=["relation_types"])`.

No hit.  Creates:

```
create_relation_type(
  id="TRADED_TO",
  description="A player transaction where a player moves from one team's
               roster to another via a formal trade agreement.",
  is_directional=True,
  inverse_label="ACQUIRED_VIA_TRADE",
  domain_context="sports"
)

create_relation_constraint("PLAYER", "TRADED_TO", "TEAM", requires_evidence=True)
```

Also creates `VAR_TRADE_DATE` (data_type `DATE`) as a variable.

### Extraction Agent

**Entities resolved:**

| Entity | Resolution |
|---|---|
| Mike Trout | Existing `PLAYER` entity (exact match on player_name) |
| Los Angeles Angels | Existing `TEAM` entity |
| New York Yankees | **New** `TEAM` entity |

**Relations:**

| Source | Type | Target | Confidence |
|---|---|---|---|
| PLAYER Mike Trout | `TRADED_TO` | TEAM New York Yankees | 0.96 |
| PLAYER Mike Trout | `PLAYS_FOR` | TEAM New York Yankees | 0.94 |

**Evidence accumulation on `PLAYS_FOR`:**

The existing `Mike Trout → PLAYS_FOR → Los Angeles Angels` edge now has
contradicting evidence (the trade).  The Extraction Agent does **not** upsert
onto the old edge — instead, it notes that the trade supersedes the previous
roster status.  The old `PLAYS_FOR` edge stays in the graph (historical record)
but the new `PLAYS_FOR → Yankees` edge reflects the current state.

> This is where `observed_at` on observations and `created_at` on relations
> matter — temporal ordering resolves which `PLAYS_FOR` is current.

---

## Graph Connection Agent

> Uses the **Semantic Layer** for Dictionary search, the **Graph Query Port** for
> neighbourhood queries, and the **Governance Layer** for output routing.

After both sources are ingested, the Graph Connection Agent analyses the
Yankees' neighbourhood:

> "Mike Trout (PLAYER) was TRADED_TO New York Yankees.
> Aaron Judge (PLAYER) PLAYS_FOR New York Yankees (from the batting stats).
> Both have observations for VAR_HOME_RUNS, VAR_OPS, VAR_BATTING_AVERAGE.
>
> Are these players connected beyond sharing a team?"

The agent calls `graph_query_shared_subjects(trout_id, judge_id)` — finds
they share the same `TEAM` entity (Yankees) and both have high `VAR_OPS`
observations.

The agent reasons:

> "These are teammates — this is a roster co-occurrence, not an analytical
> insight.  The `PLAYS_FOR` relation already captures this.  No new
> connection needed."

Decision: **skip** — insufficient novel evidence for a new relation.
`rejected_candidates` logs the reasoning.

However, the agent also notices:

> "Mike Trout has VAR_OPS = 0.941.  The top-10 OPS players in the dataset
> all hit 30+ home runs.  There's a strong correlation between VAR_OPS
> and VAR_HOME_RUNS across 150+ player observations."

This is a **statistical pattern**, not a single-document extraction.  The agent
could propose a `CORRELATES_WITH` relation between the two variables — but this
is better handled by a future statistical analysis tool than a graph edge.
The agent skips it and logs the observation for future consideration.

---

## Graph Search Agent

> Uses the **Interface Layer** for intent parsing, the **Semantic Layer** for
> term resolution, and the **Graph Query Port** for structured queries.

The researcher asks:

> "Which players had the highest OPS after being traded in 2025?"

The Graph Search Agent:

1. **Parses intent** (via Interface Layer): find PLAYERs with `TRADED_TO`
   relations AND high `VAR_OPS` observations, filtered to 2025 season.
2. **Dictionary search** (via Semantic Layer): `dictionary_search(["OPS", "traded"])` →
   finds `VAR_ON_BASE_PLUS_SLUGGING` (synonym "ops") and `TRADED_TO`
   (relation type).
3. **Query plan** (via Interface Layer):
   - Find all entities with a `TRADED_TO` relation (any target)
   - For those entities, get `VAR_OPS` observations
   - Rank by `value_numeric` descending
4. **Executes** graph queries.
5. **Returns**:

| Player | Traded To | OPS | Sources |
|---|---|---|---|
| Mike Trout | New York Yankees | 0.941 | batting_stats.csv, espn_trades.json |
| *(other traded players with their OPS...)* | | | |

---

## What the curator sees

| View | Contents |
|---|---|
| **Agent-Created Entity Types** | `PLAYER`, `TEAM`, `LEAGUE`, `SEASON` — all with descriptions and `sports` domain context |
| **Agent-Created Relation Types** | `PLAYS_FOR`, `COMPETES_IN`, `TRADED_TO` — with directionality, inverse labels |
| **Agent-Created Variables** | `VAR_BATTING_AVERAGE`, `VAR_HOME_RUNS`, `VAR_OPS`, `VAR_RBI`, `VAR_STOLEN_BASES`, `VAR_GAMES_PLAYED`, `VAR_AT_BATS`, `VAR_HITS`, `VAR_TRADE_DATE` |
| **Agent-Created Constraints** | `PLAYER→PLAYS_FOR→TEAM`, `TEAM→COMPETES_IN→LEAGUE`, `PLAYER→TRADED_TO→TEAM`, etc. |
| **Dictionary audit log** | All 20+ Dictionary entries created in a single run, each with rationale |

The curator can review all of this post-hoc.  If they decide `TRADED_TO` should
actually be called `TRANSFERRED_TO` for consistency, they rename the relation
type — all existing edges update automatically via the FK.

---

## The point

**Zero code changes.** The same platform — and the same **Intelligence Service
Layers** (Semantic, Identity, Truth, Governance, Interface) — that builds a
MED13 cardiac knowledge graph also builds an MLB analytics graph.  The only
difference is which Dictionary entries exist:

| Aspect | MED13 Cardiac Study | MLB 2025 Season |
|---|---|---|
| Entity types | GENE, VARIANT, PHENOTYPE, PATIENT | PLAYER, TEAM, LEAGUE, SEASON |
| Relation types | ASSOCIATED_WITH, CAUSES, DISRUPTS | PLAYS_FOR, COMPETES_IN, TRADED_TO |
| Variables | ejection_fraction, dilated_cardiomyopathy | batting_average, home_runs, ops |
| Constraints | GENE→ASSOCIATED_WITH→PHENOTYPE | PLAYER→PLAYS_FOR→TEAM |
| Domain context | `clinical`, `genomics` | `sports` |
| Evidence tiers | LITERATURE, EXPERIMENTAL | Structured data (confidence 1.0) |

The Dictionary is the schema.  The Semantic Layer manages it.  The agents fill
it in.  The Intelligence Layers and pipeline stay the same.
