---
name: graph_harness.literature_refresh
version: 1.0.0
summary: Refresh the research space with targeted PubMed searches when graph evidence is insufficient or stale.
tools:
  - run_pubmed_search
---
Use PubMed search only when graph evidence is missing, weak, stale, or explicitly needs
external refresh.

Keep searches scoped and explain the trigger for each search.
Prefer one focused query over multiple broad searches.

Do not claim that search results validate a relation by themselves.
Treat them as new source discovery inputs that require later extraction or review.
