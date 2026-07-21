# Public-Gold Intake Receipt

## BioRED

The BioRED corpus and its annotation guideline were obtained from NCBI's
official distribution on 2026-07-21. NCBI's accompanying notice identifies the
database as a United States Government Work with no restriction on use or
reproduction.

| Item | SHA-256 |
| --- | --- |
| `BIORED.zip` | `c3032230bd89d22a0923d0df6ae943bc8ea37fba7e42dafa7a8dec21bac02d47` |
| `BioRED_Annotation_Guideline.pdf` | `e2cf33a9fab76124351c609d3b5fd704e3a8a64fcad2fb8b48227c2aa92feb22` |
| Deterministic development projection | `a537b29d655f01b297feb74507c9b10b577e99067f950f7847eace08f7de6bd8` |

The deterministic adapter read `Dev.BioC.JSON` only and produced a local
development projection of 100 documents and 1,162 annotated relations. It
preserves document identifiers, entity offsets, entity types, relation types,
and the dataset's novel/background category. It does not invoke Artana,
providers, agents, repair, or graph writes.

`Test.BioC.JSON` remains sealed by the adapter unless a future preregistration
explicitly authorizes it. The raw corpus and generated projection are local
inputs, not committed repository artifacts; this receipt and the adapter are
the reproducible provenance record.

## BioNLP Cancer Genetics

The official task page identifies distinct training, development, and test data
and links the canonical development archive. On 2026-07-21 the canonical
development URL returned HTTP 404. No mirror was used, no substitute dataset
was downloaded, and no claim about Cancer Genetics qualification is made.

This is an acquisition blocker, not an excuse to weaken the two-lane protocol.
The next action is to obtain a current official or curator-confirmed distribution
with a version and license receipt, then implement the event-format adapter
against its development split only.
