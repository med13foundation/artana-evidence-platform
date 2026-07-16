# Codex Agent-Expert Evaluation Protocol

## Purpose

Use Artana as the system under test and Codex as an external evaluation
laboratory. Artana runs its existing evidence workflow with
`openai:gpt-5.6-luna`; independent Codex subagents inspect the frozen results,
challenge them, research authoritative sources, and produce categorical review
findings. This protocol does not add an agent council or reviewer logic to the
Artana product.

The outcome is diagnostic evidence about quality and usefulness. It is not
human-expert gold, does not make records expert-eligible, and cannot authorize
trusted-graph promotion.

## Fixed Boundaries

- Use one evaluation branch: `alvaro/luna-expert-agent-evaluation`.
- Do not change Artana extraction, ranking, linking, promotion, or graph logic.
- Do not add deterministic semantic fallbacks.
- Do not write reviewer conclusions into the trusted graph.
- Do not import Codex reviews as human completions or expert attestations.
- Reviewer agents receive no production credentials and may perform only
  read-only research operations. They return findings to the parent task; they
  do not write evaluation artifacts or mutate local or remote systems.
- Stop after the evaluation report. Findings become explicit future decisions;
  they do not trigger an automatic implementation loop.

## System Under Test

- Configured model: `openai:gpt-5.6-luna`.
- Preflight must report the normalized execution model
  `openai/gpt-5.6-luna` before a run counts.
- Run the same frozen case set three times because the model currently has no
  dated snapshot in the Artana registry.
- A run is invalid if the agent does not complete, the configured model is not
  the executed model, or any fallback output is credited as agent evidence.
- Preserve the exact commit, model identifier, prompt/configuration hashes,
  source-case hashes, run timestamps, and Artana output digests.

## Codex Review Council

The parent Codex task is the operator and final diagnostic adjudicator. Before
review begins, it freezes a reviewer-assignment manifest containing each agent
run ID, exact model ID, role, prompt hash, packet hash, tool policy, assignment,
and start time. It dispatches separate subagents with isolated instructions and
no access to other reviewers' conclusions during their first pass.

| Reviewer | Primary question |
|---|---|
| Claim and entailment | Does the cited source actually support the relation and its direction, qualifiers, population, and outcome? |
| Entity and identifier | Are genes, variants, diseases, interventions, outcomes, and CURIEs correctly resolved? |
| Specificity and usefulness | Is the relation precise and actionable, or merely a generic restatement? |
| Contradiction and negatives | Did Artana ignore null results, exclusions, conflicts, corrections, or contrary evidence? |
| Novelty and hypothesis | Is a new finding being preserved honestly as a hypothesis rather than discarded or promoted as established fact? |
| Provenance and safety | Can every conclusion be traced to the supplied evidence and reproduced without fallback or hidden context? |

Every evaluated claim receives at least two independent first-pass reviews in
each applicable review mode. Packet-only and source-enriched judgments are
assigned to different agent sessions; no agent authors both judgments for the
same claim. High-impact disagreements, possible false claims, and possible
missed novel findings receive a fresh adversarial review before parent
adjudication.

## Browsing And Tool Use

Source-enriched review agents may browse the internet and use available tools
when that can improve their analysis. Packet-only agents may not browse, use
network tools, inspect the repository, or run shell commands. They receive only
the bounded frozen packet content in an isolated session. Any attempted access
outside that content invalidates the review.

Source-enriched reviewers run in an isolated workspace containing only the
content-addressed frozen packet and explicitly enumerated, operator-approved
inputs. They have no repository checkout, benchmark labels, prior reviews,
production credentials, live Artana API, or database access. Permitted
read-only tools include:

- web search and browser inspection;
- PubMed and PMC article records and full text;
- ClinVar variant records and review status;
- ClinicalTrials.gov registrations and current status;
- DOI, Crossref, journal, and publisher correction or retraction metadata;
- relevant government, standards-body, registry, and primary research sources;
- shell inspection and structured-data analysis tools restricted to the
  isolated input workspace;
- browser automation when a primary source requires interactive access.

Source-enriched agents receive no write-capable API tokens, production database
credentials, signing keys, or trusted-graph credentials. Browser and shell
activity must be preserved in the tool transcript. A review is invalid if the
agent mutates a source, repository file, Artana state, graph state, or another
reviewer's artifact, or reads any local path outside its enumerated input
manifest. Live Artana state is never a reviewer input; only frozen,
content-addressed exports may be supplied.

