# Public-Gold Scientific Qualification Plan

## Decision

The agent-generated custom-reference path is permanently closed. Artana will be
qualified only against public biomedical corpora whose annotations and splits
were created independently of Artana and its evaluation agents.

## Benchmark Portfolio

| Lane | Benchmark | What it tests | Why it matters |
| --- | --- | --- | --- |
| Event structure | BioNLP-ST 2013 Cancer Genetics | Typed triggers, arguments, nested and multi-argument cancer-biology events | Tests whether Artana preserves event identity and participant roles rather than flattening claims into generic binary relations. |
| Relation breadth | BioRED | Document-level gene/protein, disease, and chemical relations, plus novel-versus-background labels | Tests evidence-grounded relation recovery across entity types and whether the system distinguishes a study finding from contextual knowledge. |
| Optional later task | PubMedQA | Abstract-grounded yes/no/maybe research questions | Measures question-answering faithfulness, not claim extraction; it is not a graph-qualification substitute. |

The first two lanes are required. Neither may be replaced by Artana-generated
gold labels, an LLM judge, or a hand-selected sample after seeing results.

## Preregistration Before Any Model Call

1. Download the benchmark only from its authoritative distribution and record
   license, release/version, files, SHA-256 hashes, and published split.
2. Select an untouched test split before running Artana. Development data may
   be used once for contract integration; it must never be scored as a final
   scientific result.
3. Define a deterministic projection from each public annotation format to an
   Artana claim frame. Preserve fields that lack an Artana representation as
   `UNREPRESENTABLE`, rather than silently dropping them.
4. Freeze the model, prompt hashes, schemas, token budget, no-retry rule,
   evidence-offset rule, and categorical adjudication rules.
5. Generate adversarial controls mechanically from public gold: role reversal,
   participant merge, negation, direction/comparison reversal, out-of-scope
   evidence, and unsupported modifier. No agent assigns numeric scores.

## Deterministic Measures

For each lane, deterministic code calculates:

- complete-event recovery and trigger recovery;
- typed participant-role fidelity;
- relation/event-type fidelity;
- direction, polarity, comparison, uncertainty, and statistical fidelity where
  present in the source annotations;
- exact evidence-span grounding and cross-event leakage;
- unsupported claims, contradictions, and abstentions;
- repeatability across two frozen executions;
- provider calls, tokens, latency, and cost from receipts.

Agents may return only categorical findings with exact evidence and a short
explanation. They do not emit the numerical score or create gold labels.

## Gates

The public-gold experiment is `INVALID_EXPERIMENT` if a corpus hash, split,
receipt, no-retry, no-fallback, or no-graph-write rule is violated.

Artana can advance from a lane only if it improves complete supported-event
recovery over its preregistered baseline without increasing unsupported claims,
role errors, or evidence leakage. Results from BioNLP-ST and BioRED are
reported separately; they must not be averaged into a single flattering score.

Trusted graph promotion remains disabled throughout qualification. Promotion is
a separate product decision after both public-gold lanes pass their gates.

## Sources

- BioNLP-ST 2013 Cancer Genetics task: https://2013.bionlp-st.org/tasks/cancer-genetics-cg-task
- BioNLP-ST 2013 task overview and corpus scale: https://pmc.ncbi.nlm.nih.gov/articles/PMC4511510/
- BioRED paper and official dataset location: https://arxiv.org/abs/2204.04263
- BioREx reference implementation: https://github.com/ncbi/BioREx
- PubMedQA official repository: https://github.com/pubmedqa/pubmedqa
