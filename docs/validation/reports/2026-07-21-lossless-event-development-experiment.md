# Lossless Event Development Experiment

## Decision

`INVALID_EXPERIMENT`

The experiment stopped during preregistration custody preflight, before any
provider request. No scientific output exists and no scientific metric may be
claimed from this attempt.

## Exact Failure

The frozen preregistration states that `PMID-10473104` was selected by the rule
"lowest SHA-256 among development `.txt` files." Its source hash is
`a69c23105caa402b9f830e18d5cfc76bd08f6b97c9b4a56bfa79f440b29115f3`.

Recomputing SHA-256 across all 100 exposed development documents showed that
the actual minimum is `PMID-16428936`, with hash
`00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab`.

The earlier selection script iterated lexicographically sorted filenames and
reported the first row without sorting those rows by hash. The source itself
was correctly hashed, but the stated content-blind selection rule was not
actually applied. This is the root cause.

Changing the document, changing the rule, or ignoring the mismatch after
authorization would modify or reinterpret the frozen experiment. The custody
stop rule therefore took precedence over the one-call instruction.

## Execution Accounting

| Measure | Result |
| --- | ---: |
| Provider calls | 0 |
| Retries | 0 |
| Fallbacks | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Cost | $0.00 |
| Graph writes | 0 |
| Promotions | 0 |
| Sealed test sources accessed | 0 |

All frozen code, schema, prompt, and named-source hashes matched before the
selection-rule check. The API key was present and the structured schema was
convertible, but those facts do not repair the custody contradiction.

## Scientific Metrics

Complete-event recovery, trigger recovery, participant-role fidelity, nested
event recovery, modifier fidelity, and unsupported-event counts are all
`NOT_MEASURED`. No model output was generated.

## Required Next Action

A new preregistration must be created rather than editing this one. It must use
one unambiguous selection statement that is independently tested before
authorization. The smallest honest choices are either:

1. Name `PMID-10473104` directly and describe it as the lexicographically first
   development document, preserving the intended source; or
2. Preserve the minimum-SHA-256 rule and select `PMID-16428936`.

That future execution is a new experiment and requires new explicit
authorization. This invalid attempt cannot be retried or reinterpreted.
