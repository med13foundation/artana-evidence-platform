# Evidence Selection Semantic Benchmark V2 Integrity Report

- Fixture provenance: **AI-adjudicated diagnostic**
- Existing expert-study gate status: **PENDING**
- Human/expert approval claim: **NO**
- Production readiness claim: **NO**
- Total visible records: `33`
- Score-eligible records: `0`
- Pending-expert records: `30`
- Ambiguous pending-expert records: `3`
- Canary gate: **UNAVAILABLE**

AI diagnostic categories, rationales, and evidence spans remain visible but are excluded from adoption metrics. Only labels derived through the existing real-shadow-review bundle and provenance gate can become score-eligible.

## Adoption Metrics

**UNAVAILABLE**: no primary records have sufficient, gate-verified human review evidence.

## Record Inventory

| Record | Role | AI diagnostic | Eligibility | Prediction |
| --- | --- | --- | --- | --- |
| `egfr:pmid:27959700` | primary | select | pending_expert | reject |
| `egfr:pmid:25923549` | primary | select | pending_expert | reject |
| `egfr:pmid:27393503` | primary | select | pending_expert | select |
| `egfr:pmid:41512290` | primary | reject | pending_expert | select |
| `egfr:pmid:30657347` | primary | reject | pending_expert | select |
| `egfr:pmid:26314834` | primary | reject | pending_expert | select |
| `egfr:pmid:31039766` | primary | reject | pending_expert | select |
| `egfr:pmid:23985030` | primary | reject | pending_expert | select |
| `brca1:pmid:40403695` | primary | select | pending_expert | reject |
| `brca1:pmid:22889855` | primary | select | pending_expert | reject |
| `brca1:pmid:26195121` | primary | select | pending_expert | select |
| `brca1:pmid:30191368` | primary | ambiguous | ambiguous_pending_expert | select |
| `brca1:pmid:40288678` | primary | select | pending_expert | select |
| `brca1:pmid:17018160` | primary | select | pending_expert | select |
| `brca1:pmid:34237702` | primary | reject | pending_expert | select |
| `brca1:pmid:21356067` | primary | reject | pending_expert | select |
| `brca1:pmid:32658311` | primary | reject | pending_expert | select |
| `brca1:pmid:31206626:selected-duplicate` | primary | reject | pending_expert | select |
| `brca1:pmid:31206626:rejected-duplicate` | primary | reject | pending_expert | reject |
| `brca1:pmid:34642874` | primary | reject | pending_expert | select |
| `brca1:pmid:27913932` | primary | reject | pending_expert | select |
| `brca1:pmid:30610487` | primary | reject | pending_expert | select |
| `brca1:pmid:26344711` | primary | reject | pending_expert | select |
| `cftr:pmid:35816621` | primary | select | pending_expert | reject |
| `cftr:pmid:40210412` | primary | select | pending_expert | reject |
| `cftr:pmid:41138737` | primary | select | pending_expert | reject |
| `cftr:pmid:40209082` | primary | select | pending_expert | reject |
| `cftr:pmid:38198345` | primary | reject | pending_expert | select |
| `cftr:pmid:35681464` | primary | reject | pending_expert | select |
| `cftr:pmid:39227072` | primary | reject | pending_expert | select |
| `canary:pmid:27959700` | canary | ambiguous | ambiguous_pending_expert | reject |
| `canary:pmid:25923549` | canary | select | pending_expert | reject |
| `canary:pmid:27393503` | canary | ambiguous | ambiguous_pending_expert | reject |

The immutable v1 fixture remains historical diagnostic evidence. Benchmark v2 does not rewrite it, promote AI adjudication to expert gold, or treat unavailable metrics as zero or passing.
