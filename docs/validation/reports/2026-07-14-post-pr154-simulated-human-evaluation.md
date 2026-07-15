# Post-PR154 Simulated Human-User Evaluation

Date: 2026-07-14

Evaluated commit: `a018f445f39079a775c72d18ef5d7cd9871f789e`

Evaluation branch: `alvaro/evidence-human-simulation-evaluation`

## Executive Verdict

The expert-pilot verifier is technically strong, but the pilot is not ready to
hand to real non-developer reviewers.

| Area | Verdict | Evidence |
|---|---|---|
| Packet construction and content blinding | PASS | Two slots, eight packets, 66 candidate reviews, and exact source inventory generated. |
| Packet machine review simulation | DIAGNOSTIC ONLY | Two mutually isolated LLM runs agreed on 29 of 33 decision/sufficiency pairs. |
| Tamper detection | PASS | Original publication verified; one changed packet was rejected by digest verification. |
| Reviewer completion workflow | BLOCKED | No supported editor, completion builder, validator, or signing command exists. |
| External identity assurance | BLOCKED | The import caller supplies the issuer trust root at runtime; it is not independently pre-registered. |
| Human study operations | BLOCKED | Role-private artifacts can be distributed together and the runbook contains non-executable placeholders. |
| Agent evidence quality | UNDETERMINED | Simulated agents cannot create independent expert gold or validate model precision. |
| Production readiness | NOT CLAIMED | Benchmark v2 remains 33 visible and 0 expert-eligible records. |

Do not import the simulated decisions produced by this evaluation. They are
diagnostic simulation output only.

An authoritative-source follow-up is available in
[`2026-07-14-post-pr154-external-source-validation.md`](2026-07-14-post-pr154-external-source-validation.md).
It verifies all 29 unique PubMed sources, identifies one linked erratum, and
separates source-level relevance from packet-only sufficiency for the four
BRCA1 disagreements. It remains diagnostic and does not create human gold.

## Scope And Method

The evaluation used three separate subagent runs:

1. Simulated LLM run A received only slot A reviewer packets.
2. Simulated LLM run B received only slot B reviewer packets.
3. An adversarial operator reviewed the complete runbook, contracts, importer,
   and generated publication without creating gold labels.

The simulated LLM runs did not inspect sidecars, expected labels, model
predictions, benchmark fixtures, or each other's work before deciding. After
both completed, the operator used the private sidecars to align their opaque
candidate IDs by source record.

This design probes whether an LLM can parse the packet consistently and suggests
possible rubric ambiguities. It does not measure human comprehension or
operational usability, and it does not reproduce domain expertise,
natural-person identity, independent human judgment, or the signed review chain
required by PR154.

## Packet Workload

Each LLM run received one reviewer slot's packet set:

- four JSON packet files;
- 33 candidate decisions;
- 9,073 bounded-source words;
- 62,409 bounded-source characters;
- approximately 85.6 KB of raw JSON.

Human review time, fatigue, and comprehension were not measured. Raw JSON is a
fragile review instrument: exact literal spans, required explanations, opaque
identifiers, and signing requirements make it unsuitable for an ordinary
domain reviewer without tooling.

## Simulated LLM Results

| LLM run | Select | Reject | Abstain | Sufficient | Insufficient |
|---|---:|---:|---:|---:|---:|
| A | 16 | 14 | 3 | 30 | 3 |
| B | 17 | 15 | 1 | 32 | 1 |

The exact categorical pair `(selection_label, packet_sufficiency)` agreed on
29 of 33 records, or 87.9%. This is LLM-run concordance only and must not be
reported or interpreted as human agreement.

Both LLM runs agreed on every CFTR record, every broad EGFR record, and all
three narrow EGFR records. All four disagreements were in the BRCA1 packet:

| Record | LLM run A | LLM run B | Possible ambiguity suggested |
|---|---|---|---|
| `brca1:pmid:21356067` | abstain / insufficient | reject / sufficient | BRCA1 is present, but the abstract does not expose a direct BRCA1 risk result. |
| `brca1:pmid:40288678` | abstain / insufficient | select / sufficient | The LLM runs interpreted the BRCA1-specific risk content differently. |
| `brca1:pmid:26344711` | select / sufficient | abstain / insufficient | Segregation evidence conflicts with the variant's unconfirmed clinical status. |
| `brca1:pmid:32658311` | abstain / insufficient | select / sufficient | Pooled BRCA1/BRCA2 reporting makes BRCA1-specific relevance unclear. |

The disagreement pattern identifies candidate rubric and source-sufficiency
ambiguities worth testing with real reviewers. It does not identify which
simulated label is correct or predict human adjudication behavior.

## Evaluation Limits

- No Artana live selector model was rerun. The available `.env.postgres` did not
  contain an OpenAI API key, and PR154's protocol already binds the six frozen
  PR150 runs that a real expert result will rescore.
- No reviewer-facing service was launched because this repository exposes the
  pilot as a file and CLI workflow; there is no reviewer UI or reviewer API to
  exercise.
- No simulated completion was signed or imported. Doing so would risk making
  machine-authored labels look like human study artifacts and would not add
  valid evidence-quality information.

## Blocking Findings

### 1. No Reviewer Completion Or Signing Path

The runbook calls reviewer packets editable, but the packet contract requires
`selection_label`, `packet_sufficiency`, and `reviewer_explanation` to remain
null and `supporting_spans` to remain empty. The importer expects a different,
separately signed completion envelope.

