# PR-17 Readiness Failure Attribution Evidence Snapshot

Date: 2026-07-05

Branch: `alvaro/evidence-pr17-readiness-failure-attribution`

Base branch: `alvaro/evidence-pr16-repeatability-readiness`

## Scope

PR-17 starts the trusted-graph recovery loop by making repeated readiness
failures explainable before changing extraction, entity linking, or promotion
policy.

It adds:

- `scripts/validation/relation_feasibility/failure_analysis.py`
- `scripts/summarize_relation_readiness_failures.py`
- `tests/unit/test_relation_feasibility_failure_analysis.py`

The analyzer reads one or more `relation_feasibility_report.json` files and
emits:

- repeated missed gold relations
- repeated false-positive candidates
- canonical-supported CURIE gaps
- governed proposal capture separated from trusted promotion
- model-labeled comparison metrics

## Baseline Inputs

The first report uses the three PR-16 strict live-agent repeatability reports:

```text
/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run1/relation_feasibility_report.json
/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run2/relation_feasibility_report.json
/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run3/relation_feasibility_report.json
```

## Failure Attribution Command

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run1/relation_feasibility_report.json \
  --report current=/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run2/relation_feasibility_report.json \
  --report current=/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run3/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr17-pr16-baseline
```

Result:

```text
relation_feasibility_failure_analysis runs=3 missed=9 false_positives=7 curie_gaps=11
```

## Output Artifacts

- JSON:
  `reports/relation_feasibility_failure_analysis/2026-07-05-pr17-pr16-baseline/relation_feasibility_failure_analysis_report.json`
- Markdown:
  `reports/relation_feasibility_failure_analysis/2026-07-05-pr17-pr16-baseline/relation_feasibility_failure_analysis_report.md`

Hashes:

| Artifact | SHA-256 |
|---|---|
| failure analysis JSON | `ac139412da316d709e903d0d0e22a8334e62e00db92d4992cef7c285230ad1b5` |
| failure analysis Markdown | `521f62a7cc1eb9ab754e39c14653752a5e330d4a6b00bcda892680f1ac2efcf6` |

## Key Findings

Repeated high-value misses across all three runs:

| Case | Missed relation |
|---|---|
| `complex_nsclc_alias` | `MET amplification CONFERS_RESISTANCE_TO erlotinib` |
| `generic_sibling_met_resistance` | `MET amplification CONFERS_RESISTANCE_TO erlotinib` |
| `generic_sibling_egfr_t790m_resistance` | `EGFR T790M CAUSES resistance to gefitinib` |

Repeated false-positive or non-gold patterns across all three runs:

| Case | Candidate |
|---|---|
| `generic_sibling_met_resistance` | `MET amplification PROPOSE_NEW_RELATION_TYPE CONFERS_RESISTANCE_TO erlotinib` |
| `generic_sibling_egfr_t790m_resistance` | `EGFR T790M PROPOSE_NEW_RELATION_TYPE CONFERS_RESISTANCE_TO gefitinib` |
| `strong_mek_inhibits_erk` | `ERK phosphorylation DOWNSTREAM_OF MEK` |

Top CURIE gaps:

| Endpoint | Gap |
|---|---|
| `MAPK signaling` | model hint `GO:0000165`, not verified |
| `homologous recombination DNA repair` | model hint `GO:0000724`, not verified |
| `response to pembrolizumab` | missing CURIE |
| `aggressive tumor growth` | missing CURIE |
| `cardiac septal development` | unstable model hints, none verified |

Proposal capture stayed review-only:

| Metric | Value |
|---|---:|
| Proposal candidates | 9 |
| Proposal gold matches | 4 |
| Proposal-eligible gold count | 6 |
| Proposal recall against proposal-eligible gold | 0.6667 |
| Trusted proposal capture count | 0 |

Model comparison currently has one group, `current`, because no controlled
stronger-model repeatability run has been executed on this branch yet.

## Tests

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_failure_analysis.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  -q
```

Result:

```text
........                                                                 [100%]
```

## Adversarial Finding Fixed During PR-17

The first analyzer draft incorrectly classified verified links on governed
proposal captures as `wrong_verified_match` CURIE gaps. That was misleading
because proposal-matched candidates do not have canonical gold endpoint
comparison semantics.

Regression added:

```text
tests/unit/test_relation_feasibility_failure_analysis.py::test_failure_analysis_does_not_call_verified_proposal_links_wrong
```

The analyzer now reports CURIE gaps only for canonically supported candidates.
Governed proposal captures remain in the proposal-capture section.

## Next PR Lane

PR-18 should use the `curie_gaps` section as its starting queue. The highest
leverage verified-linking targets are:

- `MAPK signaling`
- `homologous recombination DNA repair`
- `response to pembrolizumab`
- `aggressive tumor growth`
- `cardiac septal development`
- `ERK phosphorylation`
