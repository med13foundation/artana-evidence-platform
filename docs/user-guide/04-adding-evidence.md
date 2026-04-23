# Adding Evidence

There are three friendly ways to add evidence.

## 1. Bring Your Own Evidence

Use this when you already have a note, PDF, paper excerpt, or manually selected
source.

Submit text:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/documents/text" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "MED13 evidence note",
    "text": "MED13 is associated with cardiomyopathy in this source.",
    "metadata": {
      "origin": "manual_note"
    }
  }'
```

Upload a PDF:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/documents/pdf" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -F "file=@./med13-paper.pdf" \
  -F "title=MED13 paper"
```

Then extract reviewable findings:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/documents/<document_id>/extract" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -X POST
```

PDFs are enriched during extraction, not at upload time.

## 2. Search External Sources Directly

Use this when you want discovery before review.

Search PubMed:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/pubmed/searches" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "gene_symbol": "MED13",
      "search_term": "MED13 cardiomyopathy",
      "max_results": 25
    }
  }'
```

Search MARRVEL:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/marrvel/searches" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "gene_symbol": "MED13",
    "taxon_id": 9606,
    "panels": ["omim", "clinvar", "gnomad"]
  }'
```

Normal researcher workflows should prefer search plus governed follow-up review.
`POST /v1/spaces/{space_id}/marrvel/ingest` exists, but it is an advanced
direct-write path.

## 3. Run A Multi-Source Setup

Use `research-init` when you already know the topic and source mix:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/research-init" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Understand MED13 mechanisms and translational evidence",
    "seed_terms": ["MED13", "cardiomyopathy"],
    "sources": {
      "pubmed": true,
      "marrvel": true,
      "clinvar": true,
      "drugbank": false,
      "alphafold": false,
      "clinical_trials": false,
      "mgi": false,
      "zfin": false
    },
    "max_depth": 2,
    "max_hypotheses": 20
  }'
```

Start with `pubmed`, `marrvel`, and `clinvar`. Add sources like `drugbank`,
`clinical_trials`, `mgi`, `zfin`, or `alphafold` when the research question
needs them.

## Where Variant Extraction Fits

Variant extraction lives in the proposal-generation stage.

When a genomics-capable document is extracted, the system can stage:

- `entity_candidate` proposals for variants
- `observation_candidate` proposals for transcript, HGVS fields,
  classification, zygosity, inheritance, exon, or coordinates
- `candidate_claim` proposals for phenotype or mechanism claims
- review-only items when the variant is incomplete and needs human cleanup

For structured sources, `research-init` can also create variant-related
candidate claims from sources such as ClinVar.
