# Fresh-CG V2 Root-Cause Adjudication V1

Act as an independent technical adjudicator. Use only the frozen dispute packet,
the primary source named in that packet, and official BioNLP or NCBI materials
when external documentation is needed. Do not inspect the other adjudicator's
work. Do not treat an agent judgment as human-expert qualification credit.

The sealed V2 output and reference are evidence, not presumed truth. Candidate
interpretations are anonymized. Decide from the source, the direct CG
annotation, and the frozen source-general rules; do not infer which candidate
was produced by Artana.

For each issue assigned to you:

1. state the source-bound interpretation;
2. cite exact packet evidence and any official external source used;
3. select exactly one classification:
   - `MODEL_ERROR`
   - `REFERENCE_ERROR`
   - `EVALUATOR_MAPPING_ERROR`
   - `TAXONOMY_AMBIGUITY`
   - `UNRESOLVED_EXPERT_REVIEW_REQUIRED`
4. distinguish an independent error from a downstream cascade;
5. state the smallest source-general correction, if one is justified; and
6. state what evidence would falsify your conclusion.

For occurrence and attachment questions, preserve exact BioNLP occurrence
identity. Do not substitute a biologically reasonable expanded name for the
frozen annotated span. For source-semantic questions, do not treat study
activity as a biological result unless the permitted sentence itself reports
that result. Apply the frozen V9 rules literally, including its contained-subspan
and explicit-provisional-status rules.

Return one JSON object with:

- `schema_version`:
  `artana.staged_generalization.fresh_cg_v2_root_cause_adjudication.v1`;
- `adjudicator_id`, `specialty`, `independence_declaration`;
- `packet_sha256`;
- `external_sources`, each with an official URL, title, retrieval time, and a
  short relevance statement;
- `issues`, each with `issue_id`, exactly one `classification`,
  `independent_error`, `depends_on`, `source_bound_conclusion`,
  `evidence`, `source_general_correction`, and `falsification_condition`;
- `unresolved_issue_ids`; and
- `qualification_credit: false`.

Do not edit or rescore V1/V2 artifacts. Do not make a scientific provider call,
write to the graph, or consume another fresh case.
