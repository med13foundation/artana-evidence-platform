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
| Deterministic development projection | `6c33bb41182305bf2a0874fd8c21b4f762373799268bb7a5de4b623a3b05b944` |

The deterministic adapter read `Dev.BioC.JSON` only and produced a local
development projection of 100 documents and 1,162 annotated relations. It
preserves document identifiers, entity offsets, entity types, relation types,
and the dataset's novel/background category. It does not invoke Artana,
providers, agents, repair, or graph writes.

The official development file uses `Novel` and `No` as novelty labels. A
pre-execution audit found and corrected an adapter defect that had accepted only
`Yes` as novel and therefore mislabeled every relation as background. The
corrected projection contains 835 novel and 327 background relations. Unknown
novelty labels now fail closed.

`Test.BioC.JSON` remains sealed by the adapter unless a future preregistration
explicitly authorizes it. The raw corpus and generated projection are local
inputs, not committed repository artifacts; this receipt and the adapter are
the reproducible provenance record.

## BioNLP Cancer Genetics

The official task page identifies distinct training, development, and test data,
but its canonical development URL returned HTTP 404 on 2026-07-21. The
OpenBioCorpora preservation repository referenced by the BigBio benchmark loader
was therefore used as a curator-backed secondary distribution. Its `SOURCE`
file records the original BioNLP URLs, and its archive is pinned to commit
`b4a603dee25bd6ac5636017c2be41fd2edc52a3e` with SHA-256
`7da78deacb2d567875cc0db7af5af3dca0d54197d904ef36701eccedaf56c07c`.

The included license states that NaCTeM annotations use CC BY-SA 3.0 while the
abstracts remain subject to PubMed terms. The development-only adapter validated
100 documents containing 3,634 physical entities, 2,451 triggers, 2,915 nested
events, and 214 modifiers. It preserves exact offsets, event types, argument
roles, event-to-event arguments, and negation/speculation modifiers. The test
directory remains rejected by the adapter and sealed for later preregistration.
