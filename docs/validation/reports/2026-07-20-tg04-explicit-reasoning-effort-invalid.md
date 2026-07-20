# TG04 Explicit Reasoning-Effort Probe

Status: `INVALID_RUN`

Scientific conclusion: `NONE`

This exposed one-source probe tested whether explicitly increasing Sol's reasoning effort improves event decomposition. It changed no Artana product code and made no graph write.

## Why This Test Was Needed

The prior Luna and Sol extraction probes did not pass an explicit `reasoning_effort` through `ModelCallOptions`; they used the provider default. Reviewer subagents had used high reasoning, but Artana's extraction calls had not. Therefore, higher extraction effort had not previously been tested in a controlled way.

## Sealed Comparison

- same model: `openai:gpt-5.6-sol`;
- same exposed CIITA source, scientific prompt body, schema, compiler, and validation;
- explicit `medium` versus explicit `xhigh`;
- exactly one call per arm;
- no retry, chat fallback, parser proposal, or untouched source;
- provider effort intended to be verified from retrieved response records;
- benchmark exactness designated diagnostic-only;
- scientific comparison permitted only after two valid blinded source reviews.

The adversarial preflight reached `GO` after the protocol added strict invalid-arm handling, sealed mutable inputs, prose-free blinded packets, create-once packet hashing, controlled-event topology, categorical-domain validation, and a deterministic two-review join.

## Actual Result

- provider calls: `2`;
- graph writes: `0`;
- medium: `schema_invalid`, with a live provider response ID;
- xhigh: `invocation_failed`, `ModelTimeoutError` after the fixed 90-second one-shot timeout;
- accepted arms: `0/2`;
- blinded reviews: `0`;
- result SHA-256: `d9d4424741ea26f8ad4dda422bd2fb372c218453718e040bc9ba8315e89857c6`.

The runner correctly forced `INVALID_RUN`. No scientific gain, regression, tie, or benchmark conclusion may be inferred.

## Decision

Higher reasoning effort remains scientifically unmeasured. This run does not prove that xhigh is ineffective. It does show that simply turning on xhigh is not an operationally complete remedy under this latency contract, while medium effort can still fail the extraction schema.

Following the agreed stop rule, do not retry this source or build more effort-specific evaluation machinery. Advance the established biomedical-parser hybrid, which already produced a source-supported proposal with the exact trigger, separate `Sp1` and `Sp3` participants, and zero unsupported claims. The agent's next job is to correct or extend that anchored structure, not rediscover every role from scratch.