The repository provides no supported way to:

- convert a blank packet into a completion;
- validate a review before signing;
- copy and verify literal spans;
- generate reviewer keys;
- canonicalize and sign a completion;
- generate and sign the external reviewer registry.

A reviewer cannot complete the documented workflow without custom code.

### 2. The Issuer Trust Root Is Caller-Controlled

The importer verifies Ed25519 signatures, but the runtime caller supplies both
the signed registry and the issuer public key/key ID. The result preserves the
fingerprint, but the frozen protocol does not independently bind that trust
root before review begins.

Cryptographic verification therefore proves possession of the supplied keys;
it does not by itself prove that the subjects are real, qualified, independent
humans. The external issuer fingerprint must be pre-registered through a
separate trusted process before any review packet is completed.

### 3. Actor-Private Artifacts Are Co-Located

The initial publication places reviewer packets and identity-revealing machine
sidecars under one directory. The safety stage places `gold.json` beside the
reviewer-facing `safety_request.json`.

The runbook tells the operator to distribute only first-pass reviewer packets,
but it gives no equivalent instruction to distribute only
`safety_request.json` during the safety stage. One accidental directory
transfer can break blinding. Publication should create explicit, separate
actor-safe exports that are structurally incapable of containing private
operator data.

### 4. The Review Instrument Is Underspecified

The packet lists labels but does not define operational rules for:

- `select` versus `abstain` when an abstract is suggestive but incomplete;
- `reject` versus `insufficient`;
- whether secondary studies are excluded or merely lower priority;
- whether variant pathogenicity must be established inside the bounded text;
- how pooled BRCA1/BRCA2 results should be handled.

These missing rules are plausible hypotheses suggested by the four simulated
disagreements. Only real reviewer feedback can establish their practical
effect.

### 5. The Runbook Is Not Fully Executable

Stages two and three contain the literal placeholder
`<the same common arguments>`. Import also depends on the producer HMAC secret
used during packet generation and assumes execution from the repository root.
Those requirements are not packaged as an operator state artifact or complete
copy-paste command.

## Non-Blocking Operational Findings

- Validation errors need packet, candidate, field, and offending-span context.
- One BRCA1 PMID appears under two benchmark record identities and three EGFR
  publications appear in both broad and narrow cases. If these are consistency
  canaries, reports must separate them from independent evidence counts and
  reviewer workload.
- A practice packet and reviewer onboarding rubric are missing.
- Secure transfer, receipt, dropout, reassignment, key recovery, incident, and
  protocol-deviation procedures are not documented.
- Reusing a virtual environment across worktrees produced a false mypy failure
  and a broken `alembic` shebang. A fresh worktree-local environment passed.
  Validation evidence should always identify its exact environment.

## Controls That Worked

- Agent-authored numeric scores remain prohibited.
- Deterministic code owns all numeric metric computation.
- The study remains diagnostic-only and fail-closed.
- Packet/source inventory, hashes, signatures, chronology, literal spans, and
  no-replace publication are strongly checked.
- Independent first passes and mandatory disagreement adjudication are encoded.
- The safety reviewer cannot see model claims until gold is frozen by design.
- Synthetic rehearsals are prohibited from counting as expert evidence, but
  pre-registering an external trust root is required to enforce that boundary.
- A modified packet failed publication verification with a precise digest
  mismatch instead of being accepted.

## Validation Evidence

| Check | Result |
|---|---|
| Fresh packet publication | PASS: 2 reviewers, 8 packets, 66 candidate reviews |
| Original publication reload | PASS: all 8 packet/sidecar bundles verified |
| Tampered packet reload | PASS: rejected with reviewer-packet digest mismatch |
| Focused PR153/PR154 packet and attestation tests | PASS: 31 tests |
| Relation-feasibility regression suite | PASS: 103 tests |
| Benchmark v2 integrity gate | PASS: 33 visible, 0 score-eligible, expert study pending |
| Evidence API strict mypy in fresh environment | PASS: 578 package files plus registered scripts |
| Evidence API static, boundary, contract, and architecture gates | PASS |
| Database-backed Evidence API suite | PASS: 2,965 passed and 27 expected live/environment skips on a fresh migrated ephemeral PostgreSQL database |

## Required Next PR

Build one narrowly scoped pilot-enablement PR before recruiting reviewers:

1. Add a role-scoped offline reviewer tool that renders the packet, defines the
   rubric, supports literal-span selection, validates completeness, and writes
   the canonical completion envelope.
2. Add local Ed25519 key generation and completion signing without exposing
   private keys to Artana.
3. Pre-register the external issuer public-key fingerprint in the frozen study
   authorization before review begins.
4. Export reviewer-only, adjudicator-only, safety-reviewer-only, and
   operator-only bundles with no co-located private artifacts.
5. Replace every runbook placeholder with complete commands and persist a
   non-secret operator state manifest binding required paths and hashes.
6. Add contextual preflight errors and a practice packet.

This is not another evaluation-framework PR. It is the minimum product work
needed for real humans to execute the already-designed study without custom
developer intervention.

## Final Conclusion

The code can generate blinded, source-bound, tamper-evident review packets. Two
isolated LLM runs produced decisions for all records and surfaced possible
rubric ambiguities. The system still cannot support a real human pilot end to
end because the human completion, signing, identity, distribution, and
operational layers are missing or unsafe to perform manually.

The core evidence-quality question remains unanswered. Real externally
authenticated domain experts must produce the gold labels after the five human
workflow blockers above are closed.