Broad web search may discover a source, but a diagnostic biomedical conclusion
must cite the primary publication, authoritative registry, official trial
record, or publisher correction whenever one exists. Blogs, search snippets,
AI summaries, and unsourced secondary pages cannot independently verify a
claim.

For every external fact, the reviewer records:

- source URL and authoritative identifier;
- title or record name;
- source version or retrieval timestamp when available;
- exact supporting passage or structured field;
- whether the source supports, contradicts, or only contextualizes the claim;
- any correction, retraction, conflict, or temporal-classification issue.

Agents may use tools to derive insight, but they may not hide the tool result,
invent a source, or convert a search result into unsupported certainty.

## Two Separate Judgments

Browsing must not repair Artana's output after the fact. Two independent agent
pools record two categorical judgments:

1. `packet_only`: produced first in a network-disabled, repository-blind session
   using only Artana's frozen evidence and provenance. The parent publishes the
   result without replacement and records its digest before any source-enriched
   reviewer starts.
2. `source_enriched`: produced by a fresh agent session after consulting
   authoritative external sources. It may see the frozen Artana packet, but it
   may not see packet-only decisions, benchmark labels, or other reviews.

An externally supported fact can reveal that Artana missed useful knowledge or
supplied insufficient evidence. It cannot retroactively make the `packet_only`
result sufficient. Both pools remain blinded to benchmark labels until their
no-replace first-pass artifacts and digests are frozen. This separation is
mandatory for honest measurement.

## Reviewer Output Contract

Agents provide categories, explanations, evidence spans, and citations. They do
not produce confidence percentages, precision estimates, or other numeric
scores that deterministic calculation can derive later.

Packet-only and source-enriched findings use the same categorical schema but
are stored in separate artifacts. Each artifact records its review mode, unique
agent run ID, model ID, prompt hash, input packet hash, tool-policy hash, start
and completion timestamps, and parent-observed result digest.

Required categorical fields:

| Field | Allowed values |
|---|---|
| `claim_status` | `supported`, `contradicted`, `uncertain`, `novel_hypothesis`, `insufficient_evidence` |
| `source_identity` | `matched`, `mismatched`, `unresolved` |
| `grounding_status` | `both_entities_and_relation_grounded`, `partially_grounded`, `ungrounded` |
| `entity_status` | `verified`, `conflicting`, `unresolved`, `not_applicable` |
| `specificity_status` | `specific_and_useful`, `specific_low_value`, `generic`, `overstated` |
| `integrity_status` | `clear`, `correction_review_required`, `expression_of_concern`, `retracted`, `unresolved` |
| `review_action` | `keep`, `revise`, `reject`, `abstain`, `route_to_human` |
| `impact` | `critical`, `major`, `moderate`, `minor` |

Each finding also contains a plain-language rationale, Artana evidence spans,
external evidence spans when used, source citations, and a falsification note
describing what would change the decision.

## Execution Loop

1. **Pre-register measurement:** Before reviews, freeze the metric names,
   category mapping, denominators, exclusions, abstention handling,
   repeated-run aggregation, disagreement precedence, thresholds, and exact
   calculation-command or script hash. Post-hoc metrics cannot count.
2. **Preflight:** Verify service health, database migrations, API access, and
   the resolved Luna model. Fail closed on any mismatch.
3. **Run Artana:** Execute three Luna runs over the same frozen benchmark and
   selected real-world cases. Do not retry a failed case with fallback logic.
4. **Freeze outputs:** Publish without replacement and hash the complete Artana
   outputs and provenance before any reviewer begins.
5. **Freeze assignments:** Publish the reviewer-assignment manifest before
   dispatch. A unique artifact path is reserved for every agent run and claim.
6. **Packet-only first pass:** Send only bounded packet content to isolated,
   network-disabled, repository-blind Codex sessions. Publish and hash every
   result without replacement before source research begins.
7. **Source-enriched first pass:** Dispatch fresh Codex sessions that cannot see
   packet-only findings or labels. They may browse and use read-only tools under
   the source rules above. Preserve their complete source and tool ledgers.
