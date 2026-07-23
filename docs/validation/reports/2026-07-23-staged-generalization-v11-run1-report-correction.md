# V11 Exposed Run 1 Final-Report Correction

The sealed final report rendered `None` for both the root-cause classification and the single V11 scientific change. This was a report-generation defect: the invalid-terminal result omitted fields that the renderer expected, even though both values were frozen in the preregistration and repeated in the seal report.

The correct preregistered root-cause classification is `SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP`.

The correct frozen V11 scientific change is `UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING`.

V11 exposed run 1 was operationally invalid before any provider output was scientifically admitted. Therefore neither the root-cause hypothesis nor the V11 change was scientifically validated by run 1. This correction supplies missing report context only; it does not change, rescore, reinterpret, or replace the sealed run-1 result.

The original run-1 preregistration, result, final report, seal report, attempt receipt, and late-status receipt remain byte-identical. Their frozen SHA-256 values are recorded in the run-2 operational diagnosis and preregistration.
