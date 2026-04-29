# Adding Evidence

There are three friendly ways to add evidence.

## 1. Bring Your Own Evidence

Use this when you already have a note, PDF, paper excerpt, or manually selected
source.

Submit text:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/documents/text" \
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
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/documents/pdf" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -F "file=@./med13-paper.pdf" \
  -F "title=MED13 paper"
```

Then extract reviewable findings:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/documents/<document_id>/extraction" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -X POST
```

PDFs are enriched during extraction, not at upload time.

## 2. Search External Sources Directly

Use this when you want discovery before review.

List source capabilities first:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/sources" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

Direct source search currently supports sources whose capability record has
`"direct_search_enabled": true`: PubMed, MARRVEL, ClinVar, AlphaFold,
UniProt, ClinicalTrials.gov, MGI, and ZFIN. DrugBank also supports direct
search when `DRUGBANK_API_KEY` is configured. MONDO and HGNC are
ontology/authority-grounding sources, not bounded direct-search endpoints. Text
and PDF are document-capture sources. Direct source-search responses are durable
captured source results: the search result can be fetched later by id, but it is
not promoted into the trusted graph until downstream extraction, proposal, and
review steps approve it.

Search PubMed:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/sources/pubmed/searches" \
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
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/sources/marrvel/searches" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "gene_symbol": "MED13",
    "taxon_id": 9606,
    "panels": ["omim", "clinvar", "gnomad"]
  }'
```

Search ClinVar:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/sources/clinvar/searches" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "gene_symbol": "MED13",
    "clinical_significance": ["Pathogenic"],
    "max_results": 20
  }'
```

Search ClinicalTrials.gov:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/sources/clinical_trials/searches" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MED13 cardiomyopathy",
    "max_results": 20
  }'
```

Search responses from the generic v2 source route include a `source_capture`
object. Use it to trace a result back to its source key, source family, query,
locator, search id, and provenance before you decide what to extract or review.

Direct source search captures the search result. It does not silently promote
trusted graph knowledge. When you want to work on one selected result from a
captured search, hand it off:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/sources/clinvar/searches/$SEARCH_ID/handoffs" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "record_index": 0
  }'
```

Handoff is idempotent. Repeating the same handoff request returns the same
completed or failed outcome instead of creating duplicate documents, runs, or
review items. ClinVar and MARRVEL variant records enter the variant-aware
extraction path. PubMed, ClinicalTrials.gov, UniProt, AlphaFold, DrugBank, MGI,
and ZFIN handoffs create durable source documents with the selected record,
source-capture metadata, normalized fields, and readable extraction text.

Normal researcher workflows should follow search or handoff with extraction,
proposal review, and promotion. The graph only changes after review.

## 3. Run A Multi-Source Setup

Use `research-plan` when you already know the topic and source mix:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/research-plan" \
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

For structured sources, `research-plan` can also create variant-related
candidate claims from sources such as ClinVar.