8. **Freeze first passes:** Publish and hash all source-enriched results without
   replacement. Benchmark labels remain inaccessible. The parent may now
   compare reviewer findings with each other, but not with labels.
9. **Adversarial pass:** While still label-blind, fresh subagents attempt to
   falsify supported claims, rescue wrongly rejected novel hypotheses, and
   identify missing negative or contradictory evidence.
10. **Adjudication:** While still label-blind, the parent Codex task resolves
    diagnostic disagreements from the frozen record and cited sources.
    Unresolved cases remain `uncertain` or `route_to_human`.
11. **Freeze adjudication:** Publish and hash adversarial findings and
    adjudication without replacement. No review category may change after this
    point.
12. **Label-provenance preflight and unblind:** Verify the frozen label artifact,
    provenance, attestation, and `score_eligible` state. Only then load labels.
    Ineligible labels permit diagnostic concordance only.
13. **Deterministic measurement:** The pre-registered calculation counts frozen
    categorical outcomes. No agent-authored number is a metric input. Changes
    to metric semantics invalidate the run rather than silently rescoring it.
14. **Report and stop:** Publish the evidence-backed result, limitations, and
    diagnostic recommendation. Do not continue into product changes
    automatically.

## Required Artifacts

Store one immutable evaluation bundle under the versioned path
`docs/validation/reports/luna-agent-expert-evaluation/<run-id>/`. An external
write-once archive is allowed only when its URI and digest are committed in the
run manifest; an ignored top-level `reports/` directory cannot satisfy this
protocol.

- `run-manifest.json`: commit, model, configuration, case, artifact hashes, and
  the URI plus digest for any externally archived artifact;
- `provider-receipts.json`: one record per credited semantic call containing
  the retrievable provider response ID, expected and retrieved model IDs,
  completion status, normalized prompt hash, canonical provider-output hash,
  structured-payload hash, retrieval timestamp, and categorical verification
  result;
- `metric-protocol.json`: pre-registered definitions, denominators, thresholds,
  aggregation rules, and calculation-command or script hash;
- `reviewer-assignments.json`: roles, unique agent run IDs, model IDs, prompt
  hashes, input hashes, tool policies, and reserved artifact paths;
- `prompts/<agent-run-id>.txt`: exact immutable prompt bytes supplied to each
  reviewer;
- `tool-policies/<agent-run-id>.md`: exact tool and access policy supplied to
  each reviewer;
- `artana-output/`: untouched results from every Luna run, each joined to its
  `provider-receipts.json` record;
- `reviews/packet-only/<agent-run-id>/`: independent network-disabled findings;
- `reviews/source-enriched/<agent-run-id>/`: independent tool-enabled findings;
- `raw-responses/<agent-run-id>.txt`: complete unedited reviewer responses;
- `tool-ledgers/<agent-run-id>.jsonl`: source retrievals and read-only tool use;
- `source-ledger.jsonl`: authoritative sources, retrieval facts, and spans;
- `adversarial-findings.json`: attempted falsifications and rescued hypotheses;
- `adjudication.json`: parent decisions and unresolved disagreements;
- `metrics.json`: deterministic counts and rates with explicit denominators;
- `root-manifest.json` and `root-manifest.sha256`: the complete no-replace
  artifact inventory and root digest, also recorded outside the bundle;
- `evaluation-report.md`: plain-language conclusions and limitations.

The parent task is the only artifact publisher. It refuses an existing output
path, verifies all first-pass digests before unblinding, and records any tool or
publication-policy violation as an invalid review rather than repairing it.

## Decision Rules

The final report separates three claims:

- **Engineering validity:** Luna ran as configured, completed, and did not use
  credited fallback evidence.
- **Label-provenance result:** precision and recall may be reported only for
  independently human-attested, `score_eligible` labels bound to the frozen
  protocol. Comparisons with AI-adjudicated, synthetic, pending, or otherwise
  ineligible labels are named `diagnostic_label_concordance`; they are not
  benchmark precision, gold, or an adoption gate.
- **Agent-expert usefulness:** diagnostic agreement and source-backed findings
  from Codex reviewers, explicitly called internal Codex diagnostic consistency
  rather than human-expert precision or independent validation.

A strong diagnostic result can justify proceeding to a small human pilot. It
cannot establish human usability, clinical correctness, or trusted-graph
readiness by itself.
