# PR-15 Governed Proposal Inventory Evidence Snapshot

Date: 2026-07-05

Branch: `alvaro/evidence-pr15-governed-proposal-inventory`

Base branch: `alvaro/evidence-pr14-entailment-coverage-hardening`

## Scope

PR-15 makes governed relation proposals auditable without promoting them as
trusted graph edges:

- Add `candidate_relation.proposed_relation_type` to the relation-type
  inventory for structured governed proposals.
- Carry governance status on relation-type inventory surfaces.
- Keep `candidate_relation.relation_type` as the canonical
  `PROPOSE_NEW_RELATION_TYPE` sentinel.
- Do not count governed proposed relation-type surfaces as raw unknown blockers.
- Preserve raw-unknown blocking for ungoverned review, proposal, graph, or
  dictionary surfaces.

## Repository Gates

- Failing regression was reproduced before implementation.
- Focused governed-proposal inventory regression passed.
- Adversarial review found that proposed-type surfaces were exempted by surface
  name alone; a negative regression now proves ungoverned proposed types block.
- `tests/unit/test_relation_feasibility_audit.py` passed.
- `make relation-feasibility-quality-gate` passed.
- `make artana-evidence-api-lint` passed.
- `make artana-evidence-api-type-check` passed.
- `make service-checks` passed with coverage at `86.86%`.

## Strict Live-Agent Result

Command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 \
  scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr15-governed-proposal-inventory-r2
```

| Metric | PR-14 live | PR-15 live |
|---|---:|---:|
| Verdict | RED | RED |
| Completed-agent precision | 0.7727 | 0.8571 |
| Completed-agent recall | 0.6800 | 0.7200 |
| High-value recall | 0.8500 | 0.9000 |
| Completed-agent valuable rate | 0.7727 | 0.8571 |
| Generic relation rate | 0.0455 | 0.0000 |
| Pruned generic relation siblings | 5 | 5 |
| Quality-filtered candidates | 5 | 7 |
| Relation type inventory surfaces | not tracked in PR-14 summary | 23 |
| Raw unknown inventory relation types | not tracked in PR-14 summary | 0 |
| Governed proposal candidates | not tracked in PR-14 summary | 2 |
| Governed proposal gold matches | not tracked in PR-14 summary | 2 |
| Governed proposal-eligible gold relations | not tracked in PR-14 summary | 2 |
| Governed proposal recall among proposal-eligible gold | 1.0000 | 1.0000 |
| Candidate CURIE present rate | 0.8636 | 0.9048 |
| Verified CURIE match rate | 0.7027 | 0.7568 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Fallback cases | 0 | 0 |
| Invalid strict-agent cases | 0 | 0 |
| Negative-control leakage cases | 0 | 0 |

Observed governed proposed relation-type inventory surfaces:

| Proposed type | Source | Governance |
|---|---|---|
| `CONFERS_RESISTANCE_TO` | `MET amplification->erlotinib` | `requires_relation_review` |
| `CONFERS_RESISTANCE_TO` | `MET amplification->erlotinib` | `requires_relation_review` |

## Artifacts

- JSON:
  `reports/relation_feasibility/2026-07-05-pr15-governed-proposal-inventory-r2/relation_feasibility_report.json`
- Markdown:
  `reports/relation_feasibility/2026-07-05-pr15-governed-proposal-inventory-r2/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| live-agent JSON | `b7620d0024c2b74a35a510c15056b5b3963083197a26b1e45be7c6851c5eff2b` |
| live-agent Markdown | `b7b4f8c9dd26e79aba667468c49e4e5a580a192b2a2ffcf1b039a54c520e696a` |

## Interpretation

The strict live-agent path completed without deterministic fallback. PR-15
does not make governed relation proposals trusted graph evidence; it makes the
actual proposed relation type visible in audit inventory and verifies those
governed surfaces do not trigger raw-unknown blockers. The scorecard now checks
the inventory surface governance status before exempting proposed relation
types, so malformed or ungoverned proposed types still fail closed.

The PR is still not trusted-graph ready by itself. The current live-agent run
remains RED because verified CURIE-linked endpoint recovery remains below
target.
