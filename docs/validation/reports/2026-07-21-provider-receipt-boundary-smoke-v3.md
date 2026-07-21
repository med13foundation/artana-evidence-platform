# Provider Receipt Boundary Smoke V3

**Decision:** `RECEIPT_BOUNDARY_VALIDATED`

This was one non-scientific categorical provider call. It did not access biomedical sources, run the scientific experiment, write to the graph, or enable promotion.

## Minimal Correction

V2 failed because the request omitted `$.description` while the creation
response materialized it as `null`. V3 supplied one frozen, non-empty response
format description and required exact equality. It did not introduce generic
absent/null equivalence or a wildcard transport allowlist.

The description is a documented JSON Schema response-format field in the
OpenAI Responses API. Creation and retrieval returned the exact frozen value.

## Custody

- Preregistration: `0fc101cb1ef6c84cf3f3f70b55397291ba9777eea9b19a1ab54bac93a68c1c54`
- Response ID: `resp_0d2e3634ca9883a9006a5fefa20198819ab6c43dae7c371c37`
- Provider creation calls: `1`
- Response retrieval requests: `1`
- Input-item custody retrieval requests: `1`
- Provider retries and fallbacks: `0`
- Biomedical sources accessed: `0`

## Accounting

- Input tokens: `110`
- Cached input tokens: `0`
- Output tokens: `22`
- Reasoning tokens: `0`
- Total tokens: `132`
- Latency seconds: `1.7329161670058966`
- Cost USD: `0.0012100000000000001`
- Scientific payload SHA-256: `b085e4863220a624d609043b70b978c468b4d96e9a8952d6a715de8b5085cc9f`
- Creation envelope SHA-256: `66f9310c144f65f6bfdb37a6ee6282bece88049548474e7ab336be423f473f2a`
- Retrieval envelope SHA-256: `66f9310c144f65f6bfdb37a6ee6282bece88049548474e7ab336be423f473f2a`

## Loop Budget

- New smoke executions used: `1 / 3`
- Provider creation calls used: `1 / 3`
- Combined cost used: `$0.00121 / $0.75`
- Retries, fallbacks, repairs, and alternate models: `0`
- Additional smokes after validation: `0`

## Validation Evidence

- Explicit-description boundary tests: absent, `null`, empty, and changed values fail.
- Focused receipt and preflight tests: `36 passed` before V3 execution.
- Final scientific-format focused suite: `42 passed`.
- Focused Ruff: passed.
- Focused strict MyPy: passed for changed modules.
- Final `make service-checks`: passed with `87.62%` coverage.
- Raw provider output: retained outside git.

The receipt boundary is validated. Scientific execution remains unauthorized
and requires a separate explicit authorization.
