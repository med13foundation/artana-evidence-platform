# TG04 Normalization-Only Replay V1

Created: 2026-07-20

Status: `COMPLETED_OFFLINE`

Recommendation: **agent-only**

This replay corrected only the adapters over preserved outputs. It made no
provider, API, or model calls; accessed no untouched source; did not modify V3;
performed no scientific adjudication; and wrote nothing to the graph.

## Executive Result

The corrected adapters recovered real specialist candidates, but neither
specialist contributed a formal scope that the fixed Sol lane had missed.

| Lane | Formal scope recall | Trigger recall | Unique scopes |
| --- | ---: | ---: | ---: |
| Sol discovery agent, fixed | **29/31 (93.55%)** | **29/31 (93.55%)** | **25** |
| PubTator 3 / BioREx | 1/31 (3.23%) | 0/31 | 0 |
| DeepEventMine GE11 | 4/31 (12.90%) | 2/31 (6.45%) | 0 |
| PubTator + DeepEventMine | 4/31 (12.90%) | 2/31 (6.45%) | n/a |
| Three-way union | **29/31 (93.55%)** | **29/31 (93.55%)** | n/a |

Sol was not rerun or reinterpreted. Its raw exact passage and trigger coverage
remains fixed at **31/31**, while its participant-grounded formal result remains
**29/31**.

## PubTator And BioREx

The replay parsed the actual `{"PubTator3": [...]}` wrapper and preserved:

- **84/84 entities** with original records and provenance;
- **16/16 relations** with original records and provenance;
- the omitted PMID **42454948** as explicit missing tool coverage.

The omitted human-genetics publication remained in the 31-scope denominator.
It was not silently removed.

Entity normalization resolved 63 exact source spans, marked 14 repeated spans
ambiguous, and identified seven title-only annotations outside the frozen
abstract. Relation normalization resolved ten sentence-local relations, rejected
five cross-sentence relations, and left one relation unresolved because a
participant was not reproducibly grounded. No occurrence was chosen using gold
annotations.

BioREx encodes relation participants as positional annotation indexes inside
`nodes[].role`. The corrected parser resolves those indexes against the wrapper's
ordered annotation inventory. A real regression proves that `44,40` maps to
annotation IDs `89,85` rather than being misread as annotation IDs.

## DeepEventMine

The replay preserved all **nine** postprocessed events. For every event it:

1. matched the event and referenced text-bound IDs to preserved token-space
   output;
2. verified the postprocessed offsets against the exact original source slice;
3. required trigger and participant spans to remain in one source sentence;
4. failed closed rather than choosing an occurrence from gold data.

All nine events resolved exactly, with zero invented or unresolvable spans and
zero duplicate events. They covered all **4/4 molecular scopes** and overlapped
**2/4 molecular gold triggers**. The GE11 output covered no clinical or genetic
scope in this exposed corpus.

## Recall By Family

| Lane | Clinical (24) | Genetic (3) | Molecular (4) |
| --- | ---: | ---: | ---: |
| Sol, fixed | 22/24 | 3/3 | 4/4 |
| PubTator / BioREx | 0/24 | 0/3 | 1/4 |
| DeepEventMine | 0/24 | 0/3 | 4/4 |

DeepEventMine's four molecular scopes and PubTator's one molecular scope were
already among Sol's 29 formal scopes. Their unique correct contribution was
therefore zero. Sol alone contributed 25 scopes not recovered by either
specialist lane.

## Duplicate And Span Accounting

| Lane | Preserved records | Resolved candidates | Unresolvable | Invented | Duplicates |
| --- | ---: | ---: | ---: | ---: | ---: |
| PubTator / BioREx | 100 | 73 | 27 | 0 | 0 |
| DeepEventMine | 9 | 9 | 0 | 0 | 0 |

PubTator's 100 records are the 84 entities plus 16 relations. The separate
missing-publication record is coverage accounting, not an invented candidate.

## Integrity And Validation

- exposed corpus: 5 sources and 31 adjudicated scopes;
- gold inventory SHA-256:
  `bef14f3b55d47bf41558f07a5c2da80a3f28686843aee097288f7f4f7408be61`;
- frozen normalization implementation SHA-256:
  `002144704851e75c60d3af6bef4195fb8b28bda99da0758c45e6ca539d0968f4`;
- preregistration SHA-256:
  `7db9720f9078e68f0e89f7cc4c6c8a755920227c074fea1bf1fca92f1ee71025`;
- result SHA-256:
  `63472b61d0ce9ed3e0e3fb8331d45ee1a154651a2c699425575afbbe9bcca4a2`;
- normalized PubTator SHA-256:
  `8a6b2610cecd896dcd19bdb87cc6ecd474169b23126ee65537d996df19b1d150`;
- normalized DeepEventMine SHA-256:
  `4dda900ce522544ed28e97a21f94659390560de0932c7746f0c55f6df94513c3`.

Focused validation passed:

- pytest: **8 passed**;
- Ruff: passed;
- strict mypy: passed;
- regressions cover the response wrapper, omitted publication, positional
  relation indexes, token-to-source alignment, repeated text, ambiguous
  offsets, and cross-event rejection.

## Conclusion

Use **agent-only** candidate discovery for the next scientific experiment.
The specialist tools now have a fair normalized score, but on this exposed
corpus they add no formal recall beyond Sol. This result concerns candidate
discovery only. It does not establish semantic precision, trusted evidence, or
graph readiness, and no candidate was promoted during this replay.
